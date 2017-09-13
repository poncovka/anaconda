#
# boss.py:  interface for communication with the kickstart modules
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
from pyanaconda.dbus.interface import dbus_interface

@dbus_interface
class Boss(object):
    """Manager of kickstart modules, ui modules and the installer.

    The boss is responsible for starting and managing kickstart modules,
    ui modules and the installer. It is able to process a kickstart file,
    distribute the kickstart data between kickstart modules, collect them back
    and create a valid kickstart file that can be used for installation by the
    installer.
    """

    def __init__(self):
        """Initialization of the boss"""
        pass

    @property
    def Screenplay(self) -> ObjPath:
        return ""

    def run(self, screenplay):
        """Run the given screen play."""
        pass


class AnacondaManager:
    """Alias the boss."""


class ConfigurationManager:
    pass


class InstallationManager:
    pass

@dbus_interface
class Screenplay(object):
    """The description of the anacondas behaviour."""

    def AddEvent(self, event):
        pass

    def AddEventAfter(self, event, event_after):
        pass

    def AddEventBefore(self, event, event_before):
        pass

    def RegisterBlocker(self, blocker_name):
        pass

    def BlockEvent(self, event, blocker_id):
        pass

    def UnblockEvent(self, event, blocker_id: Int) -> None:
        pass
