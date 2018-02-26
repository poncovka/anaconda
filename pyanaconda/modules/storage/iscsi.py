#
# Kickstart module for ISCSI.
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
from pyanaconda.core.signal import Signal
from pyanaconda.dbus import DBus

from pyanaconda import anaconda_logging
from pyanaconda.dbus.constants import STORAGE_ISCSI_PATH
from pyanaconda.modules.storage.iscsi_interface import ISCSIInterface

log = anaconda_logging.get_dbus_module_logger(__name__)


class ISCIModule(object):
    """The ISCI module."""

    def __init__(self):
        """Initialize the module."""
        self.module_properties_changed = Signal()

    def publish(self):
        """Publish the module."""
        DBus.publish_object(ISCSIInterface(self),
                            STORAGE_ISCSI_PATH)

    def process_kickstart(self, data):
        """Process the kickstart data."""
        log.debug("Processing isci data...")

    def generate_kickstart(self, data):
        """Generate the kickstart data."""
        log.debug("Generating isci data...")
