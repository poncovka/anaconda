#
# Kickstart module for autopartitioning.
#
# Copyright (C) 2018 Red Hat, Inc.
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
from pyanaconda.core.constants import DEFAULT_AUTOPART_TYPE
from pyanaconda.core.signal import Signal

from pyanaconda import anaconda_logging
log = anaconda_logging.get_dbus_module_logger(__name__)


class Autopartitioning(object):
    """The Autopartitioning module."""

    def __init__(self):
        """Initialize the module."""
        self.module_properties_changed = Signal()

        self.type_changed = Signal()
        self._type = DEFAULT_AUTOPART_TYPE

        self.fstype_changed = Signal()
        self._fstype = ""

        self.nohome_changed = Signal()
        self._nohome = False

        self.noboot_changed = Signal()
        self._noboot = False

        self.noswap_changed = Signal()
        self._noswap = False

        self.encrypted_changed = Signal()
        self._encrypted = False

        self.cipher_changed = Signal()
        self._cipher = ""

        self.passphrase_changed = Signal()
        self._passphrase = ""

        self.escrowcert_changed = Signal()
        self._escrowcert = ""

        self.backup_passphrase_enabled_changed = Signal()
        self._backup_passphrase_enabled = ""

    def process_kickstart(self, data):
        """Process the kickstart data."""
        log.debug("Processing autopart data...")
        if data.autopart.type is not None:
            self.set_type(data.autopart.type)

        if data.autopart.fstype:
            self.set_fstype(data.autopart.fstype)

        self.set_nohome(data.autopart.nohome)
        self.set_noboot(data.autopart.noboot)
        self.set_noswap(data.autopart.noswap)

        self.set_encrypted(data.autopart.encrypted)
        self.set_passphrase(data.autopart.passphrase)
        self.set_escrowcert(data.autopart.escrowcert)
        self.set_backup_passphrase_enabled(data.autopart.backuppassphrase)
        self.set_cipher(data.autopart.cipher)

    def generate_kickstart(self, data):
        """Generate the kickstart data."""
        log.debug("Generating autopart data...")
        data.autopart.autopart = True
        data.autopart.type = self.type
        data.autopart.fstype = self.fstype

        data.autopart.nohome = self.nohome
        data.autopart.noboot = self.noboot
        data.autopart.noswap = self.noswap

        data.autopart.encrypted = self.encrypted
        data.autopart.passphrase = self.passphrase
        data.autopart.escrowcert = self.escrowcert
        data.autopart.backuppassphrase = self.backup_passphrase_enabled
        data.autopart.cipher = self.cipher

    @property
    def type(self):
        """Type of a filesystem used on the partitions."""
        return self._type

    def set_type(self, scheme):
        """Set the partitioning scheme."""
        self._type = scheme
        self.type_changed.emit()
        log.debug("Type is set to %s.", scheme)

    @property
    def fstype(self):
        """Type of a filesystem used on the partitions."""
        return self._fstype

    def set_fstype(self, fstype):
        """Set the type of a filesystem used on the partitions."""
        self._fstype = fstype
        self.fstype_changed.emit()
        log.debug("Filesystem type is set to %s.", fstype)

    @property
    def nohome(self):
        """Do not create a /home partition."""
        return self._nohome

    def set_nohome(self, nohome):
        """Enable or disable creation of a /home partition."""
        self._nohome = nohome
        self.nohome_changed.emit()
        log.debug("Nohome is set to %s.", nohome)

    @property
    def noboot(self):
        """Do not create a /boot partition."""
        return self._noboot

    def set_noboot(self, noboot):
        """Enable or disable creation of a /boot partition."""
        self._noboot = noboot
        self.noboot_changed.emit()
        log.debug("Noboot is set to %s.", noboot)

    @property
    def noswap(self):
        """Do not create a swap partition."""
        return self._noswap

    def set_noswap(self, noswap):
        """Enable or disable creation of a swap partition."""
        self._noswap = noswap
        self.noswap_changed.emit()
        log.debug("Noswap is set to %s.", noswap)

    @property
    def encrypted(self):
        """Should all devices with support be encrypted by default?"""
        return self._encrypted

    def set_encrypted(self, encrypted):
        """Set if all devices with support should be encrypted by default."""
        self._encrypted = encrypted
        self.encrypted_changed.emit()
        log.debug("Encrypted is set to %s.", encrypted)

    @property
    def cipher(self):
        """Encryption algorithm used to encrypt the filesystem."""
        return self._cipher

    def set_cipher(self, cipher):
        """Set the encryption algorithm used to encrypt the filesystem."""
        self._cipher = cipher
        self.cipher_changed.emit()
        log.debug("Cipher is set to %s.", cipher)

    @property
    def passphrase(self):
        """Default passphrase for all encrypted devices."""
        return self._passphrase

    def set_passphrase(self, passphrase):
        """Set a default passphrase for all encrypted devices."""
        self._passphrase = passphrase
        self.passphrase_changed.emit()
        log.debug("Passphrase is set.")

    @property
    def escrowcert(self):
        """URL of an X.509 certificate."""
        return self._escrowcert

    def set_escrowcert(self, url):
        """Set URL of an X.509 certificate."""
        self._escrowcert = url
        self.escrowcert_changed.emit()
        log.debug("Escrowcert is set to %s.", url)

    @property
    def backup_passphrase_enabled(self):
        """Is the backup passphrase enabled?"""
        return self._backup_passphrase_enabled

    def set_backup_passphrase_enabled(self, enabled):
        """Enable or disable the backup passphrase."""
        self._backup_passphrase_enabled = enabled
        self.backup_passphrase_enabled_changed.emit()
        log.debug("Backup passphrase enabled is set to %s.", enabled)
