#
# DBus interface for Live payload.
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
from pyanaconda.dbus.interface import dbus_interface
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.dbus.property import emits_properties_changed

from pyanaconda.modules.common.constants.objects import LIVE_OS_HANDLER
from pyanaconda.modules.common.base import KickstartModuleInterfaceTemplate
from pyanaconda.modules.common.containers import TaskContainer


@dbus_interface(LIVE_OS_HANDLER.interface_name)
class LiveOSHandlerInterface(KickstartModuleInterfaceTemplate):
    """DBus interface for Live OS payload module."""

    def connect_signals(self):
        super().connect_signals()
        self.watch_property("ImagePath", self.implementation.image_path_changed)

    @property
    def ImagePath(self) -> Str:
        """Get the path to the Live OS base image.

        This image will be used as the installation.
        """
        return self.implementation.image_path

    @emits_properties_changed
    def SetImagePath(self, image_path: Str):
        """Set the path to the Live OS base image.

        This image will be used as the installation source.
        """
        self.implementation.set_image_path(image_path)

    def DetectLiveOSImage(self) -> Str:
        """Try to find valid live os image.

        :return: path to the base image
        """
        return self.implementation.detect_live_os_base_image()

    def SetupInstallationSourceWithTask(self) -> ObjPath:
        """Setup installation source resources."""
        return TaskContainer.to_object_path(
            self.implementation.setup_installation_source_with_task()
        )

    def TeardownInstallationSourceWithTask(self) -> ObjPath:
        """Teardown installation source resources."""
        return TaskContainer.to_object_path(
            self.implementation.teardown_installation_source_with_task()
        )
