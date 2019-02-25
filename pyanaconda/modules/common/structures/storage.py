#
# DBus structures for the storage data.
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
    """Device data."""

    def __init__(self):
        self._name = ""
        self._model = ""
        self._size = ""
        self._is_disk = False
        self._attrs = {}

    @property
    def name(self) -> Str:
        """A name of the device

        :return: a device name
        """
        return self._name

    @name.setter
    def name(self, name: Str):
        self._name = name

    @property
    def model(self) -> Str:
        """A model of the device.

        :return: a model name
        """
        return self._model

    @model.setter
    def model(self, model: Str):
        self._model = model

    @property
    def size(self) -> Str:
        """A size of the device

        :return: a size
        """
        return self._size

    @size.setter
    def size(self, size: Str):
        self._size = size

    @property
    def is_disk(self) -> Bool:
        """Is this device a disk?

        :return: True or False
        """
        return self._is_disk

    @is_disk.setter
    def is_disk(self, is_disk: Bool):
        self._is_disk = is_disk

    @property
    def attrs(self) -> Dict[Str, Str]:
        """Additional attributes.

        :return: a dictionary of attributes
        """
        return self._attrs

    @attrs.setter
    def attrs(self, attrs: Dict[Str, Str]):
        self._attrs = attrs

    def add_attr(self, name, value):
        """Add an additional attribute.

        :param name: a name of the attribute
        :param value: a value of the attribute
        """
        self._attrs[name] = str(value)
