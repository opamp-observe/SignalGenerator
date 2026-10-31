@echo off
rem Copyright 2026 opamp.info
rem Licensed under the Apache License, Version 2.0 (the "License");
rem you may not use this file except in compliance with the License.
rem You may obtain a copy of the License at
rem http://www.apache.org/licenses/LICENSE-2.0
rem
rem Unless required by applicable law or agreed to in writing, software
rem distributed under the License is distributed on an "AS IS" BASIS,
rem WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
rem See the License for the specific language governing permissions and
rem limitations under the License.

setlocal EnableExtensions

set "SCRIPT_DIRECTORY=%~dp0"
for %%I in ("%SCRIPT_DIRECTORY%..") do set "REPOSITORY_ROOT=%%~fI"
set "VIRTUAL_ENVIRONMENT_PYTHON=%REPOSITORY_ROOT%\.venv\Scripts\python.exe"

if not exist "%VIRTUAL_ENVIRONMENT_PYTHON%" (
  >&2 echo Project virtual environment not found. Create it with: py -m venv "%REPOSITORY_ROOT%\.venv"
  exit /b 1
)

"%VIRTUAL_ENVIRONMENT_PYTHON%" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('signal_generator') else 1)"
if errorlevel 1 (
  >&2 echo SignalGenerator is not installed in .venv. Run: "%VIRTUAL_ENVIRONMENT_PYTHON%" -m pip install -e "%REPOSITORY_ROOT%"
  exit /b 1
)

if not defined PYTHONUNBUFFERED set "PYTHONUNBUFFERED=1"
if not defined SIGNAL_GENERATOR_LOG_LEVEL set "SIGNAL_GENERATOR_LOG_LEVEL=DEBUG"

pushd "%REPOSITORY_ROOT%"
"%VIRTUAL_ENVIRONMENT_PYTHON%" -m signal_generator run %*
set "EXIT_CODE=%ERRORLEVEL%"
popd

exit /b %EXIT_CODE%
