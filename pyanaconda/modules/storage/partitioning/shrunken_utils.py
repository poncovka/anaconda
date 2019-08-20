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
