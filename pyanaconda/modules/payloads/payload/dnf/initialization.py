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
import logging

import dnf.logging
import libdnf
from pyanaconda.modules.common.structures.payload import RepoConfigurationData

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.constants import BASE_REPO_NAME, REPO_ORIGIN_SYSTEM, SOURCE_REPO_FILE_TYPES, \
    SOURCE_TYPE_URL
from pyanaconda.modules.common.errors.payload import UnknownRepositoryError, SourceSetupError
from pyanaconda.modules.common.structures.validation import ValidationReport
from pyanaconda.modules.payloads.base.initialization import SetUpSourcesTask, TearDownSourcesTask
from pyanaconda.modules.payloads.payload.dnf.dnf_manager import DNFManager, MetadataError
from pyanaconda.modules.payloads.payload.dnf.repositories import update_treeinfo_repositories
from pyanaconda.modules.payloads.source.repo_tasks import LoadTreeInfoMetadataTask

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

    def __init__(self, sources, repositories, configuration):
        """Create a new task."""
        super().__init__(sources)
        self._repositories = repositories
        self._configuration = configuration
        self._validation_report = ValidationReport()
        self._treeinfo_repositories = []
        self._repository_data = None
        self._release_version = None
        self._proxy = None

    @property
    def _source(self):
        return self._sources[0]

    def run(self):
        """Run the task."""
        # Set up the sources. It will fail if there are no sources to set up.
        super().run()

        # Process the configuration of the main source.
        self._process_source(self._source)

        # Update the treeinfo repositories if any.
        repositories = update_treeinfo_repositories(
            self._repositories,
            self._treeinfo_repositories
        )

        # Set up additional sources.
        # FIXME: Use sources to handle additional repositories.
        for data in self._repositories:
            self._set_up_additional_repository(data)

        # Configure the DNF manager.
        dnf_manager = self._configure_dnf_manager()

        # Handle the main repository.
        self._process_source_repository(dnf_manager, self._source)

        # Add and load repositories.
        for data in repositories:
            self._process_repository_data(dnf_manager, data)

        # Validate configured repositories.
        self._validate_repositories(dnf_manager)

        # Load metadata.
        self._load_metadata(dnf_manager)

        # Return the configured DNF manager and an updated list of repositories.
        # FIXME: Remember the DNF manager and updated repositories.
        return dnf_manager, repositories

    def _process_source(self, source):
        """Process the DNF source."""
        if source.type in SOURCE_REPO_FILE_TYPES:
            return

        # Generate the initial repository configuration.
        self._repository_data = source.generate_repo_configuration()

        # Load and process treeinfo metadata of the source if any.
        task = LoadTreeInfoMetadataTask(self._repository_data)
        result = task.run()

        if result.repository_data:
            self._repository_data = result.repository_data

        if result.treeinfo_repositories:
            self._treeinfo_repositories = result.treeinfo_repositories

        if result.release_version:
            self._release_version = result.release_version

        # Change the default proxy configuration.
        if self._repository_data.proxy:
            self._proxy = self._repository_data.proxy

        # Rename and enable the chosen repository.
        self._repository_data.name = BASE_REPO_NAME
        self._repository_data.enabled = True

    def _generate_sources(self, repositories):
        

    def _configure_dnf_manager(self):
        """Initialize and configure the DNF manager."""
        log.debug("Preparing the DNF base...")
        dnf_manager = DNFManager()
        dnf_manager.clear_cache()
        dnf_manager.configure_base(self._configuration)
        dnf_manager.configure_proxy(self._proxy)
        dnf_manager.configure_substitution(self._release_version)
        dnf_manager.dump_configuration()
        dnf_manager.read_system_repositories()
        # DNF5: LOCK THE DNF BASE HERE!
        return dnf_manager

    def _process_source_repository(self, dnf_manager, source):
        if source.type in SOURCE_REPO_FILE_TYPES:
            self._enable_system_repositories(dnf_manager)
        else:
            self._add_and_load_repository(dnf_manager, self._repository_data)

    def _process_repository_data(self, dnf_manager, data):
        """Process a repository data."""
        log.debug("Add the '%s' repository (%s).", data.name, data)

        if data.origin == REPO_ORIGIN_SYSTEM:
            self._set_system_repository(dnf_manager, data)
        else:
            self._add_and_load_repository(dnf_manager, data)

    def _set_system_repository(self, dnf_manager, data):
        """Handle a system repository.

        The user is trying to do "repo --name=updates" in a kickstart file.
        We can only enable or disable the already existing on-disk repo config.

        :raise: SourceSetupError if the system repository is not available
        """
        try:
            dnf_manager.set_repository_enabled(data.name, data.enabled)
        except UnknownRepositoryError:
            msg = "The '{}' repository is not one of the pre-defined repositories."
            raise SourceSetupError(msg.format(data.name)) from None

    def _add_and_load_repository(self, dnf_manager, data):
        # Add a new repository.
        dnf_manager.add_repository(data)

        # Load an enabled repository to check its validity.
        dnf_manager.load_repository(data.name)

    def _validate_repositories(self, dnf_manager):
        """Validate all enabled repositories.

        Collect error messages about invalid repositories.
        All invalid repositories are disabled.

        The user repositories are validated when we add them
        to DNF, so this covers invalid system repositories.
        """
        # Check if there is at least one enabled repository.
        if not dnf_manager.enabled_repositories:
            raise SourceSetupError(_("No repository is configured."))

        # Load all enabled repositories and collect warnings if any.
        for repo_id in dnf_manager.enabled_repositories:
            try:
                dnf_manager.load_repository(repo_id)
            except MetadataError as e:
                self._validation_report.warning_messages.append(str(e))

    def _load_metadata(self, dnf_manager):
        """Load metadata of configured repositories."""
        self.report_progress(_("Downloading group metadata..."))
        dnf_manager.load_packages_metadata()
        dnf_manager.load_repomd_hashes()


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
