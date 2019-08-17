#
# Blivet partitioning module.
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
from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.dbus import DBus
from pyanaconda.modules.common.constants.objects import BLIVET_PARTITIONING
from pyanaconda.modules.storage.partitioning.base import PartitioningModule
from pyanaconda.modules.storage.partitioning.blivet_interface import \
    BlivetPartitioningInterface
from pyanaconda.modules.storage.partitioning.interactive_partitioning import \
    InteractivePartitioningTask
from pyanaconda.modules.storage.partitioning.validate import StorageValidateTask

log = get_module_logger(__name__)


class BlivetPartitioningModule(PartitioningModule):
    """The partitioning module for Blivet-GUI."""

    def __init__(self):
        super().__init__()
        self._storage_handler = None
        self._request_handler = None

    def publish(self):
        """Publish the module."""
        DBus.publish_object(BLIVET_PARTITIONING.object_path, BlivetPartitioningInterface(self))

    @property
    def storage_handler(self):
        """The handler of the storage.

        :return: an instance of BlivetStorageHandler
        :raises UnsupportedPartitioningError: if the handler cannot be created
        """
        if not self._storage_handler:
            from pyanaconda.modules.storage.partitioning.blivet_handler import BlivetStorageHandler
            self._storage_handler = BlivetStorageHandler()

        # Make sure that the handler always uses the current storage.
        self._storage_handler.storage = self.storage
        return self._storage_handler

    @property
    def request_handler(self):
        """The handler of the requests.

        :return: an instance of BlivetRequestHandler
        :raises UnsupportedPartitioningError: if the handler cannot be created
        """
        if not self._request_handler:
            from pyanaconda.modules.storage.partitioning.blivet_handler import BlivetRequestHandler
            self._request_handler = BlivetRequestHandler()

        # Make sure that the handler always uses the current storage handler.
        self._request_handler.blivet_utils = self.storage_handler
        return self._request_handler

    def send_request(self, data):
        """Send a request to the storage handler.

        :param data: a request data in bytes
        :return: a reply data in bytes
        """
        return self.request_handler.get_reply(data)

    def configure_with_task(self):
        """Complete the scheduled partitioning."""
        return InteractivePartitioningTask(self.storage)

    def validate_with_task(self):
        """Validate the scheduled partitions."""
        return StorageValidateTask(self.storage)
