#
# DBus structures for the storage.
#
# Copyright (C) 2019  Red Hat, Inc.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from pyanaconda.dbus.structure import dbus_structure
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import

__all__ = ["DeviceData"]


@dbus_structure
class DeviceData(object):
    """Data representation of a device."""

    def __init__(self):
        self._name = ""

    @property
    def name(self) -> Str:
        """Name of the device.

        :return: a name of the device
        """
        return self._name

    @name.setter
    def name(self, name: Str):
        self._name = name
