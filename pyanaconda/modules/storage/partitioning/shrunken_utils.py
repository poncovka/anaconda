#
# Utilities for the shrunken partitioning module
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
from blivet.size import Size

from pyanaconda.core.constants import RESIZE_ACTION_PRESERVE, RESIZE_ACTION_SHRINK, \
    RESIZE_ACTION_DELETE


def schedule_resize_actions(storage, request):
    """Schedule resize actions for the given request.

    :param storage: an instance of Blivet
    :param ResizeRequest request: a resize request
    """
    # Resolve the device.
    device = storage.devicetree.resolve_device(request.device_spec)

    if not device:
        raise ValueError("Unknown device '{}'.".format(request.device_spec))

    # Nothing to to.
    if request.action == RESIZE_ACTION_PRESERVE:
        return

    # Remove the device.
    if request.action == RESIZE_ACTION_DELETE:
        recursive_remove(storage, device)
        return

    # Shrink the device.
    if request.action == RESIZE_ACTION_SHRINK:
        # Nothing to change.
        if int(device.size) == int(request.size):
            return

        if device.resizable:
            aligned = device.align_target_size(Size(request.size))
            storage.resize_device(device, aligned)
        else:
            recursive_remove(storage, device)


def recursive_remove(storage, device):
    """Remove a device.

    Remove a device, or if it has protected children, just
    remove the unprotected children.

    :param storage: an instance of Blivet
    :param device: a device to remove
    """
    if device.protected:
        return

    if not any(d.protected for d in device.children):
        # No protected children, remove the device
        storage.recursive_remove(device)
    else:
        # Only remove unprotected children
        for child in (d for d in device.children if not d.protected):
            storage.recursive_remove(child)
