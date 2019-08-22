#
# Utilities for the interactive partitioning module
#
# Copyright (C) 2019 Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#
import re

from blivet import devicefactory
from blivet.devicelibs import crypto, raid
from blivet.devices import LUKSDevice
from blivet.errors import StorageError
from blivet.formats import get_format
from blivet.size import Size

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.constants import UNSUPPORTED_FILESYSTEMS
from pyanaconda.core.i18n import _
from pyanaconda.core.util import lowerASCII
from pyanaconda.modules.storage.disk_initialization import DiskInitializationConfig
from pyanaconda.platform import platform
from pyanaconda.product import productName, productVersion
from pyanaconda.storage.root import Root
from pyanaconda.storage.utils import filter_unsupported_disklabel_devices, bound_size, \
    get_supported_filesystems, PARTITION_ONLY_FORMAT_TYPES, SUPPORTED_DEVICE_TYPES, \
    CONTAINER_DEVICE_TYPES, DEVICE_TEXT_MAP

log = get_module_logger(__name__)


def collect_used_devices(storage):
    """Collect devices used in existing or new installations.

    :param storage: an instance of Blivet
    :return: a list of devices
    """
    used_devices = []

    for root in storage.roots:
        for device in list(root.mounts.values()) + root.swaps:
            if device not in storage.devices:
                continue
            used_devices.extend(device.ancestors)

    for new in [d for d in storage.devicetree.leaves if not d.format.exists]:
        if new.format.mountable and not new.format.mountpoint:
            continue
        used_devices.extend(new.ancestors)

    for device in storage.partitions:
        if getattr(device, "is_logical", False):
            extended = device.disk.format.extended_partition.path
            used_devices.append(storage.devicetree.get_device_by_path(extended))

    return used_devices


def collect_unused_devices(storage):
    """Collect devices that are not used in existing or new installations.

    :param storage: an instance of Blivet
    :return: a list of devices
    """
    used_devices = set(collect_used_devices(storage))

    unused = [
        d for d in storage.devices
        if d.disks
        and d.media_present
        and not d.partitioned
        and (d.direct or d.isleaf)
        and d not in used_devices
    ]

    # Add incomplete VGs and MDs
    incomplete = [
        d for d in storage.devicetree._devices
        if not getattr(d, "complete", True)
    ]

    # Add partitioned devices with unsupported format.
    unsupported = [
        d for d in storage.partitioned
        if not d.format.supported
    ]

    return unused + incomplete + unsupported


def collect_bootloader_devices(storage, boot_drive):
    """Collect the bootloader devices.

    :param storage: an instance of Blivet
    :param boot_drive: a name of the bootloader drive
    :return: a list of devices
    """
    devices = []

    for device in storage.devices:
        if device.format.type not in ["biosboot", "prepboot"]:
            continue

        # Boot drive may not be setup because it IS one of these.
        if not boot_drive or boot_drive in (d.name for d in device.disks):
            devices.append(device)

    return devices


def collect_new_devices(storage, boot_drive):
    """Collect new devices.

    :param storage: an instance of Blivet
    :param boot_drive: a name of the bootloader drive
    :return: a list of devices
    """
    # A device scheduled for formatting only belongs in the new root.
    new_devices = [
        d for d in storage.devices
        if d.direct
        and not d.format.exists
        and not d.partitioned
    ]

    # If mount points have been assigned to any existing devices, go ahead
    # and pull those in along with any existing swap devices. It doesn't
    # matter if the formats being mounted exist or not.
    new_mounts = [
        d for d in storage.mountpoints.values() if d.exists
    ]

    if new_mounts or new_devices:
        new_devices.extend(storage.mountpoints.values())
        new_devices.extend(collect_bootloader_devices(storage, boot_drive))

    return list(set(new_devices))


def collect_selected_disks(storage, selection):
    """Collect selected disks.

    FIXME: Is this method really necessary? Remove it if possible.

    :param storage: an instance of Blivet
    :param selection: names of selected disks
    :return: a list of devices
    """
    return [
        d for d in storage.devices
        if d.name in selection and d.partitioned
    ]


