# Software selection text spoke
#
# Copyright (C) 2013  Red Hat, Inc.
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
from pyanaconda.flags import flags
from pyanaconda.ui.categories.software import SoftwareCategory
from pyanaconda.ui.context import context
from pyanaconda.ui.tui.spokes import NormalTUISpoke
from pyanaconda.threading import threadMgr, AnacondaThread
from pyanaconda.payload.manager import payloadMgr, PayloadState
from pyanaconda.payload.errors import DependencyError, NoSuchGroup
from pyanaconda.core.i18n import N_, _, C_
from pyanaconda.core.configuration.anaconda import conf

from pyanaconda.core.constants import THREAD_PAYLOAD, THREAD_CHECK_SOFTWARE, \
    THREAD_SOFTWARE_WATCHER, PAYLOAD_TYPE_DNF

from simpleline.render.containers import ListColumnContainer
from simpleline.render.screen import InputState
from simpleline.render.screen_handler import ScreenHandler
from simpleline.render.widgets import TextWidget, CheckboxWidget

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)

__all__ = ["SoftwareSpoke"]


class SoftwareSpoke(NormalTUISpoke):
    """ Spoke used to read new value of text to represent source repo.

       .. inheritance-diagram:: SoftwareSpoke
          :parts: 3
    """
    helpFile = "SoftwareSpoke.txt"
    category = SoftwareCategory

    @classmethod
    def should_run(cls, environment, data):
        """Don't run for any non-package payload."""
        if not NormalTUISpoke.should_run(environment, data):
            return False

        return context.payload.type == PAYLOAD_TYPE_DNF

    def __init__(self, data, storage, payload):
        super().__init__(data, storage, payload)
        self.title = N_("Software selection")
        self._container = None
        self.errors = []
        self._tx_id = None

        # Get the packages configuration.
        self._selection = self.payload.get_packages_data()

        # are we taking values (package list) from a kickstart file?
        self._kickstarted = flags.automatedInstall and self.payload.proxy.PackagesKickstarted

        # Register event listeners to update our status on payload events
        payloadMgr.add_listener(PayloadState.STARTED, self._payload_start)
        payloadMgr.add_listener(PayloadState.ERROR, self._payload_error)

    def initialize(self):
        """Initialize the spoke."""
        super().initialize()
        self.initialize_start()

        threadMgr.add(AnacondaThread(
            name=THREAD_SOFTWARE_WATCHER,
            target=self._initialize
        ))

    def _initialize(self):
        """Initialize the spoke in a separate thread."""
        threadMgr.wait(THREAD_PAYLOAD)

        if not self._kickstarted:
            # Set the environment.
            self.set_default_environment()

            # Apply the initial selection.
            self.apply()

        # Check the initial software selection.
        self.execute()

        # Wait for the software selection thread that might be started by execute().
        # We are already running in a thread, so it should not needlessly block anything
        # and only like this we can be sure we are really initialized.
        threadMgr.wait(THREAD_CHECK_SOFTWARE)

        # report that the software spoke has been initialized
        self.initialize_done()

    def set_default_environment(self):
        # If an environment was specified in the configuration, use that.
        # Otherwise, select the first environment.
        if self.payload.environments:
            environments = self.payload.environments

            if conf.payload.default_environment in environments:
                self._selection.environment = conf.payload.default_environment
            else:
                self._selection.environment = environments[0]

    def _payload_start(self):
        self.errors = []

    def _payload_error(self):
        self.errors = [payloadMgr.error]

    def _translate_env_name_to_id(self, environment):
        """ Return the id of the selected environment or None. """
        if not environment:
            # None means environment is not set, no need to try translate that to an id
            return None
        try:
            return self.payload.environment_id(environment)
        except NoSuchGroup:
            return None

    def _get_available_addons(self, environment_id):
        """ Return all add-ons of the specific environment. """
        addons = []

        if environment_id in self.payload.environment_addons:
            for addons_list in self.payload.environment_addons[environment_id]:
                addons.extend(addons_list)

        return addons

    @property
    def status(self):
        """ Where we are in the process """
        if self.errors:
            return _("Error checking software selection")
        if not self.ready:
            return _("Processing...")
        if not self.payload.base_repo:
            return _("Installation source not set up")
        if not self.txid_valid:
            return _("Source changed - please verify")
        if not self._selection.environment:
            # KS installs with %packages will have an env selected, unless
            # they did an install without a desktop environment. This should
            # catch that one case.
            if self._kickstarted:
                return _("Custom software selected")
            return _("Nothing selected")

        return self.payload.environment_description(self._selection.environment)[0]

    @property
    def completed(self):
        """ Make sure our threads are done running and vars are set.

           WARNING: This can be called before the spoke is finished initializing
           if the spoke starts a thread. It should make sure it doesn't access
           things until they are completely setup.
        """
        processing_done = self.ready and not self.errors and self.txid_valid

        if flags.automatedInstall or self._kickstarted:
            return processing_done and self.payload.base_repo and self.payload.proxy.PackagesKickstarted
        else:
            return processing_done and self.payload.base_repo and self._selection.environment

    def setup(self, args):
        """Set up the spoke right before it is used."""
        super().setup(args)

        # Join the initialization thread to block on it
        threadMgr.wait(THREAD_SOFTWARE_WATCHER)

        # Get the packages configuration.
        self._selection = self.payload.get_packages_data()

        return True

    def refresh(self, args=None):
        """ Refresh screen. """
        NormalTUISpoke.refresh(self, args)

        threadMgr.wait(THREAD_PAYLOAD)
        self._container = None

        threadMgr.wait(THREAD_CHECK_SOFTWARE)
        self._container = ListColumnContainer(2, columns_width=38, spacing=2)

        if args is None:
            msg = self._refresh_environments()
        else:
            msg = self._refresh_addons(args)

        self.window.add_with_separator(TextWidget(msg))
        self.window.add_with_separator(self._container)

    def _refresh_environments(self):
        environments = self.payload.environments

        for env in environments:
            name = self.payload.environment_description(env)[0]
            selected = (env == self._selection.environment)
            widget = CheckboxWidget(title="%s" % name, completed=selected)
            self._container.add(widget, callback=self._set_environment_callback, data=env)

        return _("Base environment")

    def _refresh_addons(self, available_addons):
        for addon_id in available_addons:
            name = self.payload.group_description(addon_id)[0]
            selected = addon_id in self._selection.groups
            widget = CheckboxWidget(title="%s" % name, completed=selected)
            self._container.add(widget, callback=self._set_addons_callback, data=addon_id)

        if available_addons:
            return _("Additional software for selected environment")
        else:
            return _("No additional software to select.")

    def _set_environment_callback(self, data):
        self._selection.environment = data

    def _set_addons_callback(self, data):
        if data not in self._selection.groups:
            self._selection.groups.append(data)
        else:
            self._selection.groups.remove(data)

    def input(self, args, key):
        """ Handle the input; this chooses the desktop environment. """
        if self._container is not None and self._container.process_user_input(key):
            self.redraw()
        else:
            # TRANSLATORS: 'c' to continue
            if key.lower() == C_('TUI|Spoke Navigation', 'c'):

                # No environment was selected, close
                if not self._selection.environment:
                    self.close()

                # The environment was selected, switch screen
                elif args is None:
                    # Get addons for the selected environment
                    environment = self._selection.environment
                    environment_id = self._translate_env_name_to_id(environment)
                    addons = self._get_available_addons(environment_id)

                    # Switch the screen
                    ScreenHandler.replace_screen(self, addons)

                # The addons were selected, apply and close
                else:
                    self.apply()
                    self.execute()
                    self.close()
            else:
                return super().input(args, key)

        return InputState.PROCESSED

    @property
    def ready(self):
        """Is the spoke ready?

        By default, the software selection spoke is not ready. We have to
        wait until the installation source spoke is completed. This could be
        because the user filled something out, or because we're done fetching
        repo metadata from the mirror list, or we detected a DVD/CD.
        """
        return not threadMgr.get(THREAD_SOFTWARE_WATCHER) \
            and not threadMgr.get(THREAD_PAYLOAD) \
            and not threadMgr.get(THREAD_CHECK_SOFTWARE) \
            and self.payload.base_repo is not None

    def apply(self):
        """Apply the changes."""
        self._kickstarted = False

        # Clear packages data.
        self._selection.packages = []
        self._selection.excluded_packages = []

        # Clear groups data.
        self._selection.excluded_groups = []
        self._selection.groups_package_types = {}

        # Select valid groups.
        # FIXME: Remove invalid groups from selected groups.

        log.debug("Setting new software selection: %s", self._selection)
        self.payload.set_packages_data(self._selection)

    def execute(self):
        """Execute the changes."""
        threadMgr.add(AnacondaThread(
            name=THREAD_CHECK_SOFTWARE,
            target=self._check_software_selection
        ))

    def _check_software_selection(self):
        """Check the software selection."""
        try:
            self.payload.check_software_selection()
        except DependencyError as e:
            self.errors = [str(e)]
            self._tx_id = None
            log.warning("Transaction error %s", str(e))
        else:
            self._tx_id = self.payload.tx_id

    @property
    def txid_valid(self):
        """ Whether we have a valid dnf tx id. """
        return self._tx_id == self.payload.tx_id
