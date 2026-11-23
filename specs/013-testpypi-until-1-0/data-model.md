# Data model: Releases go to TestPyPI until 1.0

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

Nothing new is stored in a configuration tree. Three facts change shape.

## The index pins (each repository's `pyproject.toml`)

| Field | Rule | Source |
| --- | --- | --- |
| `[[tool.uv.index]] testpypi` | `explicit = true`: used only by the names that name it | R4 |
| `[tool.uv.sources] <name> = { index = "testpypi" }` | every one of the system's names the repository reaches and does not build | R4 |
| `[dependency-groups] index-pins` | every such name that is not already a direct dependency, by its range | R4 |
| `uv.lock` | every `cs-image-system*` registry entry at `https://test.pypi.org/simple/` | R4 |

## A released umbrella's metadata

| Dependency | Pin | Source |
| --- | --- | --- |
| every workspace package | `==` the tree's version (as today) | R3 |
| the contract | `==` the tree's version (was a range) | R3, D1 |
| each family extra | `==` the newest release TestPyPI holds inside the extra's range, read at the release | R3, D1 |

## A release's record

| Field | Where | Rule | Source |
| --- | --- | --- | --- |
| `fully proven: full-test` | the annotated tag's message | present only on a release run with `--full`; the advisory measures from the newest tag that carries it | R2 |
