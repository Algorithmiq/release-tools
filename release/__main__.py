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

"""Entry point: `python3 path/to/release ...` or `python3 -m release ...`."""

from __future__ import annotations

import sys
from pathlib import Path

# The package needs Python 3.12: an older Python fails to import it with a SyntaxError.
# So check first, in this file, which older Pythons must still be able to parse.
if sys.version_info < (3, 12):  # noqa: UP036 - the check is for Pythons below the target
    sys.exit(
        "::error::release-tools needs Python 3.12 or later, not "
        + sys.version.split()[0]
        + " ("
        + sys.executable
        + ")."
    )

# `python3 path/to/release` puts the package directory itself first on sys.path. Put
# its parent there instead, so that the modules import as `release.<module>`.
_PACKAGE = Path(__file__).resolve().parent
if sys.path and Path(sys.path[0]).resolve() == _PACKAGE:
    sys.path[0] = str(_PACKAGE.parent)

from release.cli import main  # noqa: E402 - after the sys.path fix-up above

main()
