#
# Custom partitioning classes.
#
# Copyright (C) 2012-2014  Red Hat, Inc.
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

# TODO:
# - Deleting an LV is not reflected in available space in the bottom left.
#   - this is only true for preexisting LVs
# - Device descriptions, suggested sizes, etc. should be moved out into a support file.
# - Tabbing behavior in the accordion is weird.
# - Implement striping and mirroring for LVM.
# - Activating reformat should always enable resize for existing devices.
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from blivet import devicefactory
from blivet.devicefactory import DEVICE_TYPE_BTRFS, DEVICE_TYPE_LVM_THINP, SIZE_POLICY_AUTO
from blivet.devices import MDRaidArrayDevice, LVMVolumeGroupDevice
from blivet.errors import StorageError
from blivet.size import Size

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.dbus.proxy import get_object_path
from pyanaconda.dbus.structure import compare_data
from pyanaconda.core.constants import THREAD_EXECUTE_STORAGE, THREAD_STORAGE, \
    SIZE_UNITS_DEFAULT, DEFAULT_AUTOPART_TYPE, PARTITIONING_METHOD_INTERACTIVE
from pyanaconda.core.i18n import _, N_, CP_, C_
from pyanaconda.modules.common.constants.objects import BOOTLOADER, DISK_SELECTION
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.modules.common.structures.storage import OSData, DeviceFormatData, DeviceData
from pyanaconda.modules.common.structures.validation import ValidationReport
from pyanaconda.modules.common.task import sync_run_task
from pyanaconda.modules.common.errors.configuration import BootloaderConfigurationError, \
    StorageConfigurationError
from pyanaconda.modules.common.structures.partitioning import PartitioningRequest, \
    DeviceFactoryRequest
from pyanaconda.modules.storage.partitioning.interactive_partitioning import \
    InteractiveAutoPartitioningTask
from pyanaconda.modules.storage.partitioning.interactive_utils import revert_reformat, \
    resize_device, change_encryption, reformat_device, get_device_raid_level, destroy_device, \
    rename_container, get_container, collect_containers, validate_label,\
    get_device_factory_arguments
from pyanaconda.platform import platform
from pyanaconda.product import productName, productVersion
from pyanaconda.storage.checker import verify_luks_devices_have_key, storage_checker
from pyanaconda.ui.lib.storage import reset_bootloader, create_partitioning
from pyanaconda.storage.utils import DEVICE_TEXT_MAP, MOUNTPOINT_DESCRIPTIONS, NAMED_DEVICE_TYPES, \
    CONTAINER_DEVICE_TYPES, device_type_from_autopart, filter_unsupported_disklabel_devices, \
    DEVICE_TYPE_UNSUPPORTED, filter_disks_by_names
from pyanaconda.threading import threadMgr
from pyanaconda.ui.categories.system import SystemCategory
from pyanaconda.ui.communication import hubQ
from pyanaconda.ui.gui.spokes import NormalSpoke
from pyanaconda.ui.gui.spokes.lib.accordion import MountPointSelector, Accordion, Page, \
    CreateNewPage, UnknownPage
from pyanaconda.ui.gui.spokes.lib.cart import SelectedDisksDialog
from pyanaconda.ui.gui.spokes.lib.custom_storage_helpers import get_size_from_entry, \
    get_selected_raid_level, get_default_raid_level, get_supported_container_raid_levels, \
    get_container_type, get_default_container_raid_level, AddDialog, ConfirmDeleteDialog, \
    DisksDialog, ContainerDialog, NOTEBOOK_LABEL_PAGE, NOTEBOOK_DETAILS_PAGE, NOTEBOOK_LUKS_PAGE, \
    NOTEBOOK_UNEDITABLE_PAGE, NOTEBOOK_INCOMPLETE_PAGE, NEW_CONTAINER_TEXT, CONTAINER_TOOLTIP, \
    get_supported_device_raid_levels, generate_request_description
from pyanaconda.ui.gui.spokes.lib.passphrase import PassphraseDialog
from pyanaconda.ui.gui.spokes.lib.refresh import RefreshDialog
from pyanaconda.ui.gui.spokes.lib.summary import ActionSummaryDialog
from pyanaconda.ui.gui.utils import setViewportBackground, fancy_set_sensitive, ignoreEscape, \
    really_hide, really_show, timed_action, escape_markup
from pyanaconda.ui.helpers import StorageCheckHandler

log = get_module_logger(__name__)

__all__ = ["CustomPartitioningSpoke"]


