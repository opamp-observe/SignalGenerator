# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Verify phase 5 pull, push, and unified Compose profiles through public endpoints."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request

MAXIMUM_ATTEMPTS = 40


def _read(url: str) -> str:
    """Read one fixed local demo URL with a bounded timeout."""

    with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 - local demo only.
        return response.read().decode()


def _wait(url: str, expected: str) -> str:
    """Poll until the endpoint contains the expected stable marker."""

    for _attempt in range(MAXIMUM_ATTEMPTS):
        try:
            payload = _read(url)
            if expected in payload:
                return payload
        except (TimeoutError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise RuntimeError(f"timed out waiting for {expected!r} at {url}")


def _verify_prometheus(port: int) -> None:
    """Assert Prometheus has ingested the replayed NGINX series."""

    query = urllib.parse.quote("nginx_connections_active")
    url = f"http://127.0.0.1:{port}/api/v1/query?query={query}"
    for _attempt in range(MAXIMUM_ATTEMPTS):
        try:
            payload = json.loads(_read(url))
            if payload["status"] == "success" and payload["data"]["result"]:
                return
        except (KeyError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            pass
        time.sleep(1)
    raise RuntimeError("Prometheus query did not return nginx_connections_active")


def main() -> None:
    """Dispatch verification for one independently startable Compose profile."""

    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=("pull", "push", "unified"))
    arguments = parser.parse_args()
    if arguments.profile == "pull":
        _wait("http://127.0.0.1:19108/healthz", "healthy")
        _verify_prometheus(19090)
    elif arguments.profile == "push":
        payload = _wait("http://127.0.0.1:19091/metrics", "nginx_http_requests_total")
        if 'job="nginx_replay"' not in payload:
            raise RuntimeError("Pushgateway did not retain the replay job labels")
    else:
        _wait("http://127.0.0.1:19110/healthz", '"running":true')
        _wait("http://127.0.0.1:19110/api/simulator/instances", '"nginx-a"')
        _verify_prometheus(19092)
    print(f"phase 5 {arguments.profile} verification passed")


if __name__ == "__main__":
    main()
