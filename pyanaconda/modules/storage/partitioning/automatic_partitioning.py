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
from blivet.devicelibs.crypto import MIN_CREATE_ENTROPY
from blivet.errors import PartitioningError, NoDisksError, NotEnoughFreeSpaceError
from blivet.partitioning import do_partitioning, grow_lvm
from blivet.static_data import luks_data

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.i18n import _
from pyanaconda.modules.common.constants.objects import AUTO_PARTITIONING
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.modules.storage.partitioning.noninteractive_partitioning import \
    NonInteractivePartitioningTask
from pyanaconda.platform import platform
from pyanaconda.storage.checker import storage_checker
from pyanaconda.storage.partitioning import get_full_partitioning_requests, \
    get_default_partitioning
from pyanaconda.storage.utils import get_pbkdf_args, get_available_disk_space, suggest_swap_size

log = get_module_logger(__name__)

__all__ = ["AutomaticPartitioningTask"]


class AutomaticPartitioningTask(NonInteractivePartitioningTask):
    """A task for the automatic partitioning configuration."""

    def __init__(self, storage, scheme):
        """Create a task.

        :param storage: an instance of Blivet
        :param scheme: a type of the partitioning scheme
        """
        super().__init__(storage)
        self._scheme = scheme

    def _configure_partitioning(self, storage):
        """Configure the partitioning.

        :param storage: an instance of Blivet
        """
        log.debug("Executing the automatic partitioning.")

        # Create the auto partitioning proxy.
        auto_part_proxy = STORAGE.get_proxy(AUTO_PARTITIONING)

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

        requests = self._get_autopart_requests(storage)
        self._do_autopart(storage, self._scheme, requests)

        report = storage_checker.check(storage)
        report.log(log)

        if report.failure:
            raise PartitioningError("autopart failed: \n" + "\n".join(report.all_errors))

    def _do_autopart(self, storage, scheme, requests, min_luks_entropy=MIN_CREATE_ENTROPY):
        """Perform automatic partitioning.

        :param storage: an instance of Blivet
        :param scheme: a type of the partitioning scheme
        :param requests: list of partitioning requests
        :param int min_luks_entropy: minimum entropy in bits required for luks format creation
        """
        log.debug("encrypted_autopart: %s", storage.encrypted_autopart)
        log.debug("scheme: %s", scheme)
        log.debug("clear_part_type: %s", storage.config.clear_part_type)
        log.debug("clear_part_disks: %s", storage.config.clear_part_disks)
        log.debug("requests:\n%s", "".join([str(p) for p in requests]))
        log.debug("storage.disks: %s", [d.name for d in storage.disks])
        log.debug("storage.partitioned: %s", [d.name for d in storage.partitioned if d.format.supported])
        log.debug("all names: %s", [d.name for d in storage.devices])
        log.debug("boot disk: %s", getattr(storage.bootloader.stage1_disk, "name", None))

        if not any(d.format.supported for d in storage.partitioned):
            raise NoDisksError(_("No usable disks selected"))

        if min_luks_entropy is not None:
            luks_data.min_entropy = min_luks_entropy

        disks = self._get_candidate_disks(storage)
        devs = self._schedule_implicit_partitions(storage, disks, scheme)
        log.debug("candidate disks: %s", disks)
        log.debug("devs: %s", devs)

        if not disks:
            raise NotEnoughFreeSpaceError(_("Not enough free space on disks for "
                                            "automatic partitioning"))

        devs = self._schedule_partitions(storage, disks, devs, scheme, requests)

        # run the autopart function to allocate and grow partitions
        do_partitioning(storage)

        self._schedule_volumes(storage, devs, scheme, requests)

        # grow LVs
        grow_lvm(storage)

        storage.set_up_bootloader()

        # only newly added swaps should appear in the fstab
        new_swaps = (dev for dev in storage.swaps if not dev.format.exists)
        storage.set_fstab_swaps(new_swaps)

    def _get_autopart_requests(self, storage):
        """Get the partitioning requests for autopart.

        :param storage: blivet.Blivet instance
        :return: a list of full partitioning specs
        """
        requests = get_full_partitioning_requests(storage, platform, get_default_partitioning())

        # Update the size of swap.
        for request in requests:
            if request.fstype == "swap":
                disk_space = get_available_disk_space(storage)
                request.size = suggest_swap_size(disk_space=disk_space)
                break

        return requests
