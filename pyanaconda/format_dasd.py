#
# Copyright (C) 2017  Red Hat, Inc.
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
# Red Hat Author(s): Vendula Poncova <vponcova@redhat.com>
#

import gi

gi.require_version("BlockDev", "2.0")
from gi.repository import BlockDev as blockdev

from blivet import arch
from blivet.osinstall import storage_initialize

from pyanaconda.flags import flags
from pyanaconda.ui.lib.disks import getDisks
from pyanaconda.isignal import Signal
from pyanaconda.storage_utils import on_disk_storage

import logging
log = logging.getLogger("anaconda")


class DasdFormatting(object):

    def __init__(self):
        self._started = Signal()
        self._done = Signal()
        self._dasds = []

    @staticmethod
    def is_supported():
        return arch.is_s390()

    @property
    def started(self):
        return self._started

    @property
    def done(self):
        return self._done

    @property
    def dasds(self):
        return self._dasds

    @property
    def dasds_summary(self):
        return "\n".join(map(self.get_dasd_info, self.dasds))

    def get_dasd_info(self, disk):
        return "/dev/" + disk.name + " (" + disk.busid + ")"

    def _is_dasd(self, disk):
        return disk.type == "dasd"

    def _is_unformatted_dasd(self, disk):
        return self._is_dasd(disk) and blockdev.s390.dasd_needs_format(disk.busid)

    def _is_ldl_dasd(self, disk):
        return self._is_dasd(disk) and blockdev.s390.dasd_is_ldl(disk.name)

    def _get_unformatted_dasds(self, disks):
        return list(filter(self._is_unformatted_dasd, disks))

    def _get_ldl_dasds(self, disks):
        return list(filter(self._is_ldl_dasd, disks))

    def search_disks(self, disks):
        self._dasds = self._get_unformatted_dasds(disks) + self._get_ldl_dasds(disks)

    def should_run(self):
        return bool(self._dasds)

    def do_format(self, disk):
        try:
            log.debug("Running dasdfmt /dev/%s", disk.name)
            blockdev.s390.dasd_format(disk.name)
        except blockdev.S390Error as err:
            log.error("Failed dasdfmt /dev/%s: %s", disk.name, err)

    def run(self):
        if not self._dasds:
            return

        for disk in self._dasds:
            self.started.emit(disk)
            self.do_format(disk)
            self.done.emit(disk)

    def update_storage(self, storage, data):
        # Need to make the device tree aware of storage change.
        storage.devicetree.populate()

        # Initialize storage.
        storage_initialize(storage, data, storage.devicetree.protected_dev_names)

        # Update the storage snapshot to reflect these changes.
        if on_disk_storage.created:
            on_disk_storage.dispose_snapshot()
        on_disk_storage.create_snapshot(storage)


class AutomaticDasdFormatting(DasdFormatting):

    def __init__(self):
        DasdFormatting.__init__(self)
        self._can_format_unformatted = False
        self._can_format_ldl = False

    def read_restrictions(self, data):
        self._can_format_unformatted = data.zerombr.zerombr
        self._can_format_ldl = data.clearpart.cdl

    def should_run(self):
        return self.is_supported() \
               and flags.automatedInstall \
               and (self._can_format_unformatted or self._can_format_ldl) \
               and DasdFormatting.should_run(self)

    def search_storage(self, storage):
        self._dasds = []

        if self._can_format_unformatted:
            disks = getDisks(storage.devicetree)
            self._dasds += self._get_unformatted_dasds(disks)

        if self._can_format_ldl:
            disks = storage.devicetree.dasd
            self._dasds += self._get_ldl_dasds(disks)

    def update_storage(self, storage, data):
        for disk in self.dasds:
            # call removeChildren function instead of simply
            # removeDevice since the disk may have children in
            # devicetree, e.g. /dev/dasdc may have /dev/dasdc1
            storage.devicetree._removeChildrenFromTree(disk)

        storage.devicetree.populate()
