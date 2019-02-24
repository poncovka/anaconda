#
# Copyright (C) 2019  Red Hat, Inc.
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
from abc import ABC, abstractmethod

import blivet
from blivet.deviceaction import ActionResizeFormat, ActionResizeDevice, ActionCreateFormat
from blivet.devicelibs.crypto import MIN_CREATE_ENTROPY
from blivet.devicelibs.lvm import LVM_PE_SIZE, KNOWN_THPOOL_PROFILES
from blivet.devices import LUKSDevice, LVMVolumeGroupDevice
from blivet.devices.lvm import LVMCacheRequest
from blivet.errors import PartitioningError, StorageError, BTRFSValueError
from blivet.formats import get_format
from blivet.formats.disklabel import DiskLabel
from blivet.partitioning import do_partitioning, grow_lvm
from blivet.size import Size
from blivet.static_data import luks_data
from bytesize.bytesize import KiB
from pykickstart.constants import SNAPSHOT_WHEN_POST_INSTALL
from pykickstart.errors import KickstartParseError

from pyanaconda.bootloader.execution import BootloaderExecutor
from pyanaconda.core.constants import AUTOPART_TYPE_DEFAULT, MOUNT_POINT_DEVICE, \
    MOUNT_POINT_REFORMAT, MOUNT_POINT_FORMAT, MOUNT_POINT_PATH, MOUNT_POINT_FORMAT_OPTIONS, \
    MOUNT_POINT_MOUNT_OPTIONS
from pyanaconda.core.i18n import _
from pyanaconda.modules.common.constants.objects import DISK_INITIALIZATION, AUTO_PARTITIONING, \
    MANUAL_PARTITIONING, SNAPSHOT
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.modules.storage.snapshot.validate import SnapshotValidateTask
from pyanaconda.platform import platform
from pyanaconda.storage import autopart
from pyanaconda.storage.checker import storage_checker
from pyanaconda.storage.partitioning import get_default_partitioning
from pyanaconda.storage.utils import get_pbkdf_args, lookup_alias, get_available_disk_space

log = get_module_logger(__name__)

__all__ = ["do_kickstart_storage"]


def do_kickstart_storage(storage, data=None, partitioning=None):
    """Setup storage state from the kickstart data.

    :param storage: an instance of the Blivet's storage object
    :param data: an instance of kickstart data or None
    :param partitioning: an instance of the partitioning executor or None
    """
    log.debug("Setting up the storage from the kickstart data.")

    # Clear partitions.
    clear_partitions(storage)

    if not any(d for d in storage.disks
               if not d.format.hidden and not d.protected):
        return

    # Snapshot free space now, so that we know how much we had available.
    storage.create_free_space_snapshot()

    # Prepare the boot loader.
    BootloaderExecutor().execute(storage, dry_run=True)

    # Execute the partitioning.
    if not partitioning:
        partitioning = get_partitioning_executor(data)

    partitioning.execute(storage)

    # Validate the post-install snapshot requests here.
    validate_snapshot_requests(storage, data)

    # Set up the boot loader.
    storage.set_up_bootloader()


def get_partitioning_executor(data):
    """Get the executor of the enabled partitioning.

    :param data: an instance of kickstart data
    :return: an partitioning executor
    """
    if STORAGE.get_proxy(AUTO_PARTITIONING).Enabled:
        return AutomaticPartitioningExecutor()
    elif STORAGE.get_proxy(MANUAL_PARTITIONING).Enabled:
        return ManualPartitioningExecutor()
    else:
        return CustomPartitioningExecutor(data)


def clear_partitions(storage):
    """Clear partitions.

    :param storage: instance of the Blivet's storage object
    """
    disk_init_proxy = STORAGE.get_proxy(DISK_INITIALIZATION)
    storage.config.clear_part_type = disk_init_proxy.InitializationMode
    storage.config.clear_part_disks = disk_init_proxy.DrivesToClear
    storage.config.clear_part_devices = disk_init_proxy.DevicesToClear
    storage.config.initialize_disks = disk_init_proxy.InitializeLabelsEnabled

    disk_label = disk_init_proxy.DefaultDiskLabel

    if disk_label and not DiskLabel.set_default_label_type(disk_label):
        log.warning("%s is not a supported disklabel type on this platform. "
                    "Using default disklabel %s instead.", disk_label,
                    DiskLabel.get_platform_label_types()[0])

    storage.clear_partitions()


def validate_snapshot_requests(storage, data):
    """Validate the post-install snapshot requests.

    :param storage: instance of the Blivet's storage object
    :param data: an instance of kickstart data
    """
    # No kickstart data provided. Do nothing.
    if data is None:
        return

    # No post-install snapshots are requested. Do nothing.
    snapshot_proxy = STORAGE.get_proxy(SNAPSHOT)
    if not snapshot_proxy.IsRequested(SNAPSHOT_WHEN_POST_INSTALL):
        return

    # Run the validation task directly.
    requests = data.snapshot.get_requests(SNAPSHOT_WHEN_POST_INSTALL)
    task = SnapshotValidateTask(storage, requests, SNAPSHOT_WHEN_POST_INSTALL)
    task.run()


class PartitioningExecutor(ABC):
    """Base class for partitioning executors."""

    @abstractmethod
    def execute(self, storage):
        """Execute the partitioning.

        :param storage: an instance of Blivet
        """
        pass


class AutomaticPartitioningExecutor(PartitioningExecutor):
    """The executor of the automatic partitioning."""

    def execute(self, storage):
        """Execute the automatic partitioning."""
        log.debug("Executing the automatic partitioning.")

        # Create the auto partitioning proxy.
        auto_part_proxy = STORAGE.get_proxy(AUTO_PARTITIONING)

        # Enable automatic partitioning.
        storage.do_autopart = True

        # Set the filesystem type.
        fstype = auto_part_proxy.FilesystemType

        if fstype:
            storage.set_default_fstype(fstype)
            storage.set_default_boot_fstype(fstype)

        # Set the encryption.
        if auto_part_proxy.Encrypted:
            storage.encrypted_autopart = True
            storage.encryption_passphrase = auto_part_proxy.Passphrase
            storage.encryption_cipher = auto_part_proxy.Cipher
            storage.autopart_add_backup_passphrase = auto_part_proxy.BackupPassphraseEnabled
            storage.autopart_escrow_cert = storage.get_escrow_certificate(auto_part_proxy.Escrowcert)

            luks_version = auto_part_proxy.LUKSVersion or storage.default_luks_version

            pbkdf_args = get_pbkdf_args(
                luks_version=luks_version,
                pbkdf_type=auto_part_proxy.PBKDF or None,
                max_memory_kb=auto_part_proxy.PBKDFMemory,
                iterations=auto_part_proxy.PBKDFIterations,
                time_ms=auto_part_proxy.PBKDFTime
            )

            if pbkdf_args and not luks_data.pbkdf_args:
                luks_data.pbkdf_args = pbkdf_args

            storage.autopart_luks_version = luks_version
            storage.autopart_pbkdf_args = pbkdf_args

        if auto_part_proxy.Type != AUTOPART_TYPE_DEFAULT:
            storage.autopart_type = auto_part_proxy.Type

        autopart.do_autopart(storage, min_luks_entropy=MIN_CREATE_ENTROPY)

        report = storage_checker.check(storage)
        report.log(log)

        if report.failure:
            raise PartitioningError("autopart failed: \n" + "\n".join(report.all_errors))


