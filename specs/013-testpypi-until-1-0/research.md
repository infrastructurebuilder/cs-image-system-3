# Research: Releases go to TestPyPI until 1.0

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Two read-only investigations of 2026-11-23: this repository's and the
reference configuration's tooling, and uv's index rules with the two
families' repositories, tried in throwaway projects against both real
indexes (uv 0.12.18). Paths are repository-relative unless named.

## R1. Where the index is chosen, and what a `test` release proves

`just release <v> [test|pypi]` defaults to `test`
([Justfile](../../Justfile) 108); `scripts/release.py` maps both
(`INDEXES`, 106) and refuses neither. Its probes (`probes()`, 595-660)
run the venv check, the own versions (already per index), the families
released elsewhere (PyPI only), the surfaces and docker for both indexes;
the live configuration, `just preflight` and the session minutes for
`pypi` only (`if index != "pypi": return`, 632). Its gate (`gate()`,
669-694): `pypi` runs `just full-test`, requires the reference's
modification-test evidence and a clean reference; `test` runs `just test`
and `just test-docker-install` only.

**Decision**: the `test` gate is the interim release's lighter check
(FR-002), with the families-released-elsewhere probe asking TestPyPI;
`--full` (new) runs the `pypi` gate and probes against TestPyPI and
records the release as fully proven; `pypi` is refused, naming the
standing decision.

## R2. When a full proof is probably needed (FR-002a)

Nothing records which release was last fully proven.

**Decision**: a fully proven release's annotated tag message carries the
line `fully proven: full-test`; the advisory compares the paths changed
since the newest such tag with a fixed list: the runtimes' and identity
plugins' sources (`packages/*-runtime-plugin`, `packages/docker-plugin`,
`packages/posix-identity-plugin`, `packages/okta-opa-plugin` while it is
here), the release and take tooling (`scripts/release.py`,
`scripts/publish-dist`, `scripts/release-watch`, the take recipe in
`docs/examples/_skeleton/Justfile`), the starters' workflows
(`docs/examples/*/.github/`), the contract (`packages/contract`) and the
SDK (`packages/base`, `packages/hashicorp-utils`, `packages/tofu-roots`).
A match prints `release: a full proof is probably needed: <paths>; run
with --full` before anything changes, and never refuses. The list lives
in one constant beside the advisory.

Added 2026-11-26 (T043, the third convergence): the three scripts of the
release tooling that the full proof alone runs to their end,
`scripts/with-released-families` (the families' overlay under every live
command), `scripts/dev-pin-resolves` and `scripts/session-minutes-left`.
A defect in each of the first two reached a release attempt and was
caught only under `--full`.

## R3. Installing from TestPyPI without taking a squatted name

`uv tool install` has no per-package index option. The form in use since
stage 99 (`--index-url https://test.pypi.org/simple/ --extra-index-url
https://pypi.org/simple/ --index-strategy unsafe-first-match`) asks PyPI
first for every name: **an exact pin** whose version only TestPyPI holds
falls through to TestPyPI (tried: `contract==0.3.0`, and all 49
third-party names of `cs-image-system[all]` from PyPI); **a range** PyPI
can meet takes PyPI's version (tried: `contract>=0.1,<0.4` gave PyPI's
0.1.6, not TestPyPI's 0.3.0). TestPyPI holds stale or foreign copies of
our dependencies (`packaging` 16.7, `typer` 0.0.1, `pydantic` 1.5a1, …),
so TestPyPI-first or best-match would take them. The released umbrella
already pins every workspace package exactly except the contract (a
range) and the families' extras (ranges).

**Decision**: every one of the system's names a released umbrella
depends on is pinned exactly in its metadata: the contract at the
version the tree builds, and each family extra at the newest release
TestPyPI holds inside its range, read at the release (D1). With every
name of ours exact, the PyPI-first form takes each from TestPyPI and
every other from PyPI; it is the one install form, for every version,
not only `.dev`.

## R4. Locks: only the system's names from TestPyPI

In a uv project, `[[tool.uv.index]] name = "testpypi" … explicit = true`
with `<name> = { index = "testpypi" }` pins a direct dependency to
TestPyPI. A **transitive** name listed in `[tool.uv.sources]` alone is
silently ignored (tried: engine, base and contract still locked from
PyPI); it must also be a direct requirement somewhere. A non-default
dependency group (`index-pins`) naming every transitive name, each with
a source entry, pins them all (tried on a copy of the Google Cloud
family: every system name from test.pypi.org, zero third-party names).

