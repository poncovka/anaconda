#
# Kickstart handler for storage management.
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
from pykickstart import commands
from pykickstart.version import F28
from pyanaconda.modules.base_kickstart import KickstartSpecification


class StorageKickstartSpecification(KickstartSpecification):

    version = F28

    commands = {
        "autopart": commands.autopart.F26_AutoPart,
        "bootloader": commands.bootloader.F21_Bootloader,
        "btrfs": commands.btrfs.F23_BTRFS,
        "clearpart": commands.clearpart.F28_ClearPart,
        "fcoe": commands.fcoe.F13_Fcoe,
        "ignoredisk": commands.ignoredisk.F14_IgnoreDisk,
        "iscsi": commands.iscsi.F17_Iscsi,
        "iscsiname": commands.iscsiname.FC6_IscsiName,
        "logvol": commands.logvol.F23_LogVol,
        "mount": commands.mount.F27_Mount,
        "nfs": commands.nfs.FC6_NFS,
        "part": commands.partition.F23_Partition,
        "partition": commands.partition.F23_Partition,
        "raid": commands.raid.F25_Raid,
        "reqpart": commands.reqpart.F23_ReqPart,
        "snapshot": commands.snapshot.F26_Snapshot,
        "volgroup": commands.volgroup.F21_VolGroup,
        "zerombr": commands.zerombr.F9_ZeroMbr,
        "zfcp": commands.zfcp.F14_ZFCP,
    }
