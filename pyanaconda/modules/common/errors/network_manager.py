#
# DBus errors of the Network Manager.
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
from pyanaconda.modules.common.constants.namespaces import NETWORK_MANAGER_NAMESPACE
from pyanaconda.modules.common.errors import DBusError


@dbus_error("UnknownDevice", namespace=NETWORK_MANAGER_NAMESPACE)
class UnknownDeviceError(DBusError):
    """Device of specified name was not found."""
    pass


@dbus_error("UnmanagedDevice", namespace=NETWORK_MANAGER_NAMESPACE)
class UnmanagedDeviceError(Exception):
    """Device of specified name is not managed by NM or unavailable."""
    pass


@dbus_error("UnknownConnection", namespace=NETWORK_MANAGER_NAMESPACE)
class UnknownConnectionError(Exception):
    """Connection is not available for the device."""
    pass


@dbus_error("Device.NotActive", namespace=NETWORK_MANAGER_NAMESPACE)
class DeviceNotActiveError(DBusError):
    """Device of specified name is not active."""
    pass
