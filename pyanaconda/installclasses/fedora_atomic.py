#
# fedora_atomic.py
#
# Atomic-specific partitioning defaults
#
# Copyright (C) 2014  Red Hat, Inc.  All rights reserved.
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

import os
import shutil

from pyanaconda.installclasses.fedora import FedoraBaseInstallClass
from pyanaconda.product import productName
from pyanaconda import iutil
from pyanaconda.kickstart import getAvailableDiskSpace
from pyanaconda.storage.partspec import PartSpec
from pyanaconda.storage.autopart import swap_suggestion
from pyanaconda.platform import platform
from blivet.size import Size

import logging
log = logging.getLogger("anaconda")

__all__ = ["AtomicInstallClass"]


class AtomicInstallClass(FedoraBaseInstallClass):
    name = "Atomic Host"
    defaultFS = "xfs"
    sortPriority = FedoraBaseInstallClass.sortPriority + 1
    if not productName.startswith("Fedora Atomic"):  # pylint: disable=no-member
        hidden = True

    def __init__(self):
        self.localemap = {}  # loaded lazily
        FedoraBaseInstallClass.__init__(self)

    # This is intended right now to match Fedora Server; if changing this,
    # please discuss on https://lists.projectatomic.io/projectatomic-archives/atomic-devel/
    def setDefaultPartitioning(self, storage):
        autorequests = [PartSpec(mountpoint="/", fstype=storage.default_fstype,
                                 size=Size("3GiB"), max_size=Size("15GiB"),
                                 grow=True, lv=True)]

        bootreqs = platform.set_default_partitioning()
        if bootreqs:
            autorequests.extend(bootreqs)

        disk_space = getAvailableDiskSpace(storage)
        swp = swap_suggestion(disk_space=disk_space)
        autorequests.append(PartSpec(fstype="swap", size=swp, grow=False,
                                     lv=True, encrypted=True))

        for autoreq in autorequests:
            if autoreq.fstype is None:
                if autoreq.mountpoint == "/boot":
                    autoreq.fstype = storage.default_boot_fstype
                else:
                    autoreq.fstype = storage.default_fstype

        storage.autopart_requests = autorequests

    def filterSupportedLangs(self, ksdata, langs):
        self._initialize_localemap(ksdata.ostreesetup.ref,
                                   ksdata.ostreesetup.url)
        for lang in langs:
            if lang in self.localemap:
                yield lang

    def filterSupportedLocales(self, ksdata, lang, locales):
        self._initialize_localemap(ksdata.ostreesetup.ref,
                                   ksdata.ostreesetup.url)
        supported = []
        if lang in self.localemap:
            for locale in locales:
                stripped = self._strip_codeset_and_modifier(locale)
                if stripped in self.localemap[lang]:
                    supported.append(locale)
        return supported

    def _initialize_localemap(self, ref, repo):

        if self.localemap:
            return

        # fallback to just en_US in case of errors
        self.localemap = {"en": ["en_US"]}

        # Let's only handle local embedded repos for now. Anyway, it'd probably
        # not be very common to only override ostreesetup through kickstart and
        # still want the interactive installer. Though to be nice, let's handle
        # that case.
        if not repo or not repo.startswith("file://"):
            log.info("ostree repo is not local; defaulting to en_US")
            return

        # convert to regular UNIX path
        repo = repo[len("file://"):]

        iutil.mkdirChain(os.path.join(repo, "tmp/usr/lib"))
        rc = iutil.execWithRedirect("/usr/bin/ostree",
            ["checkout", "--repo", repo, ref,
             "--subpath", "/usr/lib/locale/locale-archive",
             "%s/tmp/usr/lib/locale" % repo])
        if rc != 0:
            log.error("failed to check out locale-archive; check program.log")
            return

        for line in iutil.execReadlines("/usr/bin/localedef",
                                        ["--prefix", os.path.join(repo, "tmp"),
                                         "--list-archive"]):
            line = self._strip_codeset_and_modifier(line)
            if '_' in line:
                (lang, territory) = line.split('_', 1)
            else:
                lang = line
            if lang not in self.localemap:
                self.localemap[lang] = [line]
            else:
                self.localemap[lang].append(line)

        # nuke the checkout for good measure
        shutil.rmtree(os.path.join(repo, "tmp/usr"))

    @staticmethod
    def _strip_codeset_and_modifier(locale):
        if '@' in locale:
            locale = locale[:locale.find('@')]
        if '.' in locale:
            locale = locale[:locale.find('.')]
        return locale
