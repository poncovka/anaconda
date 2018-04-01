#
# Representation of DBus connection.
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
import os
from abc import ABC, abstractmethod

from pyanaconda.dbus.constants import DBUS_ANACONDA_SESSION_ADDRESS, DBUS_STARTER_ADDRESS, \
    DBUS_REQUEST_NAME_REPLY_PRIMARY_OWNER, DBUS_NAME_FLAG_ALLOW_REPLACEMENT, DBUS_NAMESPACE
from pyanaconda.dbus.error import error_registration
from pyanaconda.dbus.gio import BusType, DBusNodeInfo, get_connection_by_address,\
    get_connection_by_type
from pyanaconda.dbus.observer import DBusObjectObserver, DBusCachedObserver
from pyanaconda.dbus.namespace import get_dbus_name, get_dbus_path

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.dbus.proxy import DBusObjectAccess, DBusObjectProxy

log = get_module_logger(__name__)

__all__ = ["Connection", "DBusConnection", "DBusSystemConnection",
           "DBusSessionConnection", "DBusDefaultConnection", ]


class Connection(ABC):
    """Abstract class to represent a bus connection.

    It will connect to a bus returned by the get_new_connection method.

    The property connection represents a connection to the bus. You can
    register a service name with register_service, or publish an object
    with publish_object and get a proxy of a remote object with get_proxy.
    """

    def __init__(self):
        self._connection = None
        self._proxy = None
        self._service_registrations = []
        self._object_registrations = []

    @property
    def proxy(self):
        """Proxy of the DBus object."""
        if not self._proxy:
            self._proxy = self.get_proxy(
                get_dbus_name(DBUS_NAMESPACE),
                get_dbus_path(DBUS_NAMESPACE)
            )

        return self._proxy

    @property
    def connection(self):
        """Returns a DBus connection."""
        if not self._connection:
            self._connection = self.get_new_connection()

        return self._connection

    @abstractmethod
    def get_new_connection(self):
        """Get a DBus connection.

        You shouldn't create new connections unless there is a good
        reason for it. Use DBus.connection instead.

        :return: an instance of Gio.DBusConnection
        """
        pass

    def check_connection(self):
        """Check if the connection is set up.

        :return: True if the connection is set up otherwise False
        """
        try:
            return self.connection is not None
        except Exception as e:  # pylint: disable=broad-except
            log.error("Connection failed to be created:\n%s", e)
            return False

    def register_service(self, service_name, flags=None):
        """Register a service on DBus.

        A service can be registered by requesting its name on DBus.
        This method should be called only after all of the required
        objects of the service are published on DBus.

        :param service_name: a DBus name of a service
        :param flags: flags for org.freedesktop.DBus.RequestName
        """
        if flags is None:
            flags = DBUS_NAME_FLAG_ALLOW_REPLACEMENT

        log.debug("Registering a service name %s.", service_name)
        result = self.proxy.RequestName(service_name, flags)

        if result != DBUS_REQUEST_NAME_REPLY_PRIMARY_OWNER:
            raise ConnectionError("Name request failed: {}".format(result))

        self._service_registrations.append(service_name)

    def publish_object(self, object_path, obj, specification=None):
        """Publish an object on DBus.

        :param object_path: a DBus path of an object
        :param obj: an instance of @dbus_interface or @dbus_class
        :param specification: a DBus specification of the object
        """
        log.debug("Publishing an object at %s.", object_path)

        if not specification:
            specification = type(obj).dbus

        node_info = DBusNodeInfo.new_for_xml(specification)

        # TODO: Connect object to bus callbacks.
        # Iterate over interfaces.
        # Transfer everything to the method call.
        # Create the object Registration.
        method_call = None

        for interface_info in node_info.interfaces:

            registration_id = self.connection.register_object(
                object_path,
                interface_info,
                method_call,
                None,
                None
            )

            self._object_registrations.append(registration_id)

    def get_proxy(self, service_name, object_path):
        """Returns a proxy of a remote DBus object.

        :param service_name: a DBus name of a service
        :param object_path: a DBus path an object
        :return: a proxy object
        """
        return DBusObjectProxy(self, service_name, object_path)

    def get_observer(self, service_name, object_path):
        """Returns an observer of a remote DBus object.

        :param service_name: a DBus name of a service
        :param object_path: a DBus path an object
        :return: an instance of DBusObjectObserver
        """
        return DBusObjectObserver(self, service_name, object_path)

    def get_cached_observer(self, service_name, object_path, interface_names):
        """Returns a cached observer of a remote DBus object.

        :param service_name: a DBus name of a service
        :param object_path: a DBus path an object
        :param interface_names: a list of interface names
        :return: an instance of DBusCachedObserver
        """
        return DBusCachedObserver(self, service_name, object_path, interface_names)

    def disconnect(self):
        """Disconnect from DBus."""
        log.debug("Disconnecting from the bus.")

        while self._object_registrations:
            registration_id = self._object_registrations.pop()
            self.connection.unregister_object(registration_id)

        while self._service_registrations:
            service_name = self._service_registrations.pop()
            self.proxy.ReleaseName(service_name)

        self._connection = None
        self._proxy = None

    @property
    def error_handler(self):
        """The object for handling DBus errors."""
        return error_registration


class DBusConnection(Connection):
    """Representation of a connection for the specified address."""

    def __init__(self, address):
        """Create a new representation of a connection.

        :param address: a bus address
        """
        super().__init__()
        self._address = address

    @property
    def address(self):
        return self._address

    def get_new_connection(self):
        """Get a connection to a bus at the specified address."""
        log.info("Connecting to a bus at %s.", self._address)
        return get_connection_by_address(self._address)


class DBusSystemConnection(Connection):
    """Representation of a system bus connection."""

    def get_new_connection(self):
        """Get a system DBus connection."""
        log.info("Connecting to the system bus.")
        return get_connection_by_type(BusType.SYSTEM)


class DBusSessionConnection(Connection):
    """Representation of a session bus connection."""

    def get_new_connection(self):
        """Get a session DBus connection."""
        log.info("Connecting to the session bus.")
        return get_connection_by_type(BusType.SESSION)


class DBusDefaultConnection(Connection):
    """Representation of a default bus connection."""

    def _get_starter_connection(self):
        """Get a starter DBus connection."""
        if DBUS_STARTER_ADDRESS not in os.environ:
            return None

        bus_address = os.environ.get(DBUS_STARTER_ADDRESS)
        log.info("Connecting to a starter bus at %s.", bus_address)
        return get_connection_by_type(BusType.STARTER)

    def _get_fallback_connection(self):
        """Get a fallback DBus connection."""
        if DBUS_ANACONDA_SESSION_ADDRESS not in os.environ:
            return None

        bus_address = os.environ.get(DBUS_ANACONDA_SESSION_ADDRESS)
        log.info("Connecting to a default bus at %s.", bus_address)
        return get_connection_by_address(bus_address)

    def _raise_connection_error(self):
        """Raise a connection error."""
        raise ConnectionError("Unable to get the default bus connection.")

    def get_new_connection(self):
        """Get a default bus connection.

        Connect to the bus specified by the environmental variable
        DBUS_STARTER_ADDRESS. If it is not specified, connect to
        the fallback bus. If it is not specified, raise an exception.
        """
        return self._get_starter_connection() \
            or self._get_fallback_connection() \
            or self._raise_connection_error()
