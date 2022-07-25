# Installation source spoke classes
#
# Copyright (C) 2019 Red Hat, Inc.
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

import time
import threading
import os
import re

from urllib.parse import urlsplit

from pyanaconda.core import constants
from pyanaconda.core.constants import PAYLOAD_TYPE_DNF, SOURCE_TYPE_HDD, SOURCE_TYPE_URL, \
    SOURCE_TYPE_CDROM, SOURCE_TYPE_NFS, SOURCE_TYPE_HMC, URL_TYPE_BASEURL, URL_TYPE_MIRRORLIST, \
    URL_TYPE_METALINK, SOURCE_TYPE_CLOSEST_MIRROR, SOURCE_TYPE_CDN
from pyanaconda.flags import flags
from pyanaconda.core.i18n import _, CN_
from pyanaconda.modules.common.structures.payload import RepoConfigurationData
from pyanaconda.modules.common.constants.services import SUBSCRIPTION
from pyanaconda.payload.image import find_optical_install_media
from pyanaconda.ui.lib.payload import find_potential_hdiso_sources, get_hdiso_source_info, \
    get_hdiso_source_description
from pyanaconda.core.payload import ProxyString, ProxyStringError, parse_nfs_url, create_nfs_url
from pyanaconda.core.util import cmp_obj_attrs, id_generator
from pyanaconda.ui.communication import hubQ
from pyanaconda.ui.context import context
from pyanaconda.ui.gui.spokes.lib.installation_source_helpers import validate_proxy, RepoChecks, \
    ProxyDialog, MediaCheckDialog, IsoChooser, BASEREPO_SETUP_MESSAGE, PROTOCOL_HTTP, \
    PROTOCOL_HTTPS, PROTOCOL_FTP, PROTOCOL_NFS, PROTOCOL_FILE, PROTOCOL_MIRROR, REPO_PROTO, \
    CLICK_FOR_DETAILS, get_unique_repo_name, validate_repo_name, check_duplicate_repo_names
from pyanaconda.ui.helpers import InputCheck, InputCheckHandler, SourceSwitchHandler
from pyanaconda.ui.lib.subscription import switch_source
from pyanaconda.ui.gui.helpers import GUISpokeInputCheckHandler
from pyanaconda.ui.gui.spokes import NormalSpoke
from pyanaconda.ui.categories.software import SoftwareCategory
from pyanaconda.ui.gui.utils import blockedHandler, fire_gtk_action
from pyanaconda.ui.gui.utils import gtk_call_once, really_hide, really_show, fancy_set_sensitive
from pyanaconda.threading import threadMgr, AnacondaThread
from pyanaconda.payload import utils as payload_utils
from pyanaconda.payload.manager import payloadMgr, PayloadState
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.core.regexes import URL_PARSE, HOSTNAME_PATTERN_WITHOUT_ANCHORS
from pyanaconda.modules.common.constants.services import NETWORK, STORAGE
from pyanaconda.modules.common.constants.objects import DEVICE_TREE
from pyanaconda.modules.common.structures.storage import DeviceData
from pyanaconda.modules.common.util import is_module_available
from pyanaconda.core.storage import device_matches

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

__all__ = ["SourceSpoke"]

# Repo Store Columns
REPO_ENABLED_COL = 0
REPO_NAME_COL = 1
REPO_OBJ = 2

# Additional repo protocol combobox fields
MODEL_ROW_VALUE = 0
MODEL_ROW_NAME = 1


