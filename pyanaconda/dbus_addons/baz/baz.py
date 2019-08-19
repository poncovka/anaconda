# baz.py
# Example DBus addon.
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
from time import sleep

from pyanaconda.dbus import DBus
from pyanaconda.dbus_addons.baz.baz_interface import BazInterface, BazCalculationTaskInterface
from pyanaconda.modules.common.base import KickstartModule
from pyanaconda.modules.common.containers import TaskContainer
from pyanaconda.modules.common.constants.services import BAZ
from pyanaconda.modules.common.task import Task

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)


class Baz(KickstartModule):
    """The Baz module."""

    def publish(self):
        """Publish the module."""
        TaskContainer.set_namespace(BAZ.namespace)
        DBus.publish_object(BAZ.object_path, BazInterface(self))
        DBus.register_service(BAZ.service_name)

    def install_with_tasks(self):
        """Return installation tasks."""
        return [BazTask()]

    def calculate_with_task(self):
        """Return a calculation task."""
        return BazCalculationTask()


class BazTask(Task):
    """The Baz task."""

    @property
    def name(self):
        return "Configure Baz"

    @property
    def steps(self):
        return 5

    def run(self):
        self.report_progress("Working..", step_size=1)
        sleep(5)

        self.report_progress("Taking a nap...", step_size=1)
        sleep(5)

        self.report_progress("Finishing...", step_size=1)
        sleep(5)


class BazCalculationTask(Task):
    """The task that calculates something."""

    @property
    def name(self):
        return "Calculate something"

    def for_publication(self):
        return BazCalculationTaskInterface(self)

    def run(self):
        result = 0

        for i in range(3):
            result = result + i
            sleep(5)

        return result