def collect_roots(storage):
    """Collect roots of existing installations.

    :param storage: an instance of Blivet
    :return: a list of roots
    """
    roots = []
    supported_devices = set(filter_unsupported_disklabel_devices(storage.devices))

    # Get the name of the new installation.
    new_root_name = get_new_root_name()

    for root in storage.roots:
        # Get the name.
        name = root.name

        # Get the supported swap devices.
        swaps = [
            d for d in root.swaps
            if d in supported_devices
            and (d.format.exists or root.name == new_root_name)
        ]

        # Get the supported mount points.
        mounts = {
            m: d for m, d in root.mounts.items()
            if d in supported_devices
            and (d.format.exists or root.name == new_root_name)
            and d.disks
        }

        if not swaps and not mounts:
            continue

        # Add a root with supported devices.
        roots.append(Root(
            name=name,
            mounts=mounts,
            swaps=swaps
        ))

    return roots


def get_new_root_name():
    """Get the name of the new installation.

    :return: a translated string
    """
    return _("New {name} {version} Installation").format(
        name=productName, version=productVersion
    )


def create_new_root(storage, boot_drive):
    """Create a new root from the given devices.

    :param storage: an instance of Blivet
    :param boot_drive: a name of the bootloader drive
    :return: a new root
    """
    devices = filter_unsupported_disklabel_devices(
        collect_new_devices(
            storage=storage,
            boot_drive=boot_drive
        )
    )

    bootloader_devices = filter_unsupported_disklabel_devices(
        collect_bootloader_devices(
            storage=storage,
            boot_drive=boot_drive
        )
    )

    swaps = [
        d for d in devices
        if d.format.type == "swap"
    ]

    mounts = {
        d.format.mountpoint: d for d in devices
        if getattr(d.format, "mountpoint", None)
    }

    for device in devices:
        if device in bootloader_devices:
            mounts[device.format.name] = device

    return Root(
        name=get_new_root_name(),
        mounts=mounts,
        swaps=swaps
    )


def collect_mount_points():
    """Collect supported mount points.

    :return: a list of paths
    """
    paths = ["/", "/boot", "/home", "/var"]

    # Add the mount point requirements for bootloader stage1 devices.
    paths.extend(platform.boot_stage1_constraint_dict["mountpoints"])

    # Sort the list now so all the real mount points go to the front,
    # then add all the pseudo mount points we have.
    paths.sort()
    paths += ["swap"]

    for fmt in ["appleboot", "biosboot", "prepboot"]:
        if get_format(fmt).supported:
            paths += [fmt]

    return paths


def validate_label(label, fmt):
    """Validate the label.

    :param str label: a label
    :param DeviceFormat fmt: a device format to label
    :return: an error message
    """
    if not label:
        return None

    if fmt.exists:
        return _("Cannot relabel already existing file system.")

    if not fmt.labeling():
        return _("Cannot set label on file system.")

    if not fmt.label_format_ok(label):
        return _("Unacceptable label format for file system.")

    return None


def validate_mount_point(path, mount_points):
    """Validate the given path of a mount point.

    :param path: a path to validate
    :param mount_points: a list of existing mount points
    :return: an error message
    """
    system_mount_points = ["/dev", "/proc", "/run", "/sys"]

    if path in mount_points:
        return _("That mount point is already in use. Try something else?")

    if not path:
        return _("Please enter a valid mount point.")

    if path in system_mount_points:
        return _("That mount point is invalid. Try something else?")

    if ((len(path) > 1 and path.endswith("/")) or
            not path.startswith("/") or
            " " in path or
            re.search(r'/\.*/', path) or
            re.search(r'/\.+$', path)):
        # - does not end with '/' unless mountpoint _is_ '/'
        # - starts with '/' except for "swap", &c
        # - does not contain spaces
        # - does not contain pairs of '/' enclosing zero or more '.'
        # - does not end with '/' followed by one or more '.'
        return _("That mount point is invalid. Try something else?")

    return None


