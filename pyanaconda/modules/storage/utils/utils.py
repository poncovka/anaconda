#
# Storage utils module
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
from pyanaconda.dbus import DBus
from pyanaconda.modules.common.base import KickstartBaseModule
from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.modules.common.constants.objects import STORAGE_UTILS
from pyanaconda.modules.common.errors.storage import UnavailableStorageError
from pyanaconda.modules.storage.utils.utils_interface import StorageUtilsInterface

log = get_module_logger(__name__)


class StorageUtilsModule(KickstartBaseModule):
    """The storage utils module."""

    def __init__(self):
        super().__init__()
        self._storage = None

    @property
    def storage(self):
        """The storage model.

        :return: an instance of Blivet
        """
        if self._storage is None:
            raise UnavailableStorageError()

        return self._storage

    def on_storage_reset(self, storage):
        """Keep the instance of the current storage."""
        self._storage = storage

    def publish(self):
        """Publish the module."""
        DBus.publish_object(STORAGE_UTILS.object_path, StorageUtilsInterface(self))
