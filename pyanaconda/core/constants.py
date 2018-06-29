#
# constants.py: anaconda constants
#
# Copyright (C) 2001  Red Hat, Inc.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# Used for digits, ascii_letters, punctuation constants
import string # pylint: disable=deprecated-module
from pyanaconda.core.i18n import N_

from enum import Enum

# Use -1 to indicate that the selinux configuration is unset
SELINUX_DEFAULT = -1

# where to look for 3rd party addons
ADDON_PATHS = ["/usr/share/anaconda/addons"]

from pykickstart.constants import AUTOPART_TYPE_LVM

# common string needs to be easy to change
from pyanaconda import product
productName = product.productName
productVersion = product.productVersion
productArch = product.productArch
bugzillaUrl = product.bugUrl
isFinal = product.isFinal

# for use in device names, eg: "fedora", "rhel"
shortProductName = productName.lower()          # pylint: disable=no-member
if productName.count(" "):                      # pylint: disable=no-member
    shortProductName = ''.join(s[0] for s in shortProductName.split())

# DriverDisc Paths
DD_ALL = "/tmp/DD"
DD_FIRMWARE = "/tmp/DD/lib/firmware"
DD_RPMS = "/tmp/DD-*"

TRANSLATIONS_UPDATE_DIR = "/tmp/updates/po"

ANACONDA_CLEANUP = "anaconda-cleanup"
MOUNT_DIR = "/run/install"
DRACUT_REPODIR = "/run/install/repo"
DRACUT_ISODIR = "/run/install/source"
ISO_DIR = MOUNT_DIR + "/isodir"
IMAGE_DIR = MOUNT_DIR + "/image"
INSTALL_TREE = MOUNT_DIR + "/source"
BASE_REPO_NAME = "anaconda"
ANACONDA_BUS_ADDR_FILE = "/run/anaconda/bus.address"
ANACONDA_DATA_DIR = "/usr/share/anaconda"

# NOTE: this should be LANG_TERRITORY.CODESET, e.g. en_US.UTF-8
DEFAULT_LANG = "en_US.UTF-8"

DEFAULT_VC_FONT = "eurlatgr"

DEFAULT_KEYBOARD = "us"

DRACUT_SHUTDOWN_EJECT = "/run/initramfs/usr/lib/dracut/hooks/shutdown/99anaconda-eject.sh"

# VNC questions
USEVNC = N_("Start VNC")
USETEXT = N_("Use text mode")

# Runlevel files
TEXT_ONLY_TARGET = 'multi-user.target'
GRAPHICAL_TARGET = 'graphical.target'

# Network
NETWORK_CONNECTION_TIMEOUT = 45  # in seconds
NETWORK_CONNECTED_CHECK_INTERVAL = 0.1  # in seconds

# DBus
DEFAULT_DBUS_TIMEOUT = -1       # use default

# Thread names
THREAD_EXECUTE_STORAGE = "AnaExecuteStorageThread"
THREAD_STORAGE = "AnaStorageThread"
THREAD_STORAGE_WATCHER = "AnaStorageWatcher"
THREAD_CHECK_STORAGE = "AnaCheckStorageThread"
THREAD_CUSTOM_STORAGE_INIT = "AnaCustomStorageInit"
THREAD_WAIT_FOR_CONNECTING_NM = "AnaWaitForConnectingNMThread"
THREAD_PAYLOAD = "AnaPayloadThread"
THREAD_PAYLOAD_RESTART = "AnaPayloadRestartThread"
THREAD_SYNC_TIME_BASENAME = "AnaSyncTime"
THREAD_EXCEPTION_HANDLING_TEST = "AnaExceptionHandlingTest"
THREAD_LIVE_PROGRESS = "AnaLiveProgressThread"
THREAD_SOFTWARE_WATCHER = "AnaSoftwareWatcher"
THREAD_CHECK_SOFTWARE = "AnaCheckSoftwareThread"
THREAD_SOURCE_WATCHER = "AnaSourceWatcher"
THREAD_INSTALL = "AnaInstallThread"
THREAD_CONFIGURATION = "AnaConfigurationThread"
THREAD_FCOE = "AnaFCOEThread"
THREAD_ISCSI_DISCOVER = "AnaIscsiDiscoverThread"
THREAD_ISCSI_LOGIN = "AnaIscsiLoginThread"
THREAD_GEOLOCATION_REFRESH = "AnaGeolocationRefreshThread"
THREAD_DATE_TIME = "AnaDateTimeThread"
THREAD_TIME_INIT = "AnaTimeInitThread"
THREAD_DASDFMT = "AnaDasdfmtThread"
THREAD_KEYBOARD_INIT = "AnaKeyboardThread"
THREAD_ADD_LAYOUTS_INIT = "AnaAddLayoutsInitThread"
THREAD_NTP_SERVER_CHECK = "AnaNTPserver"
THREAD_DBUS_TASK = "AnaTaskThread"
THREAD_NVDIMM_RECONFIGURE = "AnaNVDIMMReconfigureThread"
THREAD_NVDIMM_REPOPULATE = "AnaNVDIMMRepopulateThread"

