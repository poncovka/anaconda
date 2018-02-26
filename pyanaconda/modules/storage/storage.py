#
# Kickstart module for storage management.
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
from pyanaconda.dbus import DBus
from pyanaconda.dbus.constants import MODULE_STORAGE_PATH, MODULE_STORAGE_NAME, \
    STORAGE_AUTOPART_PATH, STORAGE_BOOTLOADER_PATH
from pyanaconda.modules.base import KickstartModule

from pyanaconda.modules.storage.autopart import Autopartitioning
from pyanaconda.modules.storage.bootloader import BootloaderModule
from pyanaconda.modules.storage.bootloader_interface import BootloaderInterface
from pyanaconda.modules.storage.fcoe import FCOEModule
from pyanaconda.modules.storage.iscsi import ISCIModule
from pyanaconda.modules.storage.kickstart import StorageKickstartSpecification
from pyanaconda.modules.storage.mount import MountPointAssignment
from pyanaconda.modules.storage.partitioning import Partitioning
from pyanaconda.modules.storage.selection import DiskSelectionModule
from pyanaconda.modules.storage.snapshot import SnapshotModule
from pyanaconda.modules.storage.storage_interface import StorageInterface
from pyanaconda.modules.storage.zfcp import ZFCPModule

from pyanaconda import anaconda_logging
from pyanaconda.modules.storage.zfcp_interface import ZFCPInterface

log = anaconda_logging.get_dbus_module_logger(__name__)


class StorageModule(KickstartModule):
    """The Storage module."""

    def __init__(self):
        super().__init__()
        self._submodules = [
            BootloaderModule(),
            DiskSelectionModule(),
            Autopartitioning(),
            MountPointAssignment(),

        ]

        self._add_submodule()
        self._add_submodule(ZFCPModule())

        self._autopart = self.add_submodule(Autopartitioning)
        self._mount = self.add_submodule()
        self._part = self.add_submodule(Partitioning)
        self._snapshot = self.add_submodule(SnapshotModule)
        self._fcoe = self.add_submodule(FCOEModule)
        self._isci = self.add_submodule(ISCIModule)
        self._zfcp = self.add_submodule(ZFCPModule)

    def publish(self):
        """Publish the module."""
        DBus.publish_object(StorageInterface(self),
                            MODULE_STORAGE_PATH)

        for submodule in self._submodules:
            submodule.publish()

        DBus.register_service(MODULE_STORAGE_NAME)

    @property
    def kickstart_specification(self):
        """Return the kickstart specification."""
        return StorageKickstartSpecification

    def process_kickstart(self, data):
        log.debug("Processing kickstart data...")
        for submodule in self._submodules:
            submodule.process_kickstart(data)

    def generate_kickstart(self):
        log.debug("Generating kickstart data...")
        data = self.get_kickstart_data()

        for submodule in self._submodules:
            submodule.generate_kickstart(data)

        return str(data)
