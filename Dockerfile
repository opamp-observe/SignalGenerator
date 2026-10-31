# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

FROM python:3.11-slim AS wheel-builder

WORKDIR /build
COPY pyproject.toml README.md license.txt ./
COPY src ./src
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.11-slim AS runtime

ARG BUILD_VERSION=0.1.0
ARG BUILD_REVISION=unknown
ARG BUILD_SOURCE=https://github.com/opamp-observe/SignalGenerator-Python

LABEL org.opencontainers.image.title="SignalGenerator Python" \
    org.opencontainers.image.description="Deterministic log and Prometheus metric replay" \
    org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.revision="${BUILD_REVISION}" \
    org.opencontainers.image.source="${BUILD_SOURCE}" \
    org.opencontainers.image.licenses="Apache-2.0"

RUN addgroup --system signal-generator \
    && adduser --system --ingroup signal-generator --home /app signal-generator
WORKDIR /app
COPY --from=wheel-builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/signal_generator-*.whl \
    && rm -rf /wheels
COPY --chown=signal-generator:signal-generator examples ./examples

USER signal-generator
EXPOSE 9108
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9108/healthz', timeout=2)"]
ENTRYPOINT ["signal-generator"]
CMD ["run", "--config", "/app/examples/metrics/container-config.json"]
