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

RUN addgroup --system signal-generator \
    && adduser --system --ingroup signal-generator --home /app signal-generator
WORKDIR /app
COPY --from=wheel-builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/signal_generator-*.whl \
    && rm -rf /wheels
COPY --chown=signal-generator:signal-generator examples ./examples

USER signal-generator
EXPOSE 9108
ENTRYPOINT ["signal-generator"]
CMD ["run", "--config", "/app/examples/metrics/container-config.json"]
