# Action summary dialog
#
# Copyright (C) 2013-2014  Red Hat, Inc.
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
from pyanaconda.modules.common.structures.storage import DeviceActionData, DeviceData, \
    DeviceFormatData
from pyanaconda.ui.gui import GUIObject
from pyanaconda.core.i18n import _

__all__ = ["ActionSummaryDialog"]


class ActionSummaryDialog(GUIObject):
    builderObjects = ["actionStore", "summaryDialog"]
    mainWidgetName = "summaryDialog"
    uiFile = "spokes/lib/summary.glade"

    def __init__(self, data, device_tree):
        super().__init__(data)
        self._store = self.builder.get_object("actionStore")

        # Get actions of the given device tree.
        self._actions = DeviceActionData.from_structure_list(
            device_tree.GetActions()
        )

        for (i, action) in enumerate(self._actions, start=1):
            # Get the device data.
            device_data = DeviceData.from_structure(
                device_tree.GetDeviceData(action.device_name)
            )

            format_data = DeviceFormatData.from_structure(
                device_tree.GetFormatData(action.device_name)
            )

            # Get the object description and the mount point.
            if action.action_object == "format":
                object_description = format_data.description
                mount_point = format_data.attrs.get("mount-point", "")
            else:
                object_description = device_data.type
                mount_point = ""

            # Get the action description.
            if action.action_type in ["destroy", "resize"]:
                action_color = "red"
                mount_point = ""
            else:
                action_color = "green"

            action_description = "<span foreground='{color}'>{action}</span>".format(
                color=action_color,
                action=action.description
            )

            # Get the device description and the serial number.
            if device_data.description:
                serial = device_data.attrs.get("serial", "")
                device_description = _("{description} ({device_name})").format(
                    desciption=device_data.description,
                    device_name=device_data.name
                )
            elif device_data.type == "partition":
                disk_name = device_data.parents[0]
                disk_data = DeviceData.from_structure(
                    device_tree.GetDeviceData(disk_name)
                )

                serial = disk_data.attrs.get("serial", "")
                device_description = _("{partition_name} on {disk_name}").format(
                    partition_name=device_data.name,
                    disk_name=disk_data.description
                )
            else:
                serial = device_data.attrs.get("serial", "")
                device_description = device_data.name

            # Create a new row in the action store.
            self._store.append([
                i,
                action_description,
                object_description,
                device_description,
                mount_point,
                serial
            ])

    @property
    def actions(self):
        """A list of scheduled actions."""
        return self._actions

    def run(self):
        rc = self.window.run()
        self.window.destroy()
        return rc
