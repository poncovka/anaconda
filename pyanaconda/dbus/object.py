#
# Anaconda DBus objects.
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

from pyanaconda.dbus import DBus
from pyanaconda.dbus.observer import DBusObjectObserver


class DBusNamespace(object):
    """DBus namespace for services and objects."""

    def __init__(self, name, path, namespace=None):
        """Create a DBus namespace.

        :param name: a DBus name
        :param path: a DBus path
        :param namespace: a DBus namespace to use
        """
        self._name = namespace.DBUS_NAME + name if namespace else name
        self._path = namespace.DBUS_PATH + path if namespace else path

    @property
    def DBUS_NAME(self):
        """DBus name."""
        return self._name

    @property
    def DBUS_PATH(self):
        """DBus path."""
        return self._path

    @property
    def INTERFACE(self):
        """DBus interface name."""
        return self._name

    @property
    def ERROR(self):
        """DBus error name."""
        return self._name + ".Error"


class DBusObject(DBusNamespace):
    """Identification of a DBus object."""

    def publish_object(self, obj):
        DBus.publish_object(obj, self.DBUS_PATH)

    def register_service(self):
        DBus.register_service(self.DBUS_NAME)

    def get_proxy(self):
        return DBus.get_proxy(self.DBUS_NAME, self.DBUS_PATH)

    def get_observer(self):
        return DBusObjectObserver(self.DBUS_NAME, self.DBUS_PATH)


# General DBus Anaconda namespace.
ANACONDA_NAMESPACE = DBusNamespace(
    "org.fedoraproject.Anaconda",
    "org/fedoraproject/Anaconda"
)

# Anaconda task namespace.
ANACONDA_TASK = DBusNamespace(
    "/Task",
    ".Task",
    namespace=ANACONDA_NAMESPACE
)

# Kickstart modules namespace.
KICKSTART_MODULE = DBusNamespace(
    ".Modules",
    "/Modules",
    namespace=ANACONDA_NAMESPACE
)

# Kickstart addons namespace.
KICKSTART_ADDON = DBusNamespace(
    ".Addons",
    "/Addons",
    namespace=ANACONDA_NAMESPACE
)


# The boss.
BOSS = DBusObject(
    ".Boss",
    "/Boss",
    namespace=ANACONDA_NAMESPACE
)


# Installation manager.
BOSS_INSTALLATION = DBusObject(
    ".Installation",
    "/Installation",
    namespace=BOSS
)

# Anaconda manager.
BOSS_ANACONDA = DBusObject(
    ".Anaconda",
    "/Anaconda",
    namespace=BOSS
)

# Foo module.
FOO = DBusObject(
    ".Foo",
    "/Foo",
    namespace=KICKSTART_MODULE
)

# Bar module.
BAR = DBusObject(
    ".Bar",
    "/Bar",
    namespace=KICKSTART_MODULE
)

# Timezone module.
TIMEZONE = DBusObject(
    ".Timezone",
    "/Timezone",
    namespace=KICKSTART_MODULE
)

# Addon Baz.
BAZ = DBusObject(
    ".Baz",
    "/Baz",
    namespace=KICKSTART_ADDON
)

# List of Anaconda kickstart modules.
KICKSTART_MODULES_LIST = [
    FOO,
    BAR,
    TIMEZONE
]
