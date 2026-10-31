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

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
$virtualEnvironmentPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $virtualEnvironmentPython -PathType Leaf)) {
    [Console]::Error.WriteLine(
        "Project virtual environment not found. Create it with: py -m venv `"$repositoryRoot\.venv`""
    )
    exit 1
}

& $virtualEnvironmentPython -c (
    "import importlib.util, sys; " +
    "sys.exit(0 if importlib.util.find_spec('signal_generator') else 1)"
)
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine(
        "SignalGenerator is not installed in .venv. Run: " +
        "`"$virtualEnvironmentPython`" -m pip install -e `"$repositoryRoot`""
    )
    exit 1
}

if ([string]::IsNullOrWhiteSpace($env:PYTHONUNBUFFERED)) {
    $env:PYTHONUNBUFFERED = "1"
}
if ([string]::IsNullOrWhiteSpace($env:SIGNAL_GENERATOR_LOG_LEVEL)) {
    $env:SIGNAL_GENERATOR_LOG_LEVEL = "DEBUG"
}

$exitCode = 0
Push-Location $repositoryRoot
try {
    & $virtualEnvironmentPython -m signal_generator run @args
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $exitCode
