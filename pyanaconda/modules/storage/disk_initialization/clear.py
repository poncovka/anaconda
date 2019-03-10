#
# Clear partitions.
#
# Copyright (C) 2018 Red Hat, Inc.
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
import parted
from blivet.devices import PartitionDevice
from pyanaconda.anaconda_loggers import get_module_logger

from pyanaconda.core.constants import CLEAR_PARTITIONS_NONE, CLEAR_PARTITIONS_DEFAULT, \
    CLEAR_PARTITIONS_LINUX, CLEAR_PARTITIONS_ALL, CLEAR_PARTITIONS_LIST
from pyanaconda.modules.common.constants.objects import DISK_INITIALIZATION, AUTO_PARTITIONING
from pyanaconda.modules.common.constants.services import STORAGE

log = get_module_logger(__name__)


class DiskInitializationConfig(object):
    """Configuration for the disk initialization."""

    def __init__(self):
        self.initialization_mode = CLEAR_PARTITIONS_DEFAULT
        self.drives_to_clear = []
        self.devices_to_clear = []
        self.initialize_labels = False
        self.format_unrecognized = False
        self.clear_non_existent = False


def get_initialization_config():
    """Get the config for clearing partitions.

    :return: an instance of DiskInitializationConfig
    """
    disk_init_proxy = STORAGE.get_proxy(DISK_INITIALIZATION)
    config = DiskInitializationConfig()

    config.initialization_mode = disk_init_proxy.InitializationMode
    config.drives_to_clear = disk_init_proxy.DrivesToClear
    config.devices_to_clear = disk_init_proxy.DevicesToClear
    config.initialize_labels = disk_init_proxy.InitializeLabelsEnabled
    config.format_unrecognized = disk_init_proxy.FormatUnrecognizedEnabled

    # If autopart is selected we want to remove whatever has been
    # created/scheduled to make room for autopart. If custom is
    # selected, we want to leave alone any storage layout the
    # user may have set up before now.
    auto_part_proxy = STORAGE.get_proxy(AUTO_PARTITIONING)
    config.clear_non_existent = auto_part_proxy.Enabled

    return config


def should_clear_device(storage, device, config):
    """Return True if a clearpart settings say a device should be cleared.

    :param storage: an instance of the storage
    :param device: the device (required)
    :param config: an instance of DiskInitializationConfig
    :return bool: whether or not clear_partitions should remove this device
    """
    for disk in device.disks:
        # this will not include disks with hidden formats like multipath
        # and firmware raid member disks
        if config.drives_to_clears and disk.name not in config.drives_to_clears:
            return False

    if not config.clear_non_existent:
        if (device.is_disk and not device.format.exists) or \
                (not device.is_disk and not device.exists):
            return False

    # the only devices we want to clear when the initialization mode is
    # CLEAR_PARTITIONS_NONE are uninitialized disks, or disks with no
    # partitions, in drives_to_clears, and then only when we have been asked
    # to initialize disks as needed
    if config.initialization_mode in [CLEAR_PARTITIONS_NONE, CLEAR_PARTITIONS_DEFAULT]:
        if not config.initialize_disks or not device.is_disk:
            return False

        if not storage.empty_device(device):
            return False

    if isinstance(device, PartitionDevice):
        # Never clear the special first partition on a Mac disk label, as
        # that holds the partition table itself.
        # Something similar for the third partition on a Sun disklabel.
        if device.is_magic:
            return False

        # We don't want to fool with extended partitions, freespace, &c
        if not device.is_primary and not device.is_logical:
            return False

        if config.initialization_mode == CLEAR_PARTITIONS_LINUX and \
                not device.format.linux_native and \
                not device.get_flag(parted.PARTITION_LVM) and \
                not device.get_flag(parted.PARTITION_RAID) and \
                not device.get_flag(parted.PARTITION_SWAP):
            return False
    elif device.is_disk:
        if device.partitioned and config.initialization_mode != CLEAR_PARTITIONS_ALL:
            # if the mode is not CLEAR_PARTITIONS_ALL but we'll still be
            # removing every partition from the disk, return True since we
            # will want to be able to create a new disklabel on this disk
            if not storage.empty_device(device):
                return False

        # Never clear disks with hidden formats
        if device.format.hidden:
            return False

        # When the mode is CLEAR_PARTITIONS_LINUX and a disk has non-
        # linux whole-disk formatting, do not clear it. The exception is
        # the case of an uninitialized disk when we've been asked to
        # initialize disks as needed
        if (config.initialization_mode == CLEAR_PARTITIONS_LINUX and
                not ((config.initialize_labels and
                      storage.empty_device(device)) or
                     (not device.partitioned and device.format.linux_native))):
            return False

    # Don't clear devices holding install media.
    descendants = storage.devicetree.get_dependent_devices(device)
    if device.protected or any(d.protected for d in descendants):
        return False

    if config.initialization_mode == CLEAR_PARTITIONS_LIST and \
            device.name not in config.devices_to_clear:
        return False

    return True


def clear_partitions(storage, config):
    """Clear partitions and dependent devices from disks.

    This is also where zerombr is handled.

    :param storage: an instance of the storage
    :param config: an instance of DiskInitializationConfig
    """
    # Sort partitions by descending partition number to minimize confusing
    # things like multiple "destroy sda5" actions due to parted renumbering
    # partitions. This can still happen through the UI but it makes sense to
    # avoid it where possible.
    partitions = sorted(storage.partitions,
                        key=lambda p: getattr(p.parted_partition, "number", 1),
                        reverse=True)
    for part in partitions:
        log.debug("clearpart: looking at %s", part.name)
        if not should_clear_device(storage, part, config):
            continue

        storage.recursive_remove(part)
        log.debug("partitions: %s", [p.name for p in part.disk.children])

    # now remove any empty extended partitions
    storage.remove_empty_extended_partitions()

    # ensure all disks have appropriate disklabels
    for disk in storage.disks:
        zerombr = (config.format_unrecognized and disk.format.type is None)
        should_clear = should_clear_device(storage, disk, config)
        if should_clear:
            storage.recursive_remove(disk)

        if zerombr or should_clear:
            if disk.protected:
                log.warning("cannot clear '%s': disk is protected or read only", disk.name)
            else:
                log.debug("clearpart: initializing %s", disk.name)
                storage.initialize_disk(disk)

    storage.update_bootloader_disk_list()
