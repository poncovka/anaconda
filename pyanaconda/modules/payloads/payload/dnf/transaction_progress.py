#
# Copyright (C) 2020  Red Hat, Inc.
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
import dnf.transaction
import dnf.callback

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.i18n import _

log = get_module_logger(__name__)

__all__ = ["TransactionError", "TransactionProgress"]


class TransactionError(Exception):
    """The transaction has failed."""


class TransactionProgress(dnf.callback.TransactionProgress):
    """The class for receiving information about an ongoing transaction."""

    def __init__(self, callback):
        """Create a new instance."""
        super().__init__()
        self._callback = callback
        self._last_ts = None
        self._postinst_phase = False
        self.cnt = 0

    def progress(self, package, action, ti_done, ti_total, ts_done, ts_total):
        """Report ongoing progress on the given transaction item.

        :param package: the DNF package object
        :param action: the ID of the current action
        :param ti_done: the number of processed bytes of the transaction item
        :param ti_total: the total number of bytes of the transaction item
        :param ts_done: the number of actions processed in the whole transaction
        :param ts_total: the total number of actions in the whole transaction
        """
        # Process DNF actions, communicating with anaconda via the queue
        # A normal installation consists of 'install' messages followed by
        # the 'post' message.
        if action == dnf.transaction.PKG_INSTALL and ti_done == 0:
            # do not report same package twice
            if self._last_ts == ts_done:
                return
            self._last_ts = ts_done

            msg = '%s.%s (%d/%d)' % \
                (package.name, package.arch, ts_done, ts_total)
            self.cnt += 1
            self._report(_("Installing {}").format(msg))

            # Log the exact package nevra, build time and checksum
            nevra = "%s-%s.%s" % (package.name, package.evr, package.arch)
            log.info("Installed: %s %s %s" % (nevra, package.buildtime, package.returnIdSum()[1]))

        elif action == dnf.transaction.TRANS_POST:
            self._report(_("Performing post-installation setup tasks"))
            log.info("Post installation setup phase started.")
            self._postinst_phase = True

        elif action == dnf.transaction.PKG_SCRIPTLET:
            # Log the exact package nevra, build time and checksum
            nevra = "%s-%s.%s" % (package.name, package.evr, package.arch)
            log.info("Configuring (running scriptlet for): %s %s %s" % (
                nevra, package.buildtime, package.returnIdSum()[1])
            )

            # only show progress in UI for post-installation scriptlets
            if self._postinst_phase:
                msg = '%s.%s' % (package.name, package.arch)
                self._report(_("Configuring {}").format(msg))

        elif action == dnf.transaction.PKG_VERIFY:
            msg = '%s.%s (%d/%d)' % (package.name, package.arch, ts_done, ts_total)
            self._report(_("Verifying {}").format(msg))

            # Log the exact package nevra, build time and checksum
            nevra = "%s-%s.%s" % (package.name, package.evr, package.arch)
            log.info("Verifying: %s %s %s" % (nevra, package.buildtime, package.returnIdSum()[1]))

    def _report(self, message):
        self._callback(message)

    def error(self, message):
        """Report an error that occurred during the transaction.

        :param message: a string that describes the error
        """
        raise TransactionError(message)
