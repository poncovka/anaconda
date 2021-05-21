#
# Copyright (C) 2021  Red Hat, Inc.  All rights reserved.
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
from dasbus.server.interface import dbus_interface

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.modules.common.constants.objects import DBUS_CONTROLLER

log = get_module_logger(__name__)


@dbus_interface(DBUS_CONTROLLER.interface_name)
class DBusControllerInterface(object):
    """The DBus interface for a message bus controller."""

    def ReloadConfig(self):
        """Reload a configuration.

        This function is called for each client-request
        of org.freedesktop.DBus.ReloadConfig().
        """
        pass
