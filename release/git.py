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

"""Run git in the current directory."""

from __future__ import annotations

import subprocess


def git(*args: str) -> str:
    """Run git in the current directory and return its stripped standard output."""
    result = subprocess.run(  # noqa: S603 - fixed executable, arguments are ours
        ["git", *args],  # noqa: S607 - git comes from PATH on every runner
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()
