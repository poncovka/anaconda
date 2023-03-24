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
from collections import namedtuple

import dnf.logging
import libdnf

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.core.constants import BASE_REPO_NAME, REPO_ORIGIN_SYSTEM, SOURCE_REPO_FILE_TYPES, \
    isFinal as is_final_release, SOURCE_TYPE_CDN, SOURCE_TYPE_CLOSEST_MIRROR
from pyanaconda.core.i18n import _
from pyanaconda.modules.common.errors.payload import UnknownRepositoryError, SourceSetupError
from pyanaconda.modules.payloads.base.initialization import SetUpSourcesTask, TearDownSourcesTask
from pyanaconda.modules.payloads.payload.dnf.dnf_manager import DNFManager, MetadataError
from pyanaconda.modules.payloads.payload.dnf.repositories import update_treeinfo_repositories
from pyanaconda.modules.payloads.payload.dnf.tree_info import LoadTreeInfoMetadataTask
from pyanaconda.modules.payloads.source.harddrive.harddrive import HardDriveSourceModule
from pyanaconda.modules.payloads.source.nfs.nfs import NFSSourceModule
from pyanaconda.modules.payloads.source.url.url import URLSourceModule

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


SetUpDNFSourcesResult = namedtuple(
    "LoadTreeInfoMetadataResult", [
        "dnf_manager",
        "repositories",
        "sources",
    ]
)
SetUpDNFSourcesResult.__doc__ += """
The result of the SetUpDNFSourcesTask task.
"""


