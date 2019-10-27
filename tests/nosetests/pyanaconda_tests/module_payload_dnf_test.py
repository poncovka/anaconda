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
# Red Hat Author(s): Jiri Konecny <jkonecny@redhat.com>
#
import unittest

from tests.nosetests.pyanaconda_tests import patch_dbus_publish_object, ModuleHandlerMixin

from pyanaconda.modules.common.constants.objects import DNF_PACKAGES
from pyanaconda.modules.common.errors import InvalidValueError
from pyanaconda.modules.payload.payloads.dnf.packages.packages import PackagesHandlerModule
from pyanaconda.modules.payload.payloads.dnf.packages.packages_interface import \
    PackagesHandlerInterface
from pyanaconda.modules.payload.payloads.dnf.packages.constants import TIMEOUT_UNSET, \
    RETRIES_UNSET, LANGUAGES_DEFAULT, LANGUAGES_NONE
from tests.nosetests.pyanaconda_tests.module_payload_shared import PayloadHandlerMixin


class PackagesHandlerKSTestCase(unittest.TestCase, PayloadHandlerMixin):

    def setUp(self):
        self.setup_payload()

        # test variables
        self._expected_env = ""
        self._expected_packages = []
        self._expected_groups = []
        self._expected_excluded_packages = []
        self._expected_excluded_groups = []

    def _get_packages_interface(self):
        payload_handler = self.get_payload_handler()
        packages_handler = payload_handler._packages_handler

        self.assertIsInstance(packages_handler, PackagesHandlerModule)
        return PackagesHandlerInterface(packages_handler)

    def _check_properties(self, nocore=False, multilib="best",
                          langs=LANGUAGES_DEFAULT, ignore_missing=False):
        intf = self._get_packages_interface()

        self.assertEqual(self._expected_env, intf.Environment)
        self.assertEqual(self._expected_packages, intf.Packages)
        self.assertEqual(self._expected_groups, intf.Groups)
        self.assertEqual(self._expected_excluded_packages, intf.ExcludedPackages)
        self.assertEqual(self._expected_excluded_groups, intf.ExcludedGroups)

        self.assertEqual(nocore, not intf.CoreGroupEnabled)
        self.assertEqual(multilib, intf.MultilibPolicy)
        if langs:
            self.assertEqual(langs, intf.Languages)
        else:
            self.assertEqual([], intf.Languages)
        self.assertEqual(ignore_missing, intf.MissingIgnored)

    @patch_dbus_publish_object
    def packages_section_empty_kickstart_test(self, publisher):
        """Test the empty packages section."""
        ks_in = """
        %packages
        %end
        """
        ks_out = """
        %packages

        %end
        """
        self.check_kickstart(ks_in, ks_out, expected_publish_calls=2)
        self._check_properties()

    @patch_dbus_publish_object
    def packages_section_kickstart_test(self, publisher):
        """Test the packages section."""
        ks_in = """
        %packages
        package
        @group
        @module:10
        @module2:1.5/server
        @^environment
        %end
        """
        ks_out = """
        %packages
        @^environment
        @group
        @module2:1.5/server
        @module:10
        package

        %end
        """
        self.check_kickstart(ks_in, ks_out, expected_publish_calls=2)

        self._expected_env = "environment"
        self._expected_packages = ["package"]
        self._expected_groups = ["group", "module:10", "module2:1.5/server"]
        self._check_properties()

    @patch_dbus_publish_object
    def packages_section_complex_kickstart_test(self, publisher):
        """Test the packages section with duplicates."""
        ks_in = """
        %packages
        @^environment1
        package1
        @group1
        package2

        # Only this environment will stay (last specified wins)
        @^environment2
        @group2

        # duplicates
        package2
        @group2

        # modules
        @module:4
        @module:3.5/server

        %end
        """
        # The last specified environment wins, you can't specify two environments
        # Same package or group specified twice will be deduplicated
        ks_out = """
        %packages
        @^environment2
        @group1
        @group2
        @module:3.5/server
        @module:4
        package1
        package2

        %end
        """
        self.check_kickstart(ks_in, ks_out, expected_publish_calls=2)

        self._expected_env = "environment2"
        self._expected_packages = ["package1", "package2"]
        self._expected_groups = ["group1", "group2", "module:4", "module:3.5/server"]
        self._check_properties()

    @patch_dbus_publish_object
    def packages_section_with_attribute_kickstart_test(self, publisher):
        """Test the packages section with attribute."""
        ks_in = """
        %packages --nocore
        %end
        """
        ks_out = """
        %packages --nocore

        %end
        """
        self.check_kickstart(ks_in, ks_out, expected_publish_calls=2)
        self._check_properties(nocore=True)

    @patch_dbus_publish_object
    def packages_section_multiple_attributes_kickstart_test(self, publisher):
        """Test the packages section with multiple attributes."""
        ks_in = """
        %packages --nocore --multilib --instLangs en_US.UTF-8

        %end
        """
        ks_out = """
        %packages --nocore --instLangs=en_US.UTF-8 --multilib

        %end
        """
        self.check_kickstart(ks_in, ks_out, expected_publish_calls=2)
        self._check_properties(nocore=True, multilib="all", langs="en_US.UTF-8")

    @patch_dbus_publish_object
    def packages_section_excludes_kickstart_test(self, publisher):
        """Test the packages section with excludes."""
        ks_in = """
        %packages
        -vim
        %end
        """
        ks_out = """
        %packages
        -vim

        %end
        """
        self.check_kickstart(ks_in, ks_out, expected_publish_calls=2)

        self._expected_excluded_packages = ["vim"]
        self._check_properties()

    @patch_dbus_publish_object
    def packages_section_complex_exclude_kickstart_test(self, publisher):
        """Test the packages section with complex exclude example."""
        ks_in = """
        %packages --nocore --ignoremissing --instLangs=
        @^environment1
        @group1
        package1
        -package2
        -@group2
        @group3
        package3
        %end
        """
        ks_out = """
        %packages --nocore --ignoremissing --instLangs=
        @^environment1
        @group1
        @group3
        package1
        package3
        -@group2
        -package2

        %end
        """
        self.check_kickstart(ks_in, ks_out, expected_publish_calls=2)

        self._expected_env = "environment1"
        self._expected_packages = ["package1", "package3"]
        self._expected_groups = ["group1", "group3"]
        self._expected_excluded_packages = ["package2"]
        self._expected_excluded_groups = ["group2"]

        self._check_properties(nocore=True, ignore_missing=True, langs=LANGUAGES_NONE)


