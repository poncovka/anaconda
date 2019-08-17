#
# DBus interface for Live Image payload.
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
from pyanaconda.dbus.interface import dbus_interface, dbus_signal
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.dbus.property import emits_properties_changed

from pyanaconda.modules.common.constants.objects import LIVE_IMAGE_HANDLER
from pyanaconda.modules.common.base import KickstartModuleInterfaceTemplate
from pyanaconda.modules.common.containers import TaskContainer


@dbus_interface(LIVE_IMAGE_HANDLER.interface_name)
class LiveImageHandlerInterface(KickstartModuleInterfaceTemplate):
    """DBus interface for Live Image payload module."""

    def connect_signals(self):
        super().connect_signals()
        self.watch_property("Url", self.implementation.url_changed)
        self.watch_property("Proxy", self.implementation.proxy_changed)
        self.watch_property("Checksum", self.implementation.checksum_changed)
        self.watch_property("VerifySSL", self.implementation.verifyssl_changed)
        self.watch_property("RequiredSpace", self.implementation.required_space_changed)
        self.implementation.kernel_version_list_changed.connect(self.KernelVersionListChanged)

    @property
    def Url(self) -> Str:
        """Get url where to obtain the live image for installation."""
        return self.implementation.url

    @emits_properties_changed
    def SetUrl(self, url: Str):
        """Set url where to obtain the live image for installation."""
        self.implementation.set_url(url)

    @property
    def Proxy(self) -> Str:
        """Get proxy setting which will be used to obtain the image."""
        return self.implementation.proxy

    @emits_properties_changed
    def SetProxy(self, proxy: Str):
        """Set proxy which will be used to obtain the image."""
        self.implementation.set_proxy(proxy)

    @property
    def Checksum(self) -> Str:
        """Get checksum of the image for verification."""
        return self.implementation.checksum

    @emits_properties_changed
    def SetChecksum(self, checksum: Str):
        """Set checksum of the image for validation."""
        self.implementation.set_checksum(checksum)

    @property
    def VerifySSL(self) -> Bool:
        """Should the ssl verification be enabled?"""
        return self.implementation.verifyssl

    @emits_properties_changed
    def SetVerifySSL(self, verify_ssl: Bool):
        """Set if the ssl verification should be enabled."""
        self.implementation.set_verifyssl(verify_ssl)

    @property
    def RequiredSpace(self) -> UInt64:
        """Space required by the source image."""
        return self.implementation.required_space

    def UpdateKernelVersionList(self):
        """Update the list of kernel versions."""
        self.implementation.update_kernel_version_list()

    def GetKernelVersionList(self) -> List[Str]:
        """Get the kernel versions list."""
        return self.implementation.kernel_version_list

    @dbus_signal
    def KernelVersionListChanged(self, kernel_version_list: List[Str]):
        """Signal kernel version list change."""
        pass

    def SetupWithTask(self) -> ObjPath:
        """Setup the handler.

        Check availability of the image and update required space
        """
        return TaskContainer.to_object_path(self.implementation.setup_with_task())

    def PreInstallWithTask(self) -> ObjPath:
        """Set up installation source image

        * Download the image
        * Check the checksum
        * Mount the image
        """
        return TaskContainer.to_object_path(self.implementation.pre_install_with_task())

    def InstallWithTask(self) -> ObjPath:
        """Install the payload.

        * Copy the payload.
        * Create rescue images
        """
        return TaskContainer.to_object_path(self.implementation.install_with_task())

    def PostInstallWithTask(self) -> ObjPath:
        """Do post installation tasks.

        * [TODO] copy driver disk files (Payload)
        * [NO] check installation requirements were applied (Payload)
        * Update BLS entries (LiveOSPayload)
        """
        return TaskContainer.to_object_path(self.implementation.post_install_with_task())

    def TeardownWithTask(self) -> ObjPath:
        """Tear down installation source image.

        * Unmount the image
        * Clean up mount point directories
        * Remove downloaded image
        """
        return TaskContainer.to_object_path(self.implementation.teardown_with_task())
