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
from abc import ABC

from pyanaconda.core.signal import Signal
from pyanaconda.core.async_utils import async_action_nowait

__all__ = ['ResultReporter']


class ResultReporter(ABC):
    """Abstract class that allows to report a result of a task."""

    def __init__(self):
        super().__init__()
        self._result_changed_signal = Signal()
        self._result = None

    @property
    def result(self):
        """Result of the task.

        :returns: a value of the result
        """
        return self._result

    @property
    def result_changed_signal(self):
        """Signal emits when the result of the task changes."""
        return self._result_changed_signal

    @async_action_nowait
    def report_result(self, value):
        """Report a result change.

        Update the result and emit the result changed signal.
        This is a thread safe method.

        :param value: a value of the result
        """
        self._result = value
        self._result_changed_signal.emit(value)
