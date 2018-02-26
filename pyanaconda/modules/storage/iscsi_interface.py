#
# DBus interface for ISCSI.
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
from pyanaconda.dbus.constants import STORAGE_ISCSI_NAME
from pyanaconda.dbus.interface import dbus_interface
from pyanaconda.dbus.template import AdvancedInterfaceTemplate
from pyanaconda.dbus.property import emits_properties_changed
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.modules.storage.iscsi import ISCIModule


@dbus_interface(STORAGE_ISCSI_NAME)
class ISCSIInterface(AdvancedInterfaceTemplate):
    """DBus interface for the kickstart module."""

    @property
    def implementation(self) -> ISCIModule:
        """Define the type of the implementation."""
        return super().implementation

    def connect_signals(self):
        """Connect to the implementation signals."""
        super().connect_signals()
        self.implementation.module_properties_changed.connect(self.flush_changes)