def validate_raid_level(raid_level, num_members):
    """Validate the given raid level.

    :param raid_level: a RAID level
    :param num_members: a number of members
    :return: an error message
    """
    if num_members < raid_level.min_members:
        return _("The RAID level you have selected {level} requires more disks "
                 "({min}) than you currently have selected ({count}).").format(
            level=raid_level,
            min=raid_level.min_members,
            count=num_members
        )

    return None


def validate_device_info(storage, dev_info, reformat):
    """Validate the given device info.

    :param storage: an instance of Blivet
    :param dev_info: a device info to validate
    :param reformat: is reformatting enabled?
    :return: an error message
    """
    device = dev_info["device"]
    disks = dev_info["disks"]
    device_type = dev_info["device_type"]
    fs_type = dev_info["fstype"]
    encrypted = dev_info["encrypted"]
    raid_level = dev_info["raid_level"]
    mount_point = dev_info["mountpoint"]

    changed_label = dev_info["label"] != getattr(device.format, "label", "")
    changed_fstype = dev_info["fstype"] != device.format.type

    if changed_label or changed_fstype:
        error = validate_label(
            dev_info["label"],
            get_format(fs_type)
        )
        if error:
            return error

    is_format_mountable = get_format(fs_type).mountable
    changed_mount_point = dev_info["mountpoint"] != getattr(device.format, "mountpoint", None)

    if reformat and is_format_mountable and not mount_point:
        return _("Please enter a mount point.")

    if changed_mount_point and mount_point:
        error = validate_mount_point(
            mount_point,
            storage.mountpoints.keys()
        )
        if error:
            return error

    supported_types = (devicefactory.DEVICE_TYPE_PARTITION, devicefactory.DEVICE_TYPE_MD)

    if mount_point == "/boot/efi" and device_type not in supported_types:
        return _("/boot/efi must be on a device of type {type} or {another}").format(
            type=_(DEVICE_TEXT_MAP[devicefactory.DEVICE_TYPE_PARTITION]),
            another=_(DEVICE_TEXT_MAP[devicefactory.DEVICE_TYPE_MD])
        )

    if device_type != devicefactory.DEVICE_TYPE_PARTITION and \
            fs_type in PARTITION_ONLY_FORMAT_TYPES:
        return _("{fs} must be on a device of type {type}").format(
            fs=fs_type,
            type=_(DEVICE_TEXT_MAP[devicefactory.DEVICE_TYPE_PARTITION])
        )

    if mount_point and encrypted and mount_point.startswith("/boot"):
        return _("{} cannot be encrypted").format(mount_point)

    if encrypted and fs_type in PARTITION_ONLY_FORMAT_TYPES:
        return _("{} cannot be encrypted").format(fs_type)

    if mount_point == "/" and device.format.exists and not reformat:
        return _("You must create a new file system on the root device.")

    if (raid_level is not None or device_type == devicefactory.DEVICE_TYPE_MD) and \
            raid_level not in get_supported_raid_levels(device_type):
        return _("Device does not support RAID level selection {}.").format(raid_level)

    if raid_level is not None:
        error = validate_raid_level(
            raid_level,
            len(disks)
        )
        if error:
            return error

    return None


def suggest_device_name(storage, device):
    """Get a suggestion for a device name.

    :param storage: an instance of Blivet
    :param device: a device to name
    :return:
    """
    return storage.suggest_device_name(
        swap=bool(device.format.type == "swap"),
        mountpoint=getattr(device.format, "mountpoint", None)
    )


def revert_reformat(storage, device):
    """Revert reformat of the given device.

    :param storage: an instance of Blivet
    :param device: a device to reset
    """
    # Skip if formats exists.
    if device.format.exists and device.raw_device.format.exists:
        log.debug("Nothing to revert for %s.", device.name)
        return

    # Figure out the existing device.
    if not device.raw_device.format.exists:
        original_device = device.raw_device
    else:
        original_device = device

    # Reset it.
    log.debug("Resetting device %s.", original_device.name)
    storage.reset_device(original_device)