class SourceSpoke(NormalSpoke, GUISpokeInputCheckHandler, SourceSwitchHandler):
    """
       .. inheritance-diagram:: SourceSpoke
          :parts: 3
    """
    builderObjects = ["partitionStore", "sourceWindow", "dirImage", "repoStore"]
    mainWidgetName = "sourceWindow"
    uiFile = "spokes/installation_source.glade"
    category = SoftwareCategory

    icon = "media-optical-symbolic"
    title = CN_("GUI|Spoke", "_Installation Source")

    @staticmethod
    def get_screen_id():
        """Return a unique id of this UI screen."""
        return "software-source-configuration"

    @classmethod
    def should_run(cls, environment, data):
        """Don't run for any non-package payload."""
        if not NormalSpoke.should_run(environment, data):
            return False

        return context.payload_type == PAYLOAD_TYPE_DNF

    def __init__(self, *args, **kwargs):
        NormalSpoke.__init__(self, *args, **kwargs)
        GUISpokeInputCheckHandler.__init__(self)
        SourceSwitchHandler.__init__(self)

        self._current_iso_file = None
        self._ready = False
        self._error = False
        self._error_msg = ""
        self._proxy_url = ""
        self._proxy_change = False
        self._cdrom = None
        self._repo_counter = id_generator()
        self._repo_store_lock = threading.Lock()

        self._updates_enabled = False
        self._updates_change = False

        self._network_module = NETWORK.get_proxy()
        self._device_tree = STORAGE.get_proxy(DEVICE_TREE)

    def apply(self):
        pass

    @property
    def completed(self):
        """ WARNING: This can be called before _initialize is done, make sure that it
            doesn't access things that are not setup (eg. payload.*) until it is ready
        """
        source_proxy = self.payload.get_source_proxy()
        if source_proxy.Type == SOURCE_TYPE_CDN:
            return True
        elif flags.automatedInstall and self.ready and not self.payload.is_ready():
            return False

        return not self._error and self.ready and self.payload.is_complete()

    @property
    def mandatory(self):
        return True

    @property
    def ready(self):
        return (self._ready and
                not threadMgr.get(constants.THREAD_PAYLOAD) and
                not threadMgr.get(constants.THREAD_SOFTWARE_WATCHER) and
                not threadMgr.get(constants.THREAD_CHECK_SOFTWARE))

    @property
    def subscribed(self):
        """Report if the system is currently subscribed.

        NOTE: This will be always False when the Subscription
              module is no available.

        :return: True if subscribed, False otherwise
        :rtype: bool
        """
        subscribed = False
        if is_module_available(SUBSCRIPTION):
            subscription_proxy = SUBSCRIPTION.get_proxy()
            subscribed = subscription_proxy.IsSubscriptionAttached
        return subscribed

    @property
    def status(self):
        # When CDN is selected as installation source and system
        # is not yet subscribed, the automatic repo refresh will
        # fail. This is expected as CDN can't be used until the
        # system has been registered. So prevent the error
        # message and show CDN is used instead. If CDN still
        # fails after registration, the regular error message
        # will be displayed.
        source_proxy = self.payload.get_source_proxy()
        cdn_source = source_proxy.Type == SOURCE_TYPE_CDN
        if cdn_source and not self.subscribed:
            source_proxy = self.payload.get_source_proxy()
            return source_proxy.Description
        elif threadMgr.get(constants.THREAD_CHECK_SOFTWARE):
            return _("Checking software dependencies...")
        elif not self.ready:
            return _(BASEREPO_SETUP_MESSAGE)
        elif not self.payload.is_ready():
            return _("Error setting up base repository")
        elif self._error:
            return _("Error setting up software source")
        elif not self.payload.is_complete():
            return _("Nothing selected")
        else:
            source_proxy = self.payload.get_source_proxy()
            return source_proxy.Description

    def _get_device_name(self, device_spec):
        devices = device_matches(device_spec)

        if not devices:
            log.warning("Device for installation from HDD can't be found!")
            return ""
        elif len(devices) > 1:
            log.warning("More than one device is found for HDD installation!")

        return devices[0]

    def _grab_objects(self):
        self._autodetect_button = self.builder.get_object("autodetectRadioButton")
        self._autodetect_box = self.builder.get_object("autodetectBox")
        self._autodetect_device_label = self.builder.get_object("autodetectDeviceLabel")
        self._autodetect_label = self.builder.get_object("autodetectLabel")
        self._cdn_button = self.builder.get_object("cdnRadioButton")
        self._hmc_button = self.builder.get_object("hmcRadioButton")
        self._iso_button = self.builder.get_object("isoRadioButton")
        self._iso_box = self.builder.get_object("isoBox")
        self._iso_chooser_button = self.builder.get_object("isoChooserButton")
        self._verify_iso_button = self.builder.get_object("verifyIsoButton")

        # addon repo objects
        self._repo_entry_box = self.builder.get_object("repoEntryBox")
        self._repo_store = self.builder.get_object("repoStore")
        self._repo_selection = self.builder.get_object("repoSelection")
        self._repo_name_entry = self.builder.get_object("repoNameEntry")
        self._repo_protocol_combo_box = self.builder.get_object("repoProtocolComboBox")
        self._repo_view = self.builder.get_object("repoTreeView")
        self._repo_remove_button = self.builder.get_object("removeButton")

        # Connect scroll events on the viewport with focus events on the box
        main_viewport = self.builder.get_object("mainViewport")
        main_box = self.builder.get_object("mainBox")
        main_box.set_focus_vadjustment(Gtk.Scrollable.get_vadjustment(main_viewport))

    def initialize(self):
        NormalSpoke.initialize(self)
        self.initialize_start()
        self._grab_objects()

        threadMgr.add(AnacondaThread(
            name=constants.THREAD_SOURCE_WATCHER,
            target=self._initialize
        ))

    def _initialize(self):
        threadMgr.wait(constants.THREAD_PAYLOAD)

        # Get the current source.
        source_proxy = self.payload.get_source_proxy()
        source_type = source_proxy.Type

        # If we've previously set up to use a CD/DVD method, the media has
        # already been mounted by payload.setup.  We can't try to mount it
        # again.  So just use what we already know to create the selector.
        # Otherwise, check to see if there's anything available.
        if source_type == SOURCE_TYPE_CDROM:
            self._cdrom = source_proxy.DeviceName
        elif not flags.automatedInstall:
            self._cdrom = find_optical_install_media()

        if self._cdrom:
            self._show_autodetect_box_with_device(self._cdrom)

        if source_type == SOURCE_TYPE_HDD:
            self._current_iso_file = source_proxy.GetIsoPath() or None

            if not self._current_iso_file:
                # Installation from an expanded install tree
                device_spec = source_proxy.Partition
                device_name = self._get_device_name(device_spec)
                self._show_autodetect_box(device_name, device_spec)

        # Enable the SE/HMC option.
        gtk_call_once(self._hmc_button.set_no_show_all, False)

        self._ready = True
        # Wait to make sure the other threads are done before sending ready, otherwise
        # the spoke may not be set sensitive by _handleCompleteness in the hub.
        while not self.ready:
            time.sleep(1)
        hubQ.send_ready(self.__class__.__name__)

        # report that the source spoke has been initialized
        self.initialize_done()

    def _show_autodetect_box_with_device(self, device_name):
        device_data = DeviceData.from_structure(
            self._device_tree.GetDeviceData(device_name)
        )
        device_label = device_data.attrs.get("label", "")
        self._show_autodetect_box(device_name, device_label)

    def _show_autodetect_box(self, device_name, device_label):
        fire_gtk_action(self._autodetect_device_label.set_text, _("Device: %s") % device_name)
        fire_gtk_action(self._autodetect_label.set_text, _("Label: %s") % device_label)

        gtk_call_once(self._autodetect_box.set_no_show_all, False)
        gtk_call_once(self._autodetect_button.set_no_show_all, False)

    def refresh(self):
        NormalSpoke.refresh(self)

        # Find all hard drive partitions that could hold an ISO and add each
        # to the partitionStore.  This has to be done here because if the user
        # has done partitioning first, they may have blown away partitions
        # found during _initialize on the partitioning spoke.
        store = self.builder.get_object("partitionStore")
        store.clear()

        added = False
        idx = 0

        active_idx = 0
        active_name = None

        source_proxy = self.payload.get_source_proxy()
        source_type = source_proxy.Type

        if source_type == SOURCE_TYPE_HDD:
            device_spec = source_proxy.Partition
            active_name = self._get_device_name(device_spec)

        for device_name in find_potential_hdiso_sources():
            device_info = get_hdiso_source_info(self._device_tree, device_name)
            device_desc = get_hdiso_source_description(device_info)
            store.append([device_name, device_desc])

            if device_name == active_name:
                active_idx = idx

            added = True
            idx += 1

        # Again, only display these widgets if an HDISO source was found.
        self._iso_box.set_no_show_all(not added)
        self._iso_box.set_visible(added)
        self._iso_button.set_no_show_all(not added)
        self._iso_button.set_visible(added)

        if added:
            combo = self.builder.get_object("isoPartitionCombo")
            combo.set_active(active_idx)

    def _get_selected_partition(self):
        """Get a name of the selected partition."""
        store = self.builder.get_object("partitionStore")
        combo = self.builder.get_object("isoPartitionCombo")

        selected = combo.get_active()
        if selected == -1:
            return None
        else:
            return store[selected][0]

    # Signal handlers.
    def on_source_toggled(self, button, relatedBox):
        # When a radio button is clicked, this handler gets called for both
        # the newly enabled button as well as the previously enabled (now
        # disabled) button.
        pass

    def on_back_clicked(self, button):
        """If any input validation checks failed, keep the user on the screen.
           Otherwise, do the usual thing."""
        NormalSpoke.on_back_clicked(self, button)

    def on_info_bar_clicked(self, *args):
        log.debug("info bar clicked: %s (%s)", self._error, args)
        if not self.payload.verbose_errors:
            return

        dlg = Gtk.MessageDialog(flags=Gtk.DialogFlags.MODAL,
                                message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.CLOSE,
                                message_format="\n".join(self.payload.verbose_errors))
        dlg.set_decorated(False)

        with self.main_window.enlightbox(dlg):
            dlg.run()
            dlg.destroy()

    def on_chooser_clicked(self, button):
        dialog = IsoChooser(self.data)

        # If the chooser has been run once before, we should make it default to
        # the previously selected file.
        if self._current_iso_file:
            dialog.refresh(currentFile=self._current_iso_file)
        else:
            dialog.refresh()

        with self.main_window.enlightbox(dialog.window):
            iso_file = dialog.run(self._get_selected_partition())

        if iso_file and iso_file.endswith(".iso"):
            self._current_iso_file = iso_file
            button.set_label(os.path.basename(iso_file))
            button.set_use_underline(False)
            self._verify_iso_button.set_sensitive(True)

    def on_proxy_clicked(self, button):
        dialog = ProxyDialog(self.data, self._proxy_url)
        with self.main_window.enlightbox(dialog.window):
            dialog.refresh()
            dialog.run()

        if self._proxy_url != dialog.proxy_url:
            self._proxy_change = True
            self._proxy_url = dialog.proxy_url

    def on_verify_iso_clicked(self, button):
        partition = self._get_selected_partition()
        iso_file = self._current_iso_file

        if not partition or not iso_file:
            return

        dialog = MediaCheckDialog(self.data)
        with self.main_window.enlightbox(dialog.window):
            path = payload_utils.get_device_path(partition)

            # FIXME: Use a unique mount point.
            mounts = payload_utils.get_mount_paths(path)
            mountpoint = None
            # We have to check both ISO_DIR and the DRACUT_ISODIR because we
            # still reference both, even though /mnt/install is a symlink to
            # /run/install.  Finding mount points doesn't handle the symlink
            if constants.ISO_DIR not in mounts and constants.DRACUT_ISODIR not in mounts:
                # We're not mounted to either location, so do the mount
                mountpoint = constants.ISO_DIR
                payload_utils.mount_device(partition, mountpoint)
            dialog.run(constants.ISO_DIR + "/" + iso_file)

            if not mounts:
                payload_utils.unmount_device(partition, mountpoint)

    def on_verify_media_clicked(self, button):
        if not self._cdrom:
            return

        dialog = MediaCheckDialog(self.data)
        with self.main_window.enlightbox(dialog.window):
            dialog.run("/dev/" + self._cdrom)

    def _get_repo_by_id(self, repo_id):
        """ Return a repository by given name
        """
        for repo in self._repo_store:
            if repo[REPO_OBJ].repo_id == repo_id:
                return repo[REPO_OBJ]
        return None

    def on_repoSelection_changed(self, *args):
        """ Called when the selection changed.

            Update the repo text boxes with the current information
        """
        pass

    def on_repoEnable_toggled(self, renderer, path):
        """ Called when the repo Enable checkbox is clicked
        """
        enabled = not self._repo_store[path][REPO_ENABLED_COL]
        self._set_repo_enabled(path, enabled)

    def _set_repo_enabled(self, repo_model_path, enabled):
        self._repo_store[repo_model_path][REPO_ENABLED_COL] = enabled
        self._repo_store[repo_model_path][REPO_OBJ].enabled = enabled

    def on_urlEntry_changed(self, editable, data=None):
        pass

    def on_addRepo_clicked(self, button):
        """ Add a new repository
        """
        existing_names = [r[REPO_NAME_COL] for r in self._repo_store]
        name = get_unique_repo_name(existing_names)
        repo = self.data.RepoData(name=name)
        repo.ks_repo = True
        repo.orig_name = ""
        # Set addon repo id and increment counter
        repo.repo_id = next(self._repo_counter)

        itr = self._repo_store.append([True, repo.name, repo])
        self._repo_selection.select_iter(itr)
        self._repo_entry_box.set_sensitive(True)

    def on_removeRepo_clicked(self, button):
        """Remove the selected repository"""

    def on_resetRepos_clicked(self, button):
        """ Revert to the default list of repositories"""

    def on_repoNameEntry_changed(self, entry):
        """ repo name changed
        """

    def on_repoStore_row_changed(self, model, path, itr, user_data=None):
        pass

    def on_repoStore_row_deleted(self, model, path, user_data=None):
        pass

    def on_repoStore_row_inserted(self, model, path, itr, user_data=None):
        pass

    def on_repoProtocolComboBox_changed(self, combobox, user_data=None):
        # Set the url type and proxy fields sensitivity depending on whether NFS was selected
        source_id = self._repo_protocol_combo_box.get_active_id()
