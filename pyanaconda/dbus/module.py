#
# module.py:  interface for the kickstart modules
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
from pyanaconda.dbus.interface import dbus_interface, dbus_signal


@dbus_interface
class KickstartModule(object):

    @property
    def State(self) -> Int:
        """The current state of the module.

        INITIALIZED - The module has started and is registered on DBus,
        but it is not connected to other modules.
        READY - The module is in a valid state.
        BUSY - The module is doing something in a separate thread.
        INVALID - The module is in an invalid state.

        :return: The id of the current state.
        """
        return 0

    @dbus_signal
    def Status(self, state: Int, message: Str):
        """

        :param state: The current state of the module.
        :param message: The status message.
        """
        pass


    @dbus_signal
    def Error(self, type: Int, message: Str):
        """

        :param message:
        """
        pass

    @dbus_signal
    def Warning(self, type: Int, message: Str):
        """

        :param type:
        :param message:
        :return:
        """
        pass

    @dbus_signal
    def Status(self, type: Int, message: Str):
        """

        :param type:
        :param message:
        :return:
        """
        pass

    def Connect(self) -> None:
        """Connect the module to other DBus modules.

        Create proxies and register callbacks to signals.
        We should be able to skip this
        """
        pass

    def Read(self, data: Str) -> Bool:
        """Read a string representation of kickstart data.

        The data will be parsed, validated and applied.

        The module can emit signals: ParseError, ParseWarning,
        ValidationError and ValidationWarning.

        :param data: A string with expected kickstart commands.
        :return: True if data are valid, otherwise False.
        """
        pass

    def Write(self) -> Str:
        """Return a string representation of kickstart data.

        :return: A string representation of kickstart data.
        """