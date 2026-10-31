#!/usr/bin/env bash
# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "${script_directory}/.." && pwd)"
posix_virtual_environment_python="${repository_root}/.venv/bin/python"
windows_virtual_environment_python="${repository_root}/.venv/Scripts/python.exe"

if [[ -x "${posix_virtual_environment_python}" ]]; then
    virtual_environment_python="${posix_virtual_environment_python}"
elif [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]] && \
    [[ -x "${windows_virtual_environment_python}" ]]; then
    virtual_environment_python="${windows_virtual_environment_python}"
else
    echo "Project virtual environment not found. Create it with: python3 -m venv '${repository_root}/.venv'" >&2
    exit 1
fi

if ! "${virtual_environment_python}" -c \
    "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('signal_generator') else 1)"; then
    echo "SignalGenerator is not installed in .venv. Run: '${virtual_environment_python}' -m pip install -e '${repository_root}'" >&2
    exit 1
fi

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export SIGNAL_GENERATOR_LOG_LEVEL="${SIGNAL_GENERATOR_LOG_LEVEL:-DEBUG}"

cd "${repository_root}"
exec "${virtual_environment_python}" -m signal_generator run "$@"
