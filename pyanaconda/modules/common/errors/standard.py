#
# Standard DBus errors.
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
from pyanaconda.dbus.error import dbus_error
from pyanaconda.modules.common.constants.namespaces import DBUS_NAMESPACE
from pyanaconda.modules.common.errors import DBusError


@dbus_error("Error.AccessDenied", namespace=DBUS_NAMESPACE)
class AccessDeniedError(DBusError):
    """Thrown if a message is denied due to a security policy."""
    pass


@dbus_error("Error.InvalidArgs", namespace=DBUS_NAMESPACE)
class InvalidArgsError(DBusError):
    """Invalid arguments were passed to a method call."""
    pass


@dbus_error("Error.UnknownMethod", namespace=DBUS_NAMESPACE)
class UnknownMethodError(DBusError):
    """Method name you invoked isn't known by the object you invoked it on."""
    pass