# Geolocation constants

# geolocation providers
# - values are used by the geoloc CLI/boot option
GEOLOC_PROVIDER_FEDORA_GEOIP = "provider_fedora_geoip"
GEOLOC_PROVIDER_HOSTIP = "provider_hostip"
GEOLOC_PROVIDER_GOOGLE_WIFI = "provider_google_wifi"
# geocoding provider
GEOLOC_GEOCODER_NOMINATIM = "geocoder_nominatim"
# default providers
GEOLOC_DEFAULT_PROVIDER = GEOLOC_PROVIDER_FEDORA_GEOIP
GEOLOC_DEFAULT_GEOCODER = GEOLOC_GEOCODER_NOMINATIM
# timeout (in seconds)
GEOLOC_TIMEOUT = 3


ANACONDA_ENVIRON = "anaconda"
FIRSTBOOT_ENVIRON = "firstboot"

# Tainted hardware
UNSUPPORTED_HW = 1 << 28

# Password type
class SecretType(Enum):
    PASSWORD = "password"
    PASSPHRASE = "passphrase"

# Password validation
SECRET_MIN_LEN = 6
SECRET_EMPTY_ERROR = {
    SecretType.PASSWORD : N_("The password is empty."),
    SecretType.PASSPHRASE : N_("The passphrase is empty.")
}
SECRET_CONFIRM_ERROR_GUI = {
    SecretType.PASSWORD : N_("The passwords do not match."),
    SecretType.PASSPHRASE : N_("The passphrases do not match.")
}
SECRET_CONFIRM_ERROR_TUI = {
    SecretType.PASSWORD : N_("The passwords you entered were different. Please try again."),
    SecretType.PASSPHRASE : N_("The passphrases you entered were different. Please try again.")
}

# The secret-too-short constants is used to replace a libpwquality error message,
# which is why it does not end with a ".", like all the other do.
SECRET_TOO_SHORT = {
    SecretType.PASSWORD : N_("The password is too short"),
    SecretType.PASSPHRASE : N_("The passphrase is too short")
}
SECRET_WEAK = {
    SecretType.PASSWORD : N_("The password you have provided is weak."),
    SecretType.PASSPHRASE : N_("The passphrase you have provided is weak.")
}
SECRET_WEAK_WITH_ERROR = {
    SecretType.PASSWORD : N_("The password you have provided is weak:"),
    SecretType.PASSPHRASE : N_("The passphrase you have provided is weak:")
}
PASSWORD_FINAL_CONFIRM = N_("Press <b>Done</b> again to use the password anyway.")
SECRET_ASCII = {
    SecretType.PASSWORD : N_("The password you have provided contains non-ASCII characters. You may not be able to switch between keyboard layouts when typing it."),
    SecretType.PASSPHRASE : N_("The passphrase you have provided contains non-ASCII characters. You may not be able to switch between keyboard layouts when typing it.")
}
PASSWORD_DONE_TWICE = N_("You will have to press <b>Done</b> twice to confirm it.")
PASSWORD_DONE_TO_CONTINUE = N_("Press <b>Done</b> to continue.")

PASSWORD_SET = N_("Password set.")

class SecretStatus(Enum):
    EMPTY = N_("Empty")
    TOO_SHORT = N_("Too short")
    WEAK = N_("Weak")
    FAIR = N_("Fair")
    GOOD = N_("Good")
    STRONG = N_("Strong")

PASSWORD_HIDE = N_("Hide password.")
PASSWORD_SHOW = N_("Show password.")

PASSWORD_HIDE_ICON = "anaconda-password-show-off"
PASSWORD_SHOW_ICON = "anaconda-password-show-on"

# the number of seconds we consider a noticeable freeze of the UI
NOTICEABLE_FREEZE = 0.1

# all ASCII characters
PW_ASCII_CHARS = string.digits + string.ascii_letters + string.punctuation + " "

# Recognizing a tarfile
TAR_SUFFIX = (".tar", ".tbz", ".tgz", ".txz", ".tar.bz2", "tar.gz", "tar.xz")

# screenshots
SCREENSHOTS_DIRECTORY = "/tmp/anaconda-screenshots"
SCREENSHOTS_TARGET_DIRECTORY = "/root/anaconda-screenshots"

# cmdline arguments that append instead of overwrite
CMDLINE_APPEND = ["modprobe.blacklist", "ifname", "ip"]

# The default autopart type is lvm.
# FIXME: Move this constant to the storage module.
DEFAULT_AUTOPART_TYPE = AUTOPART_TYPE_LVM

