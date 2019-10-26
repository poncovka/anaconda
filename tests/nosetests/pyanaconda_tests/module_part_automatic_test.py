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
# Red Hat Author(s): Vendula Poncova <vponcova@redhat.com>
#
import unittest
from unittest.mock import Mock, patch

from blivet.devices import StorageDevice
from blivet.formats import get_format
from blivet.formats.luks import LUKS2PBKDFArgs
from blivet.size import Size

from pyanaconda.core.configuration.storage import PartitioningType
from pyanaconda.modules.common.structures.validation import ValidationReport
from pyanaconda.storage.partspec import PartSpec
from tests.nosetests.pyanaconda_tests import patch_dbus_publish_object, check_dbus_property, \
    check_task_creation

from pykickstart.constants import AUTOPART_TYPE_LVM_THINP

from dasbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.modules.common.constants.objects import AUTO_PARTITIONING
from pyanaconda.modules.common.errors.storage import UnavailableStorageError, ProtectedDeviceError
from pyanaconda.modules.common.structures.partitioning import PartitioningRequest
from pyanaconda.modules.storage.partitioning import AutoPartitioningModule
from pyanaconda.modules.storage.partitioning.automatic_interface import AutoPartitioningInterface
from pyanaconda.modules.storage.partitioning.automatic_partitioning import \
    AutomaticPartitioningTask, get_default_partitioning
from pyanaconda.modules.storage.partitioning.validate import StorageValidateTask
from pyanaconda.storage.initialization import create_storage


