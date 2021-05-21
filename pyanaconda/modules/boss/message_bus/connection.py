
#
# Copyright (C) 2021  Red Hat, Inc.  All rights reserved.
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
from dasbus.connection import MessageBus
from pyanaconda.anaconda_loggers import get_module_logger

log = get_module_logger(__name__)

# The controller socket file used by the broker.
CONTROLLER_SOCKET_FILE = "/run/anaconda/controller.socket"


class ControllerMessageBus(MessageBus):
    """The controller message bus."""

    @property
    def address(self):
        """The bus address."""
        return "unix:path={}".format(CONTROLLER_SOCKET_FILE)

    def _get_connection(self):
        """Get a connection to a bus at the specified address."""
        log.info("Connecting to a bus at %s.", self.address)
        return self._provider.get_addressed_bus_connection(
            bus_address=self.address, flags=0
        )