class ManualPartitioningExecutor(PartitioningExecutor):
    """The executor of the manual partitioning."""

    def execute(self, storage):
        """Execute the manual partitioning."""
        log.debug("Setting up the mount points.")
        manual_part_proxy = STORAGE.get_proxy(MANUAL_PARTITIONING)

        # Disable automatic partitioning.
        storage.do_autopart = False

        # Set up mount points.
        for mount_data in manual_part_proxy.MountPoints:
            self._setup_mount_point(storage, mount_data)

    def _setup_mount_point(self, storage, mount_data):
        """Set up a mount point.

        :param storage: an instance of the Blivet's storage object
        :param mount_data: an instance of MountData
        """
        device = mount_data[MOUNT_POINT_DEVICE]
        device_reformat = mount_data[MOUNT_POINT_REFORMAT]
        device_format = mount_data[MOUNT_POINT_FORMAT]

        dev = storage.devicetree.resolve_device(device)
        if dev is None:
            raise KickstartParseError(_("Unknown or invalid device '%s' specified") % device)

        if device_reformat:
            if device_format:
                fmt = get_format(device_format)

                if not fmt:
                    raise KickstartParseError(
                        _("Unknown or invalid format '%(format)s' specified for device "
                          "'%(device)s'") % {"format": device_format, "device": device}
                    )
            else:
                old_fmt = dev.format

                if not old_fmt or old_fmt.type is None:
                    raise KickstartParseError(_("No format on device '%s'") % device)

                fmt = get_format(old_fmt.type)
            storage.format_device(dev, fmt)
            # make sure swaps end up in /etc/fstab
            if fmt.type == "swap":
                storage.add_fstab_swap(dev)

        # only set mount points for mountable formats
        mount_point = mount_data[MOUNT_POINT_PATH]

        if dev.format.mountable and mount_point and mount_point != "none":
            dev.format.mountpoint = mount_point

        dev.format.create_options = mount_data[MOUNT_POINT_FORMAT_OPTIONS]
        dev.format.options = mount_data[MOUNT_POINT_MOUNT_OPTIONS]


