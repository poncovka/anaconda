#
# Support for DBus proxy.
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

__all__ = ["get_interface_names"]


def get_interface_names(proxy):
    """Get all interface names of a DBus proxy.

    Implementation of this method is very pydbus-specific.

    :param proxy: a DBus proxy
    :return: a list of interface names
    """
    return [cls.__name__ for cls in type(proxy).__bases__]
