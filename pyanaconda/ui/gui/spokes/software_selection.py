# Software selection spoke classes
#
# Copyright (C) 2011-2013  Red Hat, Inc.
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
import sys

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.constants import PAYLOAD_TYPE_DNF, THREAD_SOFTWARE_WATCHER, THREAD_PAYLOAD, \
    THREAD_CHECK_SOFTWARE, PAYLOAD_STATUS_PACKAGE_MD, PAYLOAD_STATUS_GROUP_MD
from pyanaconda.core.i18n import _, C_, CN_
from pyanaconda.core.util import ipmi_abort
from pyanaconda.flags import flags
from pyanaconda.payload.errors import DependencyError
from pyanaconda.payload.manager import payloadMgr, PayloadState
from pyanaconda.threading import threadMgr, AnacondaThread
from pyanaconda.ui.categories.software import SoftwareCategory
from pyanaconda.ui.communication import hubQ
from pyanaconda.ui.context import context
from pyanaconda.ui.gui.spokes import NormalSpoke
from pyanaconda.ui.gui.spokes.lib.detailederror import DetailedErrorDialog
from pyanaconda.ui.gui.utils import blockedHandler, escape_markup
from pyanaconda.ui.lib.software import SoftwareSelectionCache, get_software_selection_status, \
    is_software_selection_complete
from pyanaconda.ui.lib.subscription import is_cdn_registration_required

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango

log = get_module_logger(__name__)

__all__ = ["SoftwareSelectionSpoke"]


