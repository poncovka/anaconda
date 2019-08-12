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

from pyanaconda.modules.storage.partitioning import AutoPartitioningModule, \
    ManualPartitioningModule, CustomPartitioningModule, BlivetPartitioningModule, \
    InteractivePartitioningModule


class PartitioningFactory(object):
    """The partitioning factory."""

    def create_partitioning(self, method):
        """

        :param method: a partitioning method
        :return: a partitioning module
        """


        auto_part_module = AutoPartitioningModule()


        self._manual_part_module = ManualPartitioningModule()

        self._custom_part_module = CustomPartitioningModule()

        self._interactive_part_module = InteractivePartitioningModule()

        self._blivet_part_module = BlivetPartitioningModule()
