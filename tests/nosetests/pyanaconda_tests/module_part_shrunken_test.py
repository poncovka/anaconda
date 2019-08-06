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
# Red Hat Author(s): Vendula Poncova <vponcova@redhat.com>
#
import unittest
from unittest.mock import Mock

from pyanaconda.modules.storage.partitioning.shrunken_interface import \
    ShrunkenPartitioningInterface
from tests.nosetests.pyanaconda_tests import patch_dbus_publish_object, check_dbus_property, \
    check_task_creation

from pyanaconda.modules.common.constants.objects import SHRUNKEN_PARTITIONING
from pyanaconda.modules.storage.partitioning import ShrunkenPartitioningModule
from pyanaconda.modules.storage.partitioning.automatic_partitioning import \
    AutomaticPartitioningTask
from pyanaconda.modules.storage.partitioning.validate import StorageValidateTask


class ShrunkenPartitioningInterfaceTestCase(unittest.TestCase):
    """Test DBus interface of the shrunken module."""

    def setUp(self):
        """Set up the module."""
        self.module = ShrunkenPartitioningModule()
        self.interface = ShrunkenPartitioningInterface(self.module)

    def _test_dbus_property(self, *args, **kwargs):
        check_dbus_property(
            self,
            SHRUNKEN_PARTITIONING,
            self.interface,
            *args, **kwargs
        )

    @patch_dbus_publish_object
    def configure_with_task_test(self, publisher):
        """Test ConfigureWithTask."""
        self.module.on_storage_reset(Mock())
        task_path = self.interface.ConfigureWithTask()

        obj = check_task_creation(self, task_path, publisher, AutomaticPartitioningTask)

        self.assertEqual(obj.implementation._storage, self.module.storage)
        self.assertEqual(obj.implementation._request, self.module.request)

    @patch_dbus_publish_object
    def validate_with_task_test(self, publisher):
        """Test ValidateWithTask."""
        self.module.on_storage_reset(Mock())
        task_path = self.interface.ValidateWithTask()

        obj = check_task_creation(self, task_path, publisher, StorageValidateTask)

        self.assertEqual(obj.implementation._storage, self.module.storage)
