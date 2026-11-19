# Contract: the test kit's strict session

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R6

An addition to `cs_image_system.system.testing`, released in phase 1,
for any repository that tests a provider against the published kit.

## Using it

```toml
[tool.pytest.ini_options]
addopts = "-p cs_image_system.system.testing.strict"
```

## What it does

At the end of a session it fails the run, with exit status 1 and one
line naming why, when:

| Condition | Line |
| --- | --- |
| No test was collected | `strict: no test was collected; the tests did not run` |
| Any test was skipped | `strict: <n> skipped; a skipped check is a failed check` |

A session with failures already fails; the plugin adds nothing to it.

## One source

`scripts/isolated-run` reads its verdict from the same module, so the
two cannot disagree.
