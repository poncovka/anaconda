#
# base.py:  base interface for a module
#
# Copyright (C) 2017
# Red Hat, Inc.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author(s):  Vendula Poncova <vponcova@redhat.com>
#

from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.dbus.interface import dbus_interface, dbus_signal


@dbus_interface
class TaskReporter(object):

    @dbus_signal
    def TaskStarted(self, task_id):
        pass

    @dbus_signal
    def TaskFinished(self, task_id):
        pass

    @dbus_signal
    def TaskFailed(self, task_id, message):
        pass

    @dbus_signal
    def TaskReported(self, task_id, level, message):
        pass


@dbus_interface
class TaskManager(TaskReporter):

    @dbus_signal
    def TaskBlocked(self, task_id, blocker_id):
        """

        :param task_id:
        :param blocker_id:
        :return:
        """
        pass

    def BlockTask(self, task_id, blocker_id):
        """

        :param task_id:
        :return:
        """
        pass


    def UnblockTask(self, task_id, blocker_id):
        """

        :param task_id:
        :param blocker_id:
        :return:
        """
        pass

    def AddTask(self, task_name, task_id, ):