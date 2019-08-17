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
import threading
from abc import ABC, abstractmethod

import pydbus

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.constants import ANACONDA_BUS_ADDR_FILE
from pyanaconda.dbus.constants import DBUS_ANACONDA_SESSION_ADDRESS, DBUS_STARTER_ADDRESS

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
        self._service_registrations = []
        self._object_registrations = []

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

    def register_service(self, service_name):
        """Register a service on DBus.

        A service can be registered by requesting its name on DBus.
        This method should be called only after all of the required
        objects of the service are published on DBus.

        :param service_name: a DBus name of a service
        """
        log.debug("Registering a service name %s.", service_name)
        reg = self.connection.request_name(service_name,
                                           allow_replacement=True,
                                           replace=False)

        self._service_registrations.append((service_name, reg))

    def publish_object(self, object_path, obj):
        """Publish an object on DBus.

        :param object_path: a DBus path of an object
        :param obj: an instance of @dbus_interface or @dbus_class
        """
        log.debug("Publishing an object at %s.", object_path)
        reg = self.connection.register_object(object_path, obj, None)
        self._object_registrations.append((object_path, reg))

    def get_dbus_proxy(self):
        """Returns a proxy of DBus.

        :return: a proxy object
        """
        return self.connection.dbus

    def get_proxy(self, service_name, object_path):
        """Returns a proxy of a remote DBus object.

        :param service_name: a DBus name of a service
        :param object_path: a DBus path an object
        :return: a proxy object
        """
        self._check_service_access(service_name)
        return self.connection.get(service_name, object_path)

    def _check_service_access(self, service_name):
        """Check if we can access a DBus service.

        FIXME: This is a temporary check that should be later removed.

        This is useful during the transition of the Anaconda code from
        UI to DBus modules. This check prevents a deadlock in case that
        a DBus module tries to access a service, that it provides, from
        the main thread.

        :param service_name: a DBus name of a service
        :raises: RuntimeError if the service cannot be accessed
        """
        if service_name not in (name for name, registration in self._service_registrations):
            # We don't provide this service.
            return

        if threading.current_thread() is not threading.main_thread():
            # We don't try to access this service from the main thread.
            return

        raise RuntimeError("Cannot access {} from the main thread.".format(service_name))

    def disconnect(self):
        """Disconnect from DBus."""
        log.debug("Disconnecting from the bus.")

        while self._object_registrations:
            _, registration = self._object_registrations.pop()
            registration.unregister()

        while self._service_registrations:
            _, registration = self._service_registrations.pop()
            registration.unown()

        self._connection = None


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
        return pydbus.connect(self._address)


class DBusSystemConnection(Connection):
    """Representation of a system bus connection."""

    def get_new_connection(self):
        """Get a system DBus connection."""
        log.info("Connecting to the system bus.")
        return pydbus.SystemBus()


class DBusSessionConnection(Connection):
    """Representation of a session bus connection."""

    def get_new_connection(self):
        """Get a session DBus connection."""
        log.info("Connecting to the session bus.")
        return pydbus.SessionBus()


class DBusAnacondaConnection(Connection):
    """Representation of an Anaconda bus connection."""

    def get_new_connection(self):
        """Get an Anaconda bus connection."""
        if DBUS_ANACONDA_SESSION_ADDRESS in os.environ:
            bus_address = os.environ.get(DBUS_ANACONDA_SESSION_ADDRESS)
        elif os.path.exists(ANACONDA_BUS_ADDR_FILE):
            with open(ANACONDA_BUS_ADDR_FILE, 'rt') as f:
                bus_address = f.read().strip()
        else:
            raise ConnectionError("Can't find Anaconda bus address!")

        log.info("Connecting to an Anaconda bus at %s.", bus_address)
        return pydbus.connect(bus_address)


class DBusDefaultConnection(DBusAnacondaConnection):
    """Representation of a default bus connection."""

    def get_new_connection(self):
        """Get a default bus connection.

        Connect to the bus specified by the environmental variable
        DBUS_STARTER_ADDRESS. If it is not specified, connect to
        the Anaconda bus.
        """
        if DBUS_STARTER_ADDRESS in os.environ:
            bus_address = os.environ.get(DBUS_STARTER_ADDRESS)
            log.info("Connecting to a default bus at %s.", bus_address)
            return pydbus.connect(bus_address)

        return super().get_new_connection()
