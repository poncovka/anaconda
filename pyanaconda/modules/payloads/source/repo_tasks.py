#
# Tasks for repository initialization.
#
# Copyright (C) 2023 Red Hat, Inc.
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
import copy
from collections import namedtuple

from pyanaconda.anaconda_loggers import get_module_logger
from pyanaconda.core.constants import URL_TYPE_BASEURL
from pyanaconda.modules.common.structures.payload import RepoConfigurationData
from pyanaconda.modules.common.task import Task
from pyanaconda.modules.payloads.payload.dnf.repositories import generate_treeinfo_repositories
from pyanaconda.modules.payloads.payload.dnf.tree_info import NoTreeInfoError, \
    TreeInfoMetadataError, TreeInfoMetadata

log = get_module_logger(__name__)

LoadTreeInfoMetadataResult = namedtuple(
    "LoadTreeInfoMetadataResult", [
        "repository_data",
        "release_version",
        "treeinfo_repositories"
    ]
)


class LoadTreeInfoMetadataTask(Task):
    """Task to process treeinfo metadata of an installation source."""

    def __init__(self, data: RepoConfigurationData):
        """Create a task.

        :param RepoConfigurationData data: a repo configuration data
        """
        super().__init__()
        self._data = data
        self._treeinfo_repositories = []
        self._release_version = None
        self._ignored_urls = []

    @property
    def name(self):
        """The task name."""
        return "Load treeinfo metadata"

    def run(self):
        """Run the task."""
        log.debug("Processing treeinfo metadata of: %s", self._data)

        try:
            # Load the treeinfo metadata.
            tree_info_metadata = self._load_treeinfo_metadata()

            # Collect values of substitution variables.
            self._release_version = tree_info_metadata.release_version

            # Handle the URL of the repository.
            self._data = self._handle_url(tree_info_metadata)

            # Generate treeinfo repositories.
            self._treeinfo_repositories = self._generate_treeinfo_repositories(
                tree_info_metadata
            )

        except NoTreeInfoError as e:
            log.debug("No treeinfo metadata to use: %s", str(e))

        except TreeInfoMetadataError as e:
            log.warning("Couldn't use treeinfo metadata: %s", str(e))

        # Return the collected data.
        return LoadTreeInfoMetadataResult(
            repository_data=self._data,
            release_version=self._release_version,
            treeinfo_repositories=self._treeinfo_repositories
        )

    def _load_treeinfo_metadata(self):
        """Reload treeinfo metadata."""
        log.debug("Reload treeinfo metadata...")
        metadata = TreeInfoMetadata()
        metadata.load_data(self._data)
        return metadata

    def _handle_url(self, tree_info_metadata):
        """Handle the URL of the base repository."""
        data = copy.deepcopy(self._data)
        url = tree_info_metadata.get_base_repo_url()
        self._ignored_urls.append(url)

        if url:
            data.type = URL_TYPE_BASEURL
            data.url = url

        return data

    def _generate_treeinfo_repositories(self, tree_info_metadata):
        """Generate the treeinfo repositories."""
        return generate_treeinfo_repositories(
            self._data, tree_info_metadata
        )
