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
import dnf.exceptions
import dnf.repo
from dasbus.error import DBusError
from pyanaconda.flags import flags

from pyanaconda.modules.common.errors.installation import NonCriticalInstallationError, \
    InstallationError
from pyanaconda.modules.common.errors.payload import UnknownRepositoryError
from pyanaconda.modules.common.structures.payload import RepoConfigurationData
from pyanaconda.modules.common.structures.packages import PackagesConfigurationData, \
    PackagesSelectionData
from pyanaconda.modules.payloads.kickstart import convert_ks_repo_to_repo_data, \
    convert_repo_data_to_ks_repo
from pyanaconda.modules.payloads.payload.dnf.initialization import configure_dnf_logging
from pyanaconda.modules.payloads.payload.dnf.installation import ImportRPMKeysTask, \
    SetRPMMacrosTask, DownloadPackagesTask, InstallPackagesTask, PrepareDownloadLocationTask, \
    CleanUpDownloadLocationTask, ResolvePackagesTask, UpdateDNFConfigurationTask, \
    WriteRepositoriesTask
from pyanaconda.modules.payloads.payload.dnf.reload import ReloadRepositoriesTask
from pyanaconda.modules.payloads.payload.dnf.repositories import \
    generate_driver_disk_repositories
from pyanaconda.modules.payloads.payload.dnf.utils import get_kernel_version_list, \
    calculate_required_space
from pyanaconda.modules.payloads.payload.dnf.dnf_manager import DNFManager
from pyanaconda.modules.payloads.source.mount_tasks import TearDownMountTask
from pyanaconda.payload.errors import PayloadError
from pyanaconda.payload.image import find_optical_install_media
from pyanaconda.payload.source import SourceFactory, PayloadSourceTypeUnrecognized
from pyanaconda.anaconda_loggers import get_packaging_logger
from pyanaconda.core import constants
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.core.constants import PAYLOAD_TYPE_DNF, SOURCE_TYPE_URL, URL_TYPE_BASEURL, \
    SOURCE_REPO_FILE_TYPES, SOURCE_TYPE_CDN, MULTILIB_POLICY_ALL, SOURCE_TYPE_CDROM
from pyanaconda.core.i18n import _
from pyanaconda.errors import errorHandler as error_handler, ERROR_RAISE
from pyanaconda.modules.common.constants.services import SUBSCRIPTION
from pyanaconda.modules.payloads.source.utils import has_network_protocol
from pyanaconda.modules.common.util import is_module_available
from pyanaconda.payload.base import Payload
from pyanaconda.ui.lib.payload import get_payload, get_source, set_source, tear_down_sources, \
    create_source, set_up_sources

__all__ = ["DNFPayload"]

log = get_packaging_logger()


