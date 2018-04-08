#
# Low-level DBus libraries.
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
import gi
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")

from gi.repository.Gio import (
    BusType,
    DBusNodeInfo,
    bus_watch_name_on_connection,
    bus_unwatch_name,
    bus_get_sync,
    DBusConnection,
    DBusConnectionFlags,
    DBusError
)

from gi.repository.GLib import (
    Variant,
    VariantType,
    Error as GLibError

)

__all__ = [
    "Variant",
    "BusType",
    "DBusNodeInfo",
    "bus_watch_name_on_connection",
    "bus_unwatch_name",
    "get_connection_by_type",
    "get_connection_by_address",
    "DBusError",
    "GLibError"
]


def get_connection_by_type(bus_type):
    """Set up a DBus connection by type.

    :param bus_type: an instance of Gio.BusType
    :return: an instance of Gio.DBusConnection
    """
    return bus_get_sync(bus_type, None)


def get_connection_by_address(bus_address):
    """Set up a DBus connection by address.

    :param bus_address: a bus address
    :return: an instance of Gio.DBusConnection
    """
    return DBusConnection.new_for_address_sync(
        bus_address,
        DBusConnectionFlags.AUTHENTICATION_CLIENT |
        DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,
        None
    )
