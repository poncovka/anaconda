#
# Copyright (C) 2021 Red Hat, Inc.
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
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.modules.common.task import Task
from pyanaconda.modules.payloads.payload.live_image.installation import InstallFromImageTask
from pyanaconda.modules.payloads.payload.live_image.utils import get_kernel_version_list

__all__ = ["InstallLiveOSTask"]


class InstallLiveOSTask(Task):
    """Task for the complete live OS installation."""

    def __init__(self, sysroot, mount_point):
        """Create a new task.

        :param str sysroot: a path to the system root
        :param str mount_point: a mount point of an image
        """
        super().__init__()
        self._sysroot = sysroot
        self._mount_point = mount_point
        self._kernel_version_list = []

    @property
    def name(self):
        """The name of the task."""
        return "Install a Live OS image"

    def run(self):
        """Run the task.

        :return: a list of kernel versions
        """
        self._collect_kernels()
        self._install_image()

        return self._kernel_version_list

    def _install_image(self):
        """Install the content of the image."""
        task = InstallFromImageTask(
            sysroot=conf.target.system_root,
            mount_point=self._mount_point
        )
        self._run_task(task)

    def _collect_kernels(self):
        """Collect the kernel version list."""
        self._kernel_version_list = get_kernel_version_list(
            self._mount_point
        )

    def _run_task(self, task):
        """Run a subtask."""
        task.progress_changed_signal.connect(
            self._handle_progress_changed
        )
        return task.run()

    def _handle_progress_changed(self, step, message):
        """Handle a progress report of a subtask."""
        self.report_progress(message)
