#
# Copyright (C) 2017  Red Hat, Inc.
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

import gi
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gio


class ExampleTestCase(unittest.TestCase):

    SERVICES_PATH = ""

    def setUp(self):
        # Possible flags: NONE, READABLE, WRITABLE, CONSTRUCT_ONLY
        self.dbus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
        self.dbus.add_service_dir(SERVICES_PATH)
        self.dbus.up()

    def tearDown(self):
        self.dbus.down()

    def dbus_test(self):
        self.assertTrue(self.dbus)
        self.assertTrue(self.dbus.get_bus_address())
