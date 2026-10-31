# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Configuration loading, validation, and legacy conversion APIs."""

from signal_generator.config.loader import LoadedConfiguration, load_configuration
from signal_generator.config.validation import Diagnostic, ValidationResult, validate_config_file

__all__ = [
    "Diagnostic",
    "LoadedConfiguration",
    "ValidationResult",
    "load_configuration",
    "validate_config_file",
]
