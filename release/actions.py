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

"""GitHub Actions output: error annotations and step outputs."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
    """Report MESSAGE as a GitHub Actions error annotation and exit with status 1."""
    print(f"::error::{message}")  # noqa: T201 - the annotation goes to the job log
    sys.exit(1)


def output(**values: str) -> None:
    """Print VALUES as key=value lines and append them to $GITHUB_OUTPUT if set."""
    lines = [f"{key}={value}" for key, value in values.items()]
    print("\n".join(lines))  # noqa: T201 - the outputs are part of the CLI
    if path := os.environ.get("GITHUB_OUTPUT"):
        with Path(path).open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