class SoftwareSelectionSpoke(NormalSpoke):
    """
       .. inheritance-diagram:: SoftwareSelectionSpoke
          :parts: 3
    """
    builderObjects = ["addonStore", "environmentStore", "softwareWindow"]
    mainWidgetName = "softwareWindow"
    uiFile = "spokes/software_selection.glade"
    helpFile = "SoftwareSpoke.xml"

    category = SoftwareCategory

    icon = "package-x-generic-symbolic"
    title = CN_("GUI|Spoke", "_Software Selection")

    @classmethod
    def should_run(cls, environment, data):
        """Don't run for any non-package payload."""
        if not NormalSpoke.should_run(environment, data):
            return False

        return context.payload_type == PAYLOAD_TYPE_DNF

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.errors = []
        self._tx_id = None

        # Get the packages selection data.
        self._selection = self.payload.get_packages_selection()
        self._selection_cache = SoftwareSelectionCache(self._dnf_manager)
        self._kickstarted = flags.automatedInstall and self.payload.proxy.PackagesKickstarted

        # Get the UI elements.
        self._environment_list_box = self.builder.get_object("environmentListBox")
        self._addon_list_box = self.builder.get_object("addonListBox")

        # Connect viewport scrolling with listbox focus events
        environment_viewport = self.builder.get_object("environmentViewport")
        self._environment_list_box.set_focus_vadjustment(
            Gtk.Scrollable.get_vadjustment(environment_viewport)
        )

        addon_viewport = self.builder.get_object("addonViewport")
        self._addon_list_box.set_focus_vadjustment(
            Gtk.Scrollable.get_vadjustment(addon_viewport)
        )

        # Add an invisible radio button so that we can show the environment
        # list with no radio buttons ticked
        self._invisible_radio = Gtk.RadioButton(group=None)
        self._invisible_radio.set_active(True)

        # Register event listeners to update our status on payload events.
        payloadMgr.add_listener(PayloadState.STARTED, self._payload_started_callback)
        payloadMgr.add_listener(PayloadState.DOWNLOADING_PKG_METADATA,
                                self._downloading_package_md_callback)
        payloadMgr.add_listener(PayloadState.DOWNLOADING_GROUP_METADATA,
                                self._downloading_group_md_callback)
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

        # Update the status.
        hubQ.send_ready(self.__class__.__name__)

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

    def _downloading_package_md_callback(self):
        hubQ.send_message(self.__class__.__name__, _(PAYLOAD_STATUS_PACKAGE_MD))

    def _downloading_group_md_callback(self):
        hubQ.send_message(self.__class__.__name__, _(PAYLOAD_STATUS_GROUP_MD))

    def _payload_error_callback(self):
        self.errors = [payloadMgr.error]
        hubQ.send_message(self.__class__.__name__, payloadMgr.error)

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
        if is_cdn_registration_required(self.payload):
            return _("Red Hat CDN requires registration.")
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

    def refresh(self):
        super().refresh()
        threadMgr.wait(THREAD_PAYLOAD)

        # Get the current software selection.
        self._selection = self.payload.get_packages_selection()

        # Create a new software selection cache.
        self._selection_cache = SoftwareSelectionCache(self._dnf_manager)
        self._selection_cache.apply_selection_data(self._selection)

        # Refresh up the UI.
        self._refresh_environments()
        self._refresh_groups()

        # Set up the info bar.
        self.clear_info()

        if self.errors:
            self.set_warning(_(
                "Error checking software dependencies. "
                " <a href=\"\">Click for details.</a>"
            ))

    def _refresh_environments(self):
        """Create rows for all available environments."""
        self._clear_listbox(self._environment_list_box)

        for environment in self._dnf_manager.environments:
            self._add_environment_row(environment)

        self._environment_list_box.show_all()

    def _refresh_groups(self):
        """Create rows for all available groups."""
        self._clear_listbox(self._addon_list_box)

        if self._selection_cache.environment:
            # Get the environment data.
            environment_data = self._dnf_manager.get_environment_data(
                self._selection_cache.environment
            )

            # Add optional groups.
            for group in environment_data.optional_groups:
                self._add_group_row(group)

            # Add the separator.
            if environment_data.optional_groups and environment_data.visible_groups:
                self._addon_list_box.insert(Gtk.Separator(), -1)

            # Add user visible groups.
            for group in environment_data.visible_groups:
                self._add_group_row(group)

        self._addon_list_box.show_all()

    def _clear_listbox(self, listbox):
        for child in listbox.get_children():
            listbox.remove(child)
            del child

    def _add_environment_row(self, environment):
        """Add a new row for the specified environment."""
        # Get the environment data.
        environment_data = self._dnf_manager.get_environment_data(environment)

        # Is the environment selected?
        selected = self._selection_cache.environment == environment

        # Use the invisible radio button as a group for all these radio buttons.
        radio = Gtk.RadioButton(group=self._invisible_radio)
        radio.set_active(selected)

        # Add a new environment row.
        self._add_row(
            self._environment_list_box,
            environment_data.name,
            environment_data.description,
            radio,
            self.on_radio_button_toggled
        )

    def _add_group_row(self, group):
        """Add a new row for the specified group."""
        # Get the group data.
        group_data = self._dnf_manager.get_group_data(group)

        # Is the group selected?
        selected = self._selection_cache.is_group_selected(group)

        # Add a new group row.
        check = Gtk.CheckButton()
        check.set_active(selected)

        self._add_row(
            self._addon_list_box,
            group_data.name,
            group_data.description,
            check,
            self.on_checkbox_toggled
        )

    def _add_row(self, listbox, name, desc, button, clicked):
        """Add a new row into the specified list box."""
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        button.set_valign(Gtk.Align.START)
        button.connect("toggled", clicked, row)
        box.add(button)

        label = Gtk.Label(
            label="<b>%s</b>\n%s" % (escape_markup(name), escape_markup(desc)),
            use_markup=True,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            hexpand=True,
            xalign=0,
            yalign=0.5
        )
        box.add(label)
        row.add(box)
        listbox.insert(row, -1)

    def apply(self):
        """Apply the changes."""
        self._kickstarted = False
        self._selection = self._selection_cache.get_selection_data()

        log.debug("Setting new software selection: %s", self._selection)
        self.payload.set_packages_selection(self._selection)

        hubQ.send_not_ready(self.__class__.__name__)
        hubQ.send_not_ready("SourceSpoke")

    def execute(self):
        """Execute the changes."""
        threadMgr.add(AnacondaThread(
            name=THREAD_CHECK_SOFTWARE,
            target=self.check_software_selection
        ))

    def check_software_selection(self):
        """Check the software selection."""
        hubQ.send_message(self.__class__.__name__, _("Checking software dependencies..."))
        try:
            self.payload.check_software_selection()
        except DependencyError as e:
            self.errors = str(e)
            hubQ.send_message(self.__class__.__name__, _("Error checking software dependencies"))
            self._tx_id = None
        else:
            self.errors = None
            self._tx_id = self.payload.tx_id
        finally:
            hubQ.send_ready(self.__class__.__name__)
            hubQ.send_ready("SourceSpoke")

    @property
    def txid_valid(self):
        return self._tx_id == self.payload.tx_id

    # Signal handlers
    def on_radio_button_toggled(self, radio, row):
        # If the radio button toggled to inactive, don't reactivate the row
        if not radio.get_active():
            return

        row.activate()

    def on_environment_activated(self, listbox, row):
        box = row.get_children()[0]
        button = box.get_children()[0]

        with blockedHandler(button, self.on_radio_button_toggled):
            button.set_active(True)

        # Mark the clicked environment as selected.
        # FIXME: Get the environment id.
        self._selection_cache.select_environment(None)

        # Update the screen.
        self._refresh_groups()

    def on_checkbox_toggled(self, button, row):
        # Select the addon. The button is already toggled.
        self._select_addon_at_row(row, button.get_active())

    def on_addon_activated(self, listbox, row):
        # Skip the separator.
        box = row.get_children()[0]
        if isinstance(box, Gtk.Separator):
            return

        # Select the addon. The button is not toggled yet.
        button = box.get_children()[0]
        self._select_addon_at_row(row, not button.get_active())

    def _select_addon_at_row(self, row, is_selected):
        # Activate the row.
        with blockedHandler(row.get_parent(), self.on_addon_activated):
            row.activate()

        # Activate the button.
        box = row.get_children()[0]
        button = box.get_children()[0]
        with blockedHandler(button, self.on_checkbox_toggled):
            button.set_active(is_selected)

        # Mark the clicked group as selected/deselected.
        # FIXME: Get the group id.
        group = None

        if is_selected:
            self._selection_cache.select_group(group)
        else:
            self._selection_cache.deselect_group(group)

    def on_info_bar_clicked(self, *args):
        if not self.errors:
            return

        label = _(
            "The software marked for installation has the following errors.  "
            "This is likely caused by an error with your installation source.  "
            "You can quit the installer, change your software source, or change "
            "your software selections."
        )

        buttons = [
            C_("GUI|Software Selection|Error Dialog", "_Quit"),
            C_("GUI|Software Selection|Error Dialog", "_Modify Software Source"),
            C_("GUI|Software Selection|Error Dialog", "Modify _Selections")
        ]

        dialog = DetailedErrorDialog(self.data, buttons=buttons, label=label)

        with self.main_window.enlightbox(dialog.window):
            dialog.refresh(self.errors)
            rc = dialog.run()

        dialog.window.destroy()

        if rc == 0:
            # Quit the installation.
            ipmi_abort(scripts=self.data.scripts)
            sys.exit(0)
        elif rc == 1:
            # Send the user to the installation source spoke.
            self.skipTo = "SourceSpoke"
            self.window.emit("button-clicked")
