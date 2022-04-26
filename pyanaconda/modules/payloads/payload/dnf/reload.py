#
# Copyright (C) 2022  Red Hat, Inc.
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
from pyanaconda import product
from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.core.constants import SOURCE_TYPE_CLOSEST_MIRROR, SOURCE_REPO_FILE_TYPES, \
    SOURCE_TYPE_URL, REPO_ORIGIN_TREEINFO, BASE_REPO_NAME, URL_TYPE_BASEURL, REPO_ORIGIN_SYSTEM,\
    MOUNT_DIR, ISO_DIR, INSTALL_TREE
from pyanaconda.core.i18n import _
from pyanaconda.core.path import join_paths
from pyanaconda.core.payload import parse_hdd_url
from pyanaconda.modules.common.errors.general import AnacondaError
from pyanaconda.modules.common.errors.payload import SourceSetupError, UnknownRepositoryError
from pyanaconda.modules.common.structures.payload import RepoConfigurationData
from pyanaconda.modules.common.structures.validation import ValidationReport
from pyanaconda.modules.common.task import Task
from pyanaconda.modules.payloads.payload.dnf.dnf_manager import DNFManagerError, MetadataError
from pyanaconda.modules.payloads.payload.dnf.repositories import generate_treeinfo_repositories
from pyanaconda.modules.payloads.payload.dnf.tree_info import TreeInfoMetadata, NoTreeInfoError, \
    TreeInfoMetadataError
from pyanaconda.modules.payloads.source.harddrive.initialization import SetUpHardDriveSourceTask
from pyanaconda.modules.payloads.source.nfs.initialization import SetUpNFSSourceTask

log = get_module_logger(__name__)