def resize_device(storage, device, new_size, old_size):
    """Resize the given device.

    :param storage: an instance of Blivet
    :param device: a device to resize
    :param new_size: a new size
    :param old_size: an old size
    :return: True if the device changed its size, otherwise False
    :raise: StorageError if we fail to schedule the device resize
    """
    # If a LUKS device is being displayed, adjust the size
    # to the appropriate size for the raw device.
    use_size = new_size
    use_old_size = old_size

    if device.raw_device is not device:
        use_size = new_size + crypto.LUKS_METADATA_SIZE
        use_old_size = device.raw_device.size

    # Bound size to boundaries given by the device.
    use_size = device.raw_device.align_target_size(use_size)
    use_size = bound_size(use_size, device.raw_device, use_old_size)
    use_size = device.raw_device.align_target_size(use_size)

    # And then we need to re-check that the max size is actually
    # different from the current size.

    if use_size == device.size or use_size == device.raw_device.size:
        # The size hasn't changed.
        log.debug("canceled resize of device %s to %s", device.raw_device.name, use_size)
        return False

    if new_size == device.current_size or use_size == device.current_size:
        # The size has been set back to its original value.
        log.debug("removing resize of device %s", device.raw_device.name)

        actions = storage.devicetree.actions.find(
            action_type="resize",
            devid=device.raw_device.id
        )

        for action in reversed(actions):
            storage.devicetree.actions.remove(action)

        return bool(actions)
    else:
        # the size has changed
        log.debug("scheduling resize of device %s to %s", device.raw_device.name, use_size)

        try:
            storage.resize_device(device.raw_device, use_size)
        except (StorageError, ValueError) as e:
            log.error("failed to schedule device resize: %s", e)
            device.raw_device.size = use_old_size
            raise StorageError(str(e)) from None

        log.debug("new size: %s", device.raw_device.size)
        log.debug("target size: %s", device.raw_device.target_size)
        return True


def change_encryption(storage, device, encrypted, luks_version):
    """Change encryption of the given device.

    :param storage: an instance of Blivet
    :param device: a device to change
    :param encrypted: should we encrypt the device?
    :param luks_version: a version of LUKS
    :return: a LUKS device or a device slave
    """
    if not encrypted:
        log.info("removing encryption from %s", device.name)
        storage.destroy_device(device)
        return device.slave
    else:
        log.info("applying encryption to %s", device.name)
        new_fmt = get_format("luks", device=device.path, luks_version=luks_version)
        storage.format_device(device, new_fmt)
        luks_dev = LUKSDevice("luks-" + device.name, parents=[device])
        storage.create_device(luks_dev)
        return luks_dev


def reformat_device(storage, device, fstype, mountpoint, label):
    """Reformat the given device.

    :param storage: an instance of Blivet
    :param device: a device to reformat
    :param fstype: a file system type
    :param mountpoint: a mount point
    :param label: a label
    :raise: StorageError if we fail to format the device
    """
    log.info("scheduling reformat of %s as %s", device.name, fstype)

    old_format = device.format
    new_format = get_format(
        fstype,
        mountpoint=mountpoint,
        label=label,
        device=device.path
    )

    try:
        storage.format_device(device, new_format)
    except (StorageError, ValueError) as e:
        log.error("failed to register device format action: %s", e)
        device.format = old_format
        raise StorageError(str(e)) from None


def get_device_luks_version(device):
    """Get the LUKS version of the given device.

    :param device: a device
    :return: a LUKS version or None
    """
    device = device.raw_device

    if device.format.type == "luks":
        return device.format.luks_version

    return None


def get_device_raid_level(device):
    """Get the RAID level of the given device.

    :param device: a device
    :return: a RAID level
    """
    device = device.raw_device

    if hasattr(device, "level"):
        return device.level

    if hasattr(device, "data_level"):
        return device.data_level

    if hasattr(device, "volume"):
        return device.volume.data_level

    if not hasattr(device, "vg") and hasattr(device, "lvs") and len(device.parents) == 1:
        return get_device_raid_level(device.parents[0])

    return None


