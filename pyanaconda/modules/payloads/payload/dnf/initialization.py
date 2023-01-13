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

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.core.constants import SOURCE_TYPE_CDROM, SOURCE_REPO_FILE_TYPES, SOURCE_TYPE_URL, \
    SOURCE_TYPE_CLOSEST_MIRROR, REPO_ORIGIN_SYSTEM, REPO_ORIGIN_TREEINFO, MOUNT_DIR, ISO_DIR, \
    INSTALL_TREE, URL_TYPE_BASEURL, BASE_REPO_NAME, isFinal as is_final_release
from pyanaconda.core.i18n import _
from pyanaconda.core.path import join_paths
from pyanaconda.core.payload import parse_hdd_url
from pyanaconda.modules.common.errors.payload import SourceSetupError, UnknownRepositoryError
from pyanaconda.modules.common.task import Task
from pyanaconda.modules.payloads.payload.dnf.dnf_manager import DNFManagerError, MetadataError
from pyanaconda.modules.payloads.payload.dnf.repositories import generate_treeinfo_repositories
from pyanaconda.modules.payloads.payload.dnf.tree_info import TreeInfoMetadata, NoTreeInfoError, \
    TreeInfoMetadataError
from pyanaconda.modules.payloads.source.factory import SourceFactory
from pyanaconda.modules.payloads.source.harddrive.initialization import SetUpHardDriveSourceTask
from pyanaconda.modules.payloads.source.mount_tasks import TearDownMountTask
from pyanaconda.modules.payloads.source.nfs.initialization import SetUpNFSSourceTask
from pyanaconda.payload.image import find_optical_install_media

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


class SetUpDNFManager(Task):
    """Task for setting up the DNF manager."""

    def __init__(self, dnf_manager, configuration, source):
        """Create a new task.

        :param dnf_manager: a DNF manager
        """
        super().__init__()
        self._dnf_manager = dnf_manager
        self._configuration = configuration
        self._source = source

    @property
    def name(self):
        return "Set up DNF manager"

    def run(self):
        """Run the task."""
        # FIXME: Do we want to create a new DNF manager?

        log.debug("Preparing the DNF base")
        self._dnf_manager.clear_cache()
        self._dnf_manager.reset_substitution()
        self._dnf_manager.configure_base(self._configuration)
        self._dnf_manager.configure_proxy(self._get_proxy_url())
        self._dnf_manager.dump_configuration()
        self._dnf_manager.read_system_repositories()

    def _get_proxy_url(self):
        """Get a proxy of the current source.

        FIXME: This is super weird, try to solve it.

        :return: a proxy or None
        """
        if self._source.type != SOURCE_TYPE_URL:
            return None

        return self._source.repo_configuration.proxy


class TearDownAdditionalSourcesTask(Task):
    """The task for tearing down additional DNF sources."""

    def __init__(self, dnf_manager, mount_points):
        """Create a new task.

        :param dnf_manager: a DNF manager
        """
        super().__init__()
        self._dnf_manager = dnf_manager
        self._mount_points = mount_points

    @property
    def name(self):
        return "Tear down additional DNF sources"

    def run(self):
        """Run the task."""
        self._tear_down_additional_sources()

    def _tear_down_additional_sources(self):
        """Tear down sources of additional repositories.

        FIXME: This is a temporary workaround. Do this in tear down tasks.
        """
        while self._mount_points:
            mount_point = self._mount_points.pop()
            task = TearDownMountTask(mount_point)
            task.run()


