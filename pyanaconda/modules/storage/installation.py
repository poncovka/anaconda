#
# Installation tasks
#
# Copyright (C) 2019 Red Hat, Inc.
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
from blivet import callbacks

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.i18n import _
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.modules.common.task import Task
from pyanaconda.storage.installation import turn_on_filesystems, write_storage_configuration

log = get_module_logger(__name__)


__all__ = ["ActivateFilesystemsTask", "MountFilesystemsTask", "WriteConfigurationTask"]


class ActivateFilesystemsTask(Task):
    """Installation task for activation of the storage configuration."""

    def __init__(self, storage):
        """Create a new task."""
        super().__init__()
        self._storage = storage

    @property
    def name(self):
        return "Activate filesystems"

    def run(self):
        """Do the activation."""
        if conf.target.is_directory:
            log.debug("Don't activate file systems during "
                      "the installation to a directory.")
            return

        register = callbacks.create_new_callbacks_register(
            create_format_pre=self._report_message,
            resize_format_pre=self._report_message,
            wait_for_entropy=self._report_message
        )

        turn_on_filesystems(
            self._storage,
            callbacks=register
        )

    def _report_message(self, data):
        """Report a Blivet message."""
        self.report_progress(data.msg)


class MountFilesystemsTask(Task):
    """Installation task for mounting the filesystems."""

    def __init__(self, storage):
        """Create a new task."""
        super().__init__()
        self._storage = storage

    @property
    def name(self):
        return "Mount filesystems"

    def run(self):
        """Mount the filesystems."""
        self._storage.mount_filesystems()


class WriteConfigurationTask(Task):
    """Installation task for writing out the storage configuration."""

    def __init__(self, storage):
        """Create a new task."""
        super().__init__()
        self._storage = storage

    @property
    def name(self):
        return "Write the storage configuration"

    def run(self):
        """Mount the filesystems."""
        if conf.target.is_directory:
            log.debug("Don't write the storage configuration "
                      "during the installation to a directory.")
            return

        write_storage_configuration(self._storage)
