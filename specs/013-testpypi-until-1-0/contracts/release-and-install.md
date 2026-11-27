# Contract: releasing and installing until 1.0

**Feature**: [spec.md](../spec.md) | **Research**: [research.md](../research.md)

## This repository's release

| Command | Does |
| --- | --- |
| `just release <part\|version>` | the advisory (R2), said first; then the lighter check (`just test`, the quickstart page's own commands `just test-quickstart` since specification 002, the version, surface and families-released-elsewhere probes against TestPyPI), the bump, the families pinned (D1), the commit and the tag, then its own pushes: the release branch and the tag `v<version>` by name, then `develop`; uploads nothing |
| `just release <part\|version> --full` | the same without the advisory, and with the full proof in place of the lighter check (`just full-test`, the reference's session probes and evidence); its tag says `fully proven: full-test` |
| `just release <...> pypi` | refused, naming the standing decision; nothing changes |
| the tag's push (the release's own, above; never a second `git push` by hand) | the publish workflow builds the tag, runs the quickstart page's own commands against the built files (specification 002), then uploads every public project to TestPyPI; for a final version alone it then pushes the starter repositories (a `.dev` release pushes none: FR-006 dropped) |
| `just release-take <part\|version>` | the release as above, a wait for TestPyPI to list the version, then the take into the reference |

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
One case differs: a pinned version both indexes hold, a release from
before the decision such as the families' 0.2.1, comes from PyPI, which
the form asks first for each name. It is the same release, the same
files, and `scripts/dev-pin-resolves` accepts PyPI's copy only when
TestPyPI holds that version with exactly those files (FR-003).

## Lifting the decision at 1.0

One change per repository, named in `docs/OPERATIONS.md` (this
repository) and `docs/RELEASING.md` (each family). Here: restore the
`pypi` index in the release script, the PyPI job in the publish
workflow, and the PyPI form of the install lines, in every place the
guide's one search lists. In each family: the release script's
refusal, the PyPI job in its publish workflow, and the system's names
taken from PyPI again in its lock (the `testpypi` sources and the
`index-pins` group removed).
