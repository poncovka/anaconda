#
# DBus structures.
#
# Copyright (C) 2018  Red Hat, Inc.  All rights reserved.
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
from pyanaconda.dbus.typing import get_variant, Structure
from typing import TypeVar, Generic

# Data type of the DBus structure.
T = TypeVar('T')


class DBusField(object):
    """Description of a field in a DBus structure."""

    def __init__(self, type_hint):
        """Create a description of the field.

        :param type_hint: a type hint
        """
        self._type_hint = type_hint

    @property
    def type_hint(self):
        """Type hint of the field.

        :return: a type hint
        """
        return self._type_hint


class DBusStructure(Generic[T]):
    """Description of a DBus structure.

     The structure describes data object of type T. Each field
     of the structure should be specified in the dictionary of
     fields as an instance of DBusField.

     Call from_data to get a DBus structure from the given data
     object. Call to_data to get a data object from the given
     data mapping.
     """

    fields = {}

    @classmethod
    def from_data(cls, obj: T) -> Structure:
        """Return a DBus structure.

        The returned DBus structure is ready to be send on DBus.

        :param obj: a data object
        :return: a DBus structure
        """
        structure = {}

        for name, field in cls.fields:
            type_hint = field.type_hint
            value = getattr(obj, cls._get_attribute_name(name))
            structure[name] = get_variant(type_hint, value)

        return structure

    @classmethod
    def to_data(cls, mapping, obj: T=None) -> T:
        """Return a data object.

        The given mapping is usually a value returned by DBus.

        :param mapping: a mapping of values
        :param obj: a data object or None
        :return: a data object
        """
        cls._check_mapping(mapping)

        if obj is None:
            obj = T()

        for name, value in mapping:
            setattr(obj, cls._get_attribute_name(name), value)

        return obj

    @staticmethod
    def _get_attribute_name(name):
        """Return name of an attribute.

        :param name: a field name
        :return: an attribute name
        """
        return name.replace('-', '_')

    @classmethod
    def _check_mapping(cls, mapping):
        """Check if a given mapping has the expected structure.

        :param mapping: a dictionary
        """
        unknown = mapping.keys() - cls.fields.keys()

        if unknown:
            raise AttributeError("Unknown fields: " + ", ".join(unknown))
