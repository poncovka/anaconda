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
from pyanaconda.modules.common.constants.objects import AUTO_PARTITIONING, MANUAL_PARTITIONING, \
    CUSTOM_PARTITIONING, BLIVET_PARTITIONING, INTERACTIVE_PARTITIONING, SHRUNKEN_PARTITIONING
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.modules.common.structures.requirement import Requirement
from pyanaconda.modules.storage.bootloader import BootloaderModule
from pyanaconda.modules.storage.checker import StorageCheckerModule
from pyanaconda.modules.storage.dasd import DASDModule
from pyanaconda.modules.storage.devicetree import DeviceTreeModule
from pyanaconda.modules.storage.disk_initialization import DiskInitializationModule
from pyanaconda.modules.storage.disk_selection import DiskSelectionModule
from pyanaconda.modules.storage.fcoe import FCOEModule
from pyanaconda.modules.storage.installation import MountFilesystemsTask, ActivateFilesystemsTask, \
    WriteConfigurationTask
from pyanaconda.modules.storage.iscsi import ISCSIModule
from pyanaconda.modules.storage.kickstart import StorageKickstartSpecification
from pyanaconda.modules.storage.nvdimm import NVDIMMModule
from pyanaconda.modules.storage.partitioning import AutoPartitioningModule, \
    ManualPartitioningModule, CustomPartitioningModule, BlivetPartitioningModule, \
    InteractivePartitioningModule, ShrunkenPartitioningModule
from pyanaconda.modules.storage.partitioning.validate import StorageValidateTask
from pyanaconda.modules.storage.reset import StorageResetTask
from pyanaconda.modules.storage.snapshot import SnapshotModule
from pyanaconda.modules.storage.storage_interface import StorageInterface
from pyanaconda.modules.storage.teardown import UnmountFilesystemsTask, TeardownDiskImagesTask
from pyanaconda.modules.storage.zfcp import ZFCPModule
from pyanaconda.storage.initialization import enable_installer_mode, create_storage

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)