class AutopartitioningInterfaceTestCase(unittest.TestCase):
    """Test DBus interface of the auto partitioning module."""

    def setUp(self):
        """Set up the module."""
        self.module = AutoPartitioningModule()
        self.interface = AutoPartitioningInterface(self.module)

    def _test_dbus_property(self, *args, **kwargs):
        check_dbus_property(
            self,
            AUTO_PARTITIONING,
            self.interface,
            *args, **kwargs
        )

    def publication_test(self):
        """Test the DBus representation."""
        self.assertIsInstance(self.module.for_publication(), AutoPartitioningInterface)

    def enabled_property_test(self):
        """Test the property enabled."""
        self._test_dbus_property(
            "Enabled",
            True
        )

    def request_property_test(self):
        """Test the property request."""
        in_value = {
            'partitioning-scheme': AUTOPART_TYPE_LVM_THINP,
            'file-system-type': 'ext4',
            'excluded-mount-points': ['/home', '/boot', 'swap'],
            'encrypted': True,
            'passphrase': '123456',
            'cipher': 'aes-xts-plain64',
            'luks-version': 'luks1',
            'pbkdf': 'argon2i',
            'pbkdf-memory': 256,
            'pbkdf-time': 100,
            'pbkdf-iterations': 1000,
            'escrow-certificate': 'file:///tmp/escrow.crt',
            'backup-passphrase-enabled': True,
        }

        out_value = {
            'partitioning-scheme': get_variant(Int, AUTOPART_TYPE_LVM_THINP),
            'file-system-type': get_variant(Str, 'ext4'),
            'excluded-mount-points': get_variant(List[Str], ['/home', '/boot', 'swap']),
            'encrypted': get_variant(Bool, True),
            'passphrase': get_variant(Str, '123456'),
            'cipher': get_variant(Str, 'aes-xts-plain64'),
            'luks-version': get_variant(Str, 'luks1'),
            'pbkdf': get_variant(Str, 'argon2i'),
            'pbkdf-memory': get_variant(Int, 256),
            'pbkdf-time': get_variant(Int, 100),
            'pbkdf-iterations': get_variant(Int, 1000),
            'escrow-certificate': get_variant(Str, 'file:///tmp/escrow.crt'),
            'backup-passphrase-enabled': get_variant(Bool, True),
        }

        self._test_dbus_property(
            "Request",
            in_value,
            out_value
        )

    def requires_passphrase_test(self):
        """Test RequiresPassphrase."""
        self.assertEqual(self.interface.RequiresPassphrase(), False)

        self.module.request.encrypted = True
        self.assertEqual(self.interface.RequiresPassphrase(), True)

        self.module.request.passphrase = "123456"
        self.assertEqual(self.interface.RequiresPassphrase(), False)

    def reset_test(self):
        """Test the reset of the storage."""
        with self.assertRaises(UnavailableStorageError):
            if self.module.storage:
                self.fail("The storage shouldn't be available.")

        storage = Mock()
        self.module.on_storage_reset(storage)

        self.assertEqual(self.module._current_storage, storage)
        self.assertIsNone(self.module._storage_playground)

        self.assertNotEqual(self.module.storage, storage)
        self.assertIsNotNone(self.module._storage_playground)

    def remove_device_test(self):
        """Test RemoveDevice."""
        self.module.on_storage_reset(create_storage())

        dev1 = StorageDevice(
            "dev1",
            exists=False,
            size=Size("15 GiB"),
            fmt=get_format("disklabel")
        )
        dev2 = StorageDevice(
            "dev2",
            exists=False,
            parents=[dev1],
            size=Size("6 GiB"),
            fmt=get_format("ext4")
        )
        dev3 = StorageDevice(
            "dev3",
            exists=False,
            parents=[dev1],
            size=Size("9 GiB"),
            fmt=get_format("ext4")
        )

        self.module.storage.devicetree._add_device(dev1)
        self.module.storage.devicetree._add_device(dev2)
        self.module.storage.devicetree._add_device(dev3)

        dev1.protected = True
        with self.assertRaises(ProtectedDeviceError):
            self.interface.RemoveDevice("dev1")

        self.assertIn(dev1, self.module.storage.devices)
        self.assertIn(dev2, self.module.storage.devices)
        self.assertIn(dev3, self.module.storage.devices)

        dev1.protected = False
        dev2.protected = True
        self.interface.RemoveDevice("dev1")

        self.assertIn(dev1, self.module.storage.devices)
        self.assertIn(dev2, self.module.storage.devices)
        self.assertNotIn(dev3, self.module.storage.devices)

        dev2.protected = False
        self.interface.RemoveDevice("dev1")

        self.assertNotIn(dev1, self.module.storage.devices)
        self.assertNotIn(dev2, self.module.storage.devices)
        self.assertNotIn(dev3, self.module.storage.devices)

    def shrink_device_test(self):
        """Test ShrinkDevice."""
        self.module.on_storage_reset(create_storage())

        sda1 = StorageDevice(
            "sda1",
            exists=False,
            size=Size("10 GiB"),
            fmt=get_format("ext4")
        )
        self.module.storage.devicetree._add_device(sda1)

        def resize_device(device, size):
            device.size = size

        self.module.storage.resize_device = resize_device

        sda1.protected = True
        with self.assertRaises(ProtectedDeviceError):
            self.interface.ShrinkDevice("sda1", Size("3 GiB").get_bytes())

        sda1.protected = False
        self.interface.ShrinkDevice("sda1", Size("3 GiB").get_bytes())
        self.assertEqual(sda1.size, Size("3 GiB"))

        self.interface.ShrinkDevice("sda1", Size("5 GiB").get_bytes())
        self.assertEqual(sda1.size, Size("3 GiB"))

    @patch_dbus_publish_object
    def configure_with_task_test(self, publisher):
        """Test ConfigureWithTask."""
        self.module.on_storage_reset(Mock())
        task_path = self.interface.ConfigureWithTask()

        obj = check_task_creation(self, task_path, publisher, AutomaticPartitioningTask)

        self.assertEqual(obj.implementation._storage, self.module.storage)
        self.assertEqual(obj.implementation._request, self.module.request)

    @patch_dbus_publish_object
    def validate_with_task_test(self, publisher):
        """Test ValidateWithTask."""
        self.module.on_storage_reset(Mock())
        task_path = self.interface.ValidateWithTask()

        obj = check_task_creation(self, task_path, publisher, StorageValidateTask)
        self.assertEqual(obj.implementation._storage, self.module.storage)

        report = ValidationReport()
        report.error_messages = [
            "Something is wrong.",
            "Something is very wrong."
        ]
        report.warning_messages = [
            "Something might be wrong."
        ]
        obj.implementation._set_result(report)

        result = obj.GetResult()
        expected_result = get_variant(Structure, {
            "error-messages": get_variant(List[Str], [
                "Something is wrong.",
                "Something is very wrong."
            ]),
            "warning-messages": get_variant(List[Str], [
                "Something might be wrong."
            ])
        })

        self.assertIsInstance(result, Variant)
        self.assertEqual(get_native(result), get_native(expected_result))
        self.assertTrue(result.equal(expected_result))


