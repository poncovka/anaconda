#
# Copyright (C) 2019  Red Hat, Inc.
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
import tempfile
import unittest
from unittest.mock import Mock

from pyanaconda.core.constants import DEFAULT_LANG
from dasbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.modules.boss.boss import Boss
from pyanaconda.modules.boss.boss_interface import BossInterface
from pyanaconda.modules.boss.module_manager.start_modules import StartModulesTask
from tests.nosetests.pyanaconda_tests import patch_dbus_publish_object, check_task_creation


class BossInterfaceTestCase(unittest.TestCase):
    """Test DBus interface for the Boss module."""

    def setUp(self):
        """Set up the module."""
        self.module = Boss()
        self.interface = BossInterface(self.module)

    @patch_dbus_publish_object
    def start_modules_with_task_test(self, publisher):
        """Test StartModulesWithTask."""
        task_path = self.interface.StartModulesWithTask()
        task_proxy = check_task_creation(self, task_path, publisher, StartModulesTask)
        task = task_proxy.implementation

        callback = Mock()
        self.module._module_manager.module_observers_changed.connect(callback)

        observers = [Mock(), Mock(), Mock()]
        task._set_result(observers)
        task.succeeded_signal.emit()
        callback.assert_called_once_with(observers)

    def read_kickstart_file_test(self):
        """Test ReadKickstartFile."""
        with tempfile.NamedTemporaryFile("r+") as f:
            report = self.interface.ReadKickstartFile(f.name)

        self.assertEqual(report, {
            "error-messages": get_variant(List[Structure], []),
            "warning-messages": get_variant(List[Structure], [])
        })

    def generate_kickstart_test(self):
        """Test GenerateKickstart."""
        self.assertEqual(self.interface.GenerateKickstart(), "")

    def set_locale_test(self):
        """Test SetLocale."""
        self.assertEqual(self.interface.SetLocale(DEFAULT_LANG), None)

    def quit_test(self):
        """Test Quit."""
        self.assertEqual(self.interface.Quit(), None)
