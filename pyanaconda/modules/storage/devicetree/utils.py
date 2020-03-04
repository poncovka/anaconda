#
# Utilities for the device tree module
#
# Copyright (C) 2020 Red Hat, Inc.
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
import time

from blivet.errors import StorageError
from blivet.formats import device_formats
from blivet.formats.fs import FS

from pyanaconda.anaconda_loggers import get_module_logger

log = get_module_logger(__name__)


def get_supported_filesystems():
    """Get the supported types of filesystems.

    :return: a list of filesystem classes
    """
    fs_types = []
    for cls in device_formats.values():
        obj = cls()

        supported_fs = (
                obj.supported and obj.formattable and
                (isinstance(obj, FS) or obj.type in ["biosboot", "prepboot", "swap"])
        )

        if supported_fs:
            fs_types.append(obj)

    return fs_types


def find_optical_media(devicetree):
    """Find all devices with mountable optical media.

    Search for devices identified as cdrom along with any other
    device that has an iso9660 filesystem. This will catch USB
    media created from ISO images.

    :param devicetree: an instance of a device tree
    :return: a list of devices
    """
    devices = []

    for device in devicetree.devices:
        if device.type != "cdrom" and device.format.type != "iso9660":
            continue

        if not device.controllable:
            continue

        devicetree.handle_format(None, device)
        if not hasattr(device.format, "mount"):
            # no mountable media
            continue

        devices.append(device)

    return devices


def find_mountable_partitions(devicetree):
    """Find all mountable partitions.

    :param devicetree: an instance of a device tree
    :return: a list of devices
    """
    devices = []

    for device in devicetree.devices:
        if device.type != "partition":
            continue

        if not device.format.exists:
            continue

        if not device.format.mountable:
            continue

        devices.append(device)

    return devices


def unlock_device(storage, device, passphrase):
    """Unlock a LUKS device.

    :param storage: an instance of the storage
    :param device: a device to unlock
    :param passphrase: a passphrase to use
    :return: True if success, otherwise False
    """
    # Set the passphrase.
    device.format.passphrase = passphrase

    try:
        # Unlock the device.
        device.setup()
        device.format.setup()
    except StorageError as err:
        log.error("Failed to unlock %s: %s", device.name, err)

        # Teardown the device.
        device.teardown(recursive=True)

        # Forget the wrong passphrase.
        device.format.passphrase = None

        return False
    else:
        # Save the passphrase.
        storage.save_passphrase(device)

        # Set the passphrase also to the original format of the device.
        device.original_format.passphrase = passphrase

        # Wait for the device.
        # Otherwise, we could get a message about no Linux partitions.
        time.sleep(2)

        # Update the device tree.
        storage.devicetree.populate()
        storage.devicetree.teardown_all()

        return True


def find_unconfigured_luks(storage):
    """Find all unconfigured LUKS devices.

    Returns a list of devices that require a passphrase
    for their configuration.

    :param storage: an instance of Blivet
    :return: a list of devices
    """
    devices = []

    for device in storage.devices:
        # Only LUKS devices.
        if not device.format.type == "luks":
            continue

        # Skip existing formats.
        if device.format.exists:
            continue

        # Skip formats with keys.
        if device.format.has_key:
            continue

        devices.append(device)

    return devices
