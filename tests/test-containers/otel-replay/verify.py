# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Verify synchronized metrics and two trace cycles reached the file-backed receiver."""

from __future__ import annotations

import json
import time
import urllib.request

RECEIPTS_URL = "http://127.0.0.1:14318/receipts"


def _receipts() -> list[dict]:
    """Read every currently persisted receiver summary."""

    with urllib.request.urlopen(RECEIPTS_URL, timeout=3) as response:  # noqa: S310
        return [json.loads(line) for line in response.read().decode().splitlines()]


def main() -> None:
    """Wait for both signals, then prove timestamp shifting and loop identity renewal."""

    receipts: list[dict] = []
    for _attempt in range(30):
        receipts = _receipts()
        traces = [item for item in receipts if item["signal"] == "traces"]
        metrics = [item for item in receipts if item["signal"] == "metrics"]
        if len(traces) >= 4 and len(metrics) >= 2:
            break
        time.sleep(1)
    else:
        raise RuntimeError("timed out waiting for synchronized metric and trace receipts")
    traces = [item for item in receipts if item["signal"] == "traces"][:4]
    cycle_one_ids = {trace_id for item in traces[:2] for trace_id in item["trace_ids"]}
    cycle_two_ids = {trace_id for item in traces[2:4] for trace_id in item["trace_ids"]}
    if len(cycle_one_ids) != 1 or len(cycle_two_ids) != 1 or cycle_one_ids == cycle_two_ids:
        raise RuntimeError("trace IDs were not consistent within and renewed between loops")
    if any(
        abs(item["received_at_unix_nano"] - item["starts"][0]) > 5_000_000_000
        for item in traces
    ):
        raise RuntimeError("trace timestamps were not shifted near receiver time")
    if not any("synchronized_fixture" in item["body"] for item in metrics):
        raise RuntimeError("metric replay did not reach the dummy receiver")
    print("synchronized metrics and looping traces container verification passed")


if __name__ == "__main__":
    main()

