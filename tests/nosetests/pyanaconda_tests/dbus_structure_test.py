#
# Copyright (C) 2018  Red Hat, Inc.
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

from pyanaconda.dbus.structure import DBusStructure


class DBusStructureTestCase(unittest.TestCase):
    """Test the DBus structure support."""

    def empty_structure_test(self):
        """Test empty structure."""
        class EmptyData(object):
            pass

        class EmptyStructure(DBusStructure[EmptyData]):

            fields = {}

            @classmethod
            def create_data(cls):
                return EmptyData()

        self.assertEqual({}, EmptyStructure.from_data(EmptyData()))
        self.assertIsInstance(EmptyStructure.to_data({}), EmptyData)

        in_data = EmptyData()
        out_data = EmptyStructure.to_data({}, in_data)
        self.assertEqual(in_data, out_data)
