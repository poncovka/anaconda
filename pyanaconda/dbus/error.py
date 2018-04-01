#
# DBus errors.
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
from pyanaconda.dbus.gio import DBusError, GLibError
from pyanaconda.dbus.namespace import get_dbus_name

__all__ = ['dbus_error', 'dbus_error_by_default']


def dbus_error(error_name, namespace):
    """Define decorated class as a DBus error.

    The decorated exception class will be mapped to a DBus error.

    :param error_name: a DBus name of the error
    :param namespace: a sequence of strings
    :return: a decorator
    """
    return map_error(get_dbus_name(*namespace, error_name))


def dbus_error_by_default(cls):
    """Define a default DBus error.

    The decorated exception class will be mapped to all unknown DBus errors.

    :param cls: an exception class
    :return: a decorated class
    """
    return map_by_default(cls)


def register_error(name, domain, code):
    """Register and map decorated exception class to a DBus error."""
    def decorated(cls):
        error_registration.register_error(cls, name, domain, code)
        return cls

    return decorated


def map_error(error_name):
    """Map decorated exception class to a DBus error."""
    def decorated(cls):
        error_registration.map_error(cls, error_name)
        return cls

    return decorated


def map_by_default(cls):
    """Map decorated exception class to all unknown DBus errors."""
    error_registration.map_by_default(cls)
    return cls


class ErrorRegistration(object):
    """Class for mapping exceptions to DBus errors."""

    _default = None
    _map = dict()
    _reversed_map = dict()

    def map_by_default(self, exception_cls):
        """Set the exception class as a default."""
        self._default = exception_cls

    def map_error(self, exception_cls, name):
        """Map the exception class to a DBus name."""
        self._map[name] = exception_cls
        self._reversed_map[exception_cls] = name

    def register_error(self, exception_cls, name, domain, code):
        """Map and register the exception class to a DBus name."""
        self.map_error(exception_cls, name)
        return DBusError.register_error(domain, code, name)

    def is_registered_exception(self, obj):
        """Is the exception registered?"""
        return obj.__class__ in self._reversed_map

    def get_dbus_name(self, obj):
        """Get the DBus name of the exception."""
        return self._reversed_map.get(obj.__class__)

    def get_exception_class(self, name):
        """Get the exception class mapped to the DBus name."""
        return self._map.get(name, self._default)

    def transform_message(self, name, message):
        """Transform the message of the exception."""
        prefix = "{}:{}: ".format("GDBus.Error", name)

        if message.startswith(prefix):
            return message[len(prefix):]

        return message

    def transform_exception(self, e):
        """Transform the remote error to the exception."""
        if not isinstance(e, GLibError):
            return e

        if not DBusError.is_remote_error(e):
            return e

        # Get DBus name of the error.
        name = DBusError.get_remote_error(e)
        # Get the exception class.
        exception_cls = self.get_exception_class(name)

        # Return the original exception.
        if not exception_cls:
            return e

        # Return new exception.
        message = self.transform_message(name, e.message)
        exception = exception_cls(message)
        exception.dbus_name = name
        exception.dbus_domain = e.domain
        exception.dbus_code = e.code
        return exception


# Default error registration.
error_registration = ErrorRegistration()
