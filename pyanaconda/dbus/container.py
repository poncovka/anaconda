#
# Support for object containers
#
# Copyright (C) 2019  Red Hat, Inc.  All rights reserved.
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
from pyanaconda.dbus.namespace import get_dbus_path
from pyanaconda.dbus.publishable import Publishable
from pyanaconda.dbus.typing import ObjPath

__all__ = ["DBusContainerError", "DBusContainer"]


class DBusContainerError(Exception):
    """General exception for DBus container errors."""
    pass


class DBusContainer(object):
    """The container of DBus objects."""

    def __init__(self, namespace, basename, message_bus=DBus):
        """Create a new container.

        :param namespace: a sequence of names
        :param basename: a string with the base name
        :param message_bus: a message bus
        """
        self._message_bus = message_bus
        self._namespace = namespace
        self._basename = basename

        self._container = {}
        self._published = set()
        self._path_counter = 0

    def to_object_path(self, obj: Publishable) -> ObjPath:
        """Return a DBus path of the object.

        :param obj: an object to be published
        :return: a DBus path of the published object
        """
        if not isinstance(obj, Publishable):
            raise TypeError("The object is not publishable.")

        if not self._is_object_published(obj):
            self._publish_object(obj)

        return self._find_object_path(obj)

    def from_object_path(self, object_path: ObjPath) -> Publishable:
        """Return a published object.

        :param object_path: a DBus path of a published object
        :return: a published object
        """
        return self._find_object(object_path)

    def _is_object_published(self, obj):
        """Is the given object published?

        :param obj: an object
        :return: True if the object is published, otherwise False
        """
        return id(obj) in self._published

    def _publish_object(self, obj):
        """Publish the given object.

        :param obj: an object to publish
        :return: an object path
        """
        object_path = self._generate_object_path()

        self._message_bus.publish_object(
            object_path,
            obj.get_publishable()
        )

        self._container[object_path] = obj
        self._published.add(id(obj))
        return object_path

    def _find_object_path(self, obj):
        """Find a DBus path of the object.

        :param obj: a published object
        :return: a DBus path
        :raise: DBusContainerError if no object path is found
        """
        for object_path, found_obj in self._container.items():
            if found_obj is obj:
                return object_path

        raise DBusContainerError("Unknown object: %s", obj)

    def _find_object(self, object_path):
        """Find an object by its DBus path.

        :param object_path: a DBus path
        :return: a published object
        :raise: DBusContainerError if no object is found
        """
        found_path = self._container.get(object_path)

        if not found_path:
            raise DBusContainerError("Unknown DBus path: %s", object_path)

        return found_path

    def _generate_object_path(self):
        """Generate a unique object path.

        This method is not thread safe.

        :return: a unique object path
        """
        self._path_counter += 1

        return get_dbus_path(
            *self._namespace,
            self._basename,
            str(self._path_counter)
        )
