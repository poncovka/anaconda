#
# Kickstart module for the storage.
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
from blivet import arch

from pyanaconda.core.signal import Signal
from pyanaconda.dbus import DBus
from pyanaconda.modules.common.base import KickstartModule
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.modules.storage.bootloader import BootloaderModule
from pyanaconda.modules.storage.dasd import DASDModule
from pyanaconda.modules.storage.disk_initialization import DiskInitializationModule
from pyanaconda.modules.storage.disk_selection import DiskSelectionModule
from pyanaconda.modules.storage.fcoe import FCOEModule
from pyanaconda.modules.storage.kickstart import StorageKickstartSpecification
from pyanaconda.modules.storage.partitioning import AutoPartitioningModule, ManualPartitioningModule
from pyanaconda.modules.storage.reset import StorageResetTask
from pyanaconda.modules.storage.storage_interface import StorageInterface
from pyanaconda.modules.storage.zfcp import ZFCPModule

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.storage.initialization import enable_installer_mode, create_storage

log = get_module_logger(__name__)


class StorageModule(KickstartModule):
    """The Storage module."""

    def __init__(self):
        super().__init__()
        # Initialize Blivet.
        enable_installer_mode()

        # An instance of Blivet.
        self._storage = create_storage()
        self.storage_changed = Signal()

        # Initialize modules.
        self._modules = []

        self._disk_init_module = DiskInitializationModule()
        self._add_module(self._disk_init_module)

        self._disk_selection_module = DiskSelectionModule()
        self._add_module(self._disk_selection_module)

        self._bootloader_module = BootloaderModule()
        self._add_module(self._bootloader_module)

        self._auto_part_module = AutoPartitioningModule()
        self._add_module(self._auto_part_module)

        self._manual_part_module = ManualPartitioningModule()
        self._add_module(self._manual_part_module)

        self._fcoe_module = FCOEModule()
        self._add_module(self._fcoe_module)

        self._dasd_module = None
        self._zfcp_module = None

        if arch.is_s390():
            self._dasd_module = DASDModule()
            self._add_module(self._dasd_module)

            self._zfcp_module = ZFCPModule()
            self._add_module(self._zfcp_module)

    def _add_module(self, storage_module):
        """Add a base kickstart module."""
        self._modules.append(storage_module)

    def publish(self):
        """Publish the module."""
        for kickstart_module in self._modules:
            kickstart_module.publish()

        DBus.publish_object(STORAGE.object_path, StorageInterface(self))
        DBus.register_service(STORAGE.service_name)

    @property
    def kickstart_specification(self):
        """Return the kickstart specification."""
        return StorageKickstartSpecification

    def process_kickstart(self, data):
        """Process the kickstart data."""
        log.debug("Processing kickstart data...")

        # Process the kickstart data in modules.
        for kickstart_module in self._modules:
            kickstart_module.process_kickstart(data)

        # Set the default filesystem type.
        if data.autopart.autopart and data.autopart.fstype:
            self._storage.set_default_fstype(data.autopart.fstype)

    def generate_temporary_kickstart(self):
        """Return the temporary kickstart string."""
        return self.generate_kickstart(skip_unsupported=True)

    def generate_kickstart(self, skip_unsupported=False):  # pylint: disable=arguments-differ
        """Return the kickstart string."""
        log.debug("Generating kickstart data...")
        data = self.get_kickstart_handler()

        for kickstart_module in self._modules:
            kickstart_module.setup_kickstart(data)

        return str(data)

    @property
    def storage(self):
        """The storage model.

        :return: an instance of Blivet
        """
        return self._storage

    def set_storage(self, storage):
        self._storage = storage
        self.storage_changed.emit()
        log.debug("The storage model has changed.")

    def reset_with_task(self):
        """Reset the storage model.

        The copy of the current model will be reset. It the reset
        succeeds, the models will be switched.

        :return: a DBus path to a task
        """
        storage = self._storage.copy()
        task = StorageResetTask(storage)

        # FIXME: Don't set the storage if the task has failed.
        task.stopped_signal.connect(lambda: self.set_storage(storage))

        path = self.publish_task(STORAGE.namespace, task)
        return path
