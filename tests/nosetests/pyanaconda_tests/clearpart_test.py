import unittest
import mock

import blivet
from pyanaconda.storage.osinstall import InstallerStorage
from pyanaconda.core.constants import CLEAR_PARTITIONS_ALL, CLEAR_PARTITIONS_LINUX, CLEAR_PARTITIONS_NONE
from parted import PARTITION_NORMAL
from blivet.flags import flags

from pyanaconda.modules.storage.disk_initialization.clear import DiskInitializationConfig, \
    should_clear_device

DEVICE_CLASSES = [
    blivet.devices.DiskDevice,
    blivet.devices.PartitionDevice
]


@unittest.skipUnless(not any(x.unavailable_type_dependencies() for x in DEVICE_CLASSES), "some unsupported device classes required for this test")
class ClearPartTestCase(unittest.TestCase):

    def setUp(self):
        flags.testing = True

    def test_should_clear(self):
        """ Test the Blivet.should_clear method. """
        b = InstallerStorage()

        DiskDevice = blivet.devices.DiskDevice
        PartitionDevice = blivet.devices.PartitionDevice

        # sda is a disk with an existing disklabel containing two partitions
        sda = DiskDevice("sda", size=100000, exists=True)
        sda.format = blivet.formats.get_format("disklabel", device=sda.path,
                                               exists=True)
        sda.format._parted_disk = mock.Mock()
        sda.format._parted_device = mock.Mock()
        sda.format._parted_disk.configure_mock(partitions=[])
        b.devicetree._add_device(sda)

        # sda1 is a partition containing an existing ext4 filesystem
        sda1 = PartitionDevice("sda1", size=500, exists=True,
                               parents=[sda])
        sda1._parted_partition = mock.Mock(**{'type': PARTITION_NORMAL,
                                              'getLength.return_value': int(sda1.size),
                                              'getFlag.return_value': 0})
        sda1.format = blivet.formats.get_format("ext4", mountpoint="/boot",
                                                device=sda1.path,
                                                exists=True)
        b.devicetree._add_device(sda1)

        # sda2 is a partition containing an existing vfat filesystem
        sda2 = PartitionDevice("sda2", size=10000, exists=True,
                               parents=[sda])
        sda2._parted_partition = mock.Mock(**{'type': PARTITION_NORMAL,
                                              'getLength.return_value': int(sda2.size),
                                              'getFlag.return_value': 0})
        sda2.format = blivet.formats.get_format("vfat", mountpoint="/foo",
                                                device=sda2.path,
                                                exists=True)
        b.devicetree._add_device(sda2)

        # sdb is an unpartitioned disk containing an xfs filesystem
        sdb = DiskDevice("sdb", size=100000, exists=True)
        sdb.format = blivet.formats.get_format("xfs", device=sdb.path,
                                               exists=True)
        b.devicetree._add_device(sdb)

        # sdc is an unformatted/uninitialized/empty disk
        sdc = DiskDevice("sdc", size=100000, exists=True)
        b.devicetree._add_device(sdc)

        # sdd is a disk containing an existing disklabel with no partitions
        sdd = DiskDevice("sdd", size=100000, exists=True)
        sdd.format = blivet.formats.get_format("disklabel", device=sdd.path,
                                               exists=True)
        b.devicetree._add_device(sdd)

        #
        # clearpart type none
        #
        config = DiskInitializationConfig()
        config.initialization_mode = CLEAR_PARTITIONS_NONE
        self.assertFalse(should_clear_device(b, sda1, config),
                         msg="type none should not clear any partitions")
        self.assertFalse(should_clear_device(b, sda2, config),
                         msg="type none should not clear any partitions")

        config.initialize_labels = False
        self.assertFalse(should_clear_device(b, sda, config),
                         msg="type none should not clear non-empty disks")
        self.assertFalse(should_clear_device(b, sdb, config),
                         msg="type none should not clear formatting from "
                             "unpartitioned disks")

        self.assertFalse(should_clear_device(b, sdc, config),
                         msg="type none should not clear empty disk without "
                             "initlabel")
        self.assertFalse(should_clear_device(b, sdd, config),
                         msg="type none should not clear empty partition table "
                             "without initlabel")

        config.initialize_labels = True
        self.assertFalse(should_clear_device(b, sda, config),
                         msg="type none should not clear non-empty disks even "
                             "with initlabel")
        self.assertFalse(should_clear_device(b, sdb, config),
                         msg="type non should not clear formatting from "
                             "unpartitioned disks even with initlabel")
        self.assertTrue(should_clear_device(b, sdc, config),
                        msg="type none should clear empty disks when initlabel "
                            "is set")
        self.assertTrue(should_clear_device(b, sdd, config),
                        msg="type none should clear empty partition table when "
                            "initlabel is set")

        #
        # clearpart type linux
        #
        config.initialization_mode = CLEAR_PARTITIONS_LINUX
        self.assertTrue(should_clear_device(b, sda1, config),
                        msg="type linux should clear partitions containing "
                            "ext4 filesystems")
        self.assertFalse(should_clear_device(b, sda2, config),
                         msg="type linux should not clear partitions "
                             "containing vfat filesystems")

        config.initialize_labels = False
        self.assertFalse(should_clear_device(b, sda, config),
                         msg="type linux should not clear non-empty disklabels")
        self.assertTrue(should_clear_device(b, sdb, config),
                        msg="type linux should clear linux-native whole-disk "
                            "formatting regardless of initlabel setting")
        self.assertFalse(should_clear_device(b, sdc, config),
                         msg="type linux should not clear unformatted disks "
                             "unless initlabel is set")
        self.assertFalse(should_clear_device(b, sdd, config),
                         msg="type linux should not clear disks with empty "
                             "partition tables unless initlabel is set")

        config.initialize_labels = True
        self.assertFalse(should_clear_device(b, sda, config),
                         msg="type linux should not clear non-empty disklabels")
        self.assertTrue(should_clear_device(b, sdb, config),
                        msg="type linux should clear linux-native whole-disk "
                            "formatting regardless of initlabel setting")
        self.assertTrue(should_clear_device(b, sdc, config),
                        msg="type linux should clear unformatted disks when "
                        "initlabel is set")
        self.assertTrue(should_clear_device(b, sdd, config),
                        msg="type linux should clear disks with empty "
                        "partition tables when initlabel is set")

        sda1.protected = True
        self.assertFalse(should_clear_device(b, sda1, config),
                         msg="protected devices should never be cleared")
        self.assertFalse(should_clear_device(b, sda, config),
                         msg="disks containing protected devices should never "
                             "be cleared")
        sda1.protected = False

        #
        # clearpart type all
        #
        config.initialization_mode = CLEAR_PARTITIONS_ALL
        self.assertTrue(should_clear_device(b, sda1, config),
                        msg="type all should clear all partitions")
        self.assertTrue(should_clear_device(b, sda2, config),
                        msg="type all should clear all partitions")

        config.initialize_labels = False
        self.assertTrue(should_clear_device(b, sda, config),
                        msg="type all should initialize all disks")
        self.assertTrue(should_clear_device(b, sdb, config),
                        msg="type all should initialize all disks")
        self.assertTrue(should_clear_device(b, sdc, config),
                        msg="type all should initialize all disks")
        self.assertTrue(should_clear_device(b, sdd, config),
                        msg="type all should initialize all disks")

        config.initialize_labels = True
        self.assertTrue(should_clear_device(b, sda, config),
                        msg="type all should initialize all disks")
        self.assertTrue(should_clear_device(b, sdb, config),
                        msg="type all should initialize all disks")
        self.assertTrue(should_clear_device(b, sdc, config),
                        msg="type all should initialize all disks")
        self.assertTrue(should_clear_device(b, sdd, config),
                        msg="type all should initialize all disks")

        sda1.protected = True
        self.assertFalse(should_clear_device(b, sda1, config),
                         msg="protected devices should never be cleared")
        self.assertFalse(should_clear_device(b, sda, config),
                         msg="disks containing protected devices should never "
                             "be cleared")
        sda1.protected = False

        #
        # clearpart type list
        #
        # TODO

    def tearDown(self):
        flags.testing = False

    def test_initialize_disk(self):
        """
            magic partitions
            non-empty partition table
        """
        pass

    def test_recursive_remove(self):
        """
            protected device at various points in stack
        """
        pass
