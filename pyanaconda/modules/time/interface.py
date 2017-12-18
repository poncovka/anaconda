# time_interface.py
# DBus interface for the time module.
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

from pyanaconda.dbus.constants import MODULE_TIME_NAME
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.modules.base_interface import KickstartModuleInterface
from pyanaconda.dbus.interface import dbus_interface


@dbus_interface(MODULE_TIME_NAME)
class TimeInterface(KickstartModuleInterface):
    """DBus interface for Time.

    isUtc - If present, the system assumes the hardware clock is set to UTC (Greenwich Mean) time.(bool)
    nontp - Disable automatic starting of NTP service. (bool)
    --nontp and --ntpservers are mutually exclusive.

    --ntpservers <server1>,<server2>,...,<serverN>

    Specify a list of NTP servers to be used (comma-separated list with no spaces). The chrony package is automatically installed when this option is used. If you don’t want the package to be automatically installed then use -chrony in package selection. For example:

    ``timezone --ntpservers=ntp.cesnet.cz,tik.nic.cz Europe/Prague``

     Sets the system time zone to timezone. To view a list of available time zones, use the timedatectl list-timezones command.

    timezone timezone [options]

        --utc - If present, the system assumes the hardware clock is set to UTC (Greenwich Mean) time.
        --nontp - Disable the NTP service automatic starting.
        --ntpservers= - Specify a list of NTP servers to be used as a comma-separated list without spaces.
    """

    @property
    def Timezone(self) -> Str:
        return self.implementation.timezone

    @Timezone.setter
    def Timezone(self, timezone: Str):
        self.implementation.set_timezone(timezone)

    @property
    def UTC(self) -> Bool:
        return self.implementation.is_utc

    @property
    def NTP(self) -> Bool:
        return self.implementation.use_ntp

    @property
    def NTPServers(self) -> List[Str]:
        return self.implementation.ntp_servers

    def AddNTPServer(self, server: Str):
        self.implementation.add_ntp_server(server)

