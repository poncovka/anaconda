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
# Red Hat Author(s): Jiri Konecny <jkonecny@redhat.com>
#
import unittest

from unittest.mock import Mock, patch, create_autospec

from tests.nosetests.pyanaconda_tests import check_task_creation, patch_dbus_publish_object

from pyanaconda.core.constants import INSTALL_TREE
from pyanaconda.modules.common.errors.payload import SourceSetupError
from pyanaconda.modules.common.task.task_interface import TaskInterface
from pyanaconda.modules.payload.base.initialization import PrepareSystemForInstallationTask, \
    CopyDriverDisksFilesTask, SetUpSourcesTask, TearDownSourcesTask
from pyanaconda.modules.payload.constants import SourceType
from pyanaconda.modules.payload.base.initialization import UpdateBLSConfigurationTask
from pyanaconda.modules.payload.base.installation import InstallFromImageTask
from pyanaconda.modules.payload.payloads.live_os.live_os import LiveOSHandlerModule
from pyanaconda.modules.payload.payloads.live_os.live_os_interface import LiveOSHandlerInterface
from pyanaconda.modules.payload.sources.live_os.live_os import LiveOSSourceModule


class LiveOSHandlerInterfaceTestCase(unittest.TestCase):

    def setUp(self):
        self.live_os_module = LiveOSHandlerModule()
        self.live_os_interface = LiveOSHandlerInterface(self.live_os_module)

    def _prepare_and_use_source(self):
        source = create_autospec(LiveOSSourceModule())
        source.image_path = "/test/path"
        source.type = SourceType.LIVE_OS_IMAGE
        source.is_ready.return_value = True

        self.live_os_module.set_sources([source])

        return source

    @patch("pyanaconda.modules.payload.payloads.live_os.live_os.get_dir_size")
    def space_required_properties_test(self, get_dir_size_mock):
        """Test Live OS SpaceRequired property."""
        get_dir_size_mock.return_value = 2

        self.assertEqual(self.live_os_interface.SpaceRequired, 2048)

    @patch("pyanaconda.modules.payload.payloads.live_os.live_os.get_kernel_version_list")
    def empty_kernel_version_list_test(self, get_kernel_version_list):
        """Test Live OS empty get kernel version list."""
        self.assertEqual(self.live_os_interface.GetKernelVersionList(), [])

        get_kernel_version_list.return_value = []
        kernel_list_callback = Mock()

        # pylint: disable=no-member
        self.live_os_interface.KernelVersionListChanged.connect(kernel_list_callback)
        self.live_os_interface.UpdateKernelVersionList()

        get_kernel_version_list.assert_called_once_with(INSTALL_TREE)

        self.assertEqual(self.live_os_interface.GetKernelVersionList(), [])
        kernel_list_callback.assert_called_once_with([])

    @patch("pyanaconda.modules.payload.payloads.live_os.live_os.get_kernel_version_list")
    def kernel_version_list_test(self, get_kernel_version_list):
        """Test Live OS get kernel version list."""
        kernel_list = ["kernel-abc", "magic-kernel.fc3000.x86_64", "sad-kernel"]
        get_kernel_version_list.return_value = kernel_list
        kernel_list_callback = Mock()

        # pylint: disable=no-member
        self.live_os_interface.KernelVersionListChanged.connect(kernel_list_callback)
        self.live_os_interface.UpdateKernelVersionList()

        get_kernel_version_list.assert_called_once_with(INSTALL_TREE)

        self.assertListEqual(self.live_os_interface.GetKernelVersionList(), kernel_list)
        kernel_list_callback.assert_called_once_with(kernel_list)

    @patch_dbus_publish_object
    def set_up_installation_sources_task_test(self, publisher):
        """Test Live OS is able to create a set up installation sources task."""
        self._prepare_and_use_source()

        task_path = self.live_os_interface.SetUpSourcesWithTask()

        check_task_creation(self, task_path, publisher, SetUpSourcesTask)

    @patch_dbus_publish_object
    def prepare_system_for_installation_task_test(self, publisher):
        """Test Live OS is able to create a prepare installation task."""
        self._prepare_and_use_source()

        task_path = self.live_os_interface.PreInstallWithTask()

        check_task_creation(self, task_path, publisher, PrepareSystemForInstallationTask)

    @patch_dbus_publish_object
    def prepare_system_for_installation_task_no_source_test(self, publisher):
        """Test Live OS prepare installation task with no source fail."""
        with self.assertRaises(SourceSetupError):
            self.live_os_interface.PreInstallWithTask()

    @patch_dbus_publish_object
    def tear_down_installation_source_task_test(self, publisher):
        """Test Live OS is able to create a tear down installation sources task."""
        self._prepare_and_use_source()

        task_path = self.live_os_interface.TearDownSourcesWithTask()

        check_task_creation(self, task_path, publisher, TearDownSourcesTask)

    @patch_dbus_publish_object
    def install_with_task_test(self, publisher):
        """Test Live OS install with tasks."""
        self._prepare_and_use_source()

        task_path = self.live_os_interface.InstallWithTask()

        check_task_creation(self, task_path, publisher, InstallFromImageTask)

    @patch_dbus_publish_object
    def install_with_task_no_source_test(self, publisher):
        """Test Live OS install with tasks with no source fail."""
        with self.assertRaises(SourceSetupError):
            self.live_os_interface.InstallWithTask()

    @patch_dbus_publish_object
    def post_install_with_tasks_test(self, publisher):
        """Test Live OS post installation configuration task."""
        task_classes = [
            UpdateBLSConfigurationTask,
            CopyDriverDisksFilesTask
        ]

        task_paths = self.live_os_interface.PostInstallWithTasks()

        # Check the number of installation tasks.
        task_number = len(task_classes)
        self.assertEqual(task_number, len(task_paths))
        self.assertEqual(task_number, publisher.call_count)

        # Check the tasks.
        for i in range(task_number):
            object_path, obj = publisher.call_args_list[i][0]
            self.assertEqual(object_path, task_paths[i])
            self.assertIsInstance(obj, TaskInterface)
            self.assertIsInstance(obj.implementation, task_classes[i])
