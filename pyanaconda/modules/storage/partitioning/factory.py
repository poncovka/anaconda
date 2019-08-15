#
# The partitioning factory.
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
from pyanaconda.modules.storage.partitioning.constants import PartitioningMethod

__all__ = ["PartitioningFactory"]


class PartitioningFactory(object):
    """The partitioning factory."""

    @staticmethod
    def create_partitioning(method: PartitioningMethod):
        """Create a partitioning module.

        :param method: a partitioning method
        :return: a partitioning module
        """
        if method is PartitioningMethod.AUTOMATIC:
            from pyanaconda.modules.storage.partitioning.automatic import AutoPartitioningModule
            return AutoPartitioningModule()

        if method is PartitioningMethod.MANUAL:
            from pyanaconda.modules.storage.partitioning.manual import ManualPartitioningModule
            return ManualPartitioningModule()

        if method is PartitioningMethod.CUSTOM:
            from pyanaconda.modules.storage.partitioning.custom import CustomPartitioningModule
            return CustomPartitioningModule()

        if method is PartitioningMethod.INTERACTIVE:
            from pyanaconda.modules.storage.partitioning.interactive import \
                InteractivePartitioningModule
            return InteractivePartitioningModule()

        if method is PartitioningMethod.BLIVET:
            from pyanaconda.modules.storage.partitioning.blivet import BlivetPartitioningModule
            return BlivetPartitioningModule()

        raise ValueError("Unknown partitioning method: %s", method)
