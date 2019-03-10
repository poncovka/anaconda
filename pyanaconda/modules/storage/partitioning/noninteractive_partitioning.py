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
from abc import ABCMeta, abstractmethod

import parted
from blivet.devicelibs.crypto import MIN_CREATE_ENTROPY
from blivet.devices import PartitionDevice, LUKSDevice
from blivet.devices.lvm import DEFAULT_THPOOL_RESERVE
from blivet.devices.partition import FALLBACK_DEFAULT_PART_SIZE

from blivet.errors import NoDisksError, NotEnoughFreeSpaceError
from blivet.formats import get_format
from blivet.formats.disklabel import DiskLabel
from blivet.partitioning import get_next_partition_type, get_free_regions
from blivet.size import Size
from blivet.static_data import luks_data
from pykickstart.constants import AUTOPART_TYPE_LVM, AUTOPART_TYPE_LVM_THINP, AUTOPART_TYPE_BTRFS, \
    AUTOPART_TYPE_PLAIN

from pyanaconda.anaconda_loggers import get_module_logger

from pyanaconda.bootloader.execution import BootloaderExecutor
from pyanaconda.core.i18n import _
from pyanaconda.modules.common.constants.objects import DISK_INITIALIZATION
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.modules.storage.partitioning.base_partitioning import PartitioningTask
from pyanaconda.storage.utils import get_initialization_config

log = get_module_logger(__name__)

__all__ = ["NonInteractivePartitioningTask"]


