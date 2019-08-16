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
from pyanaconda.modules.storage.devicetree.devicetree import DeviceTreeModule
from pyanaconda.modules.storage.devicetree.devicetree_interface import DeviceTreeInterface

__all__ = ["DeviceTreeModule", "publish_device_tree"]


def publish_device_tree(message_bus, namespace, device_tree, interface=DeviceTreeInterface):
    """Publish a device tree module on the given message bus.

    :param message_bus: a message bus
    :param namespace: a sequence of names
    :param device_tree: an instance of a DeviceTreeModule
    :param interface: an interface class
    :return: a DBus path of the published task
    """
    publishable = device_tree.get_publishable()
    object_path = interface.get_object_path(namespace)
    message_bus.publish_object(object_path, publishable)
    return object_path
