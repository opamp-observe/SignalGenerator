# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

# Build context is SignalGenerator-Python with the named `opamp_core` build context.
FROM python:3.11-slim AS wheel-builder

WORKDIR /build
COPY . /build/signal-generator
COPY --from=opamp_core consumer /build/opamp2/consumer
COPY --from=opamp_core shared /build/opamp2/shared
RUN python -m pip wheel --no-cache-dir --no-deps --wheel-dir /wheels /build/opamp2/consumer \
    && python -m pip wheel --no-cache-dir --no-deps --wheel-dir /wheels /build/signal-generator \
    && python -m pip wheel --no-cache-dir --no-deps --wheel-dir /wheels /build/signal-generator/integrations/opamp-simulator

FROM python:3.11-slim AS runtime

ARG BUILD_VERSION=0.1.0
ARG BUILD_REVISION=unknown
ARG BUILD_SOURCE=https://github.com/opamp-observe/SignalGenerator-Python

LABEL org.opencontainers.image.title="SignalGenerator OpAMP simulator adapter" \
    org.opencontainers.image.description="Unified OpAMP consumer simulator and signal replay host" \
    org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.revision="${BUILD_REVISION}" \
    org.opencontainers.image.source="${BUILD_SOURCE}" \
    org.opencontainers.image.licenses="Apache-2.0"

RUN addgroup --system signal-generator \
    && adduser --system --ingroup signal-generator --home /app signal-generator
WORKDIR /app
COPY --from=wheel-builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl "hypercorn>=0.17" "quart>=0.19.4" \
    && rm -rf /wheels
COPY --from=wheel-builder --chown=signal-generator:signal-generator \
    /build/signal-generator/examples /app/examples

ENV APP_ENABLE_DEV_FEATURES=true
USER signal-generator
EXPOSE 9108
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9108/healthz', timeout=2)"]
ENTRYPOINT ["signal-generator-opamp-sim"]
CMD ["unified", "--config", "/app/examples/opamp/unified-config.json"]
