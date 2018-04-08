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
from pyanaconda.core.signal import Signal
from pyanaconda.dbus.constants import DBUS_FLAG_NONE, DBUS_DEFAULT_TIMEOUT
from pyanaconda.dbus.interface import DBusSpecification
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import


class DBusObjectAccess(object):
    """Provider of an access to a remote DBus object."""

    def __init__(self, message_bus, service_name, object_path):
        self._message_bus = message_bus
        self._service_name = service_name
        self._object_path = object_path

        self._specification = None
        self._specification_handler = DBusSpecification()

        self._members = {}
        self._defaults = {}
        self._signals = {}

    @property
    def specification(self):
        """Get the DBus specification."""
        if not self._specification:
            self._specification = self._call_introspect()

        return self._specification

    def _call_introspect(self):
        """Introspect the DBus object."""
        specification = self._sync_method_call(
            interface_name="org.freedesktop.DBus.Introspectable",
            method_name="Introspect",
            reply_type=get_variant_type(Tuple[Str])
        )

        return specification

    @property
    def members(self):
        """All object members."""
        if not self._members:
            self._members = self._specification_handler.parse_specification(self.specification)

        return self._members

    def _get_member_data(self, interface_name, member_name):
        member_data = self.members[(interface_name, member_name), None]

        if not member_data:
            raise ConnectionError(
                "Unknown member '{}.{}' of the object '{}' from '{}'.",
                interface_name, member_name, self._object_path, self._service_name
            )

        return member_data

    @property
    def defaults(self):
        """Default object members."""
        if not self._defaults:

            self._defaults = {
                member_name: interface_name
                for interface_name, member_name in self.members
            }

        return self._defaults

    def _get_default_interface(self, member_name):
        interface = self.defaults.get(member_name, None)

        if not interface:
            raise ConnectionError(
                "Unknown interface for the member '{}' of the object '{}' from '{}'.",
                member_name, self._object_path, self._service_name)

        return interface

    def _sync_method_call(self, interface_name, method_name, parameters=None, reply_type=None):
        """Synchronously call a DBus method."""

        # Get the results now.
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

        # Raise an error.
        if error:
            raise error

        # Or return the result.
        return result

    def _async_method_call(self, interface_name, method_name, callback, callback_args, parameters=None, reply_type=None):
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

    def get_signal(self, interface_name, name):
        """Get a proxy of a DBus signal."""
        # Get the full name of the signal.
        full_name = (interface_name, name)

        # Return the already created object.
        if full_name in self._signals:
            return self._signals[full_name]

        # Or create a new one.
        signal = Signal()

        # Subscribe to a DBus object.
        self._signal_subscribe(
            interface_name=interface_name,
            signal_name=name,
            callback=self._signal_callback,
            callback_args=signal
        )

        self._signals[full_name] = signal
        return signal

    def _signal_callback(self, connection, sender_name, object_path, interface_name, signal_name, parameters, user_data):
        """A callback that is called when a DBus signal is emitted."""
        signal = user_data
        values = parameters.unpack()
        signal.emit(*values)

    def get_property(self, interface_name, property_name):
        # Get a type of the property.
        specification = self._get_member_data(interface_name, property_name)

        # Return the result of the Get method.
        return self._sync_method_call(
            interface_name="org.freedesktop.DBus.Properties",
            method_name="Get",
            parameters=get_variant(
                Tuple[Str, Str],
                (interface_name, property_name)
            ),
            reply_type=Variant(specification.type)
        )

    def set_property(self, interface_name, property_name, value):
        # Get the specification of the property.
        specification = self._get_member_data(interface_name, property_name)

        # TODO: we can call the method with call_method

        # Call the Set method.
        self._sync_method_call(
            interface_name="org.freedesktop.DBus.Properties",
            method_name="Set",
            parameters=get_variant(
                Tuple[Str, Str, Variant],
                (interface_name, property_name, Variant(specification.type, value))
            )
        )

    def get_method(self, interface_name, method_name):
        return lambda *args, **kwargs: self.call_method(interface_name, method_name, *args, **kwargs)

    def call_method(self, interface_name, method_name, *args, callback=None, callback_args=None):
        specification = self._get_member_data(interface_name, method_name)

        # Do the call.
        if callback:
            self._async_method_call(
                interface_name=interface_name,
                method_name=method_name,
                parameters=Variant(specification.args_type, args),
                reply_type=VariantType(specification.reply_type),
                callback=callback,
                callback_args=callback_args
            )

        else:
            return self._sync_method_call(
                interface_name=interface_name,
                method_name=method_name,
                parameters=Variant(specification.args_type, args),
                reply_type=VariantType(specification.reply_type)
            )

    def get_object_member(self, member_name):
        """Get a member of the DBus object.

        :param member_name: a name of the member
        :return: a signal, a method or a property value
        """
        interface_name = self._get_default_interface(member_name)
        member = self._get_member_data(interface_name, member_name)

        if isinstance(member, DBusSpecification.Property):
            getter = self.get_property
        elif isinstance(member, DBusSpecification.Method):
            getter = self.get_method
        elif isinstance(member, DBusSpecification.Signal):
            getter = self.get_signal
        else:
            raise ConnectionError(
                "Unknown getter for '{}.{}' of the object '{}' from '{}'.",
                interface_name, member_name, self._object_path, self._service_name
            )

        return getter(interface_name, member_name)

    def set_object_member(self, member_name, value):
        """Set a member of the DBus object.

        :param member_name: a name of the member
        :param value: a new value of the member
        """
        interface_name = self._get_default_interface(member_name)
        member = self._get_member_data(interface_name, member_name)

        if isinstance(member, DBusSpecification.Property):
            setter = self.set_property
        else:
            raise ConnectionError(
                "Unknown setter for '{}.{}' of the object '{}' from '{}'.",
                interface_name, member_name, self._object_path, self._service_name
            )

        return setter(interface_name, member_name, value)


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
