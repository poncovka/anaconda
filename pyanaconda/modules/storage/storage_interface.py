#
# DBus interface for the storage.
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
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.modules.common.base import KickstartModuleInterface
from pyanaconda.dbus.interface import dbus_interface
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.dbus.structure import get_structure


@dbus_interface(STORAGE.interface_name)
class StorageInterface(KickstartModuleInterface):
    """DBus interface for Storage module."""

    def ResetWithTask(self) -> ObjPath:
        """Reset the storage model.

        :return: a path to a task
        """
        return self.implementation.reset_with_task()

    def GetDeviceData(self, name) -> Structure:
        """Get the device data.

        :param name: a device name
        :return: a structure with device data
        """
        return get_structure(self.implementation.get_device_data(name))

    def GetAvailableDisks(self) -> List[Str]:
        """Get the available disks.

        :return: a list of device names
        """
        return self.implementation.get_available_disks()

    def GetCapacity(self, names) -> Str:
        """Get total capacity of disks.

        :param names: names of disks
        :return: a total capacity
        """
        return str(self.implementation.get_capacity(names))

    def GetFreeSpace(self, names) -> Str:
        """Get total free space on disks.

        :param names: names of disks
        :return: a total size
        """
        return str(self.implementation.get_free_space(names))

    def ApplyPartitioning(self, partitioning: ObjPath):
        """Apply the partitioning.

        :param partitioning: a path to a partitioning
        """
        self.implementation.apply_partitioning(partitioning)

    def GetRootDevice(self):
        """Get the root device.

        :return: a name of the root device
        """
        return self.implementation.get_root_device()
