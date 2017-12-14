# boss.py
# Anaconda main DBUS module & module manager.
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

import gi

from pyanaconda.dbus import DBus

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from pyanaconda.dbus.interface import dbus_interface
from pyanaconda.modules.base import BaseModule
from pyanaconda.dbus.constants import DBUS_BOSS_NAME, DBUS_BOSS_PATH, DBUS_BOSS_INSTALLATION_PATH

from pyanaconda.modules.boss.module_manager import ModuleManager
from pyanaconda.modules.boss.install_manager.installation_interface import InstallationInterface
from pyanaconda.modules.boss.install_manager.install_manager import InstallManager

from pyanaconda import anaconda_logging
log = anaconda_logging.get_dbus_module_logger(__name__)


@dbus_interface(DBUS_BOSS_NAME)
class Boss(BaseModule):

    def __init__(self, module_manager=None, install_manager=None):
        super().__init__()
        self._module_manager = module_manager or ModuleManager()
        self._install_manager = install_manager or InstallManager()

    def _setup_install_manager(self):
        # FIXME: the modules list must to be readable from inside of InstallManager when needed
        # the modules needs to be passed to the InstallManager some other way
        # basically we need to be able to load modules from everywhere when we need them
        modules = self._module_manager.running_module_services
        self._install_manager.available_modules = modules

        # start and publish interface
        interface = InstallationInterface(self._install_manager)
        interface.publish(DBUS_BOSS_INSTALLATION_PATH)

    def publish(self):
        """Publish the boss."""
        DBus.publish_object(self, DBUS_BOSS_PATH)
        self._setup_install_manager()
        DBus.register_service(DBUS_BOSS_NAME)

    def run(self):
        """Run the boss's loop."""
        log.debug("Gather the modules.")
        self._module_manager.add_default_modules()
        self._module_manager.add_addon_modules()
        log.debug("Schedule publishing.")
        GLib.idle_add(self.publish)
        log.debug("Schedule startup of modules.")
        GLib.idle_add(self._module_manager.start_modules)
        log.info("starting mainloop")
        self._loop.run()

    def Quit(self):
        """Stop all modules and then stop the boss."""
        self._module_manager.stop_modules()
        super().stop_module()
