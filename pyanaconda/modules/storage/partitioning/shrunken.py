#
# The shrunken partitioning module
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
from pyanaconda.modules.common.constants.objects import SHRUNKEN_PARTITIONING
from pyanaconda.modules.storage.partitioning import AutoPartitioningModule
from pyanaconda.modules.storage.partitioning.automatic_partitioning import \
    AutomaticPartitioningTask
from pyanaconda.modules.storage.partitioning.interactive_interface import \
    InteractivePartitioningInterface
from pyanaconda.modules.storage.partitioning.validate import StorageValidateTask

log = get_module_logger(__name__)


class ShrunkenPartitioningModule(AutoPartitioningModule):
    """The shrunken partitioning module."""

    def publish(self):
        """Publish the module."""
        DBus.publish_object(
            SHRUNKEN_PARTITIONING.object_path,
            InteractivePartitioningInterface(self)
        )

    def configure_with_task(self):
        """Schedule the partitioning actions."""
        task = AutomaticPartitioningTask(self.storage, self.request)
        path = self.publish_task(SHRUNKEN_PARTITIONING.namespace, task)
        return path

    def validate_with_task(self):
        """Validate the scheduled partitions."""
        task = StorageValidateTask(self.storage)
        path = self.publish_task(SHRUNKEN_PARTITIONING.namespace, task)
        return path