def collect_file_system_types(device):
    """Collect supported file system types for the given device.

    :param device: a device
    :return: a list of file system names
    """
    # Collect the supported filesystem types.
    supported_types = {
        fs.name for fs in get_supported_filesystems()
        if fs.name not in UNSUPPORTED_FILESYSTEMS
    }

    # Add possibly unsupported but still required file system types:
    # Add the device format type.
    supported_types.add(device.format.name)

    # Add the original device format type.
    if device.exists:
        supported_types.add(device.original_format.name)

    return list(supported_types)


def collect_device_types(device, disks):
    """Collect supported device types for the given device.

    :param device: a device
    :param disks: a list of selected disks
    :return: a list of device types
    """
    # Collect the supported device types.
    supported_types = set(SUPPORTED_DEVICE_TYPES)

    # Include the type of the given device.
    supported_types.add(devicefactory.get_device_type(device))

    # Include md only if there are two or more disks.
    if len(disks) > 1:
        supported_types.add(devicefactory.DEVICE_TYPE_MD)

    # Include btrfs if it is both allowed and supported.
    fmt = get_format("btrfs")

    if fmt.supported \
            and fmt.formattable \
            and device.raw_device.format.type not in PARTITION_ONLY_FORMAT_TYPES + ("swap",):
        supported_types.add(devicefactory.DEVICE_TYPE_BTRFS)

    return sorted(filter(devicefactory.is_supported_device_type, supported_types))


def generate_device_info(storage, device):
    """Generate a device info for the given device.

    :param storage: an instance of Blivet
    :param device: a device
    :return: a device info
    """
    device_type = devicefactory.get_device_type(device)

    dev_info = dict()
    dev_info["device"] = device
    dev_info["name"] = getattr(device.raw_device, "lvname", device.raw_device.name)
    dev_info["size"] = device.size
    dev_info["device_type"] = device_type
    dev_info["fstype"] = device.format.type
    dev_info["encrypted"] = isinstance(device, LUKSDevice)
    dev_info["luks_version"] = get_device_luks_version(device)
    dev_info["label"] = getattr(device.format, "label", "")
    dev_info["mountpoint"] = getattr(device.format, "mountpoint", None) or None
    dev_info["raid_level"] = get_device_raid_level(device)

    if hasattr(device, "req_disks") and not device.exists:
        disks = device.req_disks
    else:
        disks = device.disks

    dev_info["disks"] = disks

    factory = devicefactory.get_device_factory(
        storage,
        device_type=device_type,
        device=device.raw_device
    )
    container = factory.get_container()

    if container:
        dev_info["container_name"] = container.name
        dev_info["container_encrypted"] = container.encrypted
        dev_info["container_raid_level"] = get_device_raid_level(container)
        dev_info["container_size"] = getattr(container, "size_policy", container.size)
    else:
        dev_info["container_name"] = None
        dev_info["container_encrypted"] = False
        dev_info["container_raid_level"] = None
        dev_info["container_size"] = devicefactory.SIZE_POLICY_AUTO

    return dev_info


def add_device(storage, dev_info):
    """Add a device to the storage model.

    :param storage: an instance of Blivet
    :param dev_info: a device info
    :raise: StorageError if the device cannot be created
    """
    log.debug("Add device: %s", dev_info)

    # Complete the device info.
    _update_device_info(storage, dev_info)

    try:
        # Trying to use a new container.
        _add_device(storage, dev_info, use_existing_container=False)
        return
    except StorageError as e:
        # Keep the first error.
        error = e

    try:
        # Trying to use an existing container.
        _add_device(storage, dev_info, use_existing_container=True)
        return
    except StorageError:
        # Ignore the second error.
        pass

    raise error


