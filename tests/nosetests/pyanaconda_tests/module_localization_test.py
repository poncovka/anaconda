#
# Copyright (C) 2018  Red Hat, Inc.
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
# Red Hat Author(s): Radek Vykydal <rvykydal@redhat.com>
#
import os
import tempfile
import unittest

from textwrap import dedent

from tests.nosetests.pyanaconda_tests import check_task_creation, patch_dbus_publish_object, \
    ModuleHandlerMixin

from pyanaconda.modules.common.constants.services import LOCALIZATION
from pyanaconda.modules.localization.installation import LanguageInstallationTask
from pyanaconda.modules.localization.localization import LocalizationService
from pyanaconda.modules.localization.localization_interface import LocalizationInterface


class LocalizationInterfaceTestCase(unittest.TestCase, ModuleHandlerMixin):
    """Test DBus interface for the localization module."""

    def setUp(self):
        """Set up the localization module."""
        self.localization_module = LocalizationService()
        self.localization_interface = LocalizationInterface(self.localization_module)
        self.set_identifier(LOCALIZATION)
        self.set_interface(self.localization_interface)

    def kickstart_properties_test(self):
        """Test kickstart properties."""
        self._check_kickstart_properties(commands=["keyboard", "lang"])

    def language_property_test(self):
        """Test the Language property."""
        self._check_dbus_property(
            "Language",
            "cs_CZ.UTF-8"
        )

    def language_support_property_test(self):
        """Test the LanguageSupport property."""
        self._check_dbus_property(
            "LanguageSupport",
            ["fr_FR"]
        )

    def keyboard_property_test(self):
        """Test the Keyboard property."""
        self._check_dbus_property(
            "Keyboard",
            "cz"
        )

    def vc_keymap_property_test(self):
        """Test the VirtualConsoleKeymap property."""
        self._check_dbus_property(
            "VirtualConsoleKeymap",
            "cz"
        )

    def x_layouts_property_test(self):
        """Test the XLayouts property."""
        self._check_dbus_property(
            "XLayouts",
            ["en", "cz(querty)"]
        )

    def switch_options_property_test(self):
        """Test the LayoutSwitchOptions property."""
        self._check_dbus_property(
            "LayoutSwitchOptions",
            ["grp:alt_shift_toggle"]
        )

    def keyboard_seen_test(self):
        """Test the KeyboardKickstarted property."""
        self.assertEqual(self.localization_interface.KeyboardKickstarted, False)
        ks_in = """
        lang cs_CZ.UTF-8
        """
        ks_in = dedent(ks_in).strip()
        self.localization_interface.ReadKickstart(ks_in)
        self.assertEqual(self.localization_interface.KeyboardKickstarted, False)
        ks_in = """
        lang cs_CZ.UTF-8
        keyboard cz
        """
        ks_in = dedent(ks_in).strip()
        self.localization_interface.ReadKickstart(ks_in)
        self.assertEqual(self.localization_interface.KeyboardKickstarted, True)

    def language_seen_test(self):
        """Test the LanguageKickstarted property."""
        self.assertEqual(self.localization_interface.LanguageKickstarted, False)
        ks_in = """
        keyboard cz
        """
        ks_in = dedent(ks_in).strip()
        self.localization_interface.ReadKickstart(ks_in)
        self.assertEqual(self.localization_interface.LanguageKickstarted, False)
        ks_in = """
        keyboard cz
        lang cs_CZ.UTF-8
        """
        ks_in = dedent(ks_in).strip()
        self.localization_interface.ReadKickstart(ks_in)
        self.assertEqual(self.localization_interface.LanguageKickstarted, True)

    def set_language_kickstarted_test(self):
        """Test SetLanguageKickstart."""
        self._check_dbus_property(
            "LanguageKickstarted",
            True
        )

    @patch_dbus_publish_object
    def install_language_with_task_test(self, publisher):
        """Test InstallLanguageWithTask."""
        self.localization_interface.SetLanguage("cs_CZ.UTF-8")
        task_path = self.localization_interface.InstallWithTasks()[0]

        obj = check_task_creation(self, task_path, publisher, LanguageInstallationTask)
        self.assertEqual(obj.implementation._lang, "cs_CZ.UTF-8")

    def no_kickstart_test(self):
        """Test with no kickstart."""
        ks_in = None
        ks_out = ""
        self._check_kickstart(ks_in, ks_out)

    def kickstart_empty_test(self):
        """Test with empty string."""
        ks_in = ""
        ks_out = ""
        self._check_kickstart(ks_in, ks_out)

    def lang_kickstart_test(self):
        """Test the lang command."""
        ks_in = """
        lang cs_CZ.UTF-8
        """
        ks_out = """
        # System language
        lang cs_CZ.UTF-8
        """
        self._check_kickstart(ks_in, ks_out)

    def lang_kickstart2_test(self):
        """Test the lang command with added language support.."""
        ks_in = """
        lang en_US.UTF-8 --addsupport=cs_CZ.UTF-8
        """
        ks_out = """
        # System language
        lang en_US.UTF-8 --addsupport=cs_CZ.UTF-8
        """
        self._check_kickstart(ks_in, ks_out)

    def keyboard_kickstart1_test(self):
        """Test the keyboard command."""
        ks_in = """
        keyboard --vckeymap=us --xlayouts='us','cz (qwerty)'
        """
        ks_out = """
        # Keyboard layouts
        keyboard --vckeymap=us --xlayouts='us','cz (qwerty)'
        """
        self._check_kickstart(ks_in, ks_out)

    def keyboard_kickstart2_test(self):
        """Test the keyboard command."""
        ks_in = """
        keyboard us
        """
        ks_out = """
        # Keyboard layouts
        keyboard 'us'
        """
        self._check_kickstart(ks_in, ks_out)

    def keyboard_kickstart3_test(self):
        """Test the keyboard command."""
        ks_in = """
        keyboard --xlayouts=cz,'cz (qwerty)' --switch=grp:alt_shift_toggle
        """
        ks_out = """
        # Keyboard layouts
        keyboard --xlayouts='cz','cz (qwerty)' --switch='grp:alt_shift_toggle'
        """
        self._check_kickstart(ks_in, ks_out)

    def keyboard_kickstart4_test(self):
        """Test the keyboard command."""
        ks_in = """
        keyboard --xlayouts='cz (qwerty)','en' en
        """
        ks_out = """
        # Keyboard layouts
        # old format: keyboard en
        # new format:
        keyboard --xlayouts='cz (qwerty)','en'
        """
        self._check_kickstart(ks_in, ks_out)


class LocalizationTasksTestCase(unittest.TestCase):
    """Test tasks of the localization module."""

    def language_installation_test(self):
        """Test the language installation task."""
        # Prepare sysroot.
        with tempfile.TemporaryDirectory() as root:

            # Prepare for the installation task.
            conf = root + "/etc/locale.conf"
            os.makedirs(os.path.dirname(conf), exist_ok=True)

            # Run the installation task.
            LanguageInstallationTask(root, "cs_CZ.UTF-8").run()

            # Check the result.
            with open(root + "/etc/locale.conf") as f:
                self.assertEqual(f.read(), "LANG=\"cs_CZ.UTF-8\"\n")
