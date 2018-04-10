#
# Known DBus objects.
#
# Copyright (C) 2018  Red Hat, Inc.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from pyanaconda.dbus.identifier import DBusObjectIdentifier
from pyanaconda.modules.common.constants.namespaces import BOSS_NAMESPACE, STORAGE_NAMESPACE

BOSS_INSTALLATION = DBusObjectIdentifier(
    namespace=BOSS_NAMESPACE,
    basename="Installation"
)

BOOTLOADER = DBusObjectIdentifier(
    namespace=STORAGE_NAMESPACE,
    basename="Bootloader"
)

DISK_INITIALIZATION = DBusObjectIdentifier(
    namespace=STORAGE_NAMESPACE,
    basename="DiskInitialization"
)

DISK_SELECTION = DBusObjectIdentifier(
    namespace=STORAGE_NAMESPACE,
    basename="DiskSelection"
)
