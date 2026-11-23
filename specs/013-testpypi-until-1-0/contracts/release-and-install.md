# Contract: releasing and installing until 1.0

**Feature**: [spec.md](../spec.md) | **Research**: [research.md](../research.md)

## This repository's release

| Command | Does |
| --- | --- |
| `just release <part\|version>` | the lighter check (`just test`, the install check, the version, surface and families-released-elsewhere probes against TestPyPI), the advisory (R2), the bump, the commit and the tag; uploads nothing |
| `just release <part\|version> --full` | the same, with the full proof in place of the lighter check (`just full-test`, the reference's session probes and evidence); its tag says `fully proven: full-test` |
| `just release <...> pypi` | refused, naming the standing decision; nothing changes |
| `git push origin main v<version>` | the publish workflow uploads every public project to TestPyPI, then pushes the starter repositories |
| `just release-take <version>` | waits for TestPyPI to list the version, then takes it into the reference |

## The families' releases

`just release <part|version>` as today, defaulting to `test`; `pypi` is
refused; the tag's push uploads to TestPyPI only.

## The one install form

```sh
uv tool install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ --index-strategy unsafe-first-match \
  'cs-image-system[<extras>]==<version>'
```

Every one of the system's names in the umbrella's metadata is exact
(data-model), so each comes from TestPyPI and every other name from PyPI.

## Lifting the decision at 1.0

One change per repository, named in `docs/OPERATIONS.md` (this
repository) and `docs/RELEASING.md` (each family): restore the `pypi`
index in the release script, the PyPI job in the publish workflow, and
the PyPI form of the install lines.
