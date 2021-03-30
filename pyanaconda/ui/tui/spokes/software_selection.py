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
from pyanaconda.ui.lib.software import get_software_selection_status, \
    is_software_selection_complete, SoftwareSelectionCache
from pyanaconda.ui.tui.spokes import NormalTUISpoke
from pyanaconda.threading import threadMgr, AnacondaThread
from pyanaconda.payload.manager import payloadMgr, PayloadState
from pyanaconda.payload.errors import DependencyError
from pyanaconda.core.i18n import N_, _
from pyanaconda.core.constants import THREAD_PAYLOAD, THREAD_CHECK_SOFTWARE, \
    THREAD_SOFTWARE_WATCHER, PAYLOAD_TYPE_DNF

from simpleline.render.containers import ListColumnContainer
from simpleline.render.prompt import Prompt
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

        return context.payload_type == PAYLOAD_TYPE_DNF

    def __init__(self, data, storage, payload):
        super().__init__(data, storage, payload)
        self.title = N_("Software selection")
        self._container = None
        self.errors = []
        self._tx_id = None

        # Get the packages configuration.
        self._selection = self.payload.get_packages_selection()
        self._selection_cache = SoftwareSelectionCache(self._dnf_manager)

        # are we taking values (package list) from a kickstart file?
        self._kickstarted = flags.automatedInstall and self.payload.proxy.PackagesKickstarted

        # Register event listeners to update our status on payload events
        payloadMgr.add_listener(PayloadState.STARTED, self._payload_started_callback)
        payloadMgr.add_listener(PayloadState.ERROR, self._payload_error_callback)

    @property
    def _dnf_manager(self):
        """The DNF manager."""
        return self.payload.dnf_manager

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

        # Initialize and check the software selection.
        self._initialize_selection()

        # Report that the software spoke has been initialized.
        self.initialize_done()

    def _initialize_selection(self):
        """Initialize and check the software selection."""
        if self.errors or not self.payload.base_repo:
            log.debug("Skip the initialization of the software selection.")
            return

        if not self._kickstarted:
            # Use the default environment.
            self._selection_cache.select_default_environment()

            # Apply the default selection.
            self.apply()

        # Check the initial software selection.
        self.execute()

        # Wait for the software selection thread that might be started by execute().
        # We are already running in a thread, so it should not needlessly block anything
        # and only like this we can be sure we are really initialized.
        threadMgr.wait(THREAD_CHECK_SOFTWARE)

    # Payload event handlers
    def _payload_started_callback(self):
        self.errors = []

    def _payload_error_callback(self):
        self.errors = [payloadMgr.error]

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

    @property
    def status(self):
        """The status of the spoke."""
        if self.errors:
            return _("Error checking software selection")
        if not self.ready:
            return _("Installation source not set up")
        if not self.txid_valid:
            return _("Source changed - please verify")

        return get_software_selection_status(
            dnf_manager=self._dnf_manager,
            selection=self._selection,
            kickstarted=self._kickstarted
        )

    @property
    def completed(self):
        """Is the spoke complete?"""
        return self.ready \
            and not self.errors \
            and self.txid_valid \
            and is_software_selection_complete(
                dnf_manager=self._dnf_manager,
                selection=self._selection,
                kickstarted=self._kickstarted
            )

    def setup(self, args):
        """Set up the spoke right before it is used."""
        super().setup(args)

        # Join the initialization thread to block on it
        threadMgr.wait(THREAD_SOFTWARE_WATCHER)

        # Get the current software selection.
        self._selection = self.payload.get_interactive_packages_selection()

        # Create a new software selection cache.
        self._selection_cache = SoftwareSelectionCache(self._dnf_manager)

        return True

    def refresh(self, args=None):
        """ Refresh screen. """
        NormalTUISpoke.refresh(self, args)

        threadMgr.wait(THREAD_PAYLOAD)
        self._container = None

        if not self.payload.base_repo:
            message = TextWidget(_("Installation source needs to be set up first."))
            self.window.add_with_separator(message)
            return

        threadMgr.wait(THREAD_CHECK_SOFTWARE)
        self._container = ListColumnContainer(2, columns_width=38, spacing=2)

        if args is None:
            msg = self._refresh_environments()
        else:
            msg = self._refresh_addons(args)

        self.window.add_with_separator(TextWidget(msg))
        self.window.add_with_separator(self._container)

    def _refresh_environments(self):
        # Generate widgets for all available environments.
        for environment_id in self.dnf_manager.environments:
            data = self.dnf_manager.get_environment_data(environment_id)

            widget = CheckboxWidget(
                title=data.name,
                completed=(environment_id == self._selection.environment)
            )

            self._container.add(
                widget,
                callback=self._set_environment_callback,
                data=environment_id
            )

        return _("Base environment")

    def _refresh_addons(self, available_groups):
        # Generate widgets for all available groups.
        for group_id in available_groups:
            data = self.dnf_manager.get_group_data(group_id)

            widget = CheckboxWidget(
                title=data.name,
                completed=(group_id in self._selection.groups)
            )

            self._container.add(
                widget,
                callback=self._set_addons_callback,
                data=group_id
            )

        if available_groups:
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
            if key.lower() == Prompt.CONTINUE:
                # No environment was selected, close
                if not self._selection.environment:
                    self.close()

                # The environment was selected, switch screen
                elif args is None:
                    data = self.dnf_manager.get_environment_data(
                        self._selection.environment
                    )
                    ScreenHandler.replace_screen(
                        self, data.get_selectable_groups()
                    )

                # The addons were selected, apply and close
                else:
                    self.apply()
                    self.execute()
                    self.close()
            else:
                return super().input(args, key)

        return InputState.PROCESSED

    def apply(self):
        """Apply the changes."""
        self._kickstarted = False
        self._selection = self._selection_cache.get_selection_data()

        log.debug("Setting new software selection: %s", self._selection)
        self.payload.set_packages_selection(self._selection)

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
