#
# Utils for date and time settings.
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
import os

from pyanaconda import iutil, ntp
from pyanaconda.flags import can_touch_runtime_system
from pyanaconda.timezone import NTP_SERVICE

from pyanaconda import anaconda_logging
log = anaconda_logging.get_dbus_module_logger(__name__)


def stop_ntp_service():
    """Stop the NTP service."""
    if not iutil.service_running(NTP_SERVICE):
        return

    if not can_touch_runtime_system("stop NTP service"):
        return

    ret = iutil.stop_service(NTP_SERVICE)

    if ret != 0:
        log.error("Failed to stop NTP service")


def start_ntp_service():
    """Start the NTP service."""
    if iutil.service_running(NTP_SERVICE):
        return

    if not can_touch_runtime_system("start NTP service"):
        return

    ret = iutil.start_service(NTP_SERVICE)

    if ret != 0:
        log.error("Failed to start NTP service")


def update_ntp_service_config(ntp_servers):
    """Update the NTP service config file.

    :param ntp_servers: a list of NTP servers
    """
    chronyd_conf_path = os.path.normpath(iutil.getSysroot() + ntp.NTP_CONFIG_FILE)
    pools, servers = ntp.internal_to_pools_and_servers(ntp_servers)

    if os.path.exists(chronyd_conf_path):
        log.debug("Modifying installed chrony configuration")
        try:
            ntp.save_servers_to_config(pools, servers, conf_file_path=chronyd_conf_path)
        except ntp.NTPconfigError as ntperr:
            log.warning("Failed to save NTP configuration: %s", ntperr)

    else:
        log.debug("Creating chrony configuration based on the "
                  "configuration from installation environment")
        try:
            ntp.save_servers_to_config(pools, servers,
                                       conf_file_path=ntp.NTP_CONFIG_FILE,
                                       out_file_path=chronyd_conf_path)
        except ntp.NTPconfigError as ntperr:
            log.warning("Failed to save NTP configuration without chrony package: %s",
                        ntperr)
