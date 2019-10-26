#
# Interface templates for Anaconda modules.
#
# Copyright (C) 2018 Red Hat, Inc.
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
from abc import ABC

from dasbus.property import PropertiesInterface


class InterfaceTemplate(ABC):
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

    @dbus_interface("org.myproject.X")
    class InterfaceX(InterfaceTemplate):
        def DoSomething(self) -> Str:
            return self.implementation.do_something()

    class X(object):
        def do_something(self):
            return "Done!"

    x = X()
    i = InterfaceX(x)

    DBus.publish_object("/org/myproject/X", i)
    """

    def __init__(self, implementation):
        """Create a publishable DBus object.

        :param implementation: an implementation of this interface
        """
        self._implementation = implementation
        self.connect_signals()

    @property
    def implementation(self):
        """Return the implementation of this interface.

        :return: an implementation
        """
        return self._implementation

    def connect_signals(self):
        """Interconnect the signals.

        You should connect the emit methods of the interface
        signals to the signals of the implementation. Every
        time the implementation emits a signal, this interface
        reemits the signal on DBus.
        """
        pass


class AdvancedInterfaceTemplate(InterfaceTemplate, PropertiesInterface):
    """Advanced template for DBus interface.

    The interface provides the support for the standard interface
    org.freedesktop.DBus.Properties.

    Usage:

        def connect_signals(self):
            super().connect_signals()

            self.implementation.module_properties_changed.connect(self.flush_changes)
            self.watch_property("X", self.implementation.x_changed)

        @property
        def X(self, x) -> Int:
            return self.implementation.x

        @emits_properties_changed
        def SetX(self, x: Int):
            self.implementation.set_x(x)

    """

    def __init__(self, implementation):
        PropertiesInterface.__init__(self)
        InterfaceTemplate.__init__(self, implementation)

    def watch_property(self, property_name, signal):
        """Watch a DBus property.

        Report a change when the property is changed.

        :param property_name: a name of a DBus property
        :param signal: a signal that emits when the property is changed
        """
        self._properties_changes.check_property(property_name)
        signal.connect(lambda *args, **kwargs: self.report_changed_property(property_name))


class ModuleInterfaceTemplate(AdvancedInterfaceTemplate):
    """The DBus interface template for a module.

    The template should be used to create DBus interfaces
    for instances of BaseModule.
    """

    def connect_signals(self):
        """Connect the signals."""
        self.implementation.module_properties_changed.connect(self.flush_changes)


class KickstartModuleInterfaceTemplate(ModuleInterfaceTemplate):
    """The DBus interface template for a kickstart module.

    The template should be used to create DBus interfaces
    for instances of KickstartBaseModule.
    """
    pass