class NonInteractivePartitioningTask(PartitioningTask, metaclass=ABCMeta):
    """A task for the non-interactive partitioning configuration."""

    def _run(self, storage):
        """Do the partitioning."""
        self._clear_partitions(storage)
        self._prepare_bootloader(storage)
        self._configure_partitioning(storage)
        self._setup_bootloader(storage)

    def _clear_partitions(self, storage):
        """Clear partitions.

        :param storage: an instance of Blivet
        """
        disk_init_proxy = STORAGE.get_proxy(DISK_INITIALIZATION)
        disk_label = disk_init_proxy.DefaultDiskLabel

        if disk_label and not DiskLabel.set_default_label_type(disk_label):
            log.warning("%s is not a supported disklabel type on this platform. "
                        "Using default disklabel %s instead.", disk_label,
                        DiskLabel.get_platform_label_types()[0])

        config = get_initialization_config()
        storage.clear_partitions(config)

        # Check the usable disks.
        if not any(d for d in storage.disks if not d.format.hidden and not d.protected):
            raise NoDisksError("No usable disks.")

    def _prepare_bootloader(self, storage):
        """Prepare the bootloader.

        :param storage: an instance of Blivet
        """
        BootloaderExecutor().execute(storage, dry_run=True)

    @abstractmethod
    def _configure_partitioning(self, storage):
        """Configure the partitioning.

        :param storage: an instance of Blivet
        """
        pass

    def _setup_bootloader(self, storage):
        """Set up the bootloader.

        :param storage: an instance of Blivet
        """
        storage.set_up_bootloader()

    def _get_candidate_disks(self, storage, config):
        """Return a list of disks to be used for autopart/reqpart.

        Disks must be partitioned and have a single free region large enough
        for a default-sized (500MiB) partition. They must also be in
        :attr:`DiskInitializationConfig.clear_part_disks` if it is non-empty.

        :param storage: an InstallerStorage instance
        :param config: an instance of DiskInitializationConfig
        :returns: a list of partitioned disks with at least 500MiB of free space
        """
        disks = []
        for disk in storage.partitioned:
            if not disk.format.supported or disk.protected:
                continue

            if config.clear_part_disks and \
               (disk.name not in config.clear_part_disks):
                continue

            if get_next_partition_type(disk.format.parted_disk) is None:
                # new partition can't be added to the disk -- there is no free slot
                # for a primary partition and no extended partition
                continue

            part = disk.format.first_partition
            while part:
                if not part.type & parted.PARTITION_FREESPACE:
                    part = part.nextPartition()
                    continue

                if Size(part.getLength(unit="B")) > PartitionDevice.default_size:
                    disks.append(disk)
                    break

                part = part.nextPartition()

        return disks

    def _get_luks_format_args(self, storage):
        """Get arguments for the LUKS format constructor.

        :param storage: an instance of Blivet
        :return: a dictionary of arguments
        """
        return {
            "passphrase": luks_data.encryption_passphrase,
            "min_luks_entropy": MIN_CREATE_ENTROPY,
            "luks_version": storage.default_luks_version,
         }

    def _schedule_implicit_partitions(self, storage, disks, scheme, encrypted=False):
        """Schedule creation of a lvm/btrfs member partitions for autopart.

        We create one such partition on each disk. They are not allocated until
        later (in :func:`doPartitioning`).

        :param storage: an InstallerStorage instance
        :param disks: list of partitioned disks with free space
        :param scheme: a type of the partitioning scheme
        :param encrypted: encrypt the partitions
        :return: list of newly created (unallocated) partitions
        """
        # create a separate pv or btrfs partition for each disk with free space
        devs = []

        # only schedule the partitions if either lvm or btrfs autopart was chosen
        if scheme == AUTOPART_TYPE_PLAIN:
            return devs

        for disk in disks:
            if encrypted:
                fmt_type = "luks"
                fmt_args = self._get_luks_format_args(storage)
            else:
                if scheme in (AUTOPART_TYPE_LVM, AUTOPART_TYPE_LVM_THINP):
                    fmt_type = "lvmpv"
                else:
                    fmt_type = "btrfs"
                fmt_args = {}
            part = storage.new_partition(fmt_type=fmt_type,
                                         fmt_args=fmt_args,
                                         grow=True,
                                         parents=[disk])
            storage.create_device(part)
            devs.append(part)

        return devs

    def _schedule_partitions(self, storage, disks, implicit_devices, scheme, requests,
                             encrypted=False):
        """Schedule creation of autopart/reqpart partitions.

        This only schedules the requests for actual partitions.

        :param storage: an InstallerStorage instance
        :param disks: list of partitioned disks with free space
        :param scheme: a type of the partitioning scheme
        :param requests: list of partitioning requests
        :param encrypted: encrypt the partitions
        """
        # basis for requests with required_space is the sum of the sizes of the
        # two largest free regions
        all_free = (Size(reg.getLength(unit="B")) for reg in get_free_regions(disks))
        all_free = sorted(all_free, reverse=True)
        if not all_free:
            # this should never happen since we've already filtered the disks
            # to those with at least 500MiB free
            log.error("no free space on disks %s", [d.name for d in disks])
            return

        free = all_free[0]
        if len(all_free) > 1:
            free += all_free[1]

        # The boot disk must be set at this point. See if any platform-specific
        # stage1 device we might allocate already exists on the boot disk.
        stage1_device = None
        for device in storage.devices:
            if storage.bootloader.stage1_disk not in device.disks:
                continue

            if storage.bootloader.is_valid_stage1_device(device, early=True):
                stage1_device = device
                break

        #
        # First pass is for partitions only. We'll do LVs later.
        #
        for request in requests:
            if request.lv and scheme in (AUTOPART_TYPE_LVM, AUTOPART_TYPE_LVM_THINP):
                continue

            if request.btr and scheme == AUTOPART_TYPE_BTRFS:
                continue

            if request.required_space and request.required_space > free:
                continue

            elif request.fstype in ("prepboot", "efi", "macefi", "hfs+") and \
                    (storage.bootloader.skip_bootloader or stage1_device):
                # there should never be a need for more than one of these
                # partitions, so skip them.
                log.info("skipping unneeded stage1 %s request", request.fstype)
                log.debug("%s", request)

                if request.fstype in ["efi", "macefi"] and stage1_device:
                    # Set the mountpoint for the existing EFI boot partition
                    stage1_device.format.mountpoint = "/boot/efi"

                log.debug("%s", stage1_device)
                continue
            elif request.fstype == "biosboot":
                is_gpt = (stage1_device and
                          getattr(stage1_device.format, "label_type", None) == "gpt")
                has_bios_boot = (stage1_device and
                                 any([p.format.type == "biosboot"
                                      for p in storage.partitions
                                      if p.disk == stage1_device]))
                if (storage.bootloader.skip_bootloader or
                    not (stage1_device and stage1_device.is_disk and
                         is_gpt and not has_bios_boot)):
                    # there should never be a need for more than one of these
                    # partitions, so skip them.
                    log.info("skipping unneeded stage1 %s request", request.fstype)
                    log.debug("%s", request)
                    log.debug("%s", stage1_device)
                    continue

            if request.size > all_free[0]:
                # no big enough free space for the requested partition
                raise NotEnoughFreeSpaceError(_("No big enough free space on disks for "
                                                "automatic partitioning"))

            if request.encrypted and encrypted:
                fmt_type = "luks"
                fmt_args = self._get_luks_format_args(storage)
            else:
                fmt_type = request.fstype
                fmt_args = {}

            dev = storage.new_partition(fmt_type=fmt_type,
                                        fmt_args=fmt_args,
                                        size=request.size,
                                        grow=request.grow,
                                        maxsize=request.max_size,
                                        mountpoint=request.mountpoint,
                                        parents=disks)

            # schedule the device for creation
            storage.create_device(dev)

            if request.encrypted and encrypted:
                luks_fmt = get_format(request.fstype,
                                      device=dev.path,
                                      mountpoint=request.mountpoint)
                luks_dev = LUKSDevice("luks-%s" % dev.name,
                                      fmt=luks_fmt,
                                      size=dev.size,
                                      parents=dev)
                storage.create_device(luks_dev)

            if scheme in (AUTOPART_TYPE_LVM, AUTOPART_TYPE_LVM_THINP, AUTOPART_TYPE_BTRFS):
                # doing LVM/BTRFS -- make sure the newly created partition fits in some
                # free space together with one of the implicitly requested partitions
                smallest_implicit = sorted(implicit_devices, key=lambda d: d.size)[0]
                if (request.size + smallest_implicit.size) > all_free[0]:
                    # not enough space to allocate the smallest implicit partition
                    # and the request, make the implicit partitions smaller in
                    # attempt to make space for the request
                    for implicit_req in implicit_devices:
                        implicit_req.size = FALLBACK_DEFAULT_PART_SIZE

        return implicit_devices

    def _schedule_volumes(self, storage, devs, scheme, requests, encrypted=False):
        """Schedule creation of autopart lvm/btrfs volumes.

        Schedules encryption of member devices if requested, schedules creation
        of the container (:class:`blivet.devices.LVMVolumeGroupDevice` or
        :class:`blivet.devices.BTRFSVolumeDevice`) then schedules creation of the
        autopart volume requests.

        If an appropriate bootloader stage1 device exists on the boot drive, any
        autopart request to create another one will be skipped/discarded.

        :param storage: an instance of Blivet
        :param devs: a list of member partitions
        :param scheme: a type of the partitioning scheme
        :param requests: list of partitioning requests to operate on
        :param encrypted: encrypt the partitions
        """
        if not devs:
            return

        if scheme in (AUTOPART_TYPE_LVM, AUTOPART_TYPE_LVM_THINP):
            new_container = storage.new_vg
            new_volume = storage.new_lv
            format_name = "lvmpv"
        else:
            new_container = storage.new_btrfs
            new_volume = storage.new_btrfs
            format_name = "btrfs"

        if encrypted:
            pvs = []
            for dev in devs:
                pv = LUKSDevice("luks-%s" % dev.name,
                                fmt=get_format(format_name, device=dev.path),
                                size=dev.size,
                                parents=dev)
                pvs.append(pv)
                storage.create_device(pv)
        else:
            pvs = devs

        # create a vg containing all of the autopart pvs
        container = new_container(parents=pvs)
        storage.create_device(container)

        #
        # Convert partitioning requests into Device instances and schedule them for creation.
        #
        # Second pass, for LVs only.
        pool = None
        for request in requests:
            btr = bool(scheme == AUTOPART_TYPE_BTRFS and request.btr)
            lv = bool(scheme in (AUTOPART_TYPE_LVM, AUTOPART_TYPE_LVM_THINP) and request.lv)
            thinlv = bool(scheme == AUTOPART_TYPE_LVM_THINP and request.lv and request.thin)

            if thinlv and pool is None:
                # create a single thin pool in the vg
                pool = storage.new_lv(parents=[container], thin_pool=True, grow=True)
                storage.create_device(pool)

                # make sure VG reserves space for the pool to grow if needed
                container.thpool_reserve = DEFAULT_THPOOL_RESERVE

            if not btr and not lv and not thinlv:
                continue

            # required space isn't relevant on btrfs
            if (lv or thinlv) and \
               request.required_space and request.required_space > container.size:
                continue

            if request.fstype is None:
                if btr:
                    # btrfs volumes can only contain btrfs filesystems
                    request.fstype = "btrfs"
                else:
                    request.fstype = storage.default_fstype

            kwargs = {"mountpoint": request.mountpoint,
                      "fmt_type": request.fstype}
            if lv or thinlv:
                if thinlv:
                    parents = [pool]
                else:
                    parents = [container]

                kwargs.update({"parents": parents,
                               "grow": request.grow,
                               "maxsize": request.max_size,
                               "size": request.size,
                               "thin_volume": thinlv})
            else:
                kwargs.update({"parents": [container],
                               "size": request.size,
                               "subvol": True})

            dev = new_volume(**kwargs)

            # schedule the device for creation
            storage.create_device(dev)
