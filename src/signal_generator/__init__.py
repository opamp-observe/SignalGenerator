# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""SignalGenerator package metadata and public interfaces."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("signal-generator")
except PackageNotFoundError:  # pragma: no cover - only used from an uninstalled source tree
    __version__ = "0.1.0"

__all__ = ["__version__"]
