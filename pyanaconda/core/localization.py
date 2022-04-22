#
# Copyright (C) 2022 Red Hat, Inc.
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
import os
from locale import setlocale, LC_ALL

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.async_utils import async_action_nowait

log = get_module_logger(__name__)


@async_action_nowait
def set_locale(locale):
    """Set the locale.

    This function modifies the process environment, which is not thread-safe.
    It should be called before any threads are run.

    We cannot get around setting $LANG. Python's gettext implementation
    differs from C in that consults only the environment for the current
    language and not the data set via setlocale. If we want translations
    from python modules to work, something needs to be set in the
    environment when the language changes.

    When this function returns, $LANG will be set, and $LANGUAGE, $LC_ALL,
    and $LC_MESSAGES will not be set, because they get in the way when changing
    the language after startup.

    :param str locale: locale to set
    """
    log.debug("Setting the locale to '%s'.", locale)

    # Save the locale in the environment.
    os.environ["LANG"] = locale  # pylint: disable=environment-modify

    # Clean up the rest of the environment variables.
    for varname in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        if varname in os.environ:
            del os.environ[varname]  # pylint: disable=environment-modify

    # Set the locale.
    setlocale(LC_ALL, locale)