class AutomaticPartitioningTaskTestCase(unittest.TestCase):
    """Test the automatic partitioning task."""

    def no_luks_format_args_test(self):
        storage = create_storage()
        request = PartitioningRequest()

        args = AutomaticPartitioningTask._get_luks_format_args(storage, request)
        self.assertEqual(args, {})

    def luks1_format_args_test(self):
        storage = create_storage()
        storage._escrow_certificates["file:///tmp/escrow.crt"] = "CERTIFICATE"

        request = PartitioningRequest()
        request.encrypted = True
        request.passphrase = "passphrase"
        request.luks_version = "luks1"
        request.cipher = "aes-xts-plain64"
        request.escrow_certificate = "file:///tmp/escrow.crt"
        request.backup_passphrase_enabled = True

        args = AutomaticPartitioningTask._get_luks_format_args(storage, request)
        self.assertEqual(args, {
            "passphrase": "passphrase",
            "cipher": "aes-xts-plain64",
            "luks_version": "luks1",
            "pbkdf_args": None,
            "escrow_cert": "CERTIFICATE",
            "add_backup_passphrase": True,
        })

    def luks2_format_args_test(self):
        storage = create_storage()
        request = PartitioningRequest()
        request.encrypted = True
        request.passphrase = "default"
        request.luks_version = "luks2"
        request.pbkdf = "argon2i"
        request.pbkdf_memory = 256
        request.pbkdf_iterations = 1000
        request.pbkdf_time = 100

        args = AutomaticPartitioningTask._get_luks_format_args(storage, request)
        pbkdf_args = args.pop("pbkdf_args")

        self.assertEqual(args, {
            "passphrase": "default",
            "cipher": "",
            "luks_version": "luks2",
            "escrow_cert": None,
            "add_backup_passphrase": False,
        })

        self.assertIsInstance(pbkdf_args, LUKS2PBKDFArgs)
        self.assertEqual(pbkdf_args.type, "argon2i")
        self.assertEqual(pbkdf_args.max_memory_kb, 256)
        self.assertEqual(pbkdf_args.iterations, 1000)
        self.assertEqual(pbkdf_args.time_ms, 100)

    @patch('pyanaconda.modules.storage.partitioning.automatic_partitioning.platform')
    def get_default_partitioning_test(self, platform):
        platform.set_default_partitioning.return_value = [PartSpec("/boot")]

        requests = get_default_partitioning(PartitioningType.WORKSTATION)
        self.assertEqual(["/boot", "/", "/home", None], [spec.mountpoint for spec in requests])

        requests = get_default_partitioning(PartitioningType.SERVER)
        self.assertEqual(["/boot", "/", None], [spec.mountpoint for spec in requests])

    @patch('pyanaconda.modules.storage.partitioning.automatic_partitioning.suggest_swap_size')
    @patch('pyanaconda.modules.storage.partitioning.automatic_partitioning.platform')
    def get_partitioning_test(self, platform, suggest_swap_size):
        storage = create_storage()

        # Set the platform specs.
        platform.set_default_partitioning.return_value = [
            PartSpec(mountpoint="/boot", size=Size("1GiB"))
        ]

        # Set the file system type for /boot.
        storage._bootloader = Mock(stage2_format_types=["xfs"])

        # Set the swap size.
        suggest_swap_size.return_value = Size("1024MiB")

        # Collect the requests.
        requests = AutomaticPartitioningTask._get_partitioning(
            storage=storage,
            excluded_mount_points=["/home", "/boot", "swap"]
        )

        self.assertEqual(["/"], [spec.mountpoint for spec in requests])

        requests = AutomaticPartitioningTask._get_partitioning(
            storage=storage,
            excluded_mount_points=[]
        )

        self.assertEqual(
            ["/boot", "/", "/home", None],
            [spec.mountpoint for spec in requests]
        )
        self.assertEqual(
            ["xfs", "ext4", "ext4", "swap"],
            [spec.fstype for spec in requests]
        )
        self.assertEqual(
            [Size("1GiB"), Size("1GiB"), Size("500MiB"), Size("1024MiB")],
            [spec.size for spec in requests]
        )
