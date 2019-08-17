#
# DASD module.
#
# Copyright (C) 2018 Red Hat, Inc.
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
from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.dbus import DBus
from pyanaconda.modules.common.base import KickstartBaseModule
from pyanaconda.modules.common.constants.objects import DASD
from pyanaconda.modules.storage.dasd.dasd_interface import DASDInterface
from pyanaconda.modules.storage.dasd.discover import DASDDiscoverTask
from pyanaconda.modules.storage.dasd.format import DASDFormatTask

log = get_module_logger(__name__)


class DASDModule(KickstartBaseModule):
    """The DASD module."""

    def publish(self):
        """Publish the module."""
        DBus.publish_object(DASD.object_path, DASDInterface(self))

    def discover_with_task(self, device_number):
        """Discover a DASD.

        :param device_number: a device number
        :return: a path to a task
        """
        return DASDDiscoverTask(device_number)

    def format_with_task(self, dasds):
        """Format specified DASD disks.

        :param dasds: a list of disk names
        :return: a DBus path to a task
        """
        return DASDFormatTask(dasds)