class CustomPartitioningExecutor(PartitioningExecutor):
    """The executor of the custom partitioning."""

    def __init__(self, data):
        """Create a new instance.

        :param data: an instance of kickstart data
        """
        super().__init__()
        self._data = data

    def execute(self, storage):
        """Execute the custom partitioning."""
        log.debug("Executing the custom partitioning.")
        data = self._data

        # Disable automatic partitioning.
        storage.do_autopart = False

        self._execute_reqpart(storage, data)
        self._execute_partition(storage, data)
        self._execute_raid(storage, data)
        self._execute_volgroup(storage, data)
        self._execute_logvol(storage, data)
        self._execute_btrfs(storage, data)

    def _execute_reqpart(self, storage, data):
        """Execute the reqpart command.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        """
        if not data.reqpart.reqpart:
            return

        log.debug("Looking for platform-specific bootloader requirements.")
        reqs = platform.set_platform_bootloader_reqs()

        if data.reqpart.addBoot:
            log.debug("Looking for platform-specific boot requirements.")
            boot_partitions = platform.set_platform_boot_partition()

            # Blivet doesn't know this - anaconda sets up the default boot fstype
            # in various places in this file. We need to duplicate that here.
            for part in boot_partitions:
                if part.mountpoint == "/boot":
                    part.fstype = storage.default_boot_fstype

            reqs += boot_partitions

        if reqs:
            log.debug("Applying requirements:\n%s", "".join(map(str, reqs)))
            autopart.do_reqpart(storage, reqs)

    def _execute_partition(self, storage, data):
        """Execute the partition command.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        """
        for partition_data in data.partition.partitions:
            self._execute_partition_data(storage, data, partition_data)

        if data.partition.partitions:
            do_partitioning(storage)

    def _execute_partition_data(self, storage, data, partition_data):
        """Execute the partition data.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        :param partition_data: an instance of PartData
        """
        devicetree = storage.devicetree
        kwargs = {}

        if partition_data.onbiosdisk != "":
            # edd_dict is only modified during storage.reset(), so don't do that
            # while executing storage.
            for (disk, biosdisk) in storage.edd_dict.items():
                if "%x" % biosdisk == partition_data.onbiosdisk:
                    partition_data.disk = disk
                    break

            if not partition_data.disk:
                raise KickstartParseError(
                    _("No disk found for specified BIOS disk \"%s\".")
                    % partition_data.onbiosdisk,
                    lineno=partition_data.lineno
                )

        size = None

        if partition_data.mountpoint == "swap":
            ty = "swap"
            partition_data.mountpoint = ""
            if partition_data.recommended or partition_data.hibernation:
                disk_space = get_available_disk_space(storage)
                size = autopart.swap_suggestion(
                    hibernation=partition_data.hibernation,
                    disk_space=disk_space
                )
                partition_data.grow = False
        # if people want to specify no mountpoint for some reason, let them
        # this is really needed for pSeries boot partitions :(
        elif partition_data.mountpoint == "None":
            partition_data.mountpoint = ""
            if partition_data.fstype:
                ty = partition_data.fstype
            else:
                ty = storage.default_fstype
        elif partition_data.mountpoint == 'appleboot':
            ty = "appleboot"
            partition_data.mountpoint = ""
        elif partition_data.mountpoint == 'prepboot':
            ty = "prepboot"
            partition_data.mountpoint = ""
        elif partition_data.mountpoint == 'biosboot':
            ty = "biosboot"
            partition_data.mountpoint = ""
        elif partition_data.mountpoint.startswith("raid."):
            ty = "mdmember"
            kwargs["name"] = partition_data.mountpoint
            partition_data.mountpoint = ""

            if devicetree.get_device_by_name(kwargs["name"]):
                raise KickstartParseError(
                    _("RAID partition \"%s\" is defined multiple times.") % kwargs["name"],
                    lineno=partition_data.lineno
                )

            if partition_data.onPart:
                data.onPart[kwargs["name"]] = partition_data.onPart
        elif partition_data.mountpoint.startswith("pv."):
            ty = "lvmpv"
            kwargs["name"] = partition_data.mountpoint
            partition_data.mountpoint = ""

            if devicetree.get_device_by_name(kwargs["name"]):
                raise KickstartParseError(
                    _("PV partition \"%s\" is defined multiple times.") % kwargs["name"],
                    lineno=partition_data.lineno
                )

            if partition_data.onPart:
                data.onPart[kwargs["name"]] = partition_data.onPart
        elif partition_data.mountpoint.startswith("btrfs."):
            ty = "btrfs"
            kwargs["name"] = partition_data.mountpoint
            partition_data.mountpoint = ""

            if devicetree.get_device_by_name(kwargs["name"]):
                raise KickstartParseError(
                    _("Btrfs partition \"%s\" is defined multiple times.") % kwargs["name"],
                    lineno=partition_data.lineno
                )

            if partition_data.onPart:
                data.onPart[kwargs["name"]] = partition_data.onPart
        elif partition_data.mountpoint == "/boot/efi":
            if blivet.arch.is_mactel():
                ty = "macefi"
            else:
                ty = "EFI System Partition"
                partition_data.fsopts = "defaults,uid=0,gid=0,umask=077,shortname=winnt"
        else:
            if partition_data.fstype != "":
                ty = partition_data.fstype
            elif partition_data.mountpoint == "/boot":
                ty = storage.default_boot_fstype
            else:
                ty = storage.default_fstype

        if not size and partition_data.size:
            try:
                size = Size("%d MiB" % partition_data.size)
            except ValueError:
                raise KickstartParseError(
                    _("The size \"%s\" is invalid.") % partition_data.size,
                    lineno=partition_data.lineno
                )

        # If this specified an existing request that we should not format,
        # quit here after setting up enough information to mount it later.
        if not partition_data.format:
            if not partition_data.onPart:
                raise KickstartParseError(
                    _("part --noformat must also use the --onpart option."),
                    lineno=partition_data.lineno
                )

            dev = devicetree.resolve_device(partition_data.onPart)
            if not dev:
                raise KickstartParseError(
                    _("Partition \"%s\" given in part command does not exist.")
                    % partition_data.onPart, lineno=partition_data.lineno
                )

            if partition_data.resize:
                size = dev.raw_device.align_target_size(size)
                if size < dev.currentSize:
                    # shrink
                    try:
                        devicetree.actions.add(ActionResizeFormat(dev, size))
                        devicetree.actions.add(ActionResizeDevice(dev, size))
                    except ValueError:
                        raise KickstartParseError(
                            _("Target size \"%(size)s\" for device \"%(device)s\" is invalid.") %
                            {"size": partition_data.size, "device": dev.name},
                            lineno=partition_data.lineno
                        )
                else:
                    # grow
                    try:
                        devicetree.actions.add(ActionResizeDevice(dev, size))
                        devicetree.actions.add(ActionResizeFormat(dev, size))
                    except ValueError:
                        raise KickstartParseError(
                            _("Target size \"%(size)s\" for device \"%(device)s\" is invalid.") %
                            {"size": partition_data.size, "device": dev.name},
                            lineno=partition_data.lineno
                        )

            dev.format.mountpoint = partition_data.mountpoint
            dev.format.mountopts = partition_data.fsopts
            if ty == "swap":
                storage.add_fstab_swap(dev)
            return

        # Now get a format to hold a lot of these extra values.
        kwargs["fmt"] = get_format(ty,
                                   mountpoint=partition_data.mountpoint,
                                   label=partition_data.label,
                                   fsprofile=partition_data.fsprofile,
                                   mountopts=partition_data.fsopts,
                                   create_options=partition_data.mkfsopts,
                                   size=size)
        if not kwargs["fmt"].type:
            raise KickstartParseError(
                _("The \"%s\" file system type is not supported.") % ty,
                lineno=partition_data.lineno
            )

        # If we were given a specific disk to create the partition on, verify
        # that it exists first.  If it doesn't exist, see if it exists with
        # mapper/ on the front.  If that doesn't exist either, it's an error.
        if partition_data.disk:
            disk = devicetree.resolve_device(partition_data.disk)
            # if this is a multipath member promote it to the real mpath
            if disk and disk.format.type == "multipath_member":
                mpath_device = disk.children[0]
                log.info("kickstart: part: promoting %s to %s", disk.name, mpath_device.name)
                disk = mpath_device
            if not disk:
                raise KickstartParseError(
                    _("Disk \"%s\" given in part command does not exist.") % partition_data.disk,
                    lineno=partition_data.lineno
                )
            if not disk.partitionable:
                raise KickstartParseError(
                    _("Cannot install to unpartitionable device \"%s\".") % partition_data.disk,
                    lineno=partition_data.lineno
                )

            should_clear = storage.should_clear(disk)
            if disk and (disk.partitioned or should_clear):
                kwargs["parents"] = [disk]
            elif disk:
                raise KickstartParseError(
                    _("Disk \"%s\" in part command is not partitioned.") % partition_data.disk,
                    lineno=partition_data.lineno
                )

            if not kwargs["parents"]:
                raise KickstartParseError(
                    _("Disk \"%s\" given in part command does not exist.") % partition_data.disk,
                    lineno=partition_data.lineno
                )

        kwargs["grow"] = partition_data.grow
        kwargs["size"] = size
        if partition_data.maxSizeMB:
            try:
                maxsize = Size("%d MiB" % partition_data.maxSizeMB)
            except ValueError:
                raise KickstartParseError(
                    _("The maximum size \"%s\" is invalid.") % partition_data.maxSizeMB,
                    lineno=partition_data.lineno
                )
        else:
            maxsize = None

        kwargs["maxsize"] = maxsize

        kwargs["primary"] = partition_data.primOnly

        add_fstab_swap = None
        # If we were given a pre-existing partition to create a filesystem on,
        # we need to verify it exists and then schedule a new format action to
        # take place there.  Also, we only support a subset of all the options
        # on pre-existing partitions.
        if partition_data.onPart:
            device = devicetree.resolve_device(partition_data.onPart)
            if not device:
                raise KickstartParseError(
                    _("Partition \"%s\" given in part command does not exist.")
                    % partition_data.onPart, lineno=partition_data.lineno
                )

            storage.devicetree.recursive_remove(device, remove_device=False)
            if partition_data.resize:
                size = device.raw_device.align_target_size(size)
                try:
                    devicetree.actions.add(ActionResizeDevice(device, size))
                except ValueError:
                    raise KickstartParseError(
                        _("Target size \"%(size)s\" for device \"%(device)s\" is invalid.")
                        % {"size": partition_data.size, "device": device.name},
                        lineno=partition_data.lineno
                    )

            devicetree.actions.add(ActionCreateFormat(device, kwargs["fmt"]))
            if ty == "swap":
                add_fstab_swap = device
        # tmpfs mounts are not disks and don't occupy a disk partition,
        # so handle them here
        elif partition_data.fstype == "tmpfs":
            try:
                request = storage.new_tmp_fs(**kwargs)
            except (StorageError, ValueError) as e:
                raise KickstartParseError(lineno=partition_data.lineno, msg=str(e))
            storage.create_device(request)
        else:
            # If a previous device has claimed this mount point, delete the
            # old one.
            try:
                if partition_data.mountpoint:
                    device = storage.mountpoints[partition_data.mountpoint]
                    storage.destroy_device(device)
            except KeyError:
                pass

            try:
                request = storage.new_partition(**kwargs)
            except (StorageError, ValueError) as e:
                raise KickstartParseError(lineno=partition_data.lineno, msg=str(e))

            storage.create_device(request)
            if ty == "swap":
                add_fstab_swap = request

        if partition_data.encrypted:
            if partition_data.passphrase and not storage.encryption_passphrase:
                storage.encryption_passphrase = partition_data.passphrase

            # try to use the global passphrase if available
            # XXX: we require the LV/part with --passphrase to be processed
            # before this one to setup the storage.encryption_passphrase
            partition_data.passphrase = partition_data.passphrase or storage.encryption_passphrase

            cert = storage.get_escrow_certificate(partition_data.escrowcert)

            # Get the version of LUKS and PBKDF arguments.
            partition_data.luks_version = partition_data.luks_version \
                                          or storage.default_luks_version

            pbkdf_args = get_pbkdf_args(
                luks_version=partition_data.luks_version,
                pbkdf_type=partition_data.pbkdf,
                max_memory_kb=partition_data.pbkdf_memory,
                iterations=partition_data.pbkdf_iterations,
                time_ms=partition_data.pbkdf_time
            )

            if pbkdf_args and not luks_data.pbkdf_args:
                luks_data.pbkdf_args = pbkdf_args

            if partition_data.onPart:
                luksformat = kwargs["fmt"]
                device.format = get_format(
                    "luks",
                    passphrase=partition_data.passphrase,
                    device=device.path,
                    cipher=partition_data.cipher,
                    escrow_cert=cert,
                    add_backup_passphrase=partition_data.backuppassphrase,
                    min_luks_entropy=MIN_CREATE_ENTROPY,
                    luks_version=partition_data.luks_version,
                    pbkdf_args=pbkdf_args
                )
                luksdev = LUKSDevice(
                    "luks%d" % storage.next_id,
                    fmt=luksformat,
                    parents=device
                )
            else:
                luksformat = request.format
                request.format = get_format(
                    "luks",
                    passphrase=partition_data.passphrase,
                    cipher=partition_data.cipher,
                    escrow_cert=cert,
                    add_backup_passphrase=partition_data.backuppassphrase,
                    min_luks_entropy=MIN_CREATE_ENTROPY,
                    luks_version=partition_data.luks_version,
                    pbkdf_args=pbkdf_args
                )
                luksdev = LUKSDevice("luks%d" % storage.next_id,
                                     fmt=luksformat,
                                     parents=request)

            if ty == "swap":
                # swap is on the LUKS device not on the LUKS' parent device,
                # override the info here
                add_fstab_swap = luksdev

            storage.create_device(luksdev)

        if add_fstab_swap:
            storage.add_fstab_swap(add_fstab_swap)

    def _execute_raid(self, storage, data):
        """Execute the raid command.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        """
        for raid_data in data.raid.raidList:
            self._execute_raid_data(storage, data, raid_data)

    def _execute_raid_data(self, storage, data, raid_data):
        """Execute the raid data.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        :param raid_data: an instance of RaidData
        """
        raidmems = []
        devicetree = storage.devicetree
        devicename = raid_data.device
        if raid_data.preexist:
            device = devicetree.resolve_device(devicename)
            if device:
                devicename = device.name

        kwargs = {}

        if raid_data.mountpoint == "swap":
            ty = "swap"
            raid_data.mountpoint = ""
        elif raid_data.mountpoint.startswith("pv."):
            ty = "lvmpv"
            kwargs["name"] = raid_data.mountpoint
            data.onPart[kwargs["name"]] = devicename

            if devicetree.get_device_by_name(kwargs["name"]):
                raise KickstartParseError(
                    _("PV partition \"%s\" is defined multiple times.") % kwargs["name"],
                    lineno=raid_data.lineno
                )

            raid_data.mountpoint = ""
        elif raid_data.mountpoint.startswith("btrfs."):
            ty = "btrfs"
            kwargs["name"] = raid_data.mountpoint
            data.onPart[kwargs["name"]] = devicename

            if devicetree.get_device_by_name(kwargs["name"]):
                raise KickstartParseError(
                    _("Btrfs partition \"%s\" is defined multiple times.") % kwargs["name"],
                    lineno=raid_data.lineno
                )

            raid_data.mountpoint = ""
        else:
            if raid_data.fstype != "":
                ty = raid_data.fstype
            elif raid_data.mountpoint == "/boot" and "mdarray" in storage.bootloader.stage2_device_types:
                ty = storage.default_boot_fstype
            else:
                ty = storage.default_fstype

        # Sanity check mountpoint
        if raid_data.mountpoint != "" and raid_data.mountpoint[0] != '/':
            raise KickstartParseError(
                _("The mount point \"%s\" is not valid.  It must start with a /.")
                % raid_data.mountpoint, lineno=raid_data.lineno
            )

        # If this specifies an existing request that we should not format,
        # quit here after setting up enough information to mount it later.
        if not raid_data.format:
            if not devicename:
                raise KickstartParseError(
                    _("raid --noformat must also use the --device option."),
                    lineno=raid_data.lineno
                )

            dev = devicetree.get_device_by_name(devicename)
            if not dev:
                raise KickstartParseError(
                    _("RAID device  \"%s\" given in raid command does not exist.") % devicename,
                    lineno=raid_data.lineno
                )

            dev.format.mountpoint = raid_data.mountpoint
            dev.format.mountopts = raid_data.fsopts
            if ty == "swap":
                storage.add_fstab_swap(dev)
            return

        # Get a list of all the RAID members.
        for member in raid_data.members:
            dev = devicetree.resolve_device(member)
            if not dev:
                # if member is using --onpart, use original device
                mem = data.onPart.get(member, member)
                dev = devicetree.resolve_device(mem) or lookup_alias(devicetree, member)
            if dev and dev.format.type == "luks":
                try:
                    dev = dev.children[0]
                except IndexError:
                    dev = None

            if dev and dev.format.type != "mdmember":
                raise KickstartParseError(
                    _("RAID device \"%(device)s\" has a format of \"%(format)s\", but should have "
                      "a format of \"mdmember\".") % {"device": member, "format": dev.format.type},
                    lineno=raid_data.lineno
                )

            if not dev:
                raise KickstartParseError(
                    _("Tried to use undefined partition \"%s\" in RAID specification.") % member,
                    lineno=raid_data.lineno
                )

            raidmems.append(dev)

        # Now get a format to hold a lot of these extra values.
        kwargs["fmt"] = get_format(
            ty,
            label=raid_data.label,
            fsprofile=raid_data.fsprofile,
            mountpoint=raid_data.mountpoint,
            mountopts=raid_data.fsopts,
            create_options=raid_data.mkfsopts
        )

        if not kwargs["fmt"].type:
            raise KickstartParseError(
                _("The \"%s\" file system type is not supported.") % ty,
                lineno=raid_data.lineno
            )

        kwargs["name"] = devicename
        kwargs["level"] = raid_data.level
        kwargs["parents"] = raidmems
        kwargs["member_devices"] = len(raidmems) - raid_data.spares
        kwargs["total_devices"] = len(raidmems)

        if raid_data.chunk_size:
            kwargs["chunk_size"] = Size("%d KiB" % raid_data.chunk_size)

        add_fstab_swap = None

        # If we were given a pre-existing RAID to create a filesystem on,
        # we need to verify it exists and then schedule a new format action
        # to take place there.  Also, we only support a subset of all the
        # options on pre-existing RAIDs.
        if raid_data.preexist:
            device = devicetree.get_device_by_name(devicename)
            if not device:
                raise KickstartParseError(
                    _("RAID volume \"%s\" specified with --useexisting does not exist.")
                    % devicename, lineno=raid_data.lineno
                )

            storage.devicetree.recursive_remove(device, remove_device=False)
            devicetree.actions.add(ActionCreateFormat(device, kwargs["fmt"]))
            if ty == "swap":
                add_fstab_swap = device
        else:
            if devicename and devicename in (a.name for a in storage.mdarrays):
                raise KickstartParseError(
                    _("The RAID volume name \"%s\" is already in use.") % devicename,
                    lineno=raid_data.lineno
                )

            # If a previous device has claimed this mount point, delete the
            # old one.
            try:
                if raid_data.mountpoint:
                    device = storage.mountpoints[raid_data.mountpoint]
                    storage.destroy_device(device)
            except KeyError:
                pass

            try:
                request = storage.new_mdarray(**kwargs)
            except (StorageError, ValueError) as e:
                raise KickstartParseError(str(e), lineno=raid_data.lineno)

            storage.create_device(request)
            if ty == "swap":
                add_fstab_swap = request

        if raid_data.encrypted:
            if raid_data.passphrase and not storage.encryption_passphrase:
                storage.encryption_passphrase = raid_data.passphrase

            cert = storage.get_escrow_certificate(raid_data.escrowcert)

            # Get the version of LUKS and PBKDF arguments.
            raid_data.luks_version = raid_data.luks_version or storage.default_luks_version

            pbkdf_args = get_pbkdf_args(
                luks_version=raid_data.luks_version,
                pbkdf_type=raid_data.pbkdf,
                max_memory_kb=raid_data.pbkdf_memory,
                iterations=raid_data.pbkdf_iterations,
                time_ms=raid_data.pbkdf_time
            )

            if pbkdf_args and not luks_data.pbkdf_args:
                luks_data.pbkdf_args = pbkdf_args

            if raid_data.preexist:
                luksformat = kwargs["fmt"]
                device.format = get_format(
                    "luks",
                    passphrase=raid_data.passphrase,
                    device=device.path,
                    cipher=raid_data.cipher,
                    escrow_cert=cert,
                    add_backup_passphrase=raid_data.backuppassphrase,
                    luks_version=raid_data.luks_version,
                    pbkdf_args=pbkdf_args
                )
                luksdev = LUKSDevice(
                    "luks%d" % storage.next_id,
                    fmt=luksformat,
                    parents=device
                )
            else:
                luksformat = request.format
                request.format = get_format(
                    "luks",
                    passphrase=raid_data.passphrase,
                    cipher=raid_data.cipher,
                    escrow_cert=cert,
                    add_backup_passphrase=raid_data.backuppassphrase,
                    luks_version=raid_data.luks_version,
                    pbkdf_args=pbkdf_args
                )
                luksdev = LUKSDevice(
                    "luks%d" % storage.next_id,
                    fmt=luksformat,
                    parents=request
                )

            if ty == "swap":
                # swap is on the LUKS device instead of the parent device,
                # override the device here
                add_fstab_swap = luksdev

            storage.create_device(luksdev)

        if add_fstab_swap:
            storage.add_fstab_swap(add_fstab_swap)

    def _execute_volgroup(self, storage, data):
        """Execute the volgroup command.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        """
        for volgroup_data in data.volgroup.vgList:
            self._execute_volgroup_data(storage, data, volgroup_data)

    def _execute_volgroup_data(self, storage, data, volgroup_data):
        """Execute the volgroup data.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        :param volgroup_data: an instance of VolGroupData
        """
        pvs = []
        devicetree = storage.devicetree

        # Get a list of all the physical volume devices that make up this VG.
        for pv in volgroup_data.physvols:
            dev = devicetree.resolve_device(pv)
            if not dev:
                # if pv is using --onpart, use original device
                pv_name = data.onPart.get(pv, pv)
                dev = devicetree.resolve_device(pv_name) or lookup_alias(devicetree, pv)
            if dev and dev.format.type == "luks":
                try:
                    dev = dev.children[0]
                except IndexError:
                    dev = None

            if dev and dev.format.type != "lvmpv":
                raise KickstartParseError(
                    _("Physical volume \"%(device)s\" has a format of \"%(format)s\", but should "
                      "have a format of \"lvmpv\".") % {"device": pv, "format": dev.format.type},
                    lineno=volgroup_data.lineno)

            if not dev:
                raise KickstartParseError(
                    _("Tried to use undefined partition \"%s\" in Volume Group specification")
                    % pv, lineno=volgroup_data.lineno
                )

            pvs.append(dev)

        if len(pvs) == 0 and not volgroup_data.preexist:
            raise KickstartParseError(
                _("Volume group \"%s\" defined without any physical volumes.  Either specify "
                  "physical volumes or use --useexisting.") % volgroup_data.vgname,
                lineno=volgroup_data.lineno
            )

        if volgroup_data.pesize == 0:
            # default PE size requested -- we use blivet's default in KiB
            volgroup_data.pesize = LVM_PE_SIZE.convert_to(KiB)

        pesize = Size("%d KiB" % volgroup_data.pesize)
        possible_extents = LVMVolumeGroupDevice.get_supported_pe_sizes()
        if pesize not in possible_extents:
            raise KickstartParseError(
                _("Volume group given physical extent size of \"%(extentSize)s\", but must be one "
                  "of:\n%(validExtentSizes)s.")
                % {
                    "extentSize": pesize,
                    "validExtentSizes": ", ".join(str(e) for e in possible_extents)
                },
                lineno=volgroup_data.lineno
            )

        # If --noformat or --useexisting was given, there's really nothing to do.
        if not volgroup_data.format or volgroup_data.preexist:
            if not volgroup_data.vgname:
                raise KickstartParseError(
                    _("volgroup --noformat and volgroup --useexisting must also use the --name= "
                      "option."), lineno=volgroup_data.lineno
                )

            dev = devicetree.get_device_by_name(volgroup_data.vgname)
            if not dev:
                raise KickstartParseError(
                    _("Volume group \"%s\" given in volgroup command does not exist.")
                    % volgroup_data.vgname, lineno=volgroup_data.lineno
                )
        elif volgroup_data.vgname in (vg.name for vg in storage.vgs):
            raise KickstartParseError(
                _("The volume group name \"%s\" is already in use.") % volgroup_data.vgname,
                lineno=volgroup_data.lineno
            )
        else:
            try:
                request = storage.new_vg(
                    parents=pvs,
                    name=volgroup_data.vgname,
                    pe_size=pesize
                )
            except (StorageError, ValueError) as e:
                raise KickstartParseError(lineno=volgroup_data.lineno, msg=str(e))

            storage.create_device(request)
            if volgroup_data.reserved_space:
                request.reserved_space = volgroup_data.reserved_space
            elif volgroup_data.reserved_percent:
                request.reserved_percent = volgroup_data.reserved_percent

            # in case we had to truncate or otherwise adjust the specified name
            data.onPart[volgroup_data.vgname] = request.name

    def _execute_logvol(self, storage, data):
        """Execute the logvol command.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        """
        for logvol_data in data.logvol.lvList:
            self._execute_logvol_data(storage, data, logvol_data)

        if data.logvol.lvList:
            grow_lvm(storage)

    def _execute_logvol_data(self, storage, data, logvol_data):
        """Execute the logvol data.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        :param logvol_data: an instance of LogVolData
        """
        devicetree = storage.devicetree

        # FIXME: we should be running sanityCheck on partitioning that is not ks
        # autopart, but that's likely too invasive for #873135 at this moment
        if logvol_data.mountpoint == "/boot" and blivet.arch.is_s390():
            raise KickstartParseError(
                "/boot can not be of type 'lvmlv' on s390x",
                lineno=logvol_data.lineno
            )

        # we might have truncated or otherwise changed the specified vg name
        vgname = data.onPart.get(logvol_data.vgname, logvol_data.vgname)

        size = None

        if logvol_data.percent:
            size = Size(0)

        if logvol_data.mountpoint == "swap":
            ty = "swap"
            logvol_data.mountpoint = ""
            if logvol_data.recommended or logvol_data.hibernation:
                disk_space = get_available_disk_space(storage)
                size = autopart.swap_suggestion(
                    hibernation=logvol_data.hibernation,
                    disk_space=disk_space
                )
                logvol_data.grow = False
        else:
            if logvol_data.fstype != "":
                ty = logvol_data.fstype
            else:
                ty = storage.default_fstype

        if size is None and not logvol_data.preexist:
            if not logvol_data.size:
                raise KickstartParseError(
                    "Size can not be decided on from kickstart nor obtained from device.",
                    lineno=logvol_data.lineno
                )
            try:
                size = Size("%d MiB" % logvol_data.size)
            except ValueError:
                raise KickstartParseError(
                    "The size \"%s\" is invalid." % logvol_data.size,
                    lineno=logvol_data.lineno
                )

        if logvol_data.thin_pool:
            logvol_data.mountpoint = ""
            ty = None

        # Sanity check mountpoint
        if logvol_data.mountpoint != "" and logvol_data.mountpoint[0] != '/':
            raise KickstartParseError(
                _("The mount point \"%s\" is not valid.  It must start with a /.")
                % logvol_data.mountpoint, lineno=logvol_data.lineno
            )

        # Check that the VG this LV is a member of has already been specified.
        vg = devicetree.get_device_by_name(vgname)
        if not vg:
            raise KickstartParseError(
                _("No volume group exists with the name \"%s\".  Specify volume groups before "
                  "logical volumes.") % logvol_data.vgname, lineno=logvol_data.lineno
            )

        # If cache PVs specified, check that they belong to the same VG this LV is a member of
        if logvol_data.cache_pvs:
            pv_devices = (lookup_alias(devicetree, pv) for pv in logvol_data.cache_pvs)
            if not all(pv in vg.pvs for pv in pv_devices):
                raise KickstartParseError(
                    _("Cache PVs must belong to the same VG as the cached LV"),
                    lineno=logvol_data.lineno
                )

        pool = None
        if logvol_data.thin_volume:
            pool = devicetree.get_device_by_name("%s-%s" % (vg.name, logvol_data.pool_name))
            if not pool:
                raise KickstartParseError(
                    _("No thin pool exists with the name \"%s\". Specify thin pools before thin "
                      "volumes.") % logvol_data.pool_name, lineno=logvol_data.lineno
                )

        # If this specifies an existing request that we should not format,
        # quit here after setting up enough information to mount it later.
        if not logvol_data.format:
            if not logvol_data.name:
                raise KickstartParseError(
                    _("logvol --noformat must also use the --name= option."),
                    lineno=logvol_data.lineno
                )

            dev = devicetree.get_device_by_name("%s-%s" % (vg.name, logvol_data.name))
            if not dev:
                raise KickstartParseError(
                    _("Logical volume \"%s\" given in logvol command does not exist.")
                    % logvol_data.name, lineno=logvol_data.lineno
                )

            if logvol_data.resize:
                size = dev.raw_device.align_target_size(size)
                if size < dev.currentSize:
                    # shrink
                    try:
                        devicetree.actions.add(ActionResizeFormat(dev, size))
                        devicetree.actions.add(ActionResizeDevice(dev, size))
                    except ValueError:
                        raise KickstartParseError(
                            _("Target size \"%(size)s\" for device \"%(device)s\" is invalid.")
                            % {"size": logvol_data.size, "device": dev.name},
                            lineno=logvol_data.lineno
                        )
                else:
                    # grow
                    try:
                        devicetree.actions.add(ActionResizeDevice(dev, size))
                        devicetree.actions.add(ActionResizeFormat(dev, size))
                    except ValueError:
                        raise KickstartParseError(
                            _("Target size \"%(size)s\" for device \"%(device)s\" is invalid.")
                            % {"size": logvol_data.size, "device": dev.name},
                            lineno=logvol_data.lineno
                        )

            dev.format.mountpoint = logvol_data.mountpoint
            dev.format.mountopts = logvol_data.fsopts
            if ty == "swap":
                storage.add_fstab_swap(dev)
            return

        # Make sure this LV name is not already used in the requested VG.
        if not logvol_data.preexist:
            tmp = devicetree.get_device_by_name("%s-%s" % (vg.name, logvol_data.name))
            if tmp:
                raise KickstartParseError(
                    _("Logical volume name \"%(logvol)s\" is already in use in volume group "
                      "\"%(volgroup)s\".") % {"logvol": logvol_data.name, "volgroup": vg.name},
                    lineno=logvol_data.lineno
                )

            if not logvol_data.percent and size and not logvol_data.grow and size < vg.pe_size:
                raise KickstartParseError(
                    _("Logical volume size \"%(logvolSize)s\" must be larger than the volume "
                      "group extent size of \"%(extentSize)s\".")
                    % {"logvolSize": size, "extentSize": vg.pe_size},
                    lineno=logvol_data.lineno
                )

        # Now get a format to hold a lot of these extra values.
        fmt = get_format(
            ty,
            mountpoint=logvol_data.mountpoint,
            label=logvol_data.label,
            fsprofile=logvol_data.fsprofile,
            create_options=logvol_data.mkfsopts,
            mountopts=logvol_data.fsopts
        )
        if not fmt.type and not logvol_data.thin_pool:
            raise KickstartParseError(
                _("The \"%s\" file system type is not supported.") % ty,
                lineno=logvol_data.lineno
            )

        add_fstab_swap = None
        # If we were given a pre-existing LV to create a filesystem on, we need
        # to verify it and its VG exists and then schedule a new format action
        # to take place there.  Also, we only support a subset of all the
        # options on pre-existing LVs.
        if logvol_data.preexist:
            device = devicetree.get_device_by_name("%s-%s" % (vg.name, logvol_data.name))
            if not device:
                raise KickstartParseError(
                    _("Logical volume \"%s\" given in logvol command does not exist.")
                    % logvol_data.name, lineno=logvol_data.lineno
                )

            storage.devicetree.recursive_remove(device, remove_device=False)

            if logvol_data.resize:
                size = device.raw_device.align_target_size(size)
                try:
                    devicetree.actions.add(ActionResizeDevice(device, size))
                except ValueError:
                    raise KickstartParseError(
                        _("Target size \"%(size)s\" for device \"%(device)s\" is invalid.") %
                        {"size": logvol_data.size, "device": device.name},
                        lineno=logvol_data.lineno
                    )

            devicetree.actions.add(ActionCreateFormat(device, fmt))
            if ty == "swap":
                add_fstab_swap = device
        else:
            # If a previous device has claimed this mount point, delete the
            # old one.
            try:
                if logvol_data.mountpoint:
                    device = storage.mountpoints[logvol_data.mountpoint]
                    storage.destroy_device(device)
            except KeyError:
                pass

            if logvol_data.thin_volume:
                parents = [pool]
            else:
                parents = [vg]

            pool_args = {}
            if logvol_data.thin_pool:
                if logvol_data.profile:
                    matching = (p for p in KNOWN_THPOOL_PROFILES if p.name == logvol_data.profile)
                    profile = next(matching, None)
                    if profile:
                        pool_args["profile"] = profile
                    else:
                        log.warning(
                            "No matching profile for %s found in LVM configuration",
                            logvol_data.profile
                        )
                if logvol_data.metadata_size:
                    pool_args["metadata_size"] = Size("%d MiB" % logvol_data.metadata_size)
                if logvol_data.chunk_size:
                    pool_args["chunk_size"] = Size("%d KiB" % logvol_data.chunk_size)

            if logvol_data.maxSizeMB:
                try:
                    maxsize = Size("%d MiB" % logvol_data.maxSizeMB)
                except ValueError:
                    raise KickstartParseError(
                        _("The maximum size \"%s\" is invalid.") % logvol_data.maxSizeMB,
                        lineno=logvol_data.lineno
                    )
            else:
                maxsize = None

            if logvol_data.cache_size and logvol_data.cache_pvs:
                pv_devices = [lookup_alias(devicetree, pv) for pv in logvol_data.cache_pvs]
                cache_size = Size("%d MiB" % logvol_data.cache_size)
                cache_mode = logvol_data.cache_mode or None
                cache_request = LVMCacheRequest(cache_size, pv_devices, cache_mode)
            else:
                cache_request = None

            try:
                request = storage.new_lv(
                    fmt=fmt,
                    name=logvol_data.name,
                    parents=parents,
                    size=size,
                    thin_pool=logvol_data.thin_pool,
                    thin_volume=logvol_data.thin_volume,
                    grow=logvol_data.grow,
                    maxsize=maxsize,
                    percent=logvol_data.percent,
                    cache_request=cache_request,
                    **pool_args
                )
            except (StorageError, ValueError) as e:
                raise KickstartParseError(str(e), lineno=logvol_data.lineno)

            storage.create_device(request)
            if ty == "swap":
                add_fstab_swap = request

        if logvol_data.encrypted:
            if logvol_data.passphrase and not storage.encryption_passphrase:
                storage.encryption_passphrase = logvol_data.passphrase

            # try to use the global passphrase if available
            # XXX: we require the LV/part with --passphrase to be processed
            # before this one to setup the storage.encryption_passphrase
            logvol_data.passphrase = logvol_data.passphrase or storage.encryption_passphrase

            cert = storage.get_escrow_certificate(logvol_data.escrowcert)

            # Get the version of LUKS and PBKDF arguments.
            logvol_data.luks_version = logvol_data.luks_version or storage.default_luks_version

            pbkdf_args = get_pbkdf_args(
                luks_version=logvol_data.luks_version,
                pbkdf_type=logvol_data.pbkdf,
                max_memory_kb=logvol_data.pbkdf_memory,
                iterations=logvol_data.pbkdf_iterations,
                time_ms=logvol_data.pbkdf_time
            )

            if pbkdf_args and not luks_data.pbkdf_args:
                luks_data.pbkdf_args = pbkdf_args

            if logvol_data.preexist:
                luksformat = fmt
                device.format = get_format(
                    "luks",
                    passphrase=logvol_data.passphrase,
                    device=device.path,
                    cipher=logvol_data.cipher,
                    escrow_cert=cert,
                    add_backup_passphrase=logvol_data.backuppassphrase,
                    luks_version=logvol_data.luks_version,
                    pbkdf_args=pbkdf_args
                )
                luksdev = LUKSDevice(
                    "luks%d" % storage.next_id,
                    fmt=luksformat,
                    parents=device
                )
            else:
                luksformat = request.format
                request.format = get_format(
                    "luks",
                    passphrase=logvol_data.passphrase,
                    cipher=logvol_data.cipher,
                    escrow_cert=cert,
                    add_backup_passphrase=logvol_data.backuppassphrase,
                    min_luks_entropy=MIN_CREATE_ENTROPY,
                    luks_version=logvol_data.luks_version,
                    pbkdf_args=pbkdf_args
                )
                luksdev = LUKSDevice(
                    "luks%d" % storage.next_id,
                    fmt=luksformat,
                    parents=request
                )

            if ty == "swap":
                # swap is on the LUKS device not on the LUKS' parent device,
                # override the info here
                add_fstab_swap = luksdev

            storage.create_device(luksdev)

        if add_fstab_swap:
            storage.add_fstab_swap(add_fstab_swap)

    def _execute_btrfs(self, storage, data):
        """Execute the btrfs command.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        """
        for btrfs_data in data.btrfs.btrfsList:
            self._execute_btrfs_data(storage, data, btrfs_data)

    def _execute_btrfs_data(self, storage, data, btrfs_data):
        """Execute the btrfs command.

        :param storage: an instance of the Blivet's storage object
        :param data: an instance of kickstart data
        :param btrfs_data: an instance of BTRFSData
        """
        devicetree = storage.devicetree
        members = []

        # Get a list of all the devices that make up this volume.
        for member in btrfs_data.devices:
            dev = devicetree.resolve_device(member)
            if not dev:
                # if using --onpart, use original device
                member_name = data.onPart.get(member, member)
                dev = devicetree.resolve_device(member_name) or lookup_alias(devicetree, member)

            if dev and dev.format.type == "luks":
                try:
                    dev = dev.children[0]
                except IndexError:
                    dev = None

            if dev and dev.format.type != "btrfs":
                raise KickstartParseError(
                    _("Btrfs partition \"%(device)s\" has a format of \"%(format)s\", but "
                      "should have a format of \"btrfs\".")
                    % {"device": member, "format": dev.format.type},
                    lineno=btrfs_data.lineno
                )

            if not dev:
                raise KickstartParseError(
                    _("Tried to use undefined partition \"%s\" in Btrfs volume specification.")
                    % member, lineno=btrfs_data.lineno
                )

            members.append(dev)

        if btrfs_data.subvol:
            name = btrfs_data.name
        elif btrfs_data.label:
            name = btrfs_data.label
        else:
            name = None

        if len(members) == 0 and not btrfs_data.preexist:
            raise KickstartParseError(
                _("Btrfs volume defined without any member devices.  Either specify member "
                  "devices or use --useexisting."), lineno=btrfs_data.lineno
            )

        # allow creating btrfs vols/subvols without specifying mountpoint
        if btrfs_data.mountpoint in ("none", "None"):
            btrfs_data.mountpoint = ""

        # Sanity check mountpoint
        if btrfs_data.mountpoint != "" and btrfs_data.mountpoint[0] != '/':
            raise KickstartParseError(
                _("The mount point \"%s\" is not valid.  It must start with a /.")
                % btrfs_data.mountpoint, lineno=btrfs_data.lineno
            )

        # If a previous device has claimed this mount point, delete the
        # old one.
        try:
            if btrfs_data.mountpoint:
                device = storage.mountpoints[btrfs_data.mountpoint]
                storage.destroy_device(device)
        except KeyError:
            pass

        if btrfs_data.preexist:
            device = devicetree.resolve_device(btrfs_data.name)
            if not device:
                raise KickstartParseError(
                    _("Btrfs volume \"%s\" specified with --useexisting does not exist.")
                    % btrfs_data.name, lineno=btrfs_data.lineno
                )

            device.format.mountpoint = btrfs_data.mountpoint
        else:
            try:
                request = storage.new_btrfs(
                    name=name,
                    subvol=btrfs_data.subvol,
                    mountpoint=btrfs_data.mountpoint,
                    metadata_level=btrfs_data.metaDataLevel,
                    data_level=btrfs_data.dataLevel,
                    parents=members,
                    create_options=btrfs_data.mkfsopts
                )
            except BTRFSValueError as e:
                raise KickstartParseError(lineno=btrfs_data.lineno, msg=str(e))

            storage.create_device(request)
