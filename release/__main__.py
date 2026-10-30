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

"""Entry point: `python3 path/to/release <command>` or `python3 -m release <command>`."""

from __future__ import annotations

import sys
from pathlib import Path

# `python3 path/to/release` puts the package directory itself first on sys.path. Put
# its parent there instead, so that the modules import as `release.<module>`.
_PACKAGE = Path(__file__).resolve().parent
if sys.path and Path(sys.path[0]).resolve() == _PACKAGE:
    sys.path[0] = str(_PACKAGE.parent)

from release.cli import main  # noqa: E402 - after the sys.path fix-up above

main()
