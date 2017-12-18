#
# base_interface.py
# Base interface for Anaconda modules.
#
# Copyright (C) 2017 Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#
from pydbus.error import map_error
from pykickstart.errors import KickstartParseError, KickstartError

from pyanaconda.dbus.template import InterfaceTemplate
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.dbus.interface import dbus_interface
from pyanaconda.dbus.constants import DBUS_MODULE_NAMESPACE

# Map some predefined exceptions.
map_error("{}.KickstartError".format(DBUS_MODULE_NAMESPACE))(KickstartError)
map_error("{}.KickstartParseError".format(DBUS_MODULE_NAMESPACE))(KickstartParseError)


@dbus_interface(DBUS_MODULE_NAMESPACE)
class KickstartModuleInterface(InterfaceTemplate):
    """DBus interface of a kickstart module.

    The implementation provides the KickstartModule class.
    """

    def AvailableTasks(self) -> List[Tuple[Str, Str]]:
        """Return DBus object paths for tasks available for this module.

        :returns: List of tuples (Name, DBus object path) for all Tasks.
                  See pyanaconda.task.Task for Task API.
        """
        result = []

        for task in self.implementation.published_tasks:
            result.append((task.Name, task.object_path))

        return result

    def Ping(self, s: Str) -> Str:
        """Ping the module."""
        return self.implementation.ping(s)

    def Quit(self):
        """Shut the module down."""
        self.implementation.stop()

    @property
    def KickstartCommands(self) -> List[Str]:
        """Return a list of kickstart command names.

        :return: a list of command names
        """
        return self.implementation.kickstart_command_names

    @property
    def KickstartSection(self) -> List[Str]:
        """Return a list of kickstart sections names.

        :return: a list of section names
        """
        return self.implementation.kickstart_section_names

    def ReadKickstart(self, s: Str):
        """Read the kickstart string.

        :param s: a kickstart string
        """
        self.implementation.read_kickstart(s)

    def WriteKickstart(self) -> Str:
        """Return a kickstart representation of the module

        :return: a kickstart string
        """
        return self.implementation.write_kickstart()
