# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from abc import ABC

from ..constants import VCT

from ..models.executable import ExecutableModel

import logging
import re
import subprocess

log = logging.getLogger(__name__)


class AbstractVersionChecker(ABC):
    """
    The base class for VersionCheckers (although a version checker really only
    needs to implement get_version, the other methods are provided for ease of
    use and extensibility).

    To extend this class, use it as the base and override the necessary methods.
    The net result should be a class that can be registered to the registry with
    type = VCT.VERSION_CHECKER and key = <executable name>
    """

    @classmethod
    def csis_classifier(cls) -> VCT:
      return VCT.VERSION_CHECKER
    
    def get_regex(self) -> str:
        return r"(.*)"

    def get_group(self) -> int:
        return 1

    def get_version_params(self) -> list[str]:
        return ["--version"]

    def get_extracted_string(self, res: subprocess.CompletedProcess[str]) -> str | None:
        return res.stdout.strip().splitlines()[0].strip()

    def get_version(self, executable: ExecutableModel) -> str | None:
        try:
            result = executable.execute(*self.get_version_params(), skips=True)
            version_data = self.get_extracted_string(result) or "OOPS!"
            match = re.search(self.get_regex(), version_data)
            ver: str | None = None
            if match:
                ver = match.group(self.get_group()) or None
            return ver
        except Exception as ex:
            log.error(f"Error while checking version for executable {executable}: {ex}")
            raise ex