class SetUpDNFSourcesTask(Task):
    """The task for setting up DNF sources."""

    def __init__(self, dnf_manager, source, repositories):
        """Create a new task.

        :param dnf_manager: a DNF manager
        """
        super().__init__()
        self._dnf_manager = dnf_manager
        self._source = source
        self._repositories = repositories
        self._fallback = True  # FIXME: Resolve the fallback.
        self._try_media = True  # FIXME: Resolve the try media.

    @property
    def name(self):
        return "Set up DNF sources"

    def run(self):
        """Run the task."""
        self.report_progress(_("Downloading package metadata..."))

        self._change_default_source(
            try_media=self._try_media
        )

        self._update_base_repo(
            fallback=self._fallback,
            try_media=self._try_media
        )

        return self._source, self._repositories

    def _change_default_source(self, try_media=True):
        """Change the default source to CDROM if there is a valid install media."""
        # FIXME: Set up the default source earlier.
        if try_media and self._source.type == conf.payload.default_source and \
                find_optical_install_media():
            self._source = SourceFactory.create_source(SOURCE_TYPE_CDROM)

    def _update_base_repo(self, fallback=True, try_media=True):
        """Update the base repository from the DBus source."""
        log.info("Configuring the base repo")

        # Set up the source.
        self._set_up_source()

        # Add a new repo.
        if self._source.type not in SOURCE_REPO_FILE_TYPES:
            try:
                self._add_base_repository()
            except DNFManagerError as e:
                # Fail if the fallback is not enabled.
                if not fallback:
                    raise e

                # Fallback to the default source
                #
                # This is at the moment CDN on RHEL
                # and closest mirror everywhere else.
                self._tear_down_source()
                self._source = SourceFactory.create_source(conf.payload.default_source)
                self._set_up_source()

        # We need to check this again separately in case REPO_FILES were set above.
        if self._source.type in SOURCE_REPO_FILE_TYPES:
            # Remove all treeinfo repositories.
            self._remove_treeinfo_repositories()

            # If this is a kickstart install, just return now as we normally do not
            # want to read the on media repo files in such a case. On the other hand,
            # the local repo files are a valid use case if the system is subscribed
            # and the CDN is selected as the installation source.
            if flags.automatedInstall and not self._is_cdn_set_up():
                return

            # Otherwise, fall back to the default repos that we disabled above
            self._enable_system_repositories()

    def _set_up_source(self):
        for task in self._source.set_up_with_tasks():
            task.run()

    def _tear_down_source(self):
        for task in self._source.tear_down_with_tasks():
            task.run()

    def _add_base_repository(self):
        """Add the base repository.

        Try to add a valid base repository to the DNF base.

        :raise: DNFManagerError if the repo is invalid
        """
        # Get the repo configuration of the first source.
        data = self._source.generate_repo_configuration()

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

        if is_final_release:
            log.debug("Disable rawhide repositories.")
            self._set_repositories_enabled(["*rawhide*"], False)

    def _get_updates_enabled(self):
        """Are latest updates enabled?"""
        if self._source.type == SOURCE_TYPE_CLOSEST_MIRROR:
            return self._source.updates_enabled
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

    def _reload_treeinfo_metadata(self, repo_data):
        """Reload treeinfo metadata.

        :param RepoConfigurationData repo_data: configuration data of the base repo
        :return: a URL of the base repository
        """
        log.debug("Reload treeinfo metadata.")
        base_repo_url = None

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

            # Add the treeinfo repositories.
            repositories = generate_treeinfo_repositories(
                repo_data,
                tree_info_metadata
            )

            self._update_treeinfo_repositories(
                treeinfo_repositories=repositories,
                existing_urls=[base_repo_url],
            )
        except NoTreeInfoError as e:
            log.debug("No treeinfo metadata to use: %s", str(e))
            self._remove_treeinfo_repositories()

        except TreeInfoMetadataError as e:
            log.warning("Couldn't use treeinfo metadata: %s", str(e))
            self._remove_treeinfo_repositories()

        return base_repo_url

    def _update_treeinfo_repositories(self, treeinfo_repositories, existing_urls):
        """Add the treeinfo repositories.

        :param [RepoConfigurationData] treeinfo_repositories: a list of treeinfo repositories
        :param [str] existing_urls: a list of repository URLs that already exist
        """
        log.debug("Update treeinfo repositories...")

        # Get the additional repositories.
        repositories = self._repositories

        # Remember names of disabled treeinfo repositories.
        disabled_names = [
            r.name for r in repositories
            if not r.enabled and r.origin == REPO_ORIGIN_TREEINFO
        ]

        # Remove the previous treeinfo repositories.
        log.debug("Remove all treeinfo repositories.")

        repositories = [
            r for r in repositories
            if r.origin != REPO_ORIGIN_TREEINFO
        ]

        # Collect URLs of non-treeinfo repositories.
        existing_urls += [r.url for r in repositories if r.url]

        # Add the new treeinfo repositories.
        for repo in treeinfo_repositories:
            # Skip existing repositories.
            if repo.url in existing_urls:
                continue

            # Disable if previously disabled.
            if repo.name in disabled_names:
                repo.enabled = False

            repositories.append(repo)
            log.debug("Add the '%s' treeinfo repository: %s", repo.name, repo)

        # Set the additional repositories.
        self._repositories = repositories

    def _remove_treeinfo_repositories(self):
        """Remove all old treeinfo repositories before loading new ones.

        Find all repositories added from treeinfo file and remove them.
        After this step new repositories will be loaded from the new link.
        """
        log.debug("Remove all treeinfo repositories.")
        repositories = [
            r for r in self._repositories
            if r.origin != REPO_ORIGIN_TREEINFO
        ]
        self._repositories = repositories


class SetUpRepositoriesTask(Task):
    """The task for setting up DNF repositories."""

    def __init__(self, dnf_manager, repositories):
        """Create a new task.

        :param dnf_manager: a DNF manager
        """
        super().__init__()
        self._dnf_manager = dnf_manager
        self._repositories = repositories
        self._mount_points = []

    @property
    def name(self):
        return "Set up repositories"

    def run(self):
        """Set up additional repositories."""
        for data in self._repositories:
            self._process_repository(data)

    def _process_repository(self, data):
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
            msg = _("The '{repository_name}' repository has no mirror, baseurl or metalink set.")
            raise SourceSetupError(msg.format(repository_name=data.name)) from None

        # There is nothing to set up for sources natively supported by DNF.
        if any(data.url.startswith(p) for p in ["file:", "http:", "https:", "ftp:"]):
            return

        # Set up the NFS source with a substituted URL.
        if data.url.startswith("nfs:"):
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


class LoadRepositoriesTask(Task):
    """The task for loading DNF repositories."""

    def __init__(self, dnf_manager, repositories):
        """Create a new task.

        :param dnf_manager: a DNF manager
        """
        super().__init__()
        self._dnf_manager = dnf_manager
        self._repositories = repositories

    @property
    def name(self):
        return "Load repositories"

    def run(self):
        """Load repository metadata."""
        # Load enabled repositories.
        self._load_enabled_repositories()

        # Gather the group data
        self.report_progress(_("Downloading group metadata..."))
        self._dnf_manager.load_packages_metadata()

        # Load the hash of the repomd.xml files.
        self._dnf_manager.load_repomd_hashes()

    def _load_enabled_repositories(self):
        """Load all enabled repositories.

        If there is an invalid enabled repository, it will be
        disabled and we will issue a warning about that.

        The user repositories are validated when we add them
        to DNF, so this covers invalid system repositories.
        """
        for repo_id in self._dnf_manager.enabled_repositories:
            try:
                self._dnf_manager.load_repository(repo_id)
            except MetadataError as e:
                log.warning(str(e))
