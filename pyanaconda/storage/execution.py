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
from pyanaconda.modules.common.constants.objects import AUTO_PARTITIONING, MANUAL_PARTITIONING
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.modules.storage.partitioning.automatic_partitioning import \
    AutomaticPartitioningTask
from pyanaconda.modules.storage.partitioning.custom_partitioning import CustomPartitioningTask
from pyanaconda.modules.storage.partitioning.interactive_partitioning import \
    InteractivePartitioningTask
from pyanaconda.modules.storage.partitioning.manual_partitioning import ManualPartitioningTask

log = get_module_logger(__name__)

__all__ = ["do_kickstart_storage"]


def do_kickstart_storage(storage, data):
    """Setup storage state from the kickstart data.

    :param storage: an instance of the Blivet's storage object
    :param data: an instance of kickstart data or None
    """
    if STORAGE.get_proxy(AUTO_PARTITIONING).Enabled:
        task = AutomaticPartitioningTask(storage)
    elif STORAGE.get_proxy(MANUAL_PARTITIONING).Enabled:
        task = ManualPartitioningTask(storage)
    else:
        task = CustomPartitioningTask(storage, data)

    task.run()


def do_interactive_storage(storage):
    """Setup storage state with the interactive partitioning.

    :param storage: an instance of the Blivet's storage object
    """
    task = InteractivePartitioningTask(storage)
    task.run()
