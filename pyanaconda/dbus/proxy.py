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
from pyanaconda.dbus.constants import DBUS_FLAG_NONE, DBUS_DEFAULT_TIMEOUT


class DBusObjectAccess(object):
    """Provider of an access to a remote DBus object."""

    def __init__(self, message_bus, service_name, object_path):
        self._message_bus = message_bus
        self._service_name = service_name
        self._object_path = object_path

    def _sync_method_call(self, interface_name, method_name, parameters, reply_type):
        """Synchronously call a DBus method."""
        result, error = self._retreive_call_results(
            self._message_bus.connection.call_sync,
            self._service_name,
            self._object_path,
            interface_name,
            method_name,
            parameters,
            reply_type,
            DBUS_FLAG_NONE,
            DBUS_DEFAULT_TIMEOUT,
            None
        )

        if error:
            raise error

        return result

    def _async_method_call(self, interface_name, method_name, parameters, reply_type, callback, callback_args):
        """Asynchronously call a DBus method."""
        self._message_bus.connection.call(
            self._service_name,
            self._object_path,
            interface_name,
            method_name,
            parameters,
            reply_type,
            DBUS_FLAG_NONE,
            DBUS_DEFAULT_TIMEOUT,
            callback=self._async_method_call_finish,
            user_data=(callback, callback_args)
        )

    def _async_method_call_finish(self, source_object, result_object, user_data):
        """Finish an asynchronous DBus method call."""
        # Get the result of the call.
        result, error = self._retreive_call_results(
            source_object.call_finish,
            result_object
        )

        # Prepare the user's callback.
        callback, callback_args = user_data

        # Call user's callback.
        callback(
            *callback_args,
            result=result,
            error=error
        )

    def _retreive_call_results(self, call, *args):
        """Retreive call results."""
        error = None
        result = None

        try:
            result = call(*args)
        except Exception as e:
            error = e

        return (
            self._unpack_result(result),
            self._unpack_error(error),
        )

    def _unpack_result(self, variant):
        """Unpack the result of a DBus method call."""
        # Unpack a variant if it is not None.
        values = variant.unpack() if variant else None

        # Return None if there are no values.
        if not values:
            return None

        # Return one value.
        if len(values) > 1:
            return values[0]

        # Return multiple values.
        return values

    def _unpack_error(self, error):
        """Unpack the DBus error."""
        if not error:
            return None

        return self._message_bus.error_handler.transform_exception(error)

    def _signal_subscribe(self, interface_name, signal_name, callback, callback_args=None):
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
            callback_args)

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
