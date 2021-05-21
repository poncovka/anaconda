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
import os
import socket
import subprocess

from dasbus.client.handler import GLibClient
from dasbus.constants import DBUS_FLAG_NONE
from dasbus.typing import get_variant_type, get_variant

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.constants import DBUS_ANACONDA_SESSION_ADDRESS, ANACONDA_BUS_ADDR_FILE
from pyanaconda.core.util import startProgram
from pyanaconda.modules.boss.message_bus.connection import ControllerMessageBus, \
    CONTROLLER_SOCKET_FILE
from pyanaconda.modules.boss.message_bus.controller import DBusControllerInterface
from pyanaconda.modules.common.constants.objects import DBUS_CONTROLLER, DBUS_BROKER

log = get_module_logger(__name__)


class DBusLauncher(object):

    def __init__(self):
        self._log_file = None
        self._broker_process = None
        self._controller_socket = None
        self._controller_bus = None
        self._listener_socket = None
        self._bus_address = None

    @property
    def bus_address(self):
        """The address of the Anaconda DBus session."""
        return self._bus_address

    @property
    def controller_bus(self):
        """The controller message bus."""
        return self._controller_bus

    def start(self):
        """Start DBus modules.

        Start the DBus session, the boss and the kickstart modules.
        """
        self._start_dbus_broker()
        self._start_dbus_session()
        # self._set_environment()
        # self._write_bus_address()

    def _start_dbus_broker(self):
        """Start the DBus broker."""
        # Open a socket for the controller.
        self._controller_socket = socket.socket(
            family=socket.AF_UNIX,
            type=socket.SOCK_STREAM | socket.SOCK_NONBLOCK
        )

        self._controller_socket.bind(
            CONTROLLER_SOCKET_FILE
        )

        self._controller_socket.listen()
        controller_fd = self._controller_socket.fileno()

        # Open a log file.
        self._log_file = open('/tmp/broker.log', 'a')
        log_fd = self._log_file.fileno()

        # Start the DBus broker.
        self._broker_process = startProgram(
            [
                "dbus-broker",
                '--controller={}'.format(controller_fd),
                '--log={}'.format(log_fd),
                '--audit'
            ],
            reset_lang=False,
            pass_fds=[controller_fd, log_fd],
        )

        if self._broker_process.poll() is not None:
            raise IOError("The DBus broker has failed to start.")

    def _start_dbus_session(self):
        """Start dbus session if not running already."""
        # Create the message bus abstraction.
        self._controller_bus = ControllerMessageBus()

        # Publish the controller.
        self._controller_bus.publish_object(
            DBUS_CONTROLLER.object_path,
            DBusControllerInterface()
        )

        # Create a listener socket.
        self._listener_socket = socket.socket(
            family=socket.AF_UNIX,
            type=socket.SOCK_STREAM | socket.SOCK_NONBLOCK
        )
        self._listener_socket.listen()
        listener_fd = self._controller_socket.fileno()

        listener_path = "/org/bus1/DBus/Listener/1"
        listener_policy = get_variant("(s)", ("test", ))

        self._controller_bus.connection.call_with_unix_fd_list(
            None,
            DBUS_BROKER.object_path,
            DBUS_BROKER.interface_name,
            "AddListener",
            get_variant("(ohv)", (
                listener_path,
                listener_fd,
                listener_policy
            )),
            None,
            DBUS_FLAG_NONE,
            10,
            [listener_fd],
            None,
            None,
            None
        )

    def _set_environment(self):
        """Set the environment variables."""
        # pylint: disable=environment-modify
        os.environ[DBUS_ANACONDA_SESSION_ADDRESS] = self._bus_address

    def _write_bus_address(self):
        """Write the bus address to a file."""
        file_name = ANACONDA_BUS_ADDR_FILE
        run_dir = os.path.dirname(file_name)

        if not os.path.exists(run_dir):
            os.mkdir(run_dir)

        with open(file_name, 'wt') as f:
            f.write(self._bus_address)

    def stop(self, timeout=20):
        """Stop the DBus modules.

        Stop the DBus session, the boss and the kickstart modules.

        :param timeout: seconds to the launcher timeout
        """
        self._stop_dbus_broker(timeout)
        # self._remove_bus_address_file()

    def _stop_dbus_broker(self, timeout):
        """Stop the DBus broker and clean bus address file."""
        if self._controller_socket:
            self._controller_socket.close()

        if self._log_file:
            self._log_file.close()

        if self._broker_process:
            try:
                self._broker_process.terminate()
                self._broker_process.wait(timeout)
            except subprocess.TimeoutExpired:
                self._broker_process.kill()

            log.debug("Process exited with %s.", self._broker_process.poll())

    def _remove_bus_address_file(self):
        """Remove the file with the bus address."""
        file_name = ANACONDA_BUS_ADDR_FILE

        if os.path.exists(file_name):
            os.unlink(file_name)
