#
# Known DBus interfaces.
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
from dasbus.identifier import DBusInterfaceIdentifier
from pyanaconda.modules.common.constants.namespaces import ANACONDA_NAMESPACE, \
    MODULES_NAMESPACE, USERS_NAMESPACE, PARTITIONING_NAMESPACE, DNF_NAMESPACE, \
    DEVICE_TREE_NAMESPACE, PAYLOAD_SOURCE_NAMESPACE


KICKSTART_MODULE = DBusInterfaceIdentifier(
    namespace=MODULES_NAMESPACE
)

USER = DBusInterfaceIdentifier(
    namespace=USERS_NAMESPACE,
    basename="User"
)

PARTITIONING = DBusInterfaceIdentifier(
    namespace=PARTITIONING_NAMESPACE
)

TASK = DBusInterfaceIdentifier(
    namespace=ANACONDA_NAMESPACE,
    basename="Task"
)

DEVICE_TREE_VIEWER = DBusInterfaceIdentifier(
    namespace=DEVICE_TREE_NAMESPACE,
    basename="Viewer"
)

DEVICE_TREE_HANDLER = DBusInterfaceIdentifier(
    namespace=DEVICE_TREE_NAMESPACE,
    basename="Handler"
)

DNF_HANDLER = DBusInterfaceIdentifier(
    namespace=DNF_NAMESPACE
)

PAYLOAD_SOURCE = DBusInterfaceIdentifier(
    namespace=PAYLOAD_SOURCE_NAMESPACE
)

PAYLOAD_SOURCE_LIVE_OS = DBusInterfaceIdentifier(
    namespace=PAYLOAD_SOURCE_NAMESPACE,
    basename="LiveOS"
)
