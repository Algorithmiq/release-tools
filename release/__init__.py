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

"""Release automation of release-tools, run by its reusable workflows.

Works out version numbers from tags and branches, tags releases, writes the release
PR and keeps CHANGELOG.md on main up to date. Run it in the root of the repository
being released: `python3 path/to/release <command>`, or `python3 -m release <command>`
from the root of release-tools. Standard library only, Python 3.12 or later.
"""