class StorageModule(KickstartModule):
    """The Storage module."""

    def __init__(self):
        super().__init__()
        # Initialize Blivet.
        enable_installer_mode()

        # The storage model.
        self._storage = None
        self.storage_changed = Signal()

        # Initialize modules.
        self._modules = []

        self._storage_checker_module = StorageCheckerModule()
        self._add_module(self._storage_checker_module)

        self._device_tree_module = DeviceTreeModule()
        self._add_module(self._device_tree_module)

        self._disk_init_module = DiskInitializationModule()
        self._add_module(self._disk_init_module)

        self._disk_selection_module = DiskSelectionModule()
        self._add_module(self._disk_selection_module)

        self._snapshot_module = SnapshotModule()
        self._add_module(self._snapshot_module)

        self._bootloader_module = BootloaderModule()
        self._add_module(self._bootloader_module)

        self._fcoe_module = FCOEModule()
        self._add_module(self._fcoe_module)

        self._iscsi_module = ISCSIModule()
        self._add_module(self._iscsi_module)

        self._nvdimm_module = NVDIMMModule()
        self._add_module(self._nvdimm_module)

        self._dasd_module = None
        self._zfcp_module = None

        if arch.is_s390():
            self._dasd_module = DASDModule()
            self._add_module(self._dasd_module)

            self._zfcp_module = ZFCPModule()
            self._add_module(self._zfcp_module)

        # Initialize the partitioning modules.
        self._partitioning_modules = {}

        self._auto_part_module = AutoPartitioningModule()
        self._add_partitioning_module(AUTO_PARTITIONING.object_path, self._auto_part_module)

        self._manual_part_module = ManualPartitioningModule()
        self._add_partitioning_module(MANUAL_PARTITIONING.object_path, self._manual_part_module)

        self._custom_part_module = CustomPartitioningModule()
        self._add_partitioning_module(CUSTOM_PARTITIONING.object_path, self._custom_part_module)

        self._shrunken_part_module = ShrunkenPartitioningModule()
        self._add_partitioning_module(SHRUNKEN_PARTITIONING.object_path, self._shrunken_part_module)

        self._interactive_part_module = InteractivePartitioningModule()
        self._add_partitioning_module(INTERACTIVE_PARTITIONING.object_path,self._interactive_part_module)

        self._blivet_part_module = BlivetPartitioningModule()
        self._add_partitioning_module(BLIVET_PARTITIONING.object_path, self._blivet_part_module)

        # Connect modules to signals.
        self.storage_changed.connect(
            self._device_tree_module.on_storage_reset
        )
        self.storage_changed.connect(
            self._disk_init_module.on_storage_reset
        )
        self.storage_changed.connect(
            self._disk_selection_module.on_storage_reset
        )
        self.storage_changed.connect(
            self._snapshot_module.on_storage_reset
        )
        self.storage_changed.connect(
            self._bootloader_module.on_storage_reset
        )
        self._disk_selection_module.protected_devices_changed.connect(
            self.on_protected_devices_changed
        )

    def _add_module(self, storage_module):
        """Add a base kickstart module."""
        self._modules.append(storage_module)

    def _add_partitioning_module(self, object_path, partitioning_module):
        """Add a partitioning module."""
        # Add the module.
        self._modules.append(partitioning_module)
        self._partitioning_modules[object_path] = partitioning_module

        # Update the module.
        partitioning_module.on_storage_reset(
            self._storage
        )
        partitioning_module.on_selected_disks_changed(
            self._disk_selection_module.selected_disks
        )

        # Connect the callbacks to signals.
        self.storage_changed.connect(
            partitioning_module.on_storage_reset
        )
        self._disk_selection_module.selected_disks_changed.connect(
            partitioning_module.on_selected_disks_changed
        )

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
            self.storage.set_default_fstype(data.autopart.fstype)

    def generate_kickstart(self):
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
        if not self._storage:
            self.set_storage(create_storage())

        return self._storage

    def set_storage(self, storage):
        """Set the storage model."""
        self._storage = storage
        self.storage_changed.emit(storage)
        log.debug("The storage model has changed.")

    def on_protected_devices_changed(self, protected_devices):
        """Update the protected devices in the storage model."""
        if not self._storage:
            return

        self.storage.protect_devices(protected_devices)

    def reset_with_task(self):
        """Reset the storage model.

        We will reset a copy of the current storage model
        and switch the models if the reset is successful.

        :return: a DBus path to a task
        """
        # Copy the storage.
        storage = self.storage.copy()

        # Set up the storage.
        storage.ignored_disks = self._disk_selection_module.ignored_disks
        storage.exclusive_disks = self._disk_selection_module.exclusive_disks
        storage.protected_devices = self._disk_selection_module.protected_devices
        storage.disk_images = self._disk_selection_module.disk_images

        # Create the task.
        task = StorageResetTask(storage)
        task.succeeded_signal.connect(lambda: self.set_storage(storage))

        # Publish the task.
        path = self.publish_task(STORAGE.namespace, task)
        return path

    def apply_partitioning(self, object_path):
        """Apply a partitioning.

        :param object_path: an object path of a partitioning module
        :raise: InvalidStorageError of the partitioning is not valid
        """
        # Get the partitioning module.
        module = self._partitioning_modules.get(object_path)

        if not module:
            raise ValueError("Unknown partitioning {}.".format(object_path))

        # Validate the partitioning.
        storage = module.storage
        task = StorageValidateTask(storage)
        task.run()

        # Apply the partitioning.
        self.set_storage(storage.copy())
        log.debug("Applied the partitioning from %s.", object_path)

    def collect_requirements(self):
        """Return installation requirements for this module.

        :return: a list of requirements
        """
        requirements = []

        # Add the storage requirements.
        for name in self.storage.packages:
            requirements.append(Requirement.for_package(
                name, reason="Required to manage storage devices."
            ))

        # Add other requirements, for example for bootloader.
        for kickstart_module in self._modules:
            requirements.extend(kickstart_module.collect_requirements())

        return requirements

    def install_with_tasks(self):
        """Returns installation tasks of this module.

        FIXME: This is a simplified version of the storage installation.

        :returns: list of object paths of installation tasks
        """
        storage = self.storage

        tasks = [
            ActivateFilesystemsTask(storage),
            MountFilesystemsTask(storage),
            WriteConfigurationTask(storage)
        ]

        paths = [
            self.publish_task(STORAGE.namespace, task) for task in tasks
        ]

        return paths

    def teardown_with_tasks(self):
        """Returns teardown tasks for this module.

        :return: a list of DBus paths of the installation tasks
        """
        storage = self.storage

        tasks = [
            UnmountFilesystemsTask(storage),
            TeardownDiskImagesTask(storage)
        ]

        paths = [
            self.publish_task(STORAGE.namespace, task) for task in tasks
        ]

        return paths
