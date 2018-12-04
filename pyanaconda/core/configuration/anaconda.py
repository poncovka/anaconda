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
#  Author(s):  Vendula Poncova <vponcova@redhat.com>
#
import os

from pyanaconda.core.configuration.services import ServicesSection
from pyanaconda.core.configuration.storage import StorageSection
from pyanaconda.core.configuration.system import SystemType, SystemSection
from pyanaconda.core.configuration.target import TargetType, TargetSection
from pyanaconda.core.configuration.base import Section, Configuration, ConfigurationError
from pyanaconda.core.configuration.product import ProductLoader
from pyanaconda.core.constants import ANACONDA_CONFIG_TMP, ANACONDA_CONFIG_DIR
from pyanaconda.product import productName, productVariant


__all__ = ["conf", "AnacondaConfiguration"]


class AnacondaSection(Section):
    """The Anaconda section."""

    @property
    def debug(self):
        """Run Anaconda in the debugging mode."""
        return self._get_option("debug", bool)

    @property
    def addons_enabled(self):
        """Enable Anaconda addons."""
        return self._get_option("addons_enabled", bool)

    @property
    def kickstart_modules(self):
        """List of enabled kickstart modules."""
        return self._get_option("kickstart_modules").split()


class AnacondaConfiguration(Configuration):
    """Representation of the Anaconda configuration."""

    @classmethod
    def from_defaults(cls):
        """Get the default Anaconda configuration.

        :return: an instance of AnacondaConfiguration
        """
        config = cls()
        config.set_from_defaults()
        return config

    def __init__(self):
        """Initialize the configuration."""
        super().__init__()
        self._anaconda = AnacondaSection("Anaconda", self.get_parser())
        self._system = SystemSection("Installation System", self.get_parser())
        self._target = TargetSection("Installation Target", self.get_parser())
        self._storage = StorageSection("Storage", self.get_parser())
        self._services = ServicesSection("Services", self.get_parser())

    @property
    def anaconda(self):
        """The Anaconda section."""
        return self._anaconda

    @property
    def system(self):
        """The Installation System section."""
        return self._system

    @property
    def target(self):
        """The Installation Target section."""
        return self._target

    @property
    def storage(self):
        """The Storage section."""
        return self._storage

    @property
    def services(self):
        """The Services section."""
        return self._services

    def set_from_defaults(self):
        """"Set the configuration from the default configuration files.

        Read the current configuration from the temporary config file.
        Or load the configuration from these files:

            /etc/anaconda/anaconda.conf
            /etc/anaconda/conf.d/*.conf

        """
        config_path = os.environ.get("ANACONDA_CONFIG_TMP", ANACONDA_CONFIG_TMP)

        if config_path and os.path.exists(config_path):
            self.read(config_path)
        else:
            config_path = os.path.join(ANACONDA_CONFIG_DIR, "anaconda.conf")
            self.read(config_path)

            config_dir = os.path.join(ANACONDA_CONFIG_DIR, "conf.d")
            self.read_from_directory(config_dir)

        self.validate()

    def set_from_product(self):
        """Set the configuration from the product configuration files.

        We will try to use configuration files of a product specified by
        the .buildstamp file. Otherwise, we will use a default product.

        The configuration files are loaded from /etc/anaconda/product.d.
        """
        loader = ProductLoader()
        loader.load_products(os.path.join(ANACONDA_CONFIG_DIR, "product.d"))

        # Use the product name and the variant name from .buildstamp.
        if loader.check_product(productName, productVariant):
            product_name = productName
            variant_name = productVariant

        # Or the product name from .buildstamp.
        elif loader.check_product(productName):
            product_name = productName
            variant_name = ""

        # Or use the default product name.
        elif loader.check_product("Fedora"):
            product_name = "Fedora"
            variant_name = ""

        # Or fail.
        else:
            raise ConfigurationError(
                "Unable to find any suitable configuration files for this product."
            )

        # Read the configuration files of the product.
        config_paths = loader.collect_configurations(product_name, variant_name)

        for config_path in config_paths:
            self.read(config_path)

        self.validate()

    def set_from_opts(self, opts):
        """Set the configuration from the Anaconda cmdline options.

        This code is too related to the Anaconda cmdline options, so it shouldn't
        be part of this class. We should find a better, more universal, way to change
        the Anaconda configuration.

        FIXME: This is a temporary solution.

        :param opts: a namespace of options
        """
        # Set the storage flags.
        self.storage._set_option("dmraid", opts.dmraid)
        self.storage._set_option("ibft", opts.ibft)
        self.storage._set_option("gpt", opts.gpt)
        self.storage._set_option("multipath_friendly_names", opts.multipath_friendly_names)

        # Set the type of the installation system.
        if opts.liveinst:
            self.system._set_option("type", SystemType.LIVE_OS.value)
        elif opts.images or opts.dirinstall:
            self.system._set_option("type", SystemType.UNKNOWN.value)
        else:
            self.system._set_option("type", SystemType.BOOT_ISO.value)

        # Set the type of the installation target.
        if opts.images:
            # The image installation is requested.
            self.target._set_option("type", TargetType.IMAGE.value)
        elif opts.dirinstall:
            # The dir installation is requested.
            self.target._set_option("type", TargetType.DIRECTORY.value)
            self.target._set_option("physical_root", opts.dirinstall)

        self.validate()


conf = AnacondaConfiguration.from_defaults()