**Decision**: each repository lists every one of the system's names it
reaches in `[tool.uv.sources]` with `index = "testpypi"` and, when not a
direct dependency, in an `index-pins` group; a test holds every
`cs-image-system*` registry entry of its `uv.lock` at
`https://test.pypi.org/simple/`. In this repository that is the two
families' names (its own are workspace members).

## R5. Overlays and the isolated runs

`uv run --with=<req>` ignores `[tool.uv.sources]` (tried, with and
without `--no-sync`); only the command-line index options apply.
`scripts/with-released-families` passes the families' ranges as
`--with`. `scripts/isolated-run` reads PyPI's JSON (98-99) for the SDK's
published versions and digests and installs a bare `name==version`.

**Decision**: `with-released-families` emits each family name exactly
(`==` the newest TestPyPI release inside the range, which its `--check`
already computes) with the PyPI-first form; `isolated-run` reads
TestPyPI's JSON and installs its exact pins with the same form;
`dev-pin-resolves` proves the newest release tag, final or `.dev`.

## R6. The families' locks, low ends and publishing

Both families' locks take every system name from PyPI (only `engine` is
reached transitively), and `just init` syncs the committed lock, so CI
tests what was locked. Their low-end leg passes the test kit on the
command line, which a member's source pin does not reach; a
`--group pyproject.toml:index-pins` in its place pins all of them
(tried: every name from TestPyPI at the oldest versions in range). Their
`publish.yml` uploads a final version to PyPI after TestPyPI; their
`scripts/release` accepts `pypi`.

**Decision**: each family pins every system name to TestPyPI (R4); its
low-end leg installs through `--group pyproject.toml:index-pins`; its CI
gains a job that re-locks the system's names to TestPyPI's newest inside
the ranges and runs the acceptance tests on that (FR-004, D2); its
`publish.yml` loses the PyPI job; its release refuses `pypi`.

## R7. This repository's publishing, by trusted publishing (FR-009)

Today `just release` uploads from the operator's machine with a token
before it tags, and CI's `publish` job (in `ci.yml`, inside a
`container:`) uploads a pushed tag with `TEST_PYPI_TOKEN` (and
`PYPI_TOKEN` for a final), one project at a time through
`scripts/publish-dist`. Eighteen projects are published (the root and 17
packages; the dummy and contract-example plugins are private); all exist
on TestPyPI, so each takes a normal publisher. One publisher may serve
many projects; up to 100 publishers a day may be added; a reusable
workflow cannot be a publisher.

**Decision**: a dedicated `.github/workflows/publish.yml` on a pushed
`v*` tag, environment `testpypi`, `id-token: write`, uploading every
public project with `uv publish --trusted-publishing always --index
testpypi`, skipping what the index holds; the release tags and never
uploads; `release-take` waits for the index to list the version
(`scripts/index-knows`, as `release-watch` does) before it takes; the
token secrets and `publish-dist`'s token proof go. The setup for the 18
projects is written down as the families' is.

## R8. The starters and the reference configuration

The starter repositories are pushed by `just publish-starters`, from CI,
only for a final tag (`pypi == 'true'`) with `STARTER_PUSH_TOKEN`; the
recipe refuses `.dev`. Each starter's CI and the reference's install the
pinned release with the TestPyPI form only for a `.dev` pin, so a final
TestPyPI-only pin would fail.

**Decision**: `publish-starters` runs for every release tag, from the
new publish workflow, after the upload; every install line (the take
recipe, every starter's and the reference's CI, `CI_SETUP.md`) uses the
one form of R3 for every version.

## R9. The Okta plugin's copy here

`packages/okta-opa-plugin` (0.1.12) is still a publishable workspace
member while cs-image-system-okta releases the same project on 0.2.x
(specification 008's Phase 4 removes it). Both publishing would split one
project across two lines.

**Decision**: the copy here is marked `Private :: Do Not Upload` now, so
nothing here publishes it again; the `okta` extra moves to the Okta
repository's line with specification 008's T041.

## R10. The documents

About thirty install lines (README, OPERATIONS, DAILY_DRIVER, CI_RUNNER,
PLUGINS, the skeleton's Justfile and CI_SETUP, five starter READMEs, the
code's install hint in `src/cs_image_system/extras.py`) give the PyPI
form; the TestPyPI form appears only for `.dev`.

**Decision**: one section of `docs/OPERATIONS.md` ("Installing a
release") states the one form and TestPyPI's limits (wiped before, rate
limits, outages; what the system does: a lost version is never re-cut,
the next patch replaces it); every other document and the install hint
use the form and link that section.
