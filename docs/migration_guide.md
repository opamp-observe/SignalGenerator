# Migration from LogGenerator

Convert an existing property file into a versioned candidate:

```text
signal-generator convert-properties --input tool.properties --output config.json
signal-generator validate --config config.json
signal-generator run --config config.json
```

The converter maps the public source, target, timing, default-field, multiline, and custom-output
properties. Unknown keys are warnings by default and errors with `--strict`. Existing output files
are never overwritten unless `--force` is supplied.

Review these changes before replay:

1. Java datetime formats must be within the documented supported subset.
2. Custom Groovy output classes must become installed `signal_generator.log_outputs` entry points.
3. `JUL` becomes `python_logging`; `ERROUT` becomes `stderr`.
4. Relative paths resolve from `config.json`, not the invoking shell's working directory.
5. Network outputs fail closed by default and use bounded timeouts.

See [LogGenerator compatibility](log_compatibility.md) for deliberate behavioral differences.