def _update_device_info(storage, dev_info):
    """Update the device info.

    :param storage: an instance of Blivet
    :param dev_info: a device info
    """
    # Set the defaults.
    dev_info.setdefault("mountpoint", None)
    dev_info.setdefault("device_type", devicefactory.DEVICE_TYPE_LVM)
    dev_info.setdefault("encrypted", False)
    dev_info.setdefault("luks_version", storage.default_luks_version)

    # Set the file system type for the given mount point.
    dev_info.setdefault("fstype", storage.get_fstype(dev_info["mountpoint"]))

    # Fix the mount point.
    if lowerASCII(dev_info["mountpoint"]) in ("swap", "biosboot", "prepboot"):
        dev_info["mountpoint"] = None

    # We should create a partition in some cases.
    # These devices should never be encrypted.
    if ((dev_info["mountpoint"] and dev_info["mountpoint"].startswith("/boot")) or
            dev_info["fstype"] in PARTITION_ONLY_FORMAT_TYPES):
        dev_info["device_type"] = devicefactory.DEVICE_TYPE_PARTITION
        dev_info["encrypted"] = False

    # We shouldn't create swap on a thinly provisioned volume.
    if (dev_info["fstype"] == "swap" and
            dev_info["device_type"] == devicefactory.DEVICE_TYPE_LVM_THINP):
        dev_info["device_type"] = devicefactory.DEVICE_TYPE_LVM

    # Encryption of thinly provisioned volumes isn't supported.
    if dev_info["device_type"] == devicefactory.DEVICE_TYPE_LVM_THINP:
        dev_info["encrypted"] = False


def _add_device(storage, dev_info, use_existing_container=False):
    """Add a device to the storage model.

    :param storage: an instance of Blivet
    :param dev_info: a device info
    :param use_existing_container: should we use an existing container?
    :raise: StorageError if the device cannot be created
    """
    # Create the device factory.
    factory = devicefactory.get_device_factory(
        storage,
        device_type=dev_info["device_type"],
        size=dev_info["size"],
    )

    # Find a container.
    container = factory.get_container(
        allow_existing=use_existing_container
    )

    if use_existing_container and not container:
        raise StorageError("No existing container found.")

    # Update the device info.
    if container:
        # Don't override user-initiated changes to a defined container.
        dev_info["disks"] = container.disks
        dev_info.update({
            "container_encrypted": container.encrypted,
            "container_raid_level": get_device_raid_level(container),
            "container_size": getattr(container, "size_policy", container.size)})

        # The existing container has a name.
        if use_existing_container:
            dev_info["container_name"] = container.name

        # The container is already encrypted
        if container.encrypted:
            dev_info["encrypted"] = False

    # Create the device.
    try:
        storage.factory_device(**dev_info)
    except StorageError as e:
        log.error("The device creation has failed: %s", e)
        raise
    except OverflowError as e:
        log.error("Invalid partition size set: %s", str(e))
        raise StorageError("Invalid partition size set. Use a valid integer.") from None