class ReloadRepositoriesTask(Task):
    """The task for reloading repositories."""

    def __init__(self, dnf_manager, source, repositories: [RepoConfigurationData]):
        """Create a new task.

        :param dnf_manager: a DNF manager
        """
        super().__init__()
        self._dnf_manager = dnf_manager
        self._source = source
        self._repositories = repositories
        self._treeinfo_repositories = []
        self._mount_points = []
        self._validation_report = ValidationReport()

    @property
    def name(self):
        return "Reload repositories"

    def run(self):
        # Set up repositories.
        self.report_progress(_("Downloading package metadata..."))

        try:
            self._prepare_dnf_base()
            self._remove_treeinfo_repositories()
            self._enable_source_repositories()
            self._include_additional_repositories()
        except (AnacondaError, DNFManagerError) as e:
            self._validation_report.error_messages.append(str(e))
            raise SourceSetupError(_("Error downloading package metadata"))

        # Validate repositories.
        self._validate_enabled_repositories()

        if not self._dnf_manager.enabled_repositories:
            raise SourceSetupError(_("Failed to set up installation source"))

        # Gather metadata.
        self.report_progress(_("Downloading group metadata..."))
        self._dnf_manager.load_packages_metadata()
        self._dnf_manager.load_repomd_hashes()

    def _prepare_dnf_base(self):
        """Prepare the DNF base."""
        log.debug("Preparing the DNF base")
        self._dnf_manager.clear_cache()
        self._dnf_manager.reset_substitution()
        self._dnf_manager.configure_proxy(self._get_proxy_url())
        self._dnf_manager.read_system_repositories()

    def _get_proxy_url(self):
        """Get a proxy of the current source.

        :return: a proxy or None
        """
        if self._source.type != SOURCE_TYPE_URL:
            return None

        return self._source.repo_configuration.proxy

    def _remove_treeinfo_repositories(self):
        """Remove all old treeinfo repositories before loading new ones.

        Find all repositories added from treeinfo file and remove them.
        After this step new repositories will be loaded from the new link.

        :return: list of repositories that were removed
        """
        log.debug("Remove treeinfo repositories.")

        self._treeinfo_repositories = [
            r for r in self._repositories
            if r.origin == REPO_ORIGIN_TREEINFO
        ]

        self._repositories = [
            r for r in self._repositories
            if r.origin != REPO_ORIGIN_TREEINFO
        ]

        log.debug("Removed treeinfo repositories: %s", self._treeinfo_repositories)

    def _enable_source_repositories(self):
        """Enable repositories of the installation source."""
        if self._source.type not in SOURCE_REPO_FILE_TYPES:
            self._add_base_repository()
        elif self._source.type == SOURCE_TYPE_CLOSEST_MIRROR:
            self._enable_system_repositories()

    def _add_base_repository(self):
        """Add the base repository.

        Try to add a valid base repository to the DNF base.

        :raise: DNFManagerError if the repo is invalid
        """
        log.info("Configuring the base repo")

        # Get the repo configuration of the first source.
        data = RepoConfigurationData.from_structure(
            self._source.get_repo_configurations()[0]
        )

        log.debug("Using the repo configuration: %s", data)
        data.name = BASE_REPO_NAME

        # Process the treeinfo metadata.
        treeinfo_base_repo_url = self._reload_treeinfo_metadata(data)

        if treeinfo_base_repo_url:
            data.type = URL_TYPE_BASEURL
            data.url = treeinfo_base_repo_url

        log.debug("Add the base repository at %s.", data.url)

        try:
            self._dnf_manager.add_repository(data)
            self._dnf_manager.load_repository(data.name)
        except DNFManagerError as e:
            log.error("The base repository is invalid: %s", str(e))
            self._dnf_manager.remove_repository(data.name)
            raise e

    def _reload_treeinfo_metadata(self, repo_data):
        """Reload treeinfo metadata.

        :param RepoConfigurationData repo_data: configuration data of the base repo
        :return: a URL of the base repository
        """
        log.debug("Reload treeinfo metadata.")
        base_repo_url = None

        # Remove previous treeinfo repositories.
        disabled_names = {r.name for r in self._treeinfo_repositories if not r.enabled}

        # Collect URLs of existing repositories.
        existing_urls = {r.url for r in self._repositories if r.url}

        try:
            # Load the treeinfo metadata.
            tree_info_metadata = TreeInfoMetadata()
            tree_info_metadata.load_data(repo_data)

            # Set up the substitutions.
            self._dnf_manager.configure_substitution(
                tree_info_metadata.release_version
            )

            # Get the new base repo URL.
            base_repo_url = tree_info_metadata.get_base_repo_url()
            existing_urls.add(base_repo_url)

            # Add the treeinfo repositories.
            repositories = generate_treeinfo_repositories(
                repo_data,
                tree_info_metadata
            )

            self._add_treeinfo_repositories(
                repositories=repositories,
                disabled_names=disabled_names,
                existing_urls=existing_urls,
            )
        except NoTreeInfoError as e:
            log.debug("No treeinfo metadata to use: %s", str(e))
        except TreeInfoMetadataError as e:
            log.warning("Couldn't use treeinfo metadata: %s", str(e))

        return base_repo_url

    def _add_treeinfo_repositories(self, repositories, disabled_names, existing_urls):
        """Add the treeinfo repositories.

        :param [RepoConfigurationData] repositories: configuration data of treeinfo repositories
        :param [str] disabled_names: a list of repository names that should be disabled
        :param [str] existing_urls: a list of repository URLs that already exist
        """
        log.debug("Add treeinfo repositories.")

        for repo in repositories:
            # Skip existing repositories.
            if repo.url in existing_urls:
                continue

            # Disable if previously disabled.
            if repo.name in disabled_names:
                repo.enabled = False

            log.debug("Add the '%s' treeinfo repository: %s", repo.name, repo)

            # Add the repository to user repositories,
            # so it'll appear in the output ks file.
            self._repositories.append(repo)

    def _enable_system_repositories(self):
        """Enable system repositories.

        * Restore previously disabled system repositories.
        * Enable or disable system repositories based on the current configuration.
        """
        self._dnf_manager.restore_system_repositories()

        log.debug("Enable or disable updates repositories.")
        self._set_repositories_enabled(
            conf.payload.updates_repositories,
            self._source.updates_enabled
        )

        log.debug("Disable repositories based on the Anaconda configuration file.")
        self._set_repositories_enabled(
            conf.payload.disabled_repositories,
            False
        )

        if product.isFinal:
            log.debug("Disable rawhide repositories.")
            self._set_repositories_enabled(["*rawhide*"], False)

    def _set_repositories_enabled(self, patterns, enabled):
        """Enable or disable matching repositories.

        :param patterns: a list of patterns to match the repo ids
        :param enabled: True to enable, False to disable
        """
        repo_ids = set()

        for pattern in patterns:
            repo_ids.update(self._dnf_manager.get_matching_repositories(pattern))

        for repo_id in sorted(repo_ids):
            self._dnf_manager.set_repository_enabled(repo_id, enabled)

    def _include_additional_repositories(self):
        """Add additional repositories to DNF."""
        for data in self._repositories:
            # Convert the repository.
            log.debug("Add the '%s' repository (%s).", data.name, data)

            # A system repository can be only enabled or disabled.
            if data.origin == REPO_ORIGIN_SYSTEM:
                self._handle_system_repository(data)
                return

            # Set up additional sources.
            self._set_up_additional_repository(data)

            # Add a new repository.
            self._dnf_manager.add_repository(data)

            # Load an enabled repository to check its validity.
            self._dnf_manager.load_repository(data.name)

    def _handle_system_repository(self, data):
        """Handle a system repository.

        The user is trying to do "repo --name=updates" in a kickstart file.
        We can only enable or disable the already existing on-disk repo config.

        :raise: SourceSetupError if the system repository is not available
        """
        try:
            self._dnf_manager.set_repository_enabled(data.name, data.enabled)
        except UnknownRepositoryError:
            msg = "The '{}' repository is not one of the pre-defined repositories."
            raise SourceSetupError(msg.format(data.name)) from None

    def _set_up_additional_repository(self, data):
        """Set up sources for the additional repository."""
        # Check the validity of the repository.
        if not data.url:
            msg = "The '{}' repository has no mirror, baseurl or metalink set."
            raise SourceSetupError(msg.format(data.name)) from None

        # Set up the NFS source with a substituted URL.
        elif data.url.startswith("nfs://"):
            device_mount = self._create_mount_point(
                MOUNT_DIR,
                data.name + "-nfs-device"
            )
            iso_mount = self._create_mount_point(
                MOUNT_DIR,
                data.name + "-nfs-iso"
            )
            task = SetUpNFSSourceTask(
                device_mount=device_mount,
                iso_mount=iso_mount,
                url=self._dnf_manager.substitute(data.url)
            )
            mount_point = task.run()
            data.url = "file://" + mount_point

        # Set up the HDD source.
        elif data.url.startswith("hd:"):
            device_mount = self._create_mount_point(
                ISO_DIR + "-" + data.name + "-hdd-device"
            )
            iso_mount = self._create_mount_point(
                INSTALL_TREE + "-" + data.name + "-hdd-iso"
            )

            partition, directory = parse_hdd_url(data.url)

            task = SetUpHardDriveSourceTask(
                device_mount=device_mount,
                iso_mount=iso_mount,
                partition=partition,
                directory=directory,
            )
            result = task.run()
            data.url = "file://" + result.install_tree_path

    def _create_mount_point(self, *paths):
        """Create a mount point from specified paths.

        FIXME: This is a temporary workaround.
        """
        mount_point = join_paths(*paths)
        self._mount_points.append(mount_point)
        return mount_point

    def _validate_enabled_repositories(self):
        """Validate all enabled repositories.

        Collect error messages about invalid repositories.
        All invalid repositories are disabled.

        The user repositories are validated when we add them
        to DNF, so this covers invalid system repositories.
        """
        for repo_id in self._dnf_manager.enabled_repositories:
            try:
                self._dnf_manager.load_repository(repo_id)
            except MetadataError as e:
                self._validation_report.warning_messages.append(str(e))
