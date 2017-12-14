#
# template.py: Templates for DBus objects.
#
# Copyright (C) 2017  Red Hat, Inc.  All rights reserved.
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

__all__ = ["InterfaceTemplate"]


class InterfaceTemplate(object):
    """Template for DBus interface.

    This template uses a software design pattern called proxy.

    This class provides a recommended way how to define DBus interfaces
    and create publishable DBus objects. The class that defines a DBus
    interface should inherit this class and be decorated with @dbus_class
    or @dbus_interface decorator. The implementation of this interface will
    be provided by a separate object called implementation. Therefore the
    methods of this class should call the methods of the implementation,
    the signals should be connected to the signals of the implementation
    and the getters and setters of properties should access the properties
    of the implementation.

    Example:

    @dbus_interface("org.myproject.InterfaceX")
    class InterfaceX(InterfaceTemplate):
        def DoSomething(self) -> Str:
            return self.implementation.do_something()

    class X(object):
        def do_something(self):
            return "Done!"

    x = X()
    i = InterfaceX(x)
    i.publish("org/myproject/X/1")

    """

    def __init__(self, implementation):
        """Create a publishable DBus object.

        :param implementation: an implementation of this interface
        """
        self._implementation = implementation
        self._object_path = None
        self.connect_signals()

    @property
    def implementation(self):
        """Return the implementation of this interface.

        :return: an implementation
        """
        return self._implementation

    @property
    def object_path(self):
        """Return an object path.

        If this object wasn't published, it returns None.

        :return: a DBus path or None
        """
        return self._object_path

    def connect_signals(self):
        """Interconnect the signals.

        You should connect the emit methods of the interface
        signals to the signals of the implementation. Every
        time the implementation emits a signal, this interface
        reemits the signal on DBus.
        """
        pass

    def publish(self, object_path):
        """Publish the object on DBus.

        :type object_path: a DBus path of the object
        """
        DBus.publish_object(self, object_path)
        self._object_path = object_path
