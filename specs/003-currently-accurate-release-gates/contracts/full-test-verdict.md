# Contract: the full test run's verdict

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R2 to R6

What `just full-test` and `just full-test-legs` accept and what they
say. The leg table and the prerequisites are in
[data-model.md](../data-model.md); `just full-test-legs list` prints
the table from its one source.

## Invocation

```text
just full-test [without=<name>[,<name>...]] ...
just full-test-legs [without=<name>[,<name>...]] ...
just full-test-legs list
```

`full-test` runs `just test` first and then the legs with the same
words. A `<name>` is a leg's name or `docker` or `reference`.

| Words | Exit | Last line |
| --- | --- | --- |
| a name that is neither a leg nor a prerequisite | 2, before any leg | `full-test: '<name>' is not a leg or a prerequisite (just full-test-legs list) -- nothing ran` |
| `list` | 0 | the table's last row |

## Lines

One line before each leg, as today (`full-test: <what it proves> (<leg>)`).
Then, at the end, in this order:

| When | Line |
| --- | --- |
| a leg failed | `full-test: FAILED <leg>` |
| a prerequisite is absent and its legs were not excluded | `full-test: DID NOT RUN <leg>, <leg> -- <cause>; without=<prerequisite> leaves them out` |
| legs were excluded | `full-test: EXCLUDED on request (without=<names>): <leg>, <leg>` |
| the last line, always | one of the three below |

```text
full-test: passed -- <run> run, 0 excluded, 0 failed
full-test: passed WITH EXCLUSIONS -- <run> run, <excluded> excluded on request, 0 failed
full-test: FAILED -- <run> run, <excluded> excluded on request, <failed> failed
```

The causes are: `docker is not available (docker info)`, `<tool> is not
on PATH`, `no reference configuration at <config_root> (just
config-guard)`, `a runtime session is absent or expired (just preflight
names the command)`, `<variable> is not set or is empty (the identity
roots' credentials)`.

## Exit status

| Result | Exit |
| --- | --- |
| `passed` | 0 |
| `passed WITH EXCLUSIONS` | 0 |
| `FAILED` | 1 |
| a refused word | 2 |

## What never happens

- No line says `SKIPPED`.
- No environment variable, file or absent tool removes a leg from the
  count: a leg is run, excluded by a word of this command, or failed.
- A pytest leg that skips a test fails (the strict session).
