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
import dnf.logging
import logging
import libdnf
from pyanaconda.modules.payloads.payload.dnf.dnf_manager import DNFManager

from pyanaconda.modules.payloads.base.initialization import SetUpSourcesTask, TearDownSourcesTask

from pyanaconda.anaconda_loggers import get_module_logger

DNF_LIBREPO_LOG = "/tmp/dnf.librepo.log"
DNF_LOGGER = "dnf"

log = get_module_logger(__name__)


def configure_dnf_logging():
    """Configure the DNF logging."""
    # Set up librepo.
    # This is still required even when the librepo has a separate logger because
    # DNF needs to have callbacks that the librepo log is written to be able to
    # process that log.
    libdnf.repo.LibrepoLog.removeAllHandlers()
    libdnf.repo.LibrepoLog.addHandler(DNF_LIBREPO_LOG)

    # Set up DNF. Increase the log level to the custom DDEBUG level.
    dnf_logger = logging.getLogger(DNF_LOGGER)
    dnf_logger.setLevel(dnf.logging.DDEBUG)


class SetUpDNFSourcesTask(SetUpSourcesTask):
    """Set up all the installation source of the DNF payload."""

    def __init__(self, sources):
        """Create a new task."""
        super().__init__(sources)
        self._dnf_manager = DNFManager()

    def run(self):
        """Run the task."""
        # Set up the sources.
        super().run()

        # Return the configured DNF manager.
        return self._dnf_manager


class TearDownDNFSourcesTask(TearDownSourcesTask):
    """Tear down all the installation sources of the DNF payload."""

    def __init__(self, sources, dnf_manager):
        """Create a new task."""
        super().__init__(sources)
        self._dnf_manager = dnf_manager

    def run(self):
        """Run the task."""
        try:
            # Tear down the sources.
            super().run()
        finally:
            # Close the DNF base.
            self._dnf_manager.reset_base()