class SetUpDNFSourcesTask(SetUpSourcesTask):
    """Set up all the installation source of the DNF payload."""

    def __init__(self, sources, repositories, configuration):
        """Create a new task."""
        super().__init__(sources)
        self._repositories = repositories
        self._configuration = configuration
        self._treeinfo_repositories = []
        self._repository_data = None
        self._release_version = None
        self._proxy = None

    @property
    def _source(self):
        return self._sources[0]

    def run(self):
        """Run the task.

        The task returns a named tuple with the following values:

            dnf_manager     a DNF manager with a configured base
            repositories    an updated list of additional repositories
            sources         a list of generated additional sources

        :return SetUpDNFSourcesResult: a result of the task
        """
        # Set up the sources. It will fail if there are no sources to set up.
        super().run()

        # Process the configuration of the main source.
        self._process_source(self._source)

        # Process the treeinfo metadata of the main source.
        # Update the treeinfo repositories if any.
        repositories = update_treeinfo_repositories(
            self._repositories,
            self._treeinfo_repositories
        )

        # Generate and set up additional sources.
        sources = self._generate_sources(repositories)
        self._set_up_sources(sources)

        # Configure the DNF manager.
        dnf_manager = self._configure_dnf_manager()

        # Load the main source.
        self._load_source(dnf_manager, self._source, self._repository_data)

        # Load additional sources.
        for source in sources:
            self._load_source(dnf_manager, source)

        # Configure existing repositories.
        for repository in repositories:
            self._set_system_repository(dnf_manager, repository)

        # Validate enabled repositories.
        self._validate_repositories(dnf_manager)

        # Load package and group metadata.
        self.report_progress(_("Downloading group metadata..."))
        self._load_metadata(dnf_manager)

        return SetUpDNFSourcesResult(
            dnf_manager=dnf_manager,
            repositories=repositories,
            sources=sources,
        )

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
        sources = []

        for data in repositories:
            if data.origin == REPO_ORIGIN_SYSTEM:
                continue

            source = self._generate_source(data)
            sources.append(source)

        return sources

    @staticmethod
    def _generate_source(data):
        if data.origin == REPO_ORIGIN_SYSTEM:
            raise ValueError()

        if not data.url:
            msg = _("The '{name}' repository has no mirror, baseurl or metalink set.")
            raise SourceSetupError(msg.format(name=data.name)) from None

        # There is nothing to set up for sources natively supported by DNF.
        if any(data.url.startswith(p) for p in ["file:", "http:", "https:", "ftp:"]):
            return URLSourceModule(data)

        # Set up the NFS source with a substituted URL.
        if data.url.startswith("nfs:"):
            # FIXME: Apply substitution (+ release_version) on the url.
            # data.url = self._dnf_manager.substitute(data.url)
            return NFSSourceModule(data)

        # Set up the HDD source.
        if data.url.startswith("hd:"):
            return HardDriveSourceModule(data)

        # Otherwise, raise an error.
        msg = _("The '{name}' repository uses an unsupported protocol.")
        raise SourceSetupError(msg.format(name=data.name)) from None

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

    def _load_source(self, dnf_manager, source, repository=None):
        if source.type == SOURCE_TYPE_CDN:
            dnf_manager.restore_system_repositories()

            log.debug("Disable repositories based on the Anaconda configuration file.")
            self._set_repositories_enabled(
                dnf_manager,
                conf.payload.disabled_repositories,
                False
            )

        elif source.type == SOURCE_TYPE_CLOSEST_MIRROR:
            dnf_manager.restore_system_repositories()

            log.debug("Enable or disable updates repositories.")
            self._set_repositories_enabled(
                dnf_manager,
                conf.payload.updates_repositories,
                source.updates_enabled
            )

            log.debug("Disable repositories based on the Anaconda configuration file.")
            self._set_repositories_enabled(
                dnf_manager,
                conf.payload.disabled_repositories,
                False
            )

            if is_final_release:
                log.debug("Disable rawhide repositories.")
                self._set_repositories_enabled(
                    dnf_manager,
                    ["*rawhide*"],
                    False
                )

        else:
            repository = repository or source.generate_repo_configuration()
            self._add_new_repository(dnf_manager, repository)

    @staticmethod
    def _set_repositories_enabled(dnf_manager, patterns, enabled):
        """Enable or disable matching repositories.

        :param patterns: a list of patterns to match the repo ids
        :param enabled: True to enable, False to disable
        """
        repo_ids = set()

        for pattern in patterns:
            repo_ids.update(dnf_manager.get_matching_repositories(pattern))

        for repo_id in sorted(repo_ids):
            dnf_manager.set_repository_enabled(repo_id, enabled)

    @staticmethod
    def _set_system_repository(dnf_manager, data):
        """Handle a system repository.

        The user is trying to do "repo --name=updates" in a kickstart file.
        We can only enable or disable the already existing on-disk repo config.

        :raise: SourceSetupError if the system repository is not available
        """
        if data.origin != REPO_ORIGIN_SYSTEM:
            return

        try:
            dnf_manager.set_repository_enabled(data.name, data.enabled)
        except UnknownRepositoryError:
            msg = "The '{}' repository is not one of the pre-defined repositories."
            raise SourceSetupError(msg.format(data.name)) from None

    @staticmethod
    def _add_new_repository(dnf_manager, data):
        log.debug("Add the '%s' repository (%s).", data.name, data)

        # Add a new repository.
        dnf_manager.add_repository(data)

        # Load an enabled repository to check its validity.
        dnf_manager.load_repository(data.name)

    @staticmethod
    def _validate_repositories(dnf_manager):
        """Validate all enabled repositories.

        Collect error messages about invalid repositories.
        All invalid repositories are disabled.

        The user repositories are validated when we add them
        to DNF, so this covers invalid system repositories.
        """
        # Check if there is at least one enabled repository.
        if not dnf_manager.enabled_repositories:
            raise SourceSetupError(_("No repository is configured."))

        # Load all enabled repositories and report warnings if any.
        for repo_id in dnf_manager.enabled_repositories:
            try:
                dnf_manager.load_repository(repo_id)
            except MetadataError as e:
                log.warning(str(e))

    @staticmethod
    def _load_metadata(dnf_manager):
        """Load metadata of configured repositories."""
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
