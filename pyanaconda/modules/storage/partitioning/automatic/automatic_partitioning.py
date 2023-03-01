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
from blivet.partitioning import do_partitioning, grow_lvm
from blivet.static_data import luks_data

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.modules.common.structures.partitioning import PartitioningRequest
from pyanaconda.modules.storage.partitioning.automatic.noninteractive_partitioning import \
    NonInteractivePartitioningTask
from pyanaconda.modules.storage.partitioning.automatic.utils import get_candidate_disks, \
    schedule_implicit_partitions, schedule_volumes, schedule_partitions, get_pbkdf_args, \
    get_default_partitioning, get_part_spec, get_disks_for_implicit_partitions
from pyanaconda.core.storage import suggest_swap_size

log = get_module_logger(__name__)

__all__ = ["AutomaticPartitioningTask"]


class AutomaticPartitioningTask(NonInteractivePartitioningTask):
    """A task for the automatic partitioning configuration."""

    def __init__(self, storage, request: PartitioningRequest):
        """Create a task.

        :param storage: an instance of Blivet
        :param request: an instance of PartitioningRequest
        """
        super().__init__(storage)
        self._request = request

    def _get_initialization_config(self):
        """Get the initialization config.

        FIXME: This is a temporary method.
        """
        config = super()._get_initialization_config()
        # If autopart is selected we want to remove whatever has been created/scheduled
        # to make room for autopart. If custom is selected, we want to leave alone any
        # storage layout the user may have set up before now.
        config.clear_non_existent = True
        return config

    def _configure_partitioning(self, storage):
        """Configure the partitioning.

        :param storage: an instance of Blivet
        """
        log.debug("Executing the automatic partitioning...")

        # Log the current state of the storage.
        log.debug("Storage disks: %s", [
            d.name for d in storage.disks
        ])
        log.debug("Storage partitioned: %s", [
            d.name for d in storage.partitioned
            if d.format.supported
        ])
        log.debug("Storage devices: %s", [
            d.name for d in storage.devices
        ])

        # Get the partitioning scheme.
        scheme = self._request.partitioning_scheme
        log.debug("Scheme: %s", scheme)

        # Set the filesystem type.
        fstype = self._request.file_system_type

        if fstype:
            storage.set_default_fstype(fstype)

        # Get LUKS format args.
        luks_format_args = self._get_luks_format_args(self._storage, self._request)

        # Set the default pbkdf args.
        pbkdf_args = luks_format_args.get('pbkdf_args', None)

        if pbkdf_args and not luks_data.pbkdf_args:
            luks_data.pbkdf_args = pbkdf_args

        # Get the partitioning specs.
        specs = self._get_partitioning(storage, scheme, self._request)
        log.debug("Requests:\n%s", "".join([str(p) for p in specs]))

        # Get the encryption configuration.
        encrypted = self._request.encrypted
        passphrase = self._request.passphrase
        log.debug("Encrypted: %s", self._request.encrypted)

        # Get the boot disk.
        boot_disk = storage.bootloader.stage1_disk
        log.debug("Boot disk: %s", getattr(boot_disk, "name", None))

        # Collect the candidate disks.
        disks = get_candidate_disks(storage)
        log.debug("Candidate disks: %s", [
            d.name for d in disks
        ])

        # Schedule implicit partitions.
        implicit_disks = get_disks_for_implicit_partitions(
            scheme=scheme,
            requests=specs,
            disks=disks,
        )

        implicit_partitions = schedule_implicit_partitions(
            scheme=scheme,
            storage=storage,
            disks=implicit_disks,
            encrypted=encrypted,
            luks_args=luks_format_args,
        )

        # Schedule requested partitions.
        schedule_partitions(
            scheme=scheme,
            requests=specs,
            storage=storage,
            disks=disks,
            implicit_devices=implicit_partitions,
            encrypted=encrypted,
            luks_fmt_args=luks_format_args
        )

        # Allocate and grow partitions.
        do_partitioning(
            storage=storage,
            boot_disk=boot_disk
        )

        # Schedule requested volumes.
        schedule_volumes(
            scheme=scheme,
            requests=specs,
            storage=storage,
            devices=implicit_partitions,
            encrypted=encrypted,
            passphrase=passphrase,
        )

        # Grow logical volumes.
        grow_lvm(storage)

        # Update fstab. Only newly added swaps should appear there.
        new_swaps = (dev for dev in storage.swaps if not dev.format.exists)
        storage.set_fstab_swaps(new_swaps)

    @staticmethod
    def _get_luks_format_args(storage, request):
        """Arguments for the LUKS format constructor.

        :param storage: blivet.Blivet instance
        :param request: a partitioning request
        :return: a dictionary of arguments
        """
        if not request.encrypted:
            return {}

        luks_version = request.luks_version or storage.default_luks_version
        escrow_cert = storage.get_escrow_certificate(request.escrow_certificate)

        pbkdf_args = get_pbkdf_args(
            luks_version=luks_version,
            pbkdf_type=request.pbkdf or None,
            max_memory_kb=request.pbkdf_memory,
            iterations=request.pbkdf_iterations,
            time_ms=request.pbkdf_time
        )

        return {
            "passphrase": request.passphrase,
            "cipher": request.cipher,
            "luks_version": luks_version,
            "pbkdf_args": pbkdf_args,
            "escrow_cert": escrow_cert,
            "add_backup_passphrase": request.backup_passphrase_enabled,
        }

    @staticmethod
    def _get_partitioning(storage, scheme, request: PartitioningRequest):
        """Get the partitioning requests for autopart.

        :param storage: blivet.Blivet instance
        :param scheme: a type of the partitioning scheme
        :param request: partitioning parameters
        :return: a list of full partitioning specs
        """
        specs = []
        swap = None

        # Create partitioning specs based on the default configuration.
        for spec in get_default_partitioning():
            # Skip mount points excluded from the chosen scheme.
            if spec.schemes and scheme not in spec.schemes:
                continue

            # Skip excluded mount points.
            if (spec.mountpoint or spec.fstype) in request.excluded_mount_points:
                continue

            # Detect swap.
            if spec.fstype == "swap":
                swap = spec

            specs.append(spec)

        # Add a swap if hibernation was requested in kickstart.
        if request.hibernation and swap is None:
            swap = get_part_spec({"name": "swap"})
            specs.append(swap)

        # Configure specs.
        for spec in specs:
            # Set the default filesystem type.
            if spec.fstype is None:
                spec.fstype = storage.get_fstype(spec.mountpoint)

            # Update the size of swap.
            if spec.fstype == "swap":
                disk_space = storage.get_disk_free_space()
                swap.size = suggest_swap_size(hibernation=request.hibernation,
                                              disk_space=disk_space)

        return specs
