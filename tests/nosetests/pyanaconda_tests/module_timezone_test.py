#
# Copyright (C) 2018  Red Hat, Inc.
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
# Red Hat Author(s): Vendula Poncova <vponcova@redhat.com>
#
import unittest

from pyanaconda.modules.common.constants.services import TIMEZONE
from pyanaconda.modules.timezone.timezone import TimezoneService
from pyanaconda.modules.timezone.timezone_interface import TimezoneInterface
from tests.nosetests.pyanaconda_tests import ModuleHandlerMixin


class TimezoneInterfaceTestCase(unittest.TestCase, ModuleHandlerMixin):
    """Test DBus interface for the timezone module."""

    def setUp(self):
        """Set up the timezone module."""
        self.timezone_module = TimezoneService()
        self.timezone_interface = TimezoneInterface(self.timezone_module)
        self.set_identifier(TIMEZONE)
        self.set_interface(self.timezone_interface)

    def kickstart_properties_test(self):
        """Test kickstart properties."""
        self._check_kickstart_properties(commands=["timezone"])

    def timezone_property_test(self):
        """Test the Timezone property."""
        self._check_dbus_property(
            "Timezone",
            "Europe/Prague"
        )

    def utc_property_test(self):
        """Test the IsUtc property."""
        self._check_dbus_property(
            "IsUTC",
            True
        )

    def ntp_property_test(self):
        """Test the NTPEnabled property."""
        self._check_dbus_property(
            "NTPEnabled",
            False
        )

    def ntp_servers_property_test(self):
        """Test the NTPServers property."""
        self._check_dbus_property(
            "NTPServers",
            ["ntp.cesnet.cz"]
        )

    def no_kickstart_test(self):
        """Test with no kickstart."""
        ks_in = None
        ks_out = """
        # System timezone
        timezone America/New_York
        """
        self._check_kickstart(ks_in, ks_out)

    def kickstart_empty_test(self):
        """Test with empty string."""
        ks_in = ""
        ks_out = ""
        self._check_kickstart(ks_in, ks_out)

    def kickstart_test(self):
        """Test the timezone command."""
        ks_in = """
        timezone Europe/Prague
        """
        ks_out = """
        # System timezone
        timezone Europe/Prague
        """
        self._check_kickstart(ks_in, ks_out)

    def kickstart2_test(self):
        """Test the timezone command with flags."""
        ks_in = """
        timezone --utc --nontp Europe/Prague
        """
        ks_out = """
        # System timezone
        timezone Europe/Prague --isUtc --nontp
        """
        self._check_kickstart(ks_in, ks_out)

    def kickstart3_test(self):
        """Test the timezone command with ntp servers.."""
        ks_in = """
        timezone --ntpservers ntp.cesnet.cz Europe/Prague
        """
        ks_out = """
        # System timezone
        timezone Europe/Prague --ntpservers=ntp.cesnet.cz
        """
        self._check_kickstart(ks_in, ks_out)
