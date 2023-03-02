# DNF/rpm software payload management.
#
# Copyright (C) 2019  Red Hat, Inc.
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
from dasbus.typing import get_native, unwrap_variant

from pyanaconda.modules.common.task import sync_run_task

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core import constants
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.core.constants import INSTALL_TREE, ISO_DIR, PAYLOAD_TYPE_DNF, \
    SOURCE_TYPE_URL, URL_TYPE_BASEURL, SOURCE_REPO_FILE_TYPES, SOURCE_TYPE_REPO_PATH, \
    SOURCE_TYPE_CDN, MULTILIB_POLICY_ALL, REPO_ORIGIN_SYSTEM, SOURCE_TYPE_CLOSEST_MIRROR, \
    REPO_ORIGIN_TREEINFO, DRACUT_REPO_DIR
from pyanaconda.core.i18n import _
from pyanaconda.core.path import join_paths
from pyanaconda.core.payload import parse_hdd_url
from pyanaconda.modules.common.constants.services import SUBSCRIPTION, PAYLOADS
from pyanaconda.modules.common.errors.payload import UnknownRepositoryError, SourceSetupError
from pyanaconda.modules.common.structures.packages import PackagesConfigurationData, \
    PackagesSelectionData
from pyanaconda.modules.common.structures.payload import RepoConfigurationData
from pyanaconda.modules.common.structures.validation import ValidationReport
from pyanaconda.modules.common.util import is_module_available
from pyanaconda.modules.payloads.payload.dnf.dnf_manager import DNFManagerError, MetadataError
from pyanaconda.modules.payloads.payload.dnf.repositories import \
    generate_driver_disk_repositories, generate_treeinfo_repositories
from pyanaconda.modules.payloads.payload.dnf.tree_info import TreeInfoMetadata, NoTreeInfoError, \
    TreeInfoMetadataError
from pyanaconda.modules.payloads.source.harddrive.initialization import SetUpHardDriveSourceTask
from pyanaconda.modules.payloads.source.mount_tasks import TearDownMountTask
from pyanaconda.modules.payloads.source.nfs.initialization import SetUpNFSSourceTask
from pyanaconda.modules.payloads.source.utils import verify_valid_repository
from pyanaconda.payload.migrated import MigratedDBusPayload
from pyanaconda.payload.source import SourceFactory, PayloadSourceTypeUnrecognized
from pyanaconda.ui.lib.payload import create_source, set_source, set_up_sources, tear_down_sources

__all__ = ["DNFPayload"]

log = get_module_logger(__name__)


