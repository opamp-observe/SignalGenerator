# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Verify pull sequencing and real Pushgateway interoperability for the metrics profile."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

PULL_URL = "http://127.0.0.1:19108/metrics"
HEALTH_URL = "http://127.0.0.1:19108/healthz"
PUSHGATEWAY_URL = "http://127.0.0.1:19091/metrics"
MAXIMUM_ATTEMPTS = 30


def _read(url: str) -> str:
    """Read one local container endpoint with a bounded timeout."""

    with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 - fixed local URLs
        return response.read().decode()


def _wait_for(url: str, expected: str) -> str:
    """Poll a container endpoint until its expected content is observable."""

    for _attempt in range(MAXIMUM_ATTEMPTS):
        try:
            payload = _read(url)
            if expected in payload:
                return payload
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError(f"timed out waiting for {expected!r} at {url}")


def main() -> None:
    """Assert non-consuming health, advancing pull, and delivered pushed metrics."""

    _wait_for(HEALTH_URL, "healthy")
    first_pull = _wait_for(PULL_URL, "nginx_connections_active")
    second_pull = _read(PULL_URL)
    if first_pull == second_pull:
        raise RuntimeError("successive pull scrapes did not advance the NGINX frame")
    pushed = _wait_for(PUSHGATEWAY_URL, "nginx_http_requests_total")
    if 'job="nginx_replay"' not in pushed or 'instance="demo-nginx"' not in pushed:
        raise RuntimeError("Pushgateway grouping labels were not applied")
    print("metrics container verification passed")


if __name__ == "__main__":
    main()
