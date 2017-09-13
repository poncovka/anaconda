#
# addon.py:  interface for the kickstart addon
#
# Copyright (C) 2017
# Red Hat, Inc.  All rights reserved.
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
# Author(s):  Vendula Poncova <vponcova@redhat.com>
#
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.dbus.api.module import KickstartModule
from pyanaconda.dbus.interface import dbus_interface, dbus_signal


@dbus_interface
class KickstartAddon(KickstartModule):
    """DBus interface for a kickstart addon.

    Kickstart addon is a custom kickstart module provided by the
    third party.

    Needs to provide:
    * UI files (GUI, TUI)
    * This module to process and manage its kickstart data.
    * The installation script that will be run during the installation.
    """

    @property
    def Location(self) -> Str:
        """Path to the addon.

        """
        return ""