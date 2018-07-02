#
# DBus structures for the security module.
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
from pyanaconda.dbus.structure import DBusStructure, DBusField
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import

__all__ = ["RealmData", "RealmStructure"]


class RealmData(object):
    """Realm data."""

    def __init__(self):
        self._name = ""
        self._discover_options = list()
        self._join_options = list()

    @property
    def name(self):
        """Specification of the realm to join."

        For example: 'domain.example.com'

        :return: a name of the realm
        """
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def discover_options(self):
        """Options for the discovery command.

        For example: ['--client-software=sssd']

        :return: a list of options
        """
        return self._discover_options

    @discover_options.setter
    def discover_options(self, options):
        self._discover_options = options

    @property
    def join_options(self):
        """Options for the join command.

        For example: ['--no-password', '--client-software=sssd']

        :return: a list of options
        """
        return self._join_options

    @join_options.setter
    def join_options(self, options):
        self._join_options = options


class RealmStructure(DBusStructure[RealmData]):
    """DBus structure of the realm data."""

    fields = {
        "name": DBusField(Str),
        "discover-options": DBusField(List[Str]),
        "join-options": DBusField(List[Str])
    }

    @classmethod
    def create_data(cls):
        return RealmData()