class DNFPayload(Payload):

    def __init__(self, data):
        super().__init__()
        self.data = data

        # Get a DBus payload to use.
        self._payload_proxy = get_payload(self.type)

        self.tx_id = None

        self._dnf_manager = DNFManager()

        # List of internal mount points.
        self._mount_points = []

        # Configure the DNF logging.
        configure_dnf_logging()

        # FIXME: Don't call this method before set_from_opts.
        # This will create a default source if there is none.
        self._configure()

    @property
    def dnf_manager(self):
        """The DNF manager."""
        return self._dnf_manager

    @property
    def _base(self):
        """Return a DNF base.

        FIXME: This is a temporary property.
        """
        return self._dnf_manager._base

    @property
    def _repos_lock(self):
        """A lock for a dictionary of DNF repositories.

        FIXME: This is a temporary property.
        """
        return self._dnf_manager._lock

    def set_from_opts(self, opts):
        """Set the payload from the Anaconda cmdline options.

        :param opts: a namespace of options
        """
        self._set_source_from_opts(opts)
        self._set_source_configuration_from_opts(opts)
        self._set_additional_repos_from_opts(opts)
        self._generate_driver_disk_repositories()
        self._set_packages_from_opts(opts)
        self._configure()

    def _set_source_from_opts(self, opts):
        """Change the source based on the Anaconda options.

        Set the source based on opts.method if it isn't already set
        - opts.method is currently set by command line/boot options.
        """
        if opts.method and (not self.proxy.Sources or self._is_source_default()):
            try:
                source = SourceFactory.parse_repo_cmdline_string(opts.method)
            except PayloadSourceTypeUnrecognized:
                log.error("Unknown method: %s", opts.method)
            else:
                source_proxy = source.create_proxy()
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
            source_proxy.SetRepoConfiguration(
                RepoConfigurationData.to_structure(repo_configuration)
            )

    def _set_additional_repos_from_opts(self, opts):
        """Set additional repositories based on the Anaconda options."""
        for repo_name, repo_url in opts.addRepo:
            try:
                source = SourceFactory.parse_repo_cmdline_string(repo_url)
            except PayloadSourceTypeUnrecognized:
                log.error("Type for additional repository %s is not recognized!", repo_url)
                return

            if self.get_addon_repo(repo_name):
                log.warning("Repository name %s is not unique. Only the first "
                            "repo will be used!", repo_name)

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

            repo = RepoConfigurationData()
            repo.name = repo_name
            repo.enabled = True
            repo.type = URL_TYPE_BASEURL
            repo.url = repo_url
            repo.installation_enabled = False

            ks_repo = convert_repo_data_to_ks_repo(repo)
            self.data.repo.dataList().append(ks_repo)

    def _generate_driver_disk_repositories(self):
        """Append generated driver disk repositories."""
        for data in generate_driver_disk_repositories():
            ks_repo = convert_repo_data_to_ks_repo(data)
            self.data.repo.dataList().append(ks_repo)

    def _set_packages_from_opts(self, opts):
        """Configure packages based on the Anaconda options."""
        if opts.multiLib:
            configuration = self.get_packages_configuration()
            configuration.multilib_policy = MULTILIB_POLICY_ALL
            self.set_packages_configuration(configuration)

    @property
    def type(self):
        """The DBus type of the payload."""
        return PAYLOAD_TYPE_DNF

    def get_source_proxy(self):
        """Get the DBus proxy of the RPM source.

        The default source for the DNF payload is set via
        the default_source option in the payload section
        of the Anaconda config file.

        :return: a DBus proxy
        """
        return get_source(self.proxy, conf.payload.default_source)

    @property
    def source_type(self):
        """The DBus type of the source."""
        source_proxy = self.get_source_proxy()
        return source_proxy.Type

    def get_packages_configuration(self) -> PackagesConfigurationData:
        """Get the DBus data with the packages configuration."""
        return PackagesConfigurationData.from_structure(
            self.proxy.PackagesConfiguration
        )

    def set_packages_configuration(self, data: PackagesConfigurationData):
        """Set the DBus data with the packages configuration."""
        return self.proxy.SetPackagesConfiguration(
            PackagesConfigurationData.to_structure(data)
        )

    def get_packages_selection(self) -> PackagesSelectionData:
        """Get the DBus data with the packages selection."""
        return PackagesSelectionData.from_structure(
            self.proxy.PackagesSelection
        )

    def set_packages_selection(self, data: PackagesSelectionData):
        """Set the DBus data with the packages selection."""
        return self.proxy.SetPackagesSelection(
            PackagesSelectionData.to_structure(data)
        )

    def is_ready(self):
        """Is the payload ready?"""
        enabled_repos = self._dnf_manager.enabled_repositories

        # If CDN is used as the installation source and we have
        # a subscription attached then any of the enabled repos
        # should be fine as the base repo.
        # If CDN is used but subscription has not been attached
        # there will be no redhat.repo file to parse and we
        # don't need to do anything.
        if self.source_type == SOURCE_TYPE_CDN:
            return self._is_cdn_set_up() and enabled_repos

        # Otherwise, a base repository has to be enabled.
        return any(map(self._is_base_repo, enabled_repos))

    def _is_cdn_set_up(self):
        """Is the CDN source set up?"""
        if not self.source_type == SOURCE_TYPE_CDN:
            return False

        if not is_module_available(SUBSCRIPTION):
            return False

        subscription_proxy = SUBSCRIPTION.get_proxy()
        return subscription_proxy.IsSubscriptionAttached

    def _is_base_repo(self, repo_id):
        """Is it a base repository?"""
        return repo_id == constants.BASE_REPO_NAME \
            or repo_id in constants.DEFAULT_REPOS

    def is_complete(self):
        """Is the payload complete?"""
        return self.source_type not in SOURCE_REPO_FILE_TYPES or self.is_ready()

    def setup(self, fallback=False, checkmount=True, onlyOnChange=False):
        """

        :param bool fallback: Whether to fall back to the default repo in case of error
        :param bool checkmount: Whether to check for valid mounted media
        :param bool onlyOnChange: Restart thread only if existing repositories changed.
                                  This won't restart thread even when a new repository was added!!
        """
        if self._verify_availability(onlyOnChange):
            return

        self.tx_id = None
        self._set_up_sources(checkmount)
        self._set_up_repositories(fallback)

    def _verify_availability(self, onlyOnChange):
        """Test if any repository changed from the last update."""
        if not onlyOnChange:
            return False

        log.debug("Testing repositories availability")
        if not self.dnf_manager.verify_repomd_hashes():
            return False

        log.debug("Payload isn't restarted, repositories are still available.")
        return True

    def _set_up_sources(self, checkmount):
        log.debug("Tearing down sources")
        tear_down_sources(self.proxy)
        self._tear_down_additional_sources()

        # Change the default source to CDROM if there is a valid install media.
        # FIXME: Set up the default source earlier.
        if checkmount and self._is_source_default() and find_optical_install_media():
            source_proxy = create_source(SOURCE_TYPE_CDROM)
            set_source(self.proxy, source_proxy)

        set_up_sources(self.proxy)

    def _set_up_repositories(self, fallback):
        try:
            self._reload_repositories()
        except (DBusError, PayloadError) as e:
            # Fail if the fallback is not enabled.
            if not fallback:
                raise e

            # If this is a kickstart install, just return now as we normally do not
            # want to read the on media repo files in such a case. On the other hand,
            # the local repo files are a valid use case if the system is subscribed
            # and the CDN is selected as the installation source.
            if flags.automatedInstall and not self._is_cdn_set_up():
                raise e

            # We already use the default source.
            if self.source_type == conf.payload.default_source:
                raise e

            # Fallback to the default source
            #
            # This is at the moment CDN on RHEL
            # and closest mirror everywhere else.
            self._create_default_source()
            self._reload_repositories()

    def _reload_repositories(self):
        task = ReloadRepositoriesTask(self._dnf_manager)
        task.progress_changed_signal.connect()

        try:
            task.run()
        finally:
            self._mount_points.extend(task._mount_points)
            self._validation_report = task._validation_report
            self.data.repo.repoList = list(map(convert_repo_data_to_ks_repo, task._repositories))

    def _create_default_source(self):
        tear_down_sources(self.proxy)
        source_proxy = create_source(conf.payload.default_source)
        set_source(self.proxy, source_proxy)
        set_up_sources(self.proxy)

    def unsetup(self):
        self._configure()
        tear_down_sources(self.proxy)

    @property
    def needs_network(self):
        """Test base and additional repositories if they require network."""
        return (self.service_proxy.IsNetworkRequired() or
                any(self._repo_needs_network(repo) for repo in self.data.repo.dataList()))

    def _repo_needs_network(self, repo):
        """Returns True if the ksdata repo requires networking."""
        urls = [repo.baseurl]
        if repo.mirrorlist:
            urls.extend(repo.mirrorlist)
        elif repo.metalink:
            urls.extend(repo.metalink)
        return self._source_needs_network(urls)

    def _source_needs_network(self, sources):
        """Return True if the source requires network.

        :param sources: Source paths for testing
        :type sources: list
        :returns: True if any source requires network
        """
        for s in sources:
            if has_network_protocol(s):
                log.debug("Source %s needs network for installation", s)
                return True

        log.debug("Source doesn't require network for installation")
        return False

    def bump_tx_id(self):
        if self.tx_id is None:
            self.tx_id = 1
        else:
            self.tx_id += 1
        return self.tx_id

    def _get_proxy_url(self):
        """Get a proxy of the current source.

        :return: a proxy or None
        """
        source_proxy = self.get_source_proxy()
        source_type = source_proxy.Type

        if source_type != SOURCE_TYPE_URL:
            return None

        data = RepoConfigurationData.from_structure(
            source_proxy.RepoConfiguration
        )

        return data.proxy

    def _configure(self):
        self._dnf_manager.reset_base()
        self._dnf_manager.configure_base(self.get_packages_configuration())
        self._dnf_manager.configure_proxy(self._get_proxy_url())
        self._dnf_manager.dump_configuration()

    ###
    # METHODS FOR WORKING WITH REPOSITORIES
    ###

    def get_addon_repo(self, repo_id):
        """Return a ksdata Repo instance matching the specified repo id."""
        repo = None
        for r in self.data.repo.dataList():
            if r.name == repo_id:
                repo = r
                break

        return repo

    def _tear_down_additional_sources(self):
        """Tear down sources of additional repositories.

        FIXME: This is a temporary workaround.
        """
        while self._mount_points:
            mount_point = self._mount_points.pop()
            task = TearDownMountTask(mount_point)
            task.run()

    @property
    def space_required(self):
        return calculate_required_space(self._dnf_manager)

    def set_updates_enabled(self, state):
        """Enable or Disable the repos used to update closest mirror.

        :param bool state: True to enable updates, False to disable.
        """
        # FIXME: Set the closest mirror source.
        self._updates_enabled = state

    def _set_repo_enabled(self, repo_id, enabled):
        """Enable or disable the repo in DNF and its data representation."""
        try:
            self._dnf_manager.set_repository_enabled(repo_id, enabled)
        except UnknownRepositoryError:
            pass

        repo = self.get_addon_repo(repo_id)
        if repo:
            repo.enabled = enabled

    def install(self):
        self._progress_cb(0, _('Starting package installation process'))

        # Get the packages configuration and selection data.
        configuration = self.get_packages_configuration()
        selection = self.get_packages_selection()

        # Add the rpm macros to the global transaction environment
        task = SetRPMMacrosTask(configuration)
        task.run()

        try:
            # Resolve packages.
            task = ResolvePackagesTask(self._dnf_manager, selection)
            task.run()
        except NonCriticalInstallationError as e:
            # FIXME: This is a temporary workaround.
            # Allow users to handle the error. If they don't want
            # to continue with the installation, raise a different
            # exception to make sure that we will not run the error
            # handler again.
            if error_handler.cb(e) == ERROR_RAISE:
                raise InstallationError(str(e)) from e

        # Set up the download location.
        task = PrepareDownloadLocationTask(self._dnf_manager)
        task.run()

        # Download the packages.
        task = DownloadPackagesTask(self._dnf_manager)
        task.progress_changed_signal.connect(self._progress_cb)
        task.run()

        # Install the packages.
        task = InstallPackagesTask(self._dnf_manager)
        task.progress_changed_signal.connect(self._progress_cb)
        task.run()

        # Clean up the download location.
        task = CleanUpDownloadLocationTask(self._dnf_manager)
        task.run()

        # Don't close the mother base here, because we still need it.

    def is_repo_enabled(self, repo_id):
        """Return True if repo is enabled."""
        try:
            return self._base.repos[repo_id].enabled
        except (dnf.exceptions.RepoError, KeyError):
            repo = self.get_addon_repo(repo_id)
            if repo:
                return repo.enabled
            else:
                return False

    def _is_source_default(self):
        """Report if the current source type is the default source type.

        NOTE: If no source was set previously a new default one
              will be created.
        """
        return self.source_type == conf.payload.default_source

    def post_install(self):
        """Perform post-installation tasks."""
        # Write selected kickstart repos to target system
        repositories = list(map(
            convert_ks_repo_to_repo_data,
            self.data.repo.dataList()
        ))

        task = WriteRepositoriesTask(
            sysroot=conf.target.system_root,
            dnf_manager=self.dnf_manager,
            repositories=repositories,
        )
        task.run()

        # We don't need the mother base anymore. Close it.
        self._base.close()
        super().post_install()

        # rpm needs importing installed certificates manually, see rhbz#748320 and rhbz#185800
        task = ImportRPMKeysTask(
            sysroot=conf.target.system_root,
            gpg_keys=conf.payload.default_rpm_gpg_keys
        )
        task.run()

        # Update the DNF configuration.
        task = UpdateDNFConfigurationTask(
            sysroot=conf.target.system_root,
            data=self.get_packages_configuration()
        )
        task.run()

    @property
    def kernel_version_list(self):
        return get_kernel_version_list()