# Is the default autopart type selected?
AUTOPART_TYPE_DEFAULT = -1

# Filesystems which are not supported by Anaconda
UNSUPPORTED_FILESYSTEMS = ("btrfs", "ntfs", "tmpfs")

# Default to these units when reading user input when no units given
SIZE_UNITS_DEFAULT = "MiB"

# An estimated ratio for metadata size to total disk space.
STORAGE_METADATA_RATIO = 0.1

# Constants for reporting status to IPMI.  These are from the IPMI spec v2 rev1.1, page 512.
IPMI_STARTED = 0x7          # installation started
IPMI_FINISHED = 0x8         # installation finished successfully
IPMI_ABORTED = 0x9          # installation finished unsuccessfully, due to some non-exn error
IPMI_FAILED = 0xA           # installation hit an exception


# for how long (in seconds) we try to wait for enough entropy for LUKS
# keep this a multiple of 60 (minutes)
MAX_ENTROPY_WAIT = 10 * 60

# X display number to use
X_DISPLAY_NUMBER = 1

# Payload status messages
PAYLOAD_STATUS_PROBING_STORAGE = N_("Probing storage...")
PAYLOAD_STATUS_TESTING_AVAILABILITY = N_("Testing availability...")
PAYLOAD_STATUS_PACKAGE_MD = N_("Downloading package metadata...")
PAYLOAD_STATUS_GROUP_MD = N_("Downloading group metadata...")

# Window title text
WINDOW_TITLE_TEXT = N_("Anaconda Installer")

# NTP server checking
NTP_SERVER_OK = 0
NTP_SERVER_NOK = 1
NTP_SERVER_QUERY = 2

# Storage checker constraints
STORAGE_MIN_RAM = "min_ram"
STORAGE_MIN_ROOT = "min_root"
STORAGE_MIN_PARTITION_SIZES = "min_partition_sizes"
STORAGE_MUST_BE_ON_LINUXFS = "must_be_on_linuxfs"
STORAGE_MUST_BE_ON_ROOT = "must_be_on_root"
STORAGE_SWAP_IS_RECOMMENDED = "swap_is_recommended"

# Display modes
class DisplayModes(Enum):
    GUI = "GUI"
    TUI = "TUI"


DISPLAY_MODE_NAME = {
    DisplayModes.GUI: "graphical mode",
    DisplayModes.TUI: "text mode"
}

INTERACTIVE_MODE_NAME = {
    True: "interactive",
    False: "noninteractive"
}

# Loggers
LOGGER_ANACONDA_ROOT = "anaconda"
LOGGER_MAIN = "anaconda.main"
LOGGER_STDOUT = "anaconda.stdout"
LOGGER_STDERR = "anaconda.stderr"
LOGGER_PROGRAM = "program"
LOGGER_STORAGE = "storage"
LOGGER_PACKAGING = "packaging"
LOGGER_DNF = "dnf"
LOGGER_BLIVET = "blivet"
LOGGER_SIMPLELINE = "simpleline"
LOGGER_IFCFG = "ifcfg"
LOGGER_SENSITIVE_INFO = "sensitive_info"

class PayloadRequirementType(Enum):
    package = "package"
    group = "group"

# Timeout for starting X
X_TIMEOUT = 60

# Setup on boot actions.
SETUP_ON_BOOT_DEFAULT = -1
SETUP_ON_BOOT_DISABLED = 0
SETUP_ON_BOOT_ENABLED = 1
SETUP_ON_BOOT_RECONFIG = 2

# Clear partitions modes.
CLEAR_PARTITIONS_DEFAULT = -1
CLEAR_PARTITIONS_NONE = 0
CLEAR_PARTITIONS_ALL = 1
CLEAR_PARTITIONS_LIST = 2
CLEAR_PARTITIONS_LINUX = 3

# Bootloader modes.
BOOTLOADER_DISABLED = 0
BOOTLOADER_ENABLED = 1
BOOTLOADER_SKIPPED = 2

# Bootloader types.
BOOTLOADER_TYPE_DEFAULT = "DEFAULT"
BOOTLOADER_TYPE_EXTLINUX = "EXTLINUX"

# Bootloader locations.
BOOTLOADER_LOCATION_DEFAULT = "DEFAULT"
BOOTLOADER_LOCATION_PARTITION = "PARTITION"
BOOTLOADER_LOCATION_MBR = "MBR"

# Bootloader timeout.
BOOTLOADER_TIMEOUT_UNSET = -1

# Bootloader drive.
BOOTLOADER_DRIVE_UNSET = ""

# Firewall mode.
FIREWALL_DEFAULT = -1
FIREWALL_DISABLED = 0
FIREWALL_ENABLED = 1
FIREWALL_USE_SYSTEM_DEFAULTS = 2
