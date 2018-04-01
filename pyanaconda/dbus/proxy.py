#
# Proxy of remote DBus objects.
#
# Copyright (C) 2017  Red Hat, Inc.  All rights reserved.
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
from pyanaconda.dbus.constants import DBUS_FLAG_NONE


class DBusObjectAccess(object):
    """Provider of an access to a remote DBus object."""

    def __init__(self, message_bus, service_name, object_path):
        self._message_bus = message_bus
        self._service_name = service_name
        self._object_path = object_path

    def _signal_subscribe(self, interface_name, signal_name, callback, *user_data):
        """Subscribe to a signal.s

        :param interface_name:
        :param signal_name:
        :param callback:
        :param user_data:
        :return:
        """
        subscription_id = self._message_bus.connection.signal_subscribe(
            self._service_name,
            interface_name,
            signal_name,
            self._object_path,
            None,
            DBUS_FLAG_NONE,
            callback,
            *user_data)

        return subscription_id

    def _signal_unsubscribe(self, subscription_id):
        """Unsubscribe from a signal.

        :param subscription_id:
        :return:
        """
        self._message_bus.connection.signal_unsubscribe(subscription_id)

    def get_object_member(self, name):
        return None

    def set_object_member(self, name, value):
        pass


class DBusObjectProxy(object):
    """Proxy of a remote DBus object."""

    # Explicitly declare data members here.
    __slots__ = ["__dbus__", "__weakref__"]

    def __init__(self, message_bus, service_name, object_path, backend=DBusObjectAccess):
        """Create the proxy.

        :param message_bus:
        :param service_name:
        :param object_path:
        :param backend:
        """
        self.__dbus__ = backend(message_bus, service_name, object_path)

    def __getattr__(self, name):
        """Get the cached property.

        Called when an attribute lookup has not found
        the attribute in the usual places.
        """
        self.__dbus__.get_object_member(name)

    def __setattr__(self, name, value):
        """Set the attribute.

        Called when an attribute assignment is attempted.
        Allow to set the attributes of this class, but
        nothing else.
        """
        if name in self.__class__.__slots__:
            return super().__setattr__(name, value)

        return self.__dbus__.set_object_member(name, value)