class CustomPartitioningSpoke(NormalSpoke, StorageCheckHandler):
    """
       .. inheritance-diagram:: CustomPartitioningSpoke
          :parts: 3
    """
    builderObjects = ["customStorageWindow", "containerStore", "deviceTypeStore",
                      "partitionStore", "raidStoreFiltered", "raidLevelStore",
                      "addImage", "removeImage", "settingsImage",
                      "mountPointCompletion", "mountPointStore", "fileSystemStore",
                      "luksVersionStore"]
    mainWidgetName = "customStorageWindow"
    uiFile = "spokes/custom_storage.glade"
    helpFile = "CustomSpoke.xml"

    category = SystemCategory
    title = N_("MANUAL PARTITIONING")

    # The maximum number of places to show when displaying a size
    MAX_SIZE_PLACES = 2

    # If the user enters a smaller size, the GUI changes it to this value
    MIN_SIZE_ENTRY = Size("1 MiB")

    def __init__(self, data, storage, payload):
        StorageCheckHandler.__init__(self)
        NormalSpoke.__init__(self, data, storage, payload)
        self._back_already_clicked = False
        self._initialized = False
        self._error = None
        self._accordion = None

        self._partitioning_scheme = DEFAULT_AUTOPART_TYPE
        self._default_file_system = ""
        self._selected_disks = []
        self._passphrase = ""
        self._os_name = ""

        self._partitioning = None
        self._device_tree = None
        self._request = DeviceFactoryRequest()

        self._storage_module = STORAGE.get_proxy()
        self._boot_loader = STORAGE.get_proxy(BOOTLOADER)
        self._disk_selection = STORAGE.get_proxy(DISK_SELECTION)

    def apply(self):
        self.clear_errors()

        # FIXME: Do we have to do this?
        # Make sure any device/passphrase pairs we've obtained are remembered.
        # setup_passphrase(self.storage, self._passphrase)

        hubQ.send_ready("StorageSpoke", True)

    @property
    def indirect(self):
        return True

    # This spoke has no status since it's not in a hub
    @property
    def status(self):
        return None

    def _grab_objects(self):
        self._partitionsViewport = self.builder.get_object("partitionsViewport")
        self._partitionsNotebook = self.builder.get_object("partitionsNotebook")

        # Connect partitionsNotebook focus events to scrolling in the parent viewport
        partitions_notebook_viewport = self.builder.get_object("partitionsNotebookViewport")
        self._partitionsNotebook.set_focus_vadjustment(
            Gtk.Scrollable.get_vadjustment(partitions_notebook_viewport))

        self._pageLabel = self.builder.get_object("pageLabel")

        self._availableSpaceLabel = self.builder.get_object("availableSpaceLabel")
        self._totalSpaceLabel = self.builder.get_object("totalSpaceLabel")
        self._summaryLabel = self.builder.get_object("summary_label")

        # Buttons
        self._addButton = self.builder.get_object("addButton")
        self._applyButton = self.builder.get_object("applyButton")
        self._configButton = self.builder.get_object("configureButton")
        self._removeButton = self.builder.get_object("removeButton")
        self._resetButton = self.builder.get_object("resetButton")

        # Detailed configuration stuff
        self._encryptCheckbox = self.builder.get_object("encryptCheckbox")
        self._fsCombo = self.builder.get_object("fileSystemTypeCombo")
        self._fsStore = self.builder.get_object("fileSystemStore")
        self._luksCombo = self.builder.get_object("luksVersionCombo")
        self._luksStore = self.builder.get_object("luksVersionStore")
        self._luksLabel = self.builder.get_object("luksVersionLabel")
        self._labelEntry = self.builder.get_object("labelEntry")
        self._mountPointEntry = self.builder.get_object("mountPointEntry")
        self._nameEntry = self.builder.get_object("nameEntry")
        self._raidLevelCombo = self.builder.get_object("raidLevelCombo")
        self._raidLevelLabel = self.builder.get_object("raidLevelLabel")
        self._reformatCheckbox = self.builder.get_object("reformatCheckbox")
        self._sizeEntry = self.builder.get_object("sizeEntry")
        self._typeStore = self.builder.get_object("deviceTypeStore")
        self._typeCombo = self.builder.get_object("deviceTypeCombo")
        self._modifyContainerButton = self.builder.get_object("modifyContainerButton")
        self._containerCombo = self.builder.get_object("containerCombo")
        self._containerStore = self.builder.get_object("containerStore")
        self._deviceDescLabel = self.builder.get_object("deviceDescLabel")

        # Set the fixed-size properties on the volume group ComboBox renderers to
        # False so that the "Create a new..." row can overlap with the free space
        # on the other rows. These properties are not accessible from glade.
        cell_area = self._containerCombo.get_area()
        desc_renderer = self.builder.get_object("descRenderer")
        free_space_renderer = self.builder.get_object("freeSpaceRenderer")
        cell_area.cell_set_property(desc_renderer, "fixed-size", False)
        cell_area.cell_set_property(free_space_renderer, "fixed-size", False)

        self._passphraseEntry = self.builder.get_object("passphraseEntry")

        # Stores
        self._raidStoreFilter = self.builder.get_object("raidStoreFiltered")

        # Labels
        self._selectedDeviceLabel = self.builder.get_object("selectedDeviceLabel")
        self._selectedDeviceDescLabel = self.builder.get_object("selectedDeviceDescLabel")
        self._encryptedDeviceLabel = self.builder.get_object("encryptedDeviceLabel")
        self._encryptedDeviceDescLabel = self.builder.get_object("encryptedDeviceDescriptionLabel")
        self._incompleteDeviceLabel = self.builder.get_object("incompleteDeviceLabel")
        self._incompleteDeviceDescLabel = self.builder.get_object(
            "incompleteDeviceDescriptionLabel")
        self._incompleteDeviceOptionsLabel = self.builder.get_object(
            "incompleteDeviceOptionsLabel")
        self._uneditableDeviceLabel = self.builder.get_object("uneditableDeviceLabel")
        self._uneditableDeviceDescLabel = self.builder.get_object(
            "uneditableDeviceDescriptionLabel")
        self._containerLabel = self.builder.get_object("containerLabel")

    def initialize(self):
        NormalSpoke.initialize(self)
        self.initialize_start()
        self._grab_objects()

        setViewportBackground(self.builder.get_object("availableSpaceViewport"), "#db3279")
        setViewportBackground(self.builder.get_object("totalSpaceViewport"), "#60605b")

        self._raidStoreFilter.set_visible_func(self._raid_level_visible)

        self._accordion = Accordion()
        self._partitionsViewport.add(self._accordion)

        # Connect viewport scrolling with accordion focus events
        self._accordion.set_focus_hadjustment(
            Gtk.Scrollable.get_hadjustment(self._partitionsViewport))
        self._accordion.set_focus_vadjustment(
            Gtk.Scrollable.get_vadjustment(self._partitionsViewport))

        self.initialize_done()

    def _get_unused_devices(self):
        return self._device_tree.CollectUnusedDevices()

    @property
    def _boot_drive(self):
        return self._boot_loader.Drive

    def _get_boot_loader_devices(self):
        return self._device_tree.CollectBootLoaderDevices(self._boot_drive)

    def _get_new_devices(self):
        return self._device_tree.CollectNewDevices(self._boot_drive)

    def _get_all_devices(self):
        return self._device_tree.GetDevices()

    @property
    def _supported_raid_levels(self):
        return get_supported_device_raid_levels(
            self._device_tree, self._get_current_device_type()
        )

    def _update_space_display(self):
        # Set up the free space/available space displays in the bottom left.
        disks = self._selected_disks
        free_space = Size(self._device_tree.GetDiskFreeSpace(disks))
        total_space = Size(self._device_tree.GetDiskTotalSpace(disks))

        self._availableSpaceLabel.set_text(str(free_space))
        self._totalSpaceLabel.set_text(str(total_space))

        count = len(disks)
        summary = CP_("GUI|Custom Partitioning",
                      "%d _storage device selected",
                      "%d _storage devices selected",
                      count) % count

        self._summaryLabel.set_text(summary)
        self._summaryLabel.set_use_underline(True)

    def refresh(self):
        self.clear_errors()
        NormalSpoke.refresh(self)

        # Make sure the storage spoke execute method has finished before we
        # copy the storage instance.
        for thread_name in [THREAD_EXECUTE_STORAGE, THREAD_STORAGE]:
            threadMgr.wait(thread_name)

        if not self._partitioning:
            # Create the partitioning now. It cannot by done earlier, because
            # the storage spoke would use it as a default partitioning.
            self._partitioning = create_partitioning(PARTITIONING_METHOD_INTERACTIVE)
            self._device_tree = STORAGE.get_proxy(self._partitioning.GetDeviceTree())

        self._back_already_clicked = False

        # Get the name of the new installation.
        self._os_name = self._device_tree.GenerateSystemName()

        # Get the default file system type.
        self._default_file_system = self._device_tree.GetDefaultFileSystem()

        # Initialize the selected disks.
        selected_disks = self._disk_selection.SelectedDisks
        partitioned_devices = self._device_tree.PartitionedDevices
        self._selected_disks = filter_disks_by_names(partitioned_devices, selected_disks)

        # Update the UI elements.
        self._do_refresh()
        self._update_space_display()
        self._applyButton.set_sensitive(False)

    def _get_container_names(self):
        for data in self._containerStore:
            yield data[0]

    def _get_fstype(self, fstype_combo):
        itr = fstype_combo.get_active_iter()
        if not itr:
            return None

        model = fstype_combo.get_model()
        return model[itr][0]

    def _get_autopart_type(self, autopart_type_combo):
        itr = autopart_type_combo.get_active_iter()
        if not itr:
            return DEFAULT_AUTOPART_TYPE

        model = autopart_type_combo.get_model()
        return model[itr][1]

    def _change_autopart_type(self, autopart_type_combo):
        """
        This is called when the autopart type combo on the left hand side of
        custom partitioning is changed.  We already know how to handle the case
        where the user changes the type and then clicks the autopart link
        button.  This handles the case where the user changes the type and then
        clicks the '+' button.

        """
        self._partitioning_scheme = self._get_autopart_type(autopart_type_combo)

    def _set_page_label_text(self):
        if self._accordion.is_multiselection:
            select_tmpl = _("%(items_selected)s of %(items_total)s mount points in %(page_name)s")
            span_tmpl = "<span size='large' weight='bold' fgcolor='%s'>%s</span>"
            pages_count = ""
            for page in self._accordion.all_pages:
                if not page.members:
                    continue

                if page.selected_members:
                    highlight_color = "black"
                    page_text_tmpl = select_tmpl
                else:
                    highlight_color = "gray"
                    page_text_tmpl = "<span fgcolor='gray'>%s</span>" % escape_markup(select_tmpl)

                selected_str = span_tmpl % (escape_markup(highlight_color),
                                            escape_markup(str(len(page.selected_members))))
                total_str = span_tmpl % (escape_markup(highlight_color),
                                         escape_markup(str(len(page.members))))
                page_name = span_tmpl % (escape_markup(highlight_color),
                                         escape_markup(page.pageTitle))

                page_line = page_text_tmpl % {"items_selected": selected_str,
                                              "items_total": total_str,
                                              "page_name": page_name}
                pages_count += page_line + "\n"

            self._pageLabel.set_markup(
                _("Please select a single mount point to edit properties.\n\n"
                  "You have currently selected:\n"
                  "%s") % pages_count)
        else:
            self._pageLabel.set_text(
                _("When you create mount points for your %(name)s %(version)s "
                  "installation, you'll be able to view their details here.")
                % {"name": productName, "version": productVersion})

    def _populate_accordion(self):
        # Make sure we start with a clean state.
        self._accordion.remove_all_pages()

        new_devices = filter_unsupported_disklabel_devices(self._get_new_devices())
        all_devices = filter_unsupported_disklabel_devices(self._get_all_devices())
        unused_devices = filter_unsupported_disklabel_devices(self._get_unused_devices())

        # Collect the existing roots.
        ui_roots = OSData.from_structure_list(
            self._device_tree.CollectSupportedSystems()
        )

        # Now it's time to populate the accordion.
        log.debug("Populating accordion for devices %s (unused %s, new %s).",
                  all_devices, unused_devices, new_devices)

        # Add the initial page.
        if not new_devices:
            self._add_initial_page(reuse_existing=bool(ui_roots or unused_devices))
        else:
            new_root = OSData.from_structure(
                self._device_tree.GenerateSystemData(self._boot_drive)
            )
            ui_roots.insert(0, new_root)

        # Add root pages.
        for root in ui_roots:
            self._add_root_page(root)

        # Add the unknown page.
        if unused_devices:
            self._add_unknown_page(unused_devices)

    def _add_initial_page(self, reuse_existing=False):
        page = CreateNewPage(
            self._os_name,
            self.on_create_clicked,
            self._change_autopart_type,
            partitions_to_reuse=reuse_existing
        )

        self._accordion.add_page(page, cb=self.on_page_clicked)
        self._partitionsNotebook.set_current_page(NOTEBOOK_LABEL_PAGE)
        self._set_page_label_text()

    def _add_root_page(self, root):
        page = Page(root.os_name)
        self._accordion.add_page(page, cb=self.on_page_clicked)

        for mount_point, device_name in root.mount_points.items():
            selector = MountPointSelector()
            self._update_selector(
                selector,
                device_name=device_name,
                root_name=root.name,
                mount_point=mount_point
            )
            page.add_selector(selector, self.on_selector_clicked)

        for device_name in root.swap_devices:
            selector = MountPointSelector()
            self._update_selector(
                selector,
                device_name=device_name,
                root_name=root.name
            )
            page.add_selector(selector, self.on_selector_clicked)

        page.show_all()

    def _add_unknown_page(self, devices):
        page = UnknownPage(_("Unknown"))
        self._accordion.add_page(page, cb=self.on_page_clicked)

        for device_name in sorted(devices):
            selector = MountPointSelector()
            self._update_selector(selector, device_name)
            page.add_selector(selector, self.on_selector_clicked)

        page.show_all()

    def _update_selector(self, selector, device_name="", root_name="", mount_point=""):
        if not selector:
            return

        if not device_name:
            device_name = selector.device_name

        if not root_name:
            root_name = selector.root_name

        device_data = DeviceData.from_structure(
            self._device_tree.GetDeviceData(device_name)
        )

        format_data = DeviceFormatData.from_structure(
            self._device_tree.GetFormatData(device_name)
        )

        mount_point = \
            format_data.attrs.get("mount_point", "") or \
            mount_point or \
            format_data.description or \
            _("Unknown")

        raw_device = self._device_tree.GetRawDevice(device_name)

        selector.props.name = device_name
        selector.props.size = str(Size(device_data.size))
        selector.props.mountpoint = mount_point
        selector.root_name = root_name

    def _do_refresh(self, mountpoint_to_show=None):
        # block mountpoint selector signal handler for now
        self._initialized = False
        self._accordion.clear_current_selector()

        # Start with buttons disabled, since nothing is selected.
        self._removeButton.set_sensitive(False)
        self._configButton.set_sensitive(False)

        # populate the accorion with roots and mount points
        self._populate_accordion()

        # And then open the first page by default.  Most of the time, this will
        # be fine since it'll be the new installation page.
        self._initialized = True
        first_page = self._accordion.all_pages[0]
        self._accordion.expand_page(first_page.pageTitle)
        self._show_mountpoint(page=first_page, mountpoint=mountpoint_to_show)

        self._applyButton.set_sensitive(False)
        self._resetButton.set_sensitive(bool(self._device_tree.GetActions()))

    ###
    ### RIGHT HAND SIDE METHODS
    ###
    def add_new_selector(self, device):
        """ Add an entry for device to the new install Page. """
        page = self._accordion.find_page_by_title(self._os_name)
        devices = [device]
        if not page.members:
            # remove the CreateNewPage and replace it with a regular Page
            expander = self._accordion.find_page_by_title(self._os_name).get_parent()
            expander.remove(expander.get_child())

            page = Page(self._os_name)
            expander.add(page)

            # also pull in biosboot and prepboot that are on our boot disk
            devices.extend(self._get_boot_loader_devices())
            devices = list(set(devices))

        for device_name in devices:
            selector = MountPointSelector()
            self._update_selector(selector, device_name)
            page.add_selector(selector, self.on_selector_clicked)

        page.show_all()

    def _update_selectors(self):
        """ Update all btrfs selectors' size properties. """
        # we're only updating selectors in the new root. problem?
        page = self._accordion.find_page_by_title(self._os_name)
        for selector in page.members:
            self._update_selector(selector)

    def _replace_device(self, selector, request):
        """ Create a replacement device and update the device selector. """
        log.debug("Replacing device: %s", request.device_name)
        arguments = get_device_factory_arguments(self._storage_playground, request)
        new_device = self._storage_playground.factory_device(**arguments)

        # update the selector with the new device and its size
        self._update_selector(selector, new_device)

    def _update_device_in_selectors(self, old_device, new_device):
        for selector in self._accordion.all_selectors:
            if selector.device_name == old_device:
                self._update_selector(selector, new_device)

    def _update_size_props(self):
        self._update_selectors()
        self._update_space_display()

    def _try_replace_device(self, selector, removed_device, new_request, old_request):
        if removed_device:
            # we don't want to pass the device if we removed it
            new_request.device_spec = ""

        try:
            self._replace_device(selector, new_request)
            return True
        except StorageError as e:
            log.error("Failed to replace device: %s", e)
            self.set_detailed_warning(_("Device reconfiguration failed."), e)

            if not removed_device:
                # nothing more to do
                return True
            else:
                try:
                    self._replace_device(selector, old_request)
                    return True
                except StorageError as e:
                    # failed to recover.
                    self.refresh()  # this calls self.clear_errors
                    self.set_detailed_warning(_("Storage configuration reset due "
                                                "to unrecoverable error."), e)
                    return False

    def _handle_encryption_change(self, encrypted, luks_version, device, old_device, selector):
        log.debug("Changing encryption: %s", device.name)

        old_device = device
        new_device = change_encryption(
            storage=self._storage_playground,
            device=device,
            encrypted=encrypted,
            luks_version=luks_version
        )

        # update the selectors
        selector.device = new_device
        self._update_device_in_selectors(old_device, new_device)

        # possibly changed device and old_device, need to return the new ones
        return new_device, old_device

    def _do_reformat(self, selector, old_request, new_request):
        log.debug("Reformatting device: %s", new_request.device_name)
        device = selector.device
        mountpoint = new_request.mount_point
        label = new_request.label
        encrypted = new_request.device_encrypted
        luks_version = new_request.luks_version
        fs_type = new_request.format_type

        self.clear_errors()
        #
        # ENCRYPTION
        #
        old_device = None

        if old_request.device_encrypted != new_request.device_encrypted:
            device, old_device = self._handle_encryption_change(
                encrypted, luks_version, device, old_device, selector
            )
        elif encrypted and old_request.luks_version != new_request.luks_version:

            device, old_device = self._handle_encryption_change(
                False, luks_version, device, old_device, selector
            )

            device, old_device = self._handle_encryption_change(
                True, luks_version, device, old_device, selector
            )
        #
        # FORMATTING
        #
        try:
            reformat_device(
                storage=self._storage_playground,
                device=device,
                fstype=fs_type,
                mountpoint=mountpoint,
                label=label
            )
        except StorageError as e:
            self.set_detailed_warning(_("Device reformat request failed."), e)
        else:
            # first, remove this selector from any old install page(s)
            new_selector = None
            for (page, _selector) in self._accordion.all_members:
                if _selector.device in (device, old_device):
                    if page.pageTitle == self._os_name:
                        new_selector = _selector
                        continue

                    page.remove_selector(_selector)
                    if not page.members:
                        self._accordion.remove_page(page.pageTitle)

            # either update the existing selector or add a new one
            if new_selector:
                self._update_selector(new_selector, device)
            else:
                self.add_new_selector(device)

        # possibly changed device, need to return the new one
        return device

    def _save_right_side(self, selector):
        """ Save settings from RHS and apply changes to the device.

            This method must never trigger a call to self._do_refresh.
        """
        self.clear_errors()

        # check if initialized and have something to operate on
        if not self._initialized or not selector:
            return

        # only call _save_right_side if on the right page and some changes need
        # to be saved (sensitivity of the Update Settings button reflects that)
        if self._partitionsNotebook.get_current_page() != NOTEBOOK_DETAILS_PAGE or \
                not self._applyButton.get_sensitive():
            return

        device_name = selector.device_name
        if device_name not in self._device_tree.GetDevices():
            # just-removed device
            return

        self._back_already_clicked = False

        log.debug("Saving the right side for device: %s", device_name)

        # Get the device factory request.
        old_request = DeviceFactoryRequest.from_structure(
            self._device_tree.GenerateDeviceFactoryRequest(device_name)
        )
        new_request = self._get_new_device_factory_request(device_name, old_request)

        # Log the results.
        description = generate_request_description(new_request, old_request)
        log.debug("Device request: %s", description)

        # Validate the device info.
        report = ValidationReport.from_structure(
            self._device_tree.ValidateDeviceFactoryRequest(
                DeviceFactoryRequest.to_structure(new_request)
            )
        )
        log.debug("Validation result: %s", report)

        if not report.is_valid():
            self.set_warning(" ".join(report.get_messages()))
            self._populate_right_side(selector)
            return

        # Apply the changes.
        self.clear_errors()

        if not device.raw_device.exists:
            self._change_device(selector, new_request, old_request)
        else:
            self._revert_device_reformat(selector, new_request.reformat)
            self._change_device_size(selector, old_request, new_request)
            self._change_device_format(selector, old_request, new_request)
            self._change_device_name(selector, old_request, new_request)

        log.debug("The device request changes are applied.")

        # Update UI.
        self._populate_right_side(selector)

    def _get_new_device_factory_request(self, device, old_request):
        log.info("Getting a new device factory request for %s", device.name)

        new_request = DeviceFactoryRequest()
        new_request.device_spec = device.name

        self._get_new_device_name(new_request, old_request)
        self._get_new_device_size(new_request, old_request)
        self._get_new_device_type(new_request, old_request)
        self._get_new_device_reformat(new_request, old_request)
        self._get_new_device_fstype(new_request, old_request)
        self._get_new_device_enctyption(new_request, old_request)
        self._get_new_device_luks_version(new_request, old_request)
        self._get_new_device_label(new_request, old_request)
        self._get_new_device_mount_point(new_request, old_request)
        self._get_new_device_raid_level(new_request, old_request)
        self._get_new_device_for_btrfs(new_request, old_request)
        self._get_new_device_disks(new_request, old_request)
        self._get_new_device_container(new_request, old_request)

        return new_request

    def _get_new_device_name(self, new_request, old_request):
        if self._nameEntry.get_sensitive():
            new_request.device_name = self._nameEntry.get_text()
        else:
            # name entry insensitive means we don't control the name
            new_request.device_name = ""
            old_request.device_name = ""

    def _get_new_device_size(self, new_request, old_request):
        # If the size text hasn't changed at all from that displayed,
        # assume no change intended.
        device = self._storage_playground.devicetree.resolve_device(new_request.device_spec)
        use_dev = device.raw_device

        size = Size(old_request.device_size)
        displayed_size = size.human_readable(max_places=self.MAX_SIZE_PLACES)

        if (displayed_size != self._sizeEntry.get_text()) \
                and (use_dev.resizable or not use_dev.exists):
            size = get_size_from_entry(
                self._sizeEntry,
                lower_bound=self.MIN_SIZE_ENTRY,
                units=SIZE_UNITS_DEFAULT
            )

        if size:
            new_request.device_size = size.get_bytes()

    def _get_new_device_type(self, new_request, old_request):
        new_request.device_type = self._get_current_device_type()

    def _get_new_device_reformat(self, new_request, old_request):
        new_request.reformat = self._reformatCheckbox.get_active()

    def _get_new_device_fstype(self, new_request, old_request):
        fs_type_index = self._fsCombo.get_active()
        fs_type_str = self._fsCombo.get_model()[fs_type_index][0]
        new_fs = get_format(fs_type_str)
        new_request.format_type = new_fs.type

    def _get_new_device_enctyption(self, new_request, old_request):
        new_request.device_encrypted = (self._encryptCheckbox.get_active()
                                        and self._encryptCheckbox.is_sensitive())

    def _get_new_device_luks_version(self, new_request, old_request):
        luks_version_index = self._luksCombo.get_active()
        luks_version_str = self._luksCombo.get_model()[luks_version_index][0]

        if new_request.device_encrypted:
            new_request.luks_version = luks_version_str

    def _get_new_device_label(self, new_request, old_request):
        new_request.label = self._labelEntry.get_text()

    def _get_new_device_mount_point(self, new_request, old_request):
        if self._mountPointEntry.get_sensitive():
            new_request.mount_point = self._mountPointEntry.get_text()

    def _get_new_device_raid_level(self, new_request, old_request):
        new_request.device_raid_level = get_selected_raid_level(self._raidLevelCombo)

    def _get_new_device_for_btrfs(self,  new_request, old_request):
        # FIXME: Move this code to the new methods.
        device = self._storage_playground.devicetree.resolve_device(new_request.device_spec)
        use_dev = device.raw_device

        # If the device is a btrfs volume, the only things we can set/update
        # are mountpoint and container-wide settings.
        if new_request.device_type == DEVICE_TYPE_BTRFS and hasattr(use_dev, "subvolumes"):
            new_request.device_size = 0
            old_request.device_size = 0

            new_request.device_encrypted = False
            old_request.device_encrypted = False

            new_request.device_raid_level = ""
            old_request.device_raid_level = ""

    def _get_new_device_disks(self, new_request, old_request):
        new_request.disks = list(self._request.disks)

    def _get_new_device_container(self, new_request, old_request):
        # create a new factory using the appropriate size and type
        names = ("device_type", "size", "disks", "encrypted", "luks_version", "raid_level")
        arguments = get_device_factory_arguments(self._storage_playground, new_request, names)

        factory = devicefactory.get_device_factory(
            self._storage_playground,
            **arguments
        )

        # Name
        if self._request.container_name:
            new_request.container_name = self._request.container_name

        # Encryption
        if self._request.container_encrypted:
            new_request.container_encrypted = True

        # Raid level
        raid_level = self._request.container_raid_level
        supported_raid_levels = get_supported_container_raid_levels(
            self._device_tree,
            new_request.device_type
        )
        default_raid_level = get_default_container_raid_level(
            new_request.device_type
        )

        if raid_level not in supported_raid_levels:
            raid_level = default_raid_level

        if raid_level:
            new_request.container_raid_level = raid_level

        # Size
        new_request.container_size_policy = self._request.container_size_policy

        # Disks
        container = factory.get_container()

        if container and old_request.device_type != new_request.device_type:
            log.debug("Overriding disk set with container's.")
            new_request.disks = [d.name for d in container.disks]

    def _change_device(self, selector, new_request, old_request):
        log.debug("Changing device: %s", old_request.device_name)

        # If something has changed but the device does not exist,
        # there is no need to schedule actions on the device.
        # It is only necessary to create a new device object
        # which reflects the current choices.
        device = selector.device

        if compare_data(new_request, old_request):
            log.debug("Nothing has changed.")
            return

        removed_device = (
            (old_request.device_type != new_request.device_type) or
            (old_request.container_name and
             new_request.container_name != old_request.container_name)
        )

        if removed_device:
            # remove the current device
            success = self._destroy_device(device)

            if not success:
                # the removal failed. don't continue.
                return

        success = self._try_replace_device(
            selector, removed_device, new_request, old_request
        )

        if not success:
            # failed, nothing more to be done
            return

        self._update_device_in_selectors(device, selector.device)
        self._update_size_props()

    def _revert_device_reformat(self, selector, reformat):
        log.debug("Reverting device reformat: %s", reformat)
        # Handle deactivation of the reformat checkbutton after having committed
        # a reformat.
        device = selector.device

        if not reformat:
            revert_reformat(self._storage_playground, device)

    def _change_device_size(self, selector, old_request, new_request):
        log.debug("Changing device size: %s", Size(new_request.device_size))
        device = selector.device

        if new_request.device_size != old_request.device_size:
            try:
                changed_size = resize_device(
                    self._storage_playground,
                    device,
                    Size(new_request.device_size),
                    Size(old_request.device_size)
                )
            except StorageError as e:
                self.set_detailed_warning(_("Device resize request failed."), e)
                return

            if changed_size:
                # update the selector's size property
                # The selector shows the visible disk, so it is necessary
                # to use device and size, which are the values visible to
                # the user.
                for s in self._accordion.all_selectors:
                    if s._device == device:
                        s.size = str(device.size)

                # update size props of all btrfs devices' selectors
                self._update_size_props()

    def _change_device_format(self, selector, old_request, new_request):
        log.debug("Changing device format: %s", new_request.format_type)

        # it's possible that reformat is active but fstype is unchanged, in
        # which case we're not going to schedule another reformat unless
        # encryption got toggled
        device = selector.device
        reformat = new_request.reformat
        changed_encryption = (old_request.device_encrypted != new_request.device_encrypted)
        changed_luks_version = (old_request.luks_version != new_request.luks_version)
        changed_fs_type = (old_request.format_type != new_request.format_type)

        do_reformat = (reformat and (changed_encryption or
                                     changed_luks_version or
                                     changed_fs_type or
                                     device.format.exists))

        # Handle reformat
        if do_reformat:
            self._do_reformat(selector, old_request, new_request)
        else:
            # Set various attributes that do not require actions.
            self._change_device_label(selector, old_request, new_request)
            self._change_device_mount_point(selector, old_request, new_request)

    def _change_device_label(self, selector, old_request, new_request):
        log.debug("Changing device label: %s", new_request.label)
        device = selector.device
        label = new_request.label

        if old_request.label != label and hasattr(device.format, "label") and \
                not validate_label(label, device.format):
            self.clear_errors()
            device.format.label = label

    def _change_device_mount_point(self, selector, old_request, new_request):
        log.debug("Changing device mount point: %s", new_request.mount_point)
        device = selector.device
        mountpoint = new_request.mount_point

        if mountpoint and old_request.mount_point != mountpoint:
            self.clear_errors()
            device.format.mountpoint = mountpoint
            if old_request.mount_point:
                self._update_selector(selector, device)
            else:
                # add an entry to the new page but do not remove any entries
                # from other pages since we haven't altered the filesystem
                self.add_new_selector(device)

    def _change_device_name(self, selector, old_request, new_request):
        log.debug("Changing device name: %s", new_request.device_name)
        device_name = selector.device_name
        use_dev = device.raw_device
        name = new_request.device_name
        old_name = old_request.device_name
        changed_name = new_request.device_name != old_request.device_name

        if changed_name:
            self.clear_errors()
            try:
                use_dev.name = name
            except ValueError as e:
                self.set_detailed_error(_("Invalid device name."), e)
            else:
                new_name = use_dev.name
                if new_name in self._storage_playground.names:
                    use_dev.name = old_name
                    self.set_info(_("Specified name %s already in use.") % new_name)
                else:
                    self._update_selector(selector, new_name)

    def _raid_level_visible(self, model, itr, user_data):
        raid_level = model[itr][1]
        return raid_level in self._supported_raid_levels

    def _populate_raid(self, raid_level):
        """Set up the raid-specific portion of the device details.

        :param str raid_level: RAID level name or an empty string
        """
        if not self._supported_raid_levels:
            for widget in [self._raidLevelLabel, self._raidLevelCombo]:
                really_hide(widget)
            return

        device_type = self._get_current_device_type()
        raid_level = raid_level or get_default_raid_level(device_type)

        # Set a default RAID level in the combo.
        for (i, row) in enumerate(self._raidLevelCombo.get_model()):
            if row[1] == raid_level:
                self._raidLevelCombo.set_active(i)
                break

        for widget in [self._raidLevelLabel, self._raidLevelCombo]:
            really_show(widget)

    def _populate_luks(self, luks_version):
        """Set up the LUKS version combo box.

        :param luks_version: a LUKS version or None
        """
        # Add the values.
        self._luksStore.clear()
        for version in ["luks1", "luks2"]:
            self._luksStore.append([version])

        # Get the selected value.
        luks_version = luks_version or self._device_tree.GetDefaultLUKSVersion()

        # Set the selected value.
        idx = next(
            i for i, data in enumerate(self._luksCombo.get_model())
            if data[0] == luks_version
        )
        self._luksCombo.set_active(idx)
        self.on_encrypt_toggled(self._encryptCheckbox)

    def _get_current_device_type(self):
        """ Return integer for type combo selection.

            :returns: the corresponding integer code, a constant in
            blivet.devicefactory.
            :rtype: int or NoneType
        """
        itr = self._typeCombo.get_active_iter()
        if not itr:
            return None

        device_type = self._typeStore[itr][1]
        if device_type == DEVICE_TYPE_UNSUPPORTED:
            return None

        return device_type

    def _setup_fstype_combo(self, device_type, device_format_type, format_types):
        """Setup the filesystem combo box."""
        format_data = DeviceFormatData.from_structure(
            self._device_tree.GetFormatTypeData(device_format_type)
        )
        default = format_data.description

        # Add all desired fileystem type names to the box, sorted alphabetically
        self._fsStore.clear()
        for ty in format_types:
            self._fsStore.append([ty])

        # set the active filesystem type
        idx = next(i for i, data in enumerate(self._fsCombo.get_model()) if data[0] == default)
        self._fsCombo.set_active(idx)

        # do additional updating handled by other method
        self._update_fstype_combo(device_type)

    def _setup_device_type_combo(self, device_type, device_types):
        """Set up device type combo."""
        # Include md only if there are two or more disks.
        if len(self._selected_disks) <= 1:
            device_types.remove(devicefactory.DEVICE_TYPE_MD)

        # For existing unsupported device add the information in the UI.
        if device_type not in device_types:
            log.debug("Existing device with unsupported type %s found.", device_type)
            device_type = DEVICE_TYPE_UNSUPPORTED
            device_types.append(device_type)

        # Add values.
        self._typeStore.clear()
        for dt in device_types:
            self._typeStore.append([_(DEVICE_TEXT_MAP[dt]), dt])

        # Set the selected value.
        idx = next(
            i for i, data in enumerate(self._typeCombo.get_model())
            if data[1] == device_type
        )
        self._typeCombo.set_active(idx)

    def _get_device_name(self, device_type):
        """Update the dictionary of device names."""
        if device_type == self._request.device_type:
            return self._request.device_name
        elif device_type in NAMED_DEVICE_TYPES:
            return self._device_tree.GenerateDeviceName(
                self._request.mount_point,
                self._request.format_type
            )
        else:
            return ""

    def _set_devices_label(self):
        disks = self._request.disks

        if not disks:
            description = _("No disks assigned")
        else:
            device_data = DeviceData.from_structure(
                self._device_tree.GetDeviceData(disks[0])
            )
            description = "{} ({})".format(
                device_data.description,
                device_data.name
            )
            num_disks = len(disks)

            if num_disks > 1:
                description += CP_(
                    "GUI|Custom Partitioning|Devices",
                    " and {} other", " and {} others",
                    num_disks - 1
                ).format(num_disks - 1)

        self._deviceDescLabel.set_text(description)

    def _populate_right_side(self, selector):
        device_name = selector.device_name

        request = DeviceFactoryRequest.from_structure(
            self._device_tree.GenerateDeviceFactoryRequest(device_name)
        )
        format_data = DeviceData.from_structure(
            self._device_tree.GetDeviceData(device_name)
        )

        description = generate_request_description(request)
        log.debug("Populating the right side for device %s: %s", device_name, description)

        self._request = request
        self._selectedDeviceLabel.set_text(device_name)
        self._selectedDeviceDescLabel.set_text(
            _(MOUNTPOINT_DESCRIPTIONS.get(device_name, ""))
        )

        self._set_devices_label()

        self._nameEntry.set_text(request.device_name)
        self._mountPointEntry.set_text(request.mount_point)
        fancy_set_sensitive(self._mountPointEntry, format_data.mountable)

        self._labelEntry.set_text(request.label)
        fancy_set_sensitive(self._labelEntry, True)

        self._sizeEntry.set_text(
            Size(request.device_size).human_readable(max_places=self.MAX_SIZE_PLACES)
        )

        self._reformatCheckbox.set_active(request.reformat)
        fancy_set_sensitive(self._reformatCheckbox,
                            use_dev.exists and not use_dev.format_immutable)

        self._encryptCheckbox.set_active(request.device_encrypted)
        fancy_set_sensitive(self._encryptCheckbox, self._reformatCheckbox.get_active())

        if request.container_encrypted:
            # The encryption checkbutton should not be sensitive if there is
            # existing encryption below the leaf layer.
            fancy_set_sensitive(self._encryptCheckbox, False)
            self._encryptCheckbox.set_active(True)
            self._encryptCheckbox.set_tooltip_text(_("The container is encrypted."))
        else:
            self._encryptCheckbox.set_tooltip_text("")

        # Set up the filesystem type combo.
        format_types = self._device_tree.GetFileSystemsForDevice(device_name)
        self._setup_fstype_combo(request.device_type, request.format_type, format_types)

        # Set up the device type combo.
        device_types = self._device_tree.GetDeviceTypesForDevice(device_name)
        self._setup_device_type_combo(request.device_type, device_types)

        # Get the current device type.
        device_type = self._get_current_device_type()

        # You can't change the fstype in some cases.
        is_sensitive = self._reformatCheckbox.get_active() \
            and device_type != DEVICE_TYPE_BTRFS

        fancy_set_sensitive(self._fsCombo, is_sensitive)

        # you can't change the type of an existing device
        fancy_set_sensitive(self._typeCombo, not use_dev.exists)
        fancy_set_sensitive(self._raidLevelCombo, not use_dev.exists)

        # FIXME: device encryption should be mutually exclusive with container
        # encryption

        # FIXME: device raid should be mutually exclusive with container raid

        # you can't encrypt a btrfs subvolume -- only the volume/container
        # XXX CHECKME: encryption of thin logical volumes is not supported at this time
        if device_type in [DEVICE_TYPE_BTRFS, DEVICE_TYPE_LVM_THINP]:
            fancy_set_sensitive(self._encryptCheckbox, False)

        # The size entry is only sensitive for resizable existing devices and
        # new devices that are not btrfs subvolumes.
        # Do this after the device type combo is set since
        # on_device_type_changed doesn't account for device existence.
        fancy_set_sensitive(
            self._sizeEntry,
            device.resizable or (not device.exists and device.format.type != "btrfs")
        )

        if self._sizeEntry.get_sensitive():
            self._sizeEntry.props.has_tooltip = False
        elif format_data.type == "btrfs":
            self._sizeEntry.set_tooltip_text(_(
                "The space available to this mount point can "
                "be changed by modifying the volume below."
            ))
        else:
            self._sizeEntry.set_tooltip_text(_(
                "This file system may not be resized."
            ))

        self._populate_raid(request.device_raid_level)
        self._populate_container(use_dev)
        self._populate_luks(request.luks_version)

        # do this last to override the decision made by on_device_type_changed if necessary
        if use_dev.exists or use_dev.type == "btrfs volume":
            fancy_set_sensitive(self._nameEntry, False)

    ###
    ### SIGNAL HANDLERS
    ###

    def on_key_pressed(self, widget, event, *args):
        if not event or event and event.type != Gdk.EventType.KEY_RELEASE:
            return

        if event.keyval in [Gdk.KEY_Delete, Gdk.KEY_minus]:
            # But we only want delete to work if you have focused a MountpointSelector,
            # and not just any random widget.  For those, it's likely the user wants
            # to delete a character.
            if isinstance(self.main_window.get_focus(), MountpointSelector):
                self._removeButton.emit("clicked")
        elif event.keyval == Gdk.KEY_plus:
            # And we only want '+' to work if you don't have a text entry focused, since
            # the user might be entering some free-form text that can include a plus.
            if not isinstance(self.main_window.get_focus(), Gtk.Entry):
                self._addButton.emit("clicked")

    def _setup_passphrase(self):
        # Find new LUKS devices without a passphrase.
        devices = self._device_tree.FindUnconfiguredLUKS()

        if not devices:
            return True

        # Ask for a passphrase.
        dialog = PassphraseDialog(self.data, default_passphrase=self._passphrase)
        with self.main_window.enlightbox(dialog.window):
            rc = dialog.run()

        # Cancel. Leave the old passphrase set if there was one.
        if rc != 1:
            return False

        # Set the new passphrase.
        self._passphrase = dialog.passphrase

        # Configure the devices.
        for device_name in devices:
            self._device_tree.SetDevicePassphrase(device_name, self._passphrase)

        return True

    def _do_check(self):
        self.clear_errors()
        StorageCheckHandler.errors = []
        StorageCheckHandler.warnings = []

        try:
            log.debug("Generating updated storage configuration")
            task_path = self._partitioning.ConfigureWithTask()
            task_proxy = STORAGE.get_proxy(task_path)
            sync_run_task(task_proxy)
        except BootloaderConfigurationError as e:
            log.error("Storage configuration failed: %s", e)
            StorageCheckHandler.errors = [str(e)]
            reset_bootloader()
        else:
            log.debug("Checking storage configuration...")
            task_path = self._partitioning.ValidateWithTask()
            task_proxy = STORAGE.get_proxy(task_path)
            sync_run_task(task_proxy)
            report = ValidationReport.from_structure(
                task_proxy.GetResult()
            )

            log.error("\n".join(report.get_messages()))
            StorageCheckHandler.errors = report.error_messages
            StorageCheckHandler.warnings = report.warning_messages

            if report.is_valid():
                self._storage_module.ApplyPartitioning(
                    get_object_path(self._partitioning)
                )

        if self.errors:
            self.set_warning(_(
                "Error checking storage configuration. <a href=\"\">Click for details</a> "
                "or press Done again to continue."))
        elif self.warnings:
            self.set_warning(_(
                "Warning checking storage configuration. <a href=\"\">Click for details</a> "
                "or press Done again to continue."))

        # on_info_bar_clicked requires self._error to be set, so set it to the
        # list of all errors and warnings that storage checking found.
        self._error = "\n".join(self.errors + self.warnings)

        return self._error == ""

    def on_back_clicked(self, button):
        # Clear any existing errors
        self.clear_errors()

        # Save anything from the currently displayed mountpoint.
        self._save_right_side(self._accordion.current_selector)
        self._applyButton.set_sensitive(False)

        # And then display the summary screen.  From there, the user will either
        # head back to the hub, or stay on the custom screen.
        # If back has been clicked on once already and no other changes made on the screen,
        # run the storage check now.  This handles displaying any errors in the info bar.
        if not self._back_already_clicked:
            self._back_already_clicked = True

            # If we hit any errors while saving things above, stop and let the
            # user think about what they have done
            if self._error is not None:
                return

            if not self._setup_passphrase():
                return

            if not self._do_check():
                return

        dialog = ActionSummaryDialog(self.data, self._device_tree)
        dialog.refresh()

        if dialog.actions:
            with self.main_window.enlightbox(dialog.window):
                rc = dialog.run()

            if rc != 1:
                # Cancel.  Stay on the custom screen.
                return

        NormalSpoke.on_back_clicked(self, button)

    def on_add_clicked(self, button):
        self._save_right_side(self._accordion.current_selector)

        # Initialize and run the AddDialog.
        dialog = AddDialog(self.data, self._device_tree)
        dialog.refresh()

        with self.main_window.enlightbox(dialog.window):
            rc = dialog.run()

            if rc != 1:
                # user cancel
                dialog.window.destroy()
                return

        self._back_already_clicked = False

        # Gather data about the added mount point.
        request = DeviceFactoryRequest()
        request.mount_point = dialog.mount_point
        request.device_size = dialog.size.get_bytes()
        request.device_type = device_type_from_autopart(self._partitioning_scheme)
        request.disks = self._selected_disks

        # Clear errors and try to add the mountpoint/device.
        self.clear_errors()

        try:
            self._device_tree.AddDevice(
                DeviceFactoryRequest.to_structure(request)
            )
        except StorageError as e:
            self.set_detailed_error(_("Failed to add new device."), e)
            self._do_refresh()
        else:
            self._do_refresh(mountpoint_to_show=dialog.mount_point)

        self._update_space_display()

    def _destroy_device(self, device):
        self.clear_errors()

        try:
            destroy_device(self._storage_playground, device)
            return True
        except StorageError as e:
            log.error("The device removal has failed: %s", e)
            self.set_detailed_warning(_("Device removal request failed."), e)
            return False

    def _show_mountpoint(self, page, mountpoint=None):
        if not self._initialized:
            return

        # Make sure there's something displayed on the RHS.  If a page and
        # mountpoint within that page is given, display that.
        log.debug("Showing mount point: %s", page.pageTitle)

        if not page.members:
            self._accordion.clear_current_selector()
            return

        if not mountpoint and len(self._accordion.selected_items) == 0 \
                and not page.get_parent().get_expanded():
            self._accordion.select(page.members[0])
            self.on_selector_clicked(None, page.members[0])
            return

        if mountpoint:
            for member in page.members:
                if member.get_property("mountpoint").lower() == mountpoint.lower():
                    self._accordion.select(member)
                    self.on_selector_clicked(None, member)
                    break

    def _show_confirmation_dialog(self, root_name, device_name):
        dialog = ConfirmDeleteDialog(self.data, self._device_tree, root_name, device_name,
                                     self._accordion.is_multiselection)
        dialog.refresh()

        with self.main_window.enlightbox(dialog.window):
            rc = dialog.run()
            option_checked = dialog.option_checked
            dialog.window.destroy()
            return rc, option_checked

    def on_remove_clicked(self, button):
        # Nothing selected?  Nothing to remove.
        if not self._accordion.is_current_selected and not self._accordion.is_multiselection:
            return

        option_checked = False
        part_removed = False
        is_multiselection = self._accordion.is_multiselection
        protected_types = platform.boot_stage1_constraint_dict["format_types"]

        for selector in self._accordion.selected_items:
            page = self._accordion.page_for_selector(selector)
            device_name = selector.device_name
            root_name = selector.root_name or page.page_title

            log.debug("Removing device %s from page %s.", device_name, root_name)

            if root_name == self._os_name:
                if is_multiselection and not option_checked:
                    (rc, option_checked) = self._show_confirmation_dialog(root_name, device_name)

                    if rc != 1:
                        if option_checked:
                            break  # skip evaluation of all other mountpoints
                        continue

                if device.exists:
                    # This is an existing device that was added to the new page.
                    # All we want to do is revert any changes to the device and
                    # it will end up back in whatever old pages it came from.
                    self._storage_playground.reset_device(device_name)
                else:
                    # Destroying a non-existing device doesn't require any
                    # confirmation.
                    self._destroy_device(device_name)
            else:
                # This is a device that exists on disk and most likely has data
                # on it.  Thus, we first need to confirm with the user and then
                # schedule actions to delete the thing.
                # In multiselection user could confirm once for all next
                # selections.
                if not option_checked:
                    (rc, option_checked) = self._show_confirmation_dialog(root_name, device_name)

                    if rc != 1:
                        if option_checked:
                            break  # skip evaluation of all other mountpoints
                        continue

                if option_checked and not is_multiselection:
                    otherpgs = (pg for pg in self._accordion.all_pages if pg is not page)
                    otherdevs = []
                    for otherpg in otherpgs:
                        otherdevs.extend(s.device_name for s in otherpg.members)
                    # We never want to delete known-shared devs here.
                    # The same rule applies for selected device. If it's shared do not
                    # remove it in other pages when Delete all option is checked.
                    for device in (s.device_name for s in page.members
                                   if s.device_name not in otherdevs):
                        # we only want to delete boot partitions if they're not
                        # shared *and* we have no unknown partitions
                        if not self._get_unused_devices() or device.format.type not in \
                                protected_types:
                            self._destroy_device(device)
                        else:
                            log.debug("Device %s cannot be removed.", d)
                else:
                    self._destroy_device(device_name)

            part_removed = True

        # Now that devices have been removed from the installation root,
        # refreshing the display will have the effect of making them disappear.
        # It's like they never existed.
        if part_removed:
            task_path = self._device_tree.FindExistingSystemsWithTask()
            task_proxy = STORAGE.get_proxy(task_path)
            sync_run_task(task_proxy)
            self._update_space_display()
            self._do_refresh()

    def on_summary_clicked(self, button):
        disks = self._selected_disks
        dialog = SelectedDisksDialog(self.data, disks, show_remove=False, set_boot=False)

        with self.main_window.enlightbox(dialog.window):
            dialog.refresh()
            dialog.run()

    def on_configure_clicked(self, button):
        selector = self._accordion.current_selector
        if not selector:
            return

        device = selector.device
        if device.exists:
            return

        if self._get_current_device_type() in CONTAINER_DEVICE_TYPES:
            # disk set management happens through container edit on RHS
            return

        self.clear_errors()

        dialog = DisksDialog(
            self.data,
            self._device_tree,
            self._selected_disks,
            self._request.disks
        )
        with self.main_window.enlightbox(dialog.window):
            rc = dialog.run()

        if rc != 1:
            return

        disks = dialog.selected_disks

        if not disks:
            self._error = _("No disks selected. Keeping previous disk set.")
            self.set_info(self._error)
            return

        if set(disks) != set(self._request.disks):
            self._applyButton.set_sensitive(True)

        self._request.disks = disks
        self._set_devices_label()
        self._populate_raid(get_selected_raid_level(self._raidLevelCombo))

    def _container_encryption_change(self, old_encrypted, new_encrypted):
        if not old_encrypted and new_encrypted:
            # container set to be encrypted, we should make sure the leaf device
            # is not encrypted and make the encryption checkbox insensitive
            self._encryptCheckbox.set_active(False)
            fancy_set_sensitive(self._encryptCheckbox, False)
        elif old_encrypted and not new_encrypted:
            fancy_set_sensitive(self._encryptCheckbox, True)

        self.on_encrypt_toggled(self._encryptCheckbox)

    def run_container_editor(self, container=None, name=None, new_container=False):
        """ Run container edit dialog and return True if changes were made. """
        size = Size(0)
        size_policy = self._request.container_size_policy
        if container:
            container_name = container.name
            size = container.size
            size_policy = container.size_policy
        elif name:
            container_name = name
            if name != self._request.container_name:
                # creating a new container -- switch to the default
                size_policy = SIZE_POLICY_AUTO

        dialog = ContainerDialog(
            self.data,
            self._storage_playground,
            device_type=self._get_current_device_type(),
            name=container_name,
            raid_level=self._request.container_raid_level,
            encrypted=self._request.container_encrypted,
            size_policy=size_policy,
            size=size,
            disks=self._selected_disks,
            selected=self._request.disks,
            exists=getattr(container, "exists", False)
        )

        with self.main_window.enlightbox(dialog.window):
            rc = dialog.run()
            dialog.window.destroy()

        if rc != 1:
            return

        disks = dialog.selected
        name = dialog.name

        if not disks:
            self._error = _("No disks selected. Not saving changes.")
            self.set_info(self._error)
            log.error("No disks selected. Not saving changes.")
            return

        if (name != container_name and name in self._storage_playground.names or
                name in self._get_container_names() and new_container):
            self._error = _("Volume Group name %s is already in use. Not "
                            "saving changes.") % name
            self.set_info(self._error)
            log.error("Volume group name %s already in use.", name)
            return

        if (new_container or
                set(disks) != set(self._request.disks) or
                name != container_name or
                dialog.raid_level != self._request.container_raid_level or
                dialog.encrypted != self._request.container_encrypted or
                dialog.size_policy != self._request.container_size_policy):
            self._applyButton.set_sensitive(True)

        if dialog.encrypted:
            self._container_encryption_change(self._request.container_encrypted,
                                              dialog.encrypted)
        self._request.disks = disks
        self._request.container_name = name
        self._request.container_raid_level = dialog.raid_level
        self._request.container_encrypted = dialog.encrypted
        self._request.container_size_policy = dialog.size_policy
        self._set_devices_label()

        return True

    def _get_container_store_row(self, container):
        name = container.name
        free_space = getattr(container, "free_space", None)

        if free_space is not None:
            return [name, _("(%s free)") % free_space]
        else:
            return [name, ""]

    def on_modify_container_clicked(self, button):
        container_name = self._containerStore[self._containerCombo.get_active()][0]
        container = self._storage_playground.devicetree.get_device_by_name(container_name)

        # pass the name along with any found vg since we could be modifying a
        # vg that hasn't been instantiated yet
        if not self.run_container_editor(container=container, name=container_name):
            return

        if container_name == self._request.container_name:
            self.on_update_settings_clicked(None)
            return

        # Rename the container.
        if container:
            try:
                rename_container(
                    storage=self._storage_playground,
                    container=container,
                    name=self._request.container_name
                )
            except StorageError as e:
                self.set_detailed_error(_("Invalid device name."), e)
                self._request.container_name = container_name
                self.on_update_settings_clicked(None)
                return

        # Update the UI.
        idx = None

        for idx, data in enumerate(self._containerStore):
            # we're looking for the original vg name
            if data[0] == container_name:
                break

        if idx:
            container = self._storage_playground.devicetree.get_device_by_name(
                self._request.container_name
            )

            row = self._get_container_store_row(container)
            self._containerStore.insert(idx, row)
            self._containerCombo.set_active(idx)

            next_idx = self._containerStore.get_iter_from_string("%s" % (idx + 1))
            self._containerStore.remove(next_idx)

            self._modifyContainerButton.set_sensitive(
                not getattr(container, "exists", False)
            )

        self._update_selectors()
        self.on_update_settings_clicked(None)

    def on_container_changed(self, combo):
        ndx = combo.get_active()
        if ndx == -1:
            return

        container_name = self._containerStore[ndx][0]
        if container_name is None:
            return

        if self._request.container_name == container_name:
            return

        device_type = self._get_current_device_type()
        container_type_name = _(get_container_type(device_type).name).lower()
        new_text = _(NEW_CONTAINER_TEXT) % {"container_type": container_type_name}
        create_new_container = container_name == new_text
        user_changed_container = True
        if create_new_container:
            # run the vg editor dialog with a default name and disk set
            name = self._storage_playground.suggest_container_name()
            # user_changed_container flips to False if "cancel" picked
            user_changed_container = self.run_container_editor(name=name, new_container=True)
            for idx, data in enumerate(self._containerStore):
                if user_changed_container and data[0] == new_text:
                    container = self._storage_playground.devicetree.get_device_by_name(
                        self._request.container_name
                    )

                    if container:
                        row = self._get_container_store_row(container)
                    else:
                        row = [self._request.container_name, ""]

                    self._containerStore.insert(idx, row)
                    combo.set_active(idx)  # triggers a call to this method
                    return
                elif not user_changed_container and data[0] == self._request.container_name:
                    combo.set_active(idx)
                    return
        # else clause runs if an already existing container is picked
        else:
            self._request.container_name = container_name

        if user_changed_container:
            self._applyButton.set_sensitive(True)

        container = self._storage_playground.devicetree.get_device_by_name(
            self._request.container_name)
        container_exists = getattr(container, "exists", False)  # might not be in the tree

        if container:
            self._request.container_raid_level = get_device_raid_level(container)
            self._request.container_encrypted = container.encrypted
            self._request.container_size_policy = getattr(container, "size_policy",
                                                  container.size)
        else:
            self._request.container_raid_level = ""
            self._request.container_encrypted = False
            self._request.container_size_policy = SIZE_POLICY_AUTO

        self._modifyContainerButton.set_sensitive(not container_exists)

    def _save_current_page(self, selector=None):
        if selector is None:
            selector = self._accordion.current_selector

        self._save_right_side(selector)

    def on_selector_clicked(self, old_selector, selector):
        if not self._initialized:
            return

        # one of them must be set and they need to differ
        if (old_selector or self._accordion.current_selector) \
                and (old_selector is self._accordion.current_selector):
            return

        # Take care of the previously chosen selector.
        if old_selector:
            self._save_current_page(old_selector)

        curr_selector = self._accordion.current_selector
        no_edit = False
        current_page_type = None
        if self._accordion.is_multiselection or not curr_selector:
            current_page_type = NOTEBOOK_LABEL_PAGE
            self._set_page_label_text()
            no_edit = True
        elif curr_selector.device.format.type == "luks" and \
                curr_selector.device.format.exists:
            current_page_type = NOTEBOOK_LUKS_PAGE
            selected_device_label = self._encryptedDeviceLabel
            selected_device_desc_label = self._encryptedDeviceDescLabel
            no_edit = True
        elif not getattr(curr_selector.device, "complete", True):
            current_page_type = NOTEBOOK_INCOMPLETE_PAGE
            selected_device_label = self._incompleteDeviceLabel
            selected_device_desc_label = self._incompleteDeviceDescLabel

            if isinstance(curr_selector.device, MDRaidArrayDevice):
                total = curr_selector.device.member_devices
                missing = total - len(curr_selector.device.parents)
                txt = _("This Software RAID array is missing %(missing)d of %(total)d "
                        "member partitions. You can remove it or select a different "
                        "device.") % {"missing": missing, "total": total}
            elif isinstance(curr_selector.device, LVMVolumeGroupDevice):
                total = curr_selector.device.pv_count
                missing = total - len(curr_selector.device.parents)
                txt = _("This LVM Volume Group is missing %(missingPVs)d of %(totalPVs)d "
                        "physical volumes. You can remove it or select a different "
                        "device.") % {"missingPVs": missing, "totalPVs": total}
            else:
                txt = _("This %(type)s device is missing member devices. You can remove "
                        "it or select a different device.") % curr_selector.device.type

            self._incompleteDeviceOptionsLabel.set_text(txt)
            no_edit = True
        elif devicefactory.get_device_type(curr_selector.device) is None:
            current_page_type = NOTEBOOK_UNEDITABLE_PAGE
            selected_device_label = self._uneditableDeviceLabel
            selected_device_desc_label = self._uneditableDeviceDescLabel
            no_edit = True

        if no_edit:
            self._partitionsNotebook.set_current_page(current_page_type)
            if current_page_type != NOTEBOOK_LABEL_PAGE:
                selected_device_label.set_text(curr_selector.device.name)
                desc = _(MOUNTPOINT_DESCRIPTIONS.get(curr_selector.device.type, ""))
                selected_device_desc_label.set_text(desc)

            self._configButton.set_sensitive(False)
            self._removeButton.set_sensitive(True)
            return

        # Make sure we're showing details instead of the "here's how you create
        # a new OS" label.
        self._partitionsNotebook.set_current_page(NOTEBOOK_DETAILS_PAGE)

        # Set up the newly chosen selector.
        self._populate_right_side(curr_selector)

        self._applyButton.set_sensitive(False)
        container_device = devicefactory.get_device_type(
            curr_selector.device) in CONTAINER_DEVICE_TYPES
        self._configButton.set_sensitive(not curr_selector.device.exists and
                                         not curr_selector.device.protected and
                                         not container_device)
        self._removeButton.set_sensitive(not curr_selector.device.protected)

    def on_page_clicked(self, page, mountpoint_to_show=None):
        if not self._initialized:
            return

        if self._accordion.is_current_selected:
            self._save_current_page()

        self._show_mountpoint(page=page, mountpoint=mountpoint_to_show)

        # This is called when a Page header is clicked upon so we can support
        # deleting an entire installation at once and displaying something
        # on the RHS.
        if isinstance(page, CreateNewPage):
            # Make sure we're showing "here's how you create a new OS" or
            # multiselection label instead of device/mountpoint details.
            self._partitionsNotebook.set_current_page(NOTEBOOK_LABEL_PAGE)
            self._set_page_label_text()
            self._removeButton.set_sensitive(False)
        else:
            self._removeButton.set_sensitive(True)

    def _do_autopart(self, scheme):
        """Helper function for on_create_clicked.
           Assumes a non-final context in which at least some errors
           discovered by storage checker are not considered fatal because they
           will be dealt with later.

           Note: There are never any non-existent devices around when this runs.
        """
        log.debug("Running automatic partitioning.")
        self.clear_errors()

        request = PartitioningRequest()
        request.partitioning_scheme = scheme

        try:

            task = InteractiveAutoPartitioningTask(self._storage_playground, request)
            task.run()
        except (StorageConfigurationError, BootloaderConfigurationError) as e:
            self._reset_storage()
            self.set_detailed_error(_("Automatic partitioning failed."), e)

        if self._error:
            return

        report = storage_checker.check(self._storage_playground,
                                       skip=(verify_luks_devices_have_key,))
        report.log(log)

        if report.errors:
            messages = "\n".join(report.errors)
            log.error("The partitioning is not valid: %s", messages)
            self._reset_storage()
            self.set_detailed_error(_("Automatic partitioning failed."), messages)

    def on_create_clicked(self, button, autopart_type_combo):
        # Then do autopartitioning.  We do not do any clearpart first.  This is
        # custom partitioning, so you have to make your own room.
        self._do_autopart(self._get_autopart_type(autopart_type_combo))

        # Refresh the spoke to make the new partitions appear.
        self._do_refresh()
        self._update_space_display()

    def on_reformat_toggled(self, widget):
        active = widget.get_active()

        encrypt_sensitive = active
        if self._accordion.current_selector:
            device = self._accordion.current_selector.device.raw_device

            ancestors = device.ancestors
            ancestors.remove(device)
            if any(a.format.type == "luks" and a.format.exists for a in ancestors):
                # The encryption checkbutton should not be sensitive if there is
                # existing encryption below the leaf layer.
                encrypt_sensitive = False

        # you can't encrypt a btrfs subvolume -- only the volume/container
        device_type = self._get_current_device_type()
        if device_type == DEVICE_TYPE_BTRFS:
            self._encryptCheckbox.set_active(False)
            encrypt_sensitive = False

        fancy_set_sensitive(self._encryptCheckbox, encrypt_sensitive)
        self.on_encrypt_toggled(self._encryptCheckbox)

        fancy_set_sensitive(self._fsCombo, active)

    def on_fs_type_changed(self, combo):
        if not self._initialized:
            return

        itr = combo.get_active_iter()
        if not itr:
            return

        new_type = self._get_fstype(combo)
        format_data = DeviceFormatData.from_structure(
            self._device_tree.GetFormatTypeData(new_type)
        )

        fancy_set_sensitive(self._mountPointEntry, format_data.mountable)

    def on_encrypt_toggled(self, encrypted):
        hide_or_show = really_show if encrypted.get_active() else really_hide

        for widget in [self._luksLabel, self._luksCombo]:
            hide_or_show(widget)

        fancy_set_sensitive(
            self._luksCombo,
            encrypted.get_active() and encrypted.get_sensitive()
        )

    def _populate_container(self, device):
        """ Set up the vg widgets for lvm or hide them for other types. """
        device_type = self._get_current_device_type()

        if device_type not in CONTAINER_DEVICE_TYPES:
            # just hide the buttons with no meaning for non-container devices
            for widget in [self._containerLabel,
                           self._containerCombo,
                           self._modifyContainerButton]:
                really_hide(widget)
            return

        # else really populate the container
        # set up the vg widgets and then bail out
        container = get_container(self._storage_playground, device_type, device)
        default_container_name = getattr(container, "name", None)
        container_exists = getattr(container, "exists", False)
        container_size_policy = getattr(container, "size_policy", SIZE_POLICY_AUTO)
        container_type = get_container_type(device_type)

        self._containerLabel.set_text(
            C_("GUI|Custom Partitioning|Configure|Devices", container_type.label).title()
        )
        self._containerLabel.set_use_underline(True)
        self._containerStore.clear()

        containers = collect_containers(self._storage_playground, device_type)
        default_seen = False

        for c in containers:
            row = self._get_container_store_row(c)
            self._containerStore.append(row)

            if default_container_name and c.name == default_container_name:
                default_seen = True
                self._containerCombo.set_active(containers.index(c))

        if default_container_name is None:
            default_container_name = self._storage_playground.suggest_container_name()

        self._request.container_name = default_container_name
        self._request.container_size_policy = container_size_policy

        if not default_seen:
            self._containerStore.append([default_container_name, ""])
            self._containerCombo.set_active(len(self._containerStore) - 1)

        container_type_name = _(container_type.name).lower()

        self._containerStore.append([
            _(NEW_CONTAINER_TEXT) % {"container_type": container_type_name}, ""
        ])
        self._containerCombo.set_tooltip_text(
            _(CONTAINER_TOOLTIP) % {"container_type": container_type_name}
        )

        if default_container_name is None:
            self._containerCombo.set_active(len(self._containerStore) - 1)

        for widget in [self._containerLabel,
                       self._containerCombo,
                       self._modifyContainerButton]:
            really_show(widget)

        # make the combo and button insensitive for existing LVs
        can_change_container = (device is not None and not device.exists and
                                device != container)
        fancy_set_sensitive(self._containerCombo, can_change_container)
        self._modifyContainerButton.set_sensitive(not container_exists)

    def _update_fstype_combo(self, device_type):
        """ Set up device type dependent portion of filesystem combo.

            :param int device_type: an int representing the device type

            Generally speaking, the filesystem combo can be set up without
            reference to the device type because the choice of filesystem
            combo and of device type is orthogonal.

            However, choice of btrfs device type requires choice of btrfs
            filesystem type, and choice of any other device type precludes
            choice of btrfs filesystem type.

            Preconditions are:
            * the filesystem combo contains at least the default filesystem
            * the default filesystem is not the same as btrfs
            * if device_type is DEVICE_TYPE_BTRFS, btrfs is supported

            This method is idempotent, and must remain so.
        """
        # Find unique instance of btrfs in fsCombo, if any.
        model = self._fsCombo.get_model()
        btrfs_iter = ((idx, row) for idx, row in enumerate(model) if row[0] == "btrfs")
        btrfs_idx, btrfs_row = next(btrfs_iter, (None, None))

        if device_type == DEVICE_TYPE_BTRFS:
            # If no btrfs entry, add one, and select the new entry
            if btrfs_idx is None:
                self._fsStore.append(["btrfs"])
                active_index = len(self._fsCombo.get_model()) - 1
            # Otherwise, select the already located btrfs entry
            else:
                active_index = btrfs_idx
        else:
            # Get the currently active index
            active_index = self._fsCombo.get_active()

            # If there is a btrfs entry, remove and adjust active_index
            if btrfs_idx is not None:
                self._fsStore.remove(btrfs_row.iter)

                # If btrfs previously selected, select default filesystem
                if active_index == btrfs_idx:
                    active_index = next(
                        idx for idx, data in enumerate(self._fsCombo.get_model())
                        if data[0] == self._default_file_system
                    )
                # Otherwise, shift index left by one if after removed entry
                elif active_index > btrfs_idx:
                    active_index = active_index - 1
            # If there is no btrfs entry, stick with user's previous choice
            else:
                pass

        self._fsCombo.set_active(active_index)
        fancy_set_sensitive(
            self._fsCombo,
            self._reformatCheckbox.get_active() and device_type != DEVICE_TYPE_BTRFS
        )

    def on_device_type_changed(self, combo):
        if combo is not self._typeCombo:
            return

        if not self._initialized:
            return

        # The name of the device type is more informative than the numeric id
        new_type = self._get_current_device_type()

        # Quit if no device type is selected.
        if new_type is None:
            return

        # lvm uses the RHS to set disk set. no foolish minds here.
        exists = \
            self._accordion.current_selector and \
            self._accordion.current_selector.device.exists

        self._configButton.set_sensitive(
            not exists and new_type not in CONTAINER_DEVICE_TYPES
        )

        # this has to be done before calling populate_raid since it will need
        # the raid level combo to contain the relevant raid levels for the new
        # device type
        self._raidStoreFilter.refilter()

        self._populate_raid(get_default_raid_level(new_type))

        if self._accordion.current_selector:
            self._populate_container(self._accordion.current_selector.device.raw_device)

        fancy_set_sensitive(self._nameEntry, new_type in NAMED_DEVICE_TYPES)
        self._nameEntry.set_text(self._get_device_name(new_type))
        fancy_set_sensitive(self._sizeEntry, new_type != DEVICE_TYPE_BTRFS)

        self._update_fstype_combo(new_type)

    def set_detailed_warning(self, msg, detailed_msg):
        self._error = detailed_msg
        self.set_warning(msg + _(" <a href=\"\">Click for details.</a>"))

    def set_detailed_error(self, msg, detailed_msg):
        self._error = detailed_msg
        self.set_error(msg + _(" <a href=\"\">Click for details.</a>"))

    def clear_errors(self):
        self._error = None
        self.clear_info()

    # This callback is for the button that just resets the UI to anaconda's
    # current understanding of the disk layout.
    def on_reset_clicked(self, *args):
        msg = _("Continuing with this action will reset all your partitioning selections "
                "to their current on-disk state.")

        dlg = Gtk.MessageDialog(
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            message_format=msg
        )
        dlg.set_decorated(False)
        dlg.add_buttons(
            C_("GUI|Custom Partitioning|Reset Dialog", "_Reset selections"),
            0,
            C_("GUI|Custom Partitioning|Reset Dialog", "_Preserve current selections"),
            1
        )
        dlg.set_default_response(1)

        with self.main_window.enlightbox(dlg):
            rc = dlg.run()
            dlg.destroy()

        if rc == 0:
            self.refresh()

    # This callback is for the button that has anaconda go back and rescan the
    # disks to pick up whatever changes the user made outside our control.
    def on_refresh_clicked(self, *args):
        dialog = RefreshDialog(self.data)
        ignoreEscape(dialog.window)

        with self.main_window.enlightbox(dialog.window):
            rc = dialog.run()
            dialog.window.destroy()

        if rc == 1:
            # User hit OK on the dialog, indicating they stayed on the dialog
            # until rescanning completed and now needs to go back to the
            # main storage spoke.
            self.skipTo = "StorageSpoke"
        elif rc != 2:
            # User either hit cancel on the dialog or closed it via escape, so
            # there was no rescanning done.
            # NOTE: rc == 2 means the user clicked on the link that takes them
            # back to the hub.
            return

        # Can't use this spoke's on_back_clicked method as that will try to
        # save the right hand side, which is no longer valid.  The user must
        # go back and select their disks all over again since whatever they
        # did on the shell could have changed what disks are available.
        NormalSpoke.on_back_clicked(self, None)

    def on_info_bar_clicked(self, *args):
        log.debug("Clicked on the info bar: %s (%s)", self._error, args)
        if not self._error:
            return

        dlg = Gtk.MessageDialog(
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            message_format=str(self._error)
        )
        dlg.set_decorated(False)

        with self.main_window.enlightbox(dlg):
            dlg.run()
            dlg.destroy()

    @timed_action(delay=50, threshold=100)
    def on_update_settings_clicked(self, button):
        """ call _save_right_side, then, perhaps, populate_right_side. """
        self._save_right_side(self._accordion.current_selector)
        self._applyButton.set_sensitive(False)

    @timed_action(delay=50, threshold=100)
    def on_unlock_clicked(self, *args):
        """ try to open the luks device, populate, then call _do_refresh. """
        self.clear_errors()
        device_name = self._accordion.current_selector.device
        passphrase = self._passphraseEntry.get_text()

        log.info("Trying to unlock device %s.", device_name)
        unlocked = self._device_tree.UnlockDevice(device_name, passphrase)

        if not unlocked:
            self._passphraseEntry.set_text("")
            self.set_detailed_warning(
                _("Failed to unlock encrypted block device."),
                "Failed to unlock {}.".format(device_name)
            )
            return

        # TODO: Run the task asynchronously.
        task_path = self._device_tree.FindExistingSystemsWithTask()
        task_proxy = STORAGE.get_proxy(task_path)
        sync_run_task(task_proxy)

        self._accordion.clear_current_selector()
        self._do_refresh()

    def on_value_changed(self, *args):
        self._applyButton.set_sensitive(True)
