# LogGenerator compatibility

Phase 2 implements the original public token vocabulary `%t`, `%m`, `%l`, `%p`, `%c`, `%i`, and
`%j`, relative `+N` millisecond delays, absolute timestamps, repeats, acceleration, multiline
grouping, and the file, HTTP, TCP, standard stream, and logging output families described by the
[original LogGenerator documentation](https://github.com/mp3monster/LogGenerator/blob/master/docs/readme.md).

Deliberate differences are:

- Configuration is versioned JSON; legacy properties are converted explicitly before use.
- Python logging replaces Java Util Logging while preserving the configured formatted payload.
- Custom outputs use installed Python entry points instead of arbitrary class or filesystem loading.
- HTTP requests have bounded timeouts, reject implicit redirects, and fail on non-success status.
- TCP and HTTP work is asynchronous and participates in deterministic shutdown.
- Unknown properties and unsupported Java datetime patterns fail validation instead of being
  silently ignored.
- Output failures use explicit `fail`, `retry`, or `continue` policies.

Metric replay, HTTP health endpoints, and containers belong to later implementation phases and are
not implied by the Phase 2 runtime.