class DNFPayload(MigratedDBusPayload):
    """The DNF payload class."""

    def __init__(self, data):
        super().__init__()
        self._report = ValidationReport()
        self.tx_id = None

    @property
    def type(self):
        """The DBus type of the payload."""
        return PAYLOAD_TYPE_DNF

    @property
    def report(self):
        """The latest report from the payload setup."""
        return self._report

    def set_from_opts(self, opts):
        """Set the payload from the Anaconda cmdline options.

        :param opts: a namespace of options
        """
        self._set_default_source(opts)
        self._set_source_configuration_from_opts(opts)
        self._set_additional_repos_from_opts(opts)
        self._generate_driver_disk_repositories()
        self._set_packages_from_opts(opts)

    def _set_default_source(self, opts):
        """Set the default source.

        Set the source based on opts.method if it isn't already set
        - opts.method is currently set by command line/boot options.

        Otherwise, use the source provided at a specific mount point
        by Dracut if there is any.

        Otherwise, use the default source specified in the Anaconda
        configuration files as a fallback.

        In summary, the installer chooses a default source of the DNF
        payload based on data processed in this order:

        1. Kickstart file
        2. Boot options or command line options
        3. Installation image mounted by Dracut
        4. Anaconda configuration file

        """
        if self.proxy.Sources:
            log.debug("The DNF source is already set.")

        elif opts.method:
            log.debug("Use the DNF source from opts.")

            try:
                source = SourceFactory.parse_repo_cmdline_string(opts.method)
            except PayloadSourceTypeUnrecognized:
                log.error("Unknown method: %s", opts.method)
            else:
                source_proxy = source.create_proxy()
                set_source(self.proxy, source_proxy)

        elif verify_valid_repository(DRACUT_REPO_DIR):
            log.debug("Use the DNF source from Dracut.")
            source_proxy = create_source(SOURCE_TYPE_REPO_PATH)
            source_proxy.Path = DRACUT_REPO_DIR
            set_source(self.proxy, source_proxy)

        else:
            log.debug("Use the DNF source from the Anaconda configuration file.")
            source_proxy = create_source(conf.payload.default_source)
            set_source(self.proxy, source_proxy)

    def _set_source_configuration_from_opts(self, opts):
        """Configure the source based on the Anaconda options."""
        source_proxy = self.get_source_proxy()

        if source_proxy.Type == SOURCE_TYPE_URL:
            # Get the repo configuration.
            repo_configuration = RepoConfigurationData.from_structure(
                source_proxy.RepoConfiguration
            )

            if opts.proxy:
                repo_configuration.proxy = opts.proxy

            if not conf.payload.verify_ssl:
                repo_configuration.ssl_verification_enabled = conf.payload.verify_ssl

            # Update the repo configuration.
            source_proxy.RepoConfiguration = \
                RepoConfigurationData.to_structure(repo_configuration)

    def _set_additional_repos_from_opts(self, opts):
        """Set additional repositories based on the Anaconda options."""
        repositories = self.get_repo_configurations()
        existing_names = {r.name for r in repositories}
        additional_repositories = []

        for repo_name, repo_url in opts.addRepo:
            # Check the name of the repository.
            is_unique = repo_name not in existing_names

            if not is_unique:
                log.warning("Repository name %s is not unique. Only the first repo will "
                            "be used!", repo_name)
                continue

            # Parse the URL of the repository.
            try:
                source = SourceFactory.parse_repo_cmdline_string(repo_url)
            except PayloadSourceTypeUnrecognized:
                log.error("Type for additional repository %s is not recognized!", repo_url)
                continue

            # Check the source type of the repository.
            is_supported = source.is_nfs \
                or source.is_http \
                or source.is_https \
                or source.is_ftp \
                or source.is_file \
                or source.is_harddrive

            if not is_supported:
                log.error("Source type %s for additional repository %s is not supported!",
                          source.source_type.value, repo_url)
                continue

            # Generate the configuration data for the new repository.
            data = RepoConfigurationData()
            data.name = repo_name
            data.url = repo_url

            existing_names.add(data.name)
            additional_repositories.append(data)

        if not additional_repositories:
            return

        repositories.extend(additional_repositories)
        self.set_repo_configurations(repositories)

    def _generate_driver_disk_repositories(self):
        """Append generated driver disk repositories."""
        dd_repositories = generate_driver_disk_repositories()

        if not dd_repositories:
            return

        repositories = self.get_repo_configurations()
        repositories.extend(dd_repositories)
        self.set_repo_configurations(repositories)

    def _set_packages_from_opts(self, opts):
        """Configure packages based on the Anaconda options."""
        if opts.multiLib:
            configuration = self.get_packages_configuration()
            configuration.multilib_policy = MULTILIB_POLICY_ALL
            self.set_packages_configuration(configuration)

    def get_repo_configurations(self) -> [RepoConfigurationData]:
        """Get a list of DBus repo configurations."""
        return RepoConfigurationData.from_structure_list(
            self.proxy.Repositories
        )

    def set_repo_configurations(self, data_list: [RepoConfigurationData]):
        """Set a list of DBus repo configurations."""
        self.proxy.Repositories = \
            RepoConfigurationData.to_structure_list(data_list)

    def get_packages_configuration(self) -> PackagesConfigurationData:
        """Get the DBus data with the packages configuration."""
        return PackagesConfigurationData.from_structure(
            self.proxy.PackagesConfiguration
        )

    def set_packages_configuration(self, data: PackagesConfigurationData):
        """Set the DBus data with the packages configuration."""
        self.proxy.PackagesConfiguration = \
            PackagesConfigurationData.to_structure(data)

    def get_packages_selection(self) -> PackagesSelectionData:
        """Get the DBus data with the packages selection."""
        return PackagesSelectionData.from_structure(
            self.proxy.PackagesSelection
        )

    def set_packages_selection(self, data: PackagesSelectionData):
        """Set the DBus data with the packages selection."""
        self.proxy.PackagesSelection = \
            PackagesSelectionData.to_structure(data)

    def is_ready(self):
        """Is the payload ready?"""
        return self.report.is_valid() and self.proxy.GetEnabledRepositories()

    def bump_tx_id(self):
        if self.tx_id is None:
            self.tx_id = 1
        else:
            self.tx_id += 1
        return self.tx_id

    ###
    # METHODS FOR WORKING WITH REPOSITORIES
    ###

    def _set_up_additional_repository(self, data):
        """Set up sources for the additional repository."""
        # Check the validity of the repository.
        if not data.url:
            msg = _("The '{repository_name}' repository has no mirror, baseurl or metalink set.")
            raise SourceSetupError(msg.format(repository_name=data.name)) from None

        # There is nothing to set up for sources natively supported by DNF.
        if any(data.url.startswith(p) for p in ["file:", "http:", "https:", "ftp:"]):
            return

        # Set up the NFS source with a substituted URL.
        if data.url.startswith("nfs:"):
            device_mount = self._create_mount_point(
                constants.MOUNT_DIR,
                data.name + "-nfs-device"
            )
            iso_mount = self._create_mount_point(
                constants.MOUNT_DIR,
                data.name + "-nfs-iso"
            )
            task = SetUpNFSSourceTask(
                device_mount=device_mount,
                iso_mount=iso_mount,
                url=self._dnf_manager.substitute(data.url)
            )
            mount_point = task.run()
            data.url = "file://" + mount_point
            return

        # Set up the HDD source.
        if data.url.startswith("hd:"):
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
            return

        # Otherwise, raise an error.
        msg = _("The '{repository_name}' repository uses an unsupported protocol.")
        raise SourceSetupError(msg.format(repository_name=data.name)) from None

    def _create_mount_point(self, *paths):
        """Create a mount point from specified paths.

        FIXME: This is a temporary workaround.
        """
        mount_point = join_paths(*paths)
        self._mount_points.append(mount_point)
        return mount_point

    def _tear_down_additional_sources(self):
        """Tear down sources of additional repositories.

        FIXME: This is a temporary workaround.
        """
        while self._mount_points:
            mount_point = self._mount_points.pop()
            task = TearDownMountTask(mount_point)
            task.run()

    # pylint: disable=arguments-differ
    def setup(self, report_progress, only_on_change=False):
        """Set up the payload.

        :param function report_progress: a callback for a progress reporting
        :param bool only_on_change: restart thread only if existing repositories changed
        """
        self._report = ValidationReport()

        # Test if any repository changed from the last update.
        if only_on_change:
            log.debug("Testing repositories availability")
            task_path = self.proxy.VerifyRepomdHashesWithTask()
            task_proxy = PAYLOADS.get_proxy(task_path)
            sync_run_task(task_proxy)

            result = unwrap_variant(task_proxy.GetResult())
            report = ValidationReport.from_structure(result)

            if not report.is_valid():
                log.debug("Payload isn't restarted, repositories are still available.")
                return

        # Set up repositories and download their metadata.
        self.tx_id = None

        try:
            log.debug("Tearing down sources")
            tear_down_sources(self.proxy)
            self._tear_down_additional_sources()

            log.debug("Setting up sources")
            set_up_sources(self.proxy)

            report_progress(_("Downloading package metadata..."))

            log.info("Configuring the base repo")
            if self.source_type == SOURCE_TYPE_CDN:
                # Remove all treeinfo repositories.
                self._remove_treeinfo_repositories()
                # Enable CDN repositories.
                self._enable_system_repositories()

            elif self.source_type == SOURCE_TYPE_CLOSEST_MIRROR:
                # Remove all treeinfo repositories.
                self._remove_treeinfo_repositories()
                # Enable system repositories.
                self._enable_system_repositories()

            # Prepare additional sources.
            for data in self.get_repo_configurations() + treeinfo_repos:
                log.debug("Add the '%s' repository (%s).", data.name, data)

                # A system repository can be only enabled or disabled.
                if data.origin == REPO_ORIGIN_SYSTEM:
                    return

                # Set up additional sources.
                self._set_up_additional_repository(data)

        except (OSError, SourceSetupError, DNFManagerError) as e:
            self._report.error_messages.append(str(e))
            raise SourceSetupError(str(e)) from e

    def _enable_system_repositories(self):
        """Enable system repositories.

        * Restore previously disabled system repositories.
        * Enable or disable system repositories based on the current configuration.
        """
        self._dnf_manager.restore_system_repositories()

        log.debug("Enable or disable updates repositories.")
        updates_enabled = self._get_updates_enabled()
        self._set_repositories_enabled(conf.payload.updates_repositories, updates_enabled)

        log.debug("Disable repositories based on the Anaconda configuration file.")
        self._set_repositories_enabled(conf.payload.disabled_repositories, False)

        if constants.isFinal:
            log.debug("Disable rawhide repositories.")
            self._set_repositories_enabled(["*rawhide*"], False)

    def _get_updates_enabled(self):
        """Are latest updates enabled?"""
        source_proxy = self.get_source_proxy()
        source_type = source_proxy.Type

        if source_type == SOURCE_TYPE_CLOSEST_MIRROR:
            return source_proxy.UpdatesEnabled
        else:
            return False

    def _set_repositories_enabled(self, patterns, enabled):
        """Enable or disable matching repositories.

        :param patterns: a list of patterns to match the repo ids
        :param enabled: True to enable, False to disable
        """
        repo_ids = set()

        for pattern in patterns:
            repo_ids.update(self._dnf_manager.get_matching_repositories(pattern))

        for repo_id in sorted(repo_ids):
            self.dnf_manager.set_repository_enabled(repo_id, enabled)
