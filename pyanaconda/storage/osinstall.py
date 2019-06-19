#
# Copyright (C) 2009-2017  Red Hat, Inc.
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
# Red Hat Author(s): David Lehman <dlehman@redhat.com>
#

"""This module provides storage functions related to OS installation."""

import os

from blivet.blivet import Blivet
from blivet.devices import BTRFSSubVolumeDevice
from blivet.formats import get_format
from blivet.size import Size
from blivet.devicelibs.crypto import DEFAULT_LUKS_VERSION

from pyanaconda.core import util
from pyanaconda.bootloader import get_bootloader
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.core.constants import shortProductName
from pyanaconda.storage.fsset import FSSet
from pyanaconda.storage.utils import download_escrow_certificate, find_live_backing_device
from pyanaconda.storage.root import find_existing_installations
from pyanaconda.modules.common.constants.services import NETWORK

import logging
log = logging.getLogger("anaconda.storage")


class InstallerStorage(Blivet):
    """ Top-level class for managing installer-related storage configuration. """

    def __init__(self):
        super().__init__()
        self.protected_devices = []
        self._escrow_certificates = {}
        self._default_boot_fstype = None
        self._bootloader = None
        self.__luks_devs = {}
        self.fsset = FSSet(self.devicetree)
        self._short_product_name = shortProductName
        self._default_luks_version = DEFAULT_LUKS_VERSION

    @property
    def bootloader(self):
        if self._bootloader is None:
            self._bootloader = get_bootloader()

        return self._bootloader

    @property
    def boot_device(self):
        root_device = self.mountpoints.get("/")
        dev = self.mountpoints.get("/boot", root_device)
        return dev

    @property
    def default_boot_fstype(self):
        """The default filesystem type for the boot partition."""
        if self._default_boot_fstype:
            return self._default_boot_fstype

        return self.bootloader.stage2_format_types[0]

    def set_default_boot_fstype(self, newtype):
        """ Set the default /boot fstype for this instance.

            Raise ValueError on invalid input.
        """
        log.debug("trying to set new default /boot fstype to '%s'", newtype)
        # This will raise ValueError if it isn't valid
        self._check_valid_fstype(newtype)
        self._default_boot_fstype = newtype

    @property
    def default_luks_version(self):
        """The default LUKS version."""
        return self._default_luks_version

    def set_default_luks_version(self, version):
        """Set the default LUKS version.

        :param version: a string with LUKS version
        :raises: ValueError on invalid input
        """
        log.debug("trying to set new default luks version to '%s'", version)
        self._check_valid_luks_version(version)
        self._default_luks_version = version

    def _check_valid_luks_version(self, version):
        get_format("luks", luks_version=version)

    def get_fstype(self, mountpoint=None):
        """ Return the default filesystem type based on mountpoint. """
        fstype = super().get_fstype(mountpoint=mountpoint)

        if mountpoint == "/boot":
            fstype = self.default_boot_fstype

        return fstype

    def get_escrow_certificate(self, url):
        """Get the escrow certificate.

        :param url: an URL of the certificate
        :return: a content of the certificate
        """
        if not url:
            return None

        certificate = self._escrow_certificates.get(url, None)

        if not certificate:
            certificate = download_escrow_certificate(url)
            self._escrow_certificates[url] = certificate

        return certificate

    @property
    def mountpoints(self):
        return self.fsset.mountpoints

    @property
    def root_device(self):
        return self.fsset.root_device

    def get_file_system_free_space(self, mount_points=("/", "/usr")):
        """Get total file system free space on the given mount points.

        Calculates total free space in / and /usr, by default.

        :param mount_points: a list of mount points
        :return: a total size
        """
        free = Size(0)
        btrfs_volumes = []

        for mount_point in mount_points:
            device = self.mountpoints.get(mount_point)
            if not device:
                continue

            # don't count the size of btrfs volumes repeatedly when multiple
            # subvolumes are present
            if isinstance(device, BTRFSSubVolumeDevice):
                if device.volume in btrfs_volumes:
                    continue
                else:
                    btrfs_volumes.append(device.volume)

            if device.format.exists:
                free += device.format.free
            else:
                free += device.format.free_space_estimate(device.size)

        return free

    def get_disk_free_space(self, disks=None):
        """Get total free space on the given disks.

        Calculates free space available for use.

        :param disks: a list of disks or None
        :return: a total size
        """
        # Use all disks in the device tree by default.
        if disks is None:
            disks = self.disks

        # Get the dictionary of free spaces for each disk.
        snapshot = self.get_free_space(disks)

        # Calculate the total free space.
        return sum((disk_free for disk_free, fs_free in snapshot.values()), Size(0))

    def get_disk_reclaimable_space(self, disks=None):
        """Get total reclaimable space on the given disks.

        Calculates free space unavailable but reclaimable
        from existing partitions.

        :param disks: a list of disks or None
        :return: a total size
        """
        # Use all disks in the device tree by default.
        if disks is None:
            disks = self.disks

        # Get the dictionary of free spaces for each disk.
        snapshot = self.get_free_space(disks)

        # Calculate the total reclaimable free space.
        return sum((fs_free for disk_free, fs_free in snapshot.values()), Size(0))

    def reset(self, cleanup_only=False):
        """ Reset storage configuration to reflect actual system state.

            This will cancel any queued actions and rescan from scratch but not
            clobber user-obtained information like passphrases, iscsi config, &c

            :keyword cleanup_only: prepare the tree only to deactivate devices
            :type cleanup_only: bool

            See :meth:`devicetree.Devicetree.populate` for more information
            about the cleanup_only keyword argument.
        """
        # set up the disk images
        if conf.target.is_image:
            self.setup_disk_images()

        # save passphrases for luks devices so we don't have to reprompt
        for device in self.devices:
            if device.format.type == "luks" and device.format.exists:
                self.save_passphrase(device)

        super().reset(cleanup_only=cleanup_only)

        self.fsset = FSSet(self.devicetree)

        # Clear out attributes that refer to devices that are no longer in the tree.
        self.bootloader.reset()

        self._mark_protected_devices()

        self.roots = []
        self.roots = find_existing_installations(self.devicetree)
        self.dump_state("initial")

    def _mark_protected_devices(self):
        """Mark protected devices.

        If a device is protected, mark it as such now. Once the tree
        has been populated, devices' protected attribute is how we will
        identify protected devices.
        """
        protected = []

        # Resolve the protected device specs to devices.
        for spec in self.protected_devices:
            dev = self.devicetree.resolve_device(spec)

            if dev is not None:
                log.debug("Protected device spec %s resolved to %s.", spec, dev.name)
                protected.append(dev)

        # Find the live backing device and its parents.
        live_device_name = find_live_backing_device()

        if live_device_name:
            log.debug("Resolved live device to %s.", live_device_name)
            dev = self.devicetree.get_device_by_name(live_device_name, hidden=True)
            protected.append(dev)
            protected.extend(dev.parents)

        # Mark the collected devices as protected.
        for dev in protected:
            log.debug("Marking device %s as protected.", dev.name)
            dev.protected = True

    def protect_devices(self, protected_names):
        """Protect given devices.

        :param protected_names: a list of device names
        """
        protected = set(protected_names)
        unprotected = set(self.protected_devices)

        # Mark unprotected devices.
        # Skip devices that should stay protected.
        for spec in unprotected - protected:
            device = self.devicetree.resolve_device(spec)

            if device:
                log.debug("Marking device %s as unprotected.", device.name)
                device.protected = False

        # Mark protected devices.
        # Skip devices that are already protected.
        for spec in protected - unprotected:
            device = self.devicetree.resolve_device(spec)

            if device:
                log.debug("Marking device %s as protected.", device.name)
                device.protected = True

        # Update the list.
        self.protected_devices = protected_names

    def empty_device(self, device):
        empty = True
        if device.partitioned:
            partitions = device.children
            empty = all([p.is_magic for p in partitions])
        else:
            empty = (device.format.type is None)

        return empty

    @property
    def usable_disks(self):
        """Disks that can be used for the installation.

        :return: a list of disks
        """
        # Get all devices.
        devices = self.devicetree.devices

        # Add the hidden devices.
        if conf.target.is_image:
            devices += [
                d for d in self.devicetree._hidden
                if d.name in self.devicetree.disk_images
            ]
        else:
            devices += self.devicetree._hidden

        # Filter out the usable disks.
        disks = []
        for d in devices:
            if d.is_disk and not d.format.hidden and not d.protected:
                # Unformatted DASDs are detected with a size of 0, but they should
                # still show up as valid disks if this function is called, since we
                # can still use them; anaconda will know how to handle them, so they
                # don't need to be ignored anymore.
                if d.type == "dasd":
                    disks.append(d)
                elif d.size > 0 and d.media_present:
                    disks.append(d)

        # Remove duplicate names from the list.
        return sorted(set(disks), key=lambda d: d.name)

    def select_disks(self, selected_names):
        """Select disks that should be used for the installation.

        Hide usable disks that are not selected.

        :param selected_names: a list of disk names
        """
        for disk in self.usable_disks:
            if disk.name not in selected_names:
                if disk in self.devices:
                    self.devicetree.hide(disk)
            else:
                if disk not in self.devices:
                    self.devicetree.unhide(disk)

    @property
    def unused_devices(self):
        used_devices = []
        for root in self.roots:
            for device in list(root.mounts.values()) + root.swaps:
                if device not in self.devices:
                    continue

                used_devices.extend(device.ancestors)

        for new in [d for d in self.devicetree.leaves if not d.format.exists]:
            if new.format.mountable and not new.format.mountpoint:
                continue

            used_devices.extend(new.ancestors)

        for device in self.partitions:
            if getattr(device, "is_logical", False):
                extended = device.disk.format.extended_partition.path
                used_devices.append(self.devicetree.get_device_by_path(extended))

        used = set(used_devices)
        _all = set(self.devices)
        return list(_all.difference(used))

    def _get_hostname(self):
        """Return a hostname."""
        ignored_hostnames = {None, "", 'localhost', 'localhost.localdomain'}

        network_proxy = NETWORK.get_proxy()
        hostname = network_proxy.Hostname

        if hostname in ignored_hostnames:
            hostname = network_proxy.GetCurrentHostname()

        if hostname in ignored_hostnames:
            hostname = None

        return hostname

    def _get_container_name_template(self, prefix=None):
        """Return a template for suggest_container_name method."""
        prefix = prefix or ""  # make sure prefix is a string instead of None

        # try to create a device name incorporating the hostname
        hostname = self._get_hostname()

        if hostname:
            template = "%s_%s" % (prefix, hostname.split('.')[0].lower())
            template = self.safe_device_name(template)
        else:
            template = prefix

        if conf.target.is_image:
            template = "%s_image" % template

        return template

    def turn_on_swap(self):
        self.fsset.turn_on_swap(root_path=util.getSysroot())

    def mount_filesystems(self, read_only=None, skip_root=False):
        self.fsset.mount_filesystems(root_path=util.getSysroot(),
                                     read_only=read_only, skip_root=skip_root)

    def umount_filesystems(self, swapoff=True):
        self.fsset.umount_filesystems(swapoff=swapoff)

    def parse_fstab(self, chroot=None):
        self.fsset.parse_fstab(chroot=chroot)

    def mk_dev_root(self):
        self.fsset.mk_dev_root()

    def create_swap_file(self, device, size):
        self.fsset.create_swap_file(device, size)

    def make_mtab(self, chroot=None):
        path = "/etc/mtab"
        target = "/proc/self/mounts"
        chroot = chroot or util.getSysroot()
        path = os.path.normpath("%s/%s" % (chroot, path))

        if os.path.islink(path):
            # return early if the mtab symlink is already how we like it
            current_target = os.path.normpath(os.path.dirname(path) +
                                              "/" + os.readlink(path))
            if current_target == target:
                return

        if os.path.exists(path):
            os.unlink(path)

        os.symlink(target, path)

    def add_fstab_swap(self, device):
        """
        Add swap device to the list of swaps that should appear in the fstab.

        :param device: swap device that should be added to the list
        :type device: blivet.devices.StorageDevice instance holding a swap format

        """

        self.fsset.add_fstab_swap(device)

    def remove_fstab_swap(self, device):
        """
        Remove swap device from the list of swaps that should appear in the fstab.

        :param device: swap device that should be removed from the list
        :type device: blivet.devices.StorageDevice instance holding a swap format

        """

        self.fsset.remove_fstab_swap(device)

    def set_fstab_swaps(self, devices):
        """
        Set swap devices that should appear in the fstab.

        :param devices: iterable providing devices that should appear in the fstab
        :type devices: iterable providing blivet.devices.StorageDevice instances holding
                       a swap format

        """

        self.fsset.set_fstab_swaps(devices)
