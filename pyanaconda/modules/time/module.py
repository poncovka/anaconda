# time.py
# Kickstart module for date and time settings.
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
from pyanaconda.dbus import DBus
from pyanaconda.dbus.constants import MODULE_TIME_PATH, MODULE_TIME_NAME, MODULE_PAYLOAD_NAME, \
    MODULE_PAYLOAD_PATH, MODULE_SERVICES_NAME, MODULE_SERVICES_PATH
from pyanaconda.dbus.observer import DBusObjectObserver
from pyanaconda.modules.base import KickstartModule, InvalidValueError
from pyanaconda.modules.time.kickstart import TimeKickstartSpecification
from pyanaconda.modules.time.interface import TimeInterface

from pyanaconda import anaconda_logging, iutil
from pyanaconda.modules.time.utils import stop_ntp_service, start_ntp_service, \
    update_ntp_service_config
from pyanaconda.timezone import NTP_SERVICE, NTP_PACKAGE, is_valid_timezone, write_timezone_config

log = anaconda_logging.get_dbus_module_logger(__name__)


class TimeModule(KickstartModule):
    """The Time module."""

    def __init__(self):
        super().__init__()
        self._timezone = None
        self._is_utc = False
        self._use_ntp = True
        self._ntp_servers = []

    def publish(self):
        """Publish the module."""
        DBus.publish_object(TimeInterface(self), MODULE_TIME_PATH)
        DBus.register_service(MODULE_TIME_NAME)

    def ping(self, s):
        log.debug(s)
        return "TimeModule says hi!"

    @property
    def kickstart_specification(self):
        return TimeKickstartSpecification

    def process_kickstart(self, data):
        log.debug(str(data))
        self._data = data

    def write_kickstart(self):
        return str(self._data)

    @property
    def default_timezone(self):
        return "America/New_York"

    @property
    def timezone(self):
        if self._timezone:
            return self._timezone

        return self.default_timezone

    def set_timezone(self, timezone):
        if not is_valid_timezone(timezone):
            raise InvalidValueError("The timezone %s is not valid.", timezone)

        self._timezone = timezone

    @property
    def use_ntp(self):
        return self._use_ntp

    @property
    def is_utc(self):
        return self._is_utc

    @property
    def ntp_servers(self):
        return self._ntp_servers

    def add_ntp_server(self, server):
        self._ntp_servers.append(server)

    def setup_task(self):
        """Setup task of the Time module."""
        payload = DBusObjectObserver(MODULE_PAYLOAD_NAME, MODULE_PAYLOAD_PATH)
        payload.watch()

        services = DBusObjectObserver(MODULE_SERVICES_NAME, MODULE_SERVICES_PATH)
        services.watch()

        enable_ntp = self.use_ntp

        if payload.is_service_available:
            if payload.proxy.IsExcluded(NTP_PACKAGE):
                enable_ntp = False

        if enable_ntp:
            log.debug("Enabling the NTP service.")
            start_ntp_service()

            if payload.is_service_available:
                payload.proxy.AddPackage(NTP_PACKAGE)

            if services.is_service_available and \
                    not services.proxy.IsDisabled(NTP_SERVICE):
                services.proxy.EnableSevice(NTP_SERVICE)
        else:
            log.debug("Disabling the NTP service.")
            stop_ntp_service()

            if services.is_service_available:
                services.proxy.DisableService(NTP_SERVICE)

        payload.unwatch()
        services.unwatch()

    def execute_task(self):
        """Execute task of the Time module."""
        log.debug("Writing timezone configuration.")
        write_timezone_config(self.timezone, self.is_utc, iutil.getSysroot())

        if self.use_ntp and self.ntp_servers:
            log.debug("Updating ntp service configuration.")
            update_ntp_service_config(self.ntp_servers)
