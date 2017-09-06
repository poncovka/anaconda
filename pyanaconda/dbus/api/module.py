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
    """DBus interface for a kickstart module.

    The kickstart module manages a part of the kickstart file.
    It is able to parse the specified commands, validate them,
    change them and write them back to the kickstart format.

    The module can also offer default values, available choices
    and validation hints.
    """

    @property
    def Specification(self) -> Dict[Str, Variant]:
        """The specification of the kickstart module.

        In the future it can be possible, that we will need
        to extend this specification, so it is a dictionary.

        For now, the module is specified only by the names of
        kickstart commands that can be managed by the module.

        The specification is interesting mostly for the boss.

        :return: a dictionary
        """
        return {"KICKSTART_COMMANDS": []}

    @property
    def Validity(self) -> Byte:
        """Are the kickstart data valid?

        Every change of the kickstart data will set the validity to UNKNOWN.
        Then the validate function has to be called, that will set the
        validity to VALID or INVALID.

        TODO: Can the kickstart data change during the validation?
        The validate function could set the validity to VALIDATING at start.
        When it is finished, in can set the validity to VALID or INVALID only
        if VALIDATING is still set.

        TODO: Do we need the complete property?
        If incomplete data are treated as invalid data, we don't have to
        care about completeness anymore.

        VALID    1
        INVALID  0
        UNKNOWN  -1
        (VALIDATING -2)

        :return: the id of the current validity
        """
        return 0

    @dbus_signal
    def Notify(self, event: UInt16):
        """Notify others of the current event.

        We should notify other modules of the
        current events of this module.

                The event:
        ================================
        UNSPECIFIED_EVENT 0

        STARTED 10
        QUIT 20
        FAILED 30

        CONNECT_STARTED 40
        CONNECT_DONE 41
        CONNECT_FAILED 42

        SETUP_STARTED 50
        SETUP_DONE 51
        SETUP_FAILED 52
        SETUP_RESET 53

        VALIDATE_STARTED 60
        VALIDATE_DONE 61
        VALIDATE_FAILED 62

        UNKNOWN_EVENT 1000
        module specific from 1001

        TODO: Should we replace this signal with many new signals?
        It would require to connect to every signal we are interested in.

        :param event: The reported event.
        """
        pass

    @dbus_signal
    def Report(self, level: UInt16, activity: UInt16, message: Str):
        """Report what the module is doing right now.

        The reporting level:
        ====================
        DEBUG 10
        INFO 20
        WARNING 30
        ERROR 40
        CRITICAL 50

        Taken from https://docs.python.org/3/library/logging.html#levels, so
        it can be directly logged by the boss.

        The current activity:
        ================================
        UNSPECIFIED 0
        STARTING 10
        QUITTING 20
        FAILING 30

        CONNECTING 40
        SETTING_UP 50

        VALIDATING 60
        READING 70
        WRITING 80

        UNKNOWN 1000
        customize 1001 - ...

        :param level: The reporting level.
        :param activity: The reported activity.
        :param message: More details about the activity.
        """
        pass

    @dbus_signal
    def PropertiesChanged(self):
        """Inform about changed properties."""
        pass

    def __init__(self):
        """Initialize the kickstart module.

        We should set all properties and default
        values to some initial values.

        DBus is not available at this point.
        """
        pass

    def publish(self, bus):
        """Publish the kickstart module on DBus.

        Publishes the kickstart module and emits
        its first signal, the STARTED notification.

        Sends reports for the STARTING activity.
        """
        pass

    def Connect(self) -> None:
        """Connect the module to other DBus modules.

        Create proxies and register callbacks to signals.
        If you are interested in properties of other modules,
        you should read the properties from a proxy and connect
        to the PropertiesChanged signal to stay updated.

        Emits CONNECT_STARTED and CONNECT_DONE notifications.
        In a case of failure, it emits CONNECT_FAILED.

        Sends reports for the CONNECTING activity.
        """
        pass

    def Setup(self) -> None:
        """Setup the module.

        The module should have all information to finish its setup, so
        the rest of the initialization should be done here. The setup
        should focus on preparing default values, available choices
        and validation hints.

        Mostly we should call some of the callbacks registered with signals
        of other modules in the Connect method to get synchronized with
        other modules.

        Emits SETUP_STARTED and SETUP_DONE notifications. In a case of failure,
        it emits SETUP_FAILED.

        Sends reports for the SETTING_UP activity.
        """
        pass

    def Validate(self) -> None:
        """Validate the kickstart data.

        See the the validity property.

        Everything we can should be validated in the setters of properties.
        A more complex validation with dependencies between properties
        and modules should be done here.

        Emits the VALIDATE_STARTED and VALIDATE_DONE notification.
        In a case of failure, it emits VALIDATE_FAILED.

        Sends reports for the VALIDATING activity.

        TODO: How to provide a feedback?
        1. Raise an error.
        2. Emit signals with errors and warnings.
        3. Collect a list of errors and warnings and return it.
        """
        pass

    def ReadData(self, data: Str) -> Bool:
        """Read a string representation of kickstart data.

        The data will be parsed and validated.

        Emits the READ_STARTED and READ_DONE notification.
        In a case of failure, it emits READ_FAILED.

        Sends reports for the READING activity.

        TODO: Couldn't we call the Validate method later?
        We could, but the validation should be partially done
        when we try to set the properties of the module.
        We can provide the exceptions in a form of the feedback
        we decide to use.

        TODO: 

        TODO: How to provide a feedback?
        Probably the same way as the validate function.

        :param data: A string with expected kickstart commands.
        :return: True if data are valid, otherwise False.
        """
        pass

    def WriteData(self) -> Str:
        """Return a string representation of kickstart data.

        Emits the WRITE_STARTED and WRITE_DONE notifications.
        In a case of failure, it emits WRITE_FAILED.

        Sends reports for the WRITING activity.

        :return: A string representation of kickstart data.
        """

    def ResetData(self) -> None:
        """Set the kickstart data from the default values.

        Emits the SETUP_RESET notification.
        Sends reports for the SETTING_UP activity.
        """
        pass

    def Quit(self) -> None:
        """Quit the kickstart module.

        Emits the QUIT notification.
        Sends reports for the QUITTING activity.
        """
        pass