class PackagesHandlerInterfaceTestCase(unittest.TestCase, ModuleHandlerMixin):

    def setUp(self):
        self.packages_module = PackagesHandlerModule()
        self.packages_interface = PackagesHandlerInterface(self.packages_module)
        self.set_identifier(DNF_PACKAGES)
        self.set_interface(self.packages_interface)

    def core_group_enabled_properties_test(self):
        self._check_dbus_property(
            "CoreGroupEnabled",
            True
        )

    def core_group_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.CoreGroupEnabled, True)

    def default_environment_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.DefaultEnvironment, False)

    def environment_properties_test(self):
        self._check_dbus_property(
            "Environment",
            "TestEnv"
        )

    def environment_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.Environment, "")

    def groups_properties_test(self):
        self._check_dbus_property(
            "Groups",
            ["group1", "group2"]
        )

    def groups_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.Groups, [])

    def packages_properties_test(self):
        self._check_dbus_property(
            "Packages",
            ["package1", "package2"]
        )

    def packages_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.Packages, [])

    def excluded_groups_properties_test(self):
        self._check_dbus_property(
            "ExcludedGroups",
            ["group1", "group2"]
        )

    def excluded_groups_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.ExcludedGroups, [])

    def excluded_packages_properties_test(self):
        self._check_dbus_property(
            "ExcludedPackages",
            ["package1", "package2"]
        )

    def excluded_packages_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.ExcludedPackages, [])

    def docs_excluded_properties_test(self):
        self._check_dbus_property(
            "DocsExcluded",
            True
        )

    def docs_excluded_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.DocsExcluded, False)

    def weakdeps_excluded_properties_test(self):
        self._check_dbus_property(
            "WeakdepsExcluded",
            True
        )

    def weakdeps_excluded_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.WeakdepsExcluded, False)

    def missing_ignored_properties_test(self):
        self._check_dbus_property(
            "MissingIgnored",
            True
        )

    def missing_ignored_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.MissingIgnored, False)

    def languages_properties_test(self):
        self._check_dbus_property(
            "Languages",
            "en, es"
        )

    def languages_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.Languages, LANGUAGES_DEFAULT)

    def languages_incorrect_value_properties_test(self):
        with self.assertRaises(InvalidValueError):
            self.packages_interface.SetLanguages("")

    def multilib_policy_properties_test(self):
        self._check_dbus_property(
            "MultilibPolicy",
            'all'
        )

    def multilib_policy_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.MultilibPolicy, 'best')

    def timeout_properties_test(self):
        self._check_dbus_property(
            "Timeout",
            60
        )

    def timeout_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.Timeout, TIMEOUT_UNSET)

    def retries_properties_test(self):
        self._check_dbus_property(
            "Retries",
            30
        )

    def retries_not_set_properties_test(self):
        self.assertEqual(self.packages_interface.Retries, RETRIES_UNSET)
