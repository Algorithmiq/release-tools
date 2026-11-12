# Copyright 2026 Algorithmiq
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Run commands (git, git cliff, gh) in the current directory."""

from __future__ import annotations

import subprocess


def run(*command: str, strip: bool = False, quiet: bool = False) -> str:
    """Run COMMAND in the current directory and return its standard output.

    The output is stripped if STRIP is true. Stderr is inherited, so the errors of git,
    gh and git cliff reach the job log; with QUIET, it is captured instead, for a caller
    that catches the failure and reports it in its own words. A failure raises
    CalledProcessError, which carries the captured stderr.
    """
    result = subprocess.run(  # noqa: S603 - fixed executables, arguments are ours
        list(command),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if quiet else None,
    )
    return result.stdout.strip() if strip else result.stdout


def git(*args: str, quiet: bool = False) -> str:
    """Run git with ARGS and return its stripped standard output (see run)."""
    return run("git", *args, strip=True, quiet=quiet)