def destroy_device(storage, device):
    """Destroy the given device in the storage model.

    :param storage: an instance of Blivet
    :param device: an instance of a device
    """
    log.debug("Destroying device '%s'.", device.name)

    # Remove the device.
    if device.is_disk and device.partitioned and not device.format.supported:
        storage.recursive_remove(device)
    elif device.direct and not device.isleaf:
        # We shouldn't call this method for with non-leaf devices
        # except for those which are also directly accessible like
        # lvm snapshot origins and btrfs subvolumes that contain
        # other subvolumes.
        storage.recursive_remove(device)
    else:
        storage.destroy_device(device)

    # Initialize the disk.
    if device.is_disk:
        storage.initialize_disk(device)

    # Remove empty extended partitions.
    if getattr(device, "is_logical", False):
        storage.remove_empty_extended_partitions()

    # If we've just removed the last partition and the disk label
    # is preexisting, reinitialize the disk.
    if device.type == "partition" and device.exists and device.disk.format.exists:
        config = DiskInitializationConfig()

        if config.can_initialize(storage, device.disk):
            storage.initialize_disk(device.disk)

    # Get the device container.
    if hasattr(device, "vg"):
        container = device.vg
        device_type = devicefactory.get_device_type(device)
    elif hasattr(device, "volume"):
        container = device.volume
        device_type = devicefactory.DEVICE_TYPE_BTRFS
    else:
        container = None
        device_type = None

    # Adjust container to size of remaining devices, if auto-sized.
    if (container and not container.exists and container.children and
            container.size_policy == devicefactory.SIZE_POLICY_AUTO):
        # Create the device factory.
        factory = devicefactory.get_device_factory(
            storage,
            device_type=device_type,
            size=Size(0),
            disks=container.disks,
            container_name=container.name,
            container_encrypted=container.encrypted,
            container_raid_level=get_device_raid_level(container),
            container_size=container.size_policy,
        )

        # Configure the factory's devices.
        log.debug("Adjusting container: %s", container.name)
        factory.configure()

    # Finally, remove empty parents of the device.
    for parent in device.parents:
        if not parent.children and not parent.is_disk:
            destroy_device(storage, parent)

    log.debug("Destroyed device '%s'.", device.name)


def rename_container(storage, container, name):
    """Rename the given container.

    :param storage: an instance of Blivet
    :param container: an instance of a container
    :param name: a new name of the container
    """
    # Remove the names of the container and its child
    # devices from the list of already-used names.
    for device in [container] + container.children:
        if device.name in storage.devicetree.names:
            storage.devicetree.names.remove(device.name)

        luks_name = "luks-%s" % device.name
        if luks_name in storage.devicetree.names:
            storage.devicetree.names.remove(luks_name)

    # Set the name of the container.
    try:
        container.name = name
    except ValueError as e:
        raise StorageError(str(e)) from None

    # Fix the btrfs label.
    if container.format.type == "btrfs":
        container.format.label = name

    # Add the new names to the list of the already-used
    # names and prevent potential issues with making the
    # devices encrypted later
    for device in [container] + container.children:
        storage.devicetree.names.append(device.name)

        luks_name = "luks-%s" % device.name
        storage.devicetree.names.append(luks_name)


def get_container(storage, device_type, device=None):
    """Get a container of the given type.

    :param storage: an instance of Blivet
    :param device_type: a device type
    :param device: a defined factory device or None
    :return: a container device
    """
    if device_type not in CONTAINER_DEVICE_TYPES:
        raise StorageError("Invalid device type {}".format(device_type))

    if device and devicefactory.get_device_type(device) != device_type:
        device = None

    factory = devicefactory.get_device_factory(
        storage,
        device_type=device_type,
        size=Size(0),
    )

    return factory.get_container(device=device)


def collect_containers(storage, device_type):
    """Collect containers of the given type.

    :param storage: an instance of Blivet
    :param device_type: a device type
    :return: a list of container devices
    """
    if device_type == devicefactory.DEVICE_TYPE_BTRFS:
        return storage.btrfs_volumes
    else:
        return storage.vgs


def get_supported_raid_levels(device_type):
    """Get RAID levels supported for the given device type.

    It supports any RAID levels that it expects to support and that blivet
    supports for the given device type.

    Since anaconda only ever allows the user to choose RAID levels for
    device type DEVICE_TYPE_MD, hiding the RAID menu for all other device
    types, the function only returns a non-empty set for this device type.
    If this changes, then so should this function, but at this time it
    is not clear what RAID levels should be offered for other device types.

    :param int device_type: one of an enumeration of device types
    :return: a set of supported raid levels
    :rtype: a set of instances of blivet.devicelibs.raid.RAIDLevel
    """
    if device_type == devicefactory.DEVICE_TYPE_MD:
        supported = set(raid.RAIDLevels(["raid0", "raid1", "raid4", "raid5", "raid6", "raid10"]))
    else:
        supported = set()

    return devicefactory.get_supported_raid_levels(device_type).intersection(supported)
