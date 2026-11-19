# Research: The Google Cloud provider in a repository of its own

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each decision is marked with what it rests on: **read** (seen in the
code or on the index on 2026-11-19), **decided** (the operator's answer
in the spec's Clarifications), or **chosen** (this plan's choice, with
the alternatives).

## R1. The order of work across two repositories and two releases

**Decision** (**chosen**): four phases, each finished before the next.

1. **Here, prepare.** The family is made ready to leave while it is
   still in this workspace: its SDK pins become ranges, its test stubs
   move out of this repository's shared harness into the family's own
   package, and the test kit gains what an outside repository needs
   (R6). This repository then **releases**, so the SDK the family will
   range on exists on the index.
2. **There, stand alone.** The family's files are carried, with their
   history, into `cs-image-system-google-cloud` (R4). Its own tests,
   fixture and golden are built there (R5, R7), against the SDK and
   the test kit from the index. The family **releases** on its own
   version line (R8).
3. **Here, remove.** The three packages, their tests and their parts
   of the shared suite leave this repository (R9, R10); the umbrella's
   `gcloud` and `all` extras name the family by a range on its
   release (R8). This repository **releases** again.
4. **The reference.** The reference configuration takes that release;
   its drift check exits 0 (R12).

**Rests on** (**read**): none of the SDK at its current versions is
published. The index holds `cs-image-system-contract` up to 0.4.2 and
`cs-image-system-base`, `-hashicorp-utils` and `-tofu-roots` up to
0.1.10; this workspace is at contract 0.5.0 and the three SDK libraries
at 0.2.0 (specs 001 and 004, unreleased). `cs-image-system-docker-plugin`
is not published either. The family cannot pass its bar against
published releases (FR-002) until phase 1's release exists.

**Alternatives considered**:
- *Point the family's repository at a sibling checkout of this one
  while it is built* (`[tool.uv.sources]` path entries). Rejected as
  the finished state: FR-002 needs published releases, and a path
  source is exactly the hidden coupling the move removes. Allowed only
  while phase 2 is in progress, if phase 1's release is late; never
  committed on the family's `develop`.
- *Remove the family here first, then build it there.* Rejected: this
  repository's `develop` would install no Google Cloud for a time, the
  reference configuration could not take a release, and the golden the
  family must reproduce (R7) would exist only in history.

## R2. The phases are this specification's, the releases are the operator's

**Decision** (**chosen**): the two releases of this repository (phases
1 and 3) and the family's first release (phase 2) are cut by the
operator with the existing release walk (`just release` on `main`,
`just release-take`, `just release-watch`). The tasks stop before each
and record what the release must carry.

**Rests on** (**read**): releases publish to PyPI, which is outward-
facing and irreversible (a deleted version is never cut again); the
release walk is the operator's.

## R3. What the family is

**Decision** (**read**): three distributions that release together.

| Distribution | Import package | Entry points | Package data |
| --- | --- | --- | --- |
| `cs-image-system-gcloud-runtime-plugin` | `cs_image_system.gcloud_runtime` | runtime `gcloud`; bootstrap `gcp`; modules | `tfmodules/` (5 modules, 19 files), `data/image-sources.yml` |
| `cs-image-system-tf-gcp-plugin` | `cs_image_system.tf_gcp_plugin` | instance `tf-gcp-plugin` | none (its modules are the runtime's) |
| `cs-image-system-gcs-state-plugin` | `cs_image_system.gcs_state_plugin` | state `gcs_state_plugin` | none |

`tf-gcp-plugin` imports `gcloud_runtime` (three edges, held by
`tests/test_import_closure.py`); that edge stays inside the family.
Source: 30 Python files, 3,030 lines. Their own tests: 26, in 472
lines.

Names, import packages and entry points do not change, so the
namespaces derived from the distribution names (`gcloud-runtime`,
`tf-gcp`, `gcs-state`) stay, and a configuration that wrote a
qualified word loads as before (spec edge case).

**Alternatives considered**: *merge the three into one distribution,
as spec 001 did for docker.* Rejected: the names are on the index with
ten releases each, the reference configuration installs them, and a
rename moves every qualified word. The family releases the three
together instead (R8).

## R4. History is carried by a filtered clone, merged once

**Decision** (**chosen**): in a fresh clone of this repository,
`git filter-repo` keeps only the family's paths (the three package
directories and the test files that move with them, R7), renaming the
moved test files to their place in the family's layout; the result is
merged once into the family repository's `develop` with
`--allow-unrelated-histories`. This repository's own history is not
rewritten; its removal (phase 3) is an ordinary commit.

**Rests on** (**read**): the destination's `develop` holds one commit
(`ddb3533`, LICENSE and README) on the remote; an unpushed local
`master` (`38c4bf5`, a `.gitignore` and two stub documents) and an
uncommitted `pyproject.toml` are the operator's draft (spec
assumption), taken as a starting point and replaced where stale (it
pins `cs-image-system-contract==0.1.7.dev1` and lists packages the
family does not have).

**Alternatives considered**:
- *`git subtree split`* per package. Rejected: three prefixes and the
  moved tests need one history, which `filter-repo` gives in one pass.
- *Copy the files, no history.* Rejected by FR-005.

## R5. The family's repository layout

**Decision** (**chosen**): a uv workspace of the three packages, with
the family's shared suite at the repository root.

```text
cs-image-system-google-cloud/
├── pyproject.toml          # the workspace; dev group; no published umbrella
├── Justfile                # init, build, test, full-test, release (+ golden-regen, surface-check)
├── packages/
│   ├── gcloud-runtime-plugin/   # src/, tests/ (its unit tests), README.md
│   ├── tf-gcp-plugin/
│   └── gcs-state-plugin/
├── tests/
│   ├── fixture/            # the family's configuration (R7)
│   ├── golden/             # its emission (R7)
│   ├── pipeline/           # tests that drive the pipeline with the test kit
│   └── live/               # the cycle tests that need a GCP session; never in `just test`
├── docs/                   # what the family's READMEs link to beyond themselves
└── .github/workflows/ci.yml
```

The root manifest publishes nothing: the skeleton's metadata-only
umbrella `cs-image-system-google-cloud` and its console script are
dropped, since the system's own `gcloud` extra is how an operator
installs the family (FR-009, decided).

**Alternatives considered**: *the fixture and golden inside the
runtime package, as docker keeps them.* Rejected: docker is one
distribution; here the suite spans three, and a root `tests/` keeps it
out of any one package's wheel.

## R6. What the family's tests take from the index

**Decision** (**chosen**): the family's tests are written against the
test kit `cs_image_system.system.testing`, installed from the index as
`cs-image-system-system[testing]`, as docker's are. The kit already
gives `Run`, `copy_fixture`, `stub_core`, `emitted`, `assert_matches`,
`write`, `broken_neighbour` and the isolation fixture (**read**). Two
things are added to it in phase 1:

1. **A strict session** (`cs_image_system.system.testing.strict`, a
   pytest plugin): a session that collects zero tests, or skips any,
   fails, with the same verdict `scripts/isolated-run` gives. Here it
   is `isolated-run`'s rule; there it is the family's bar's. One
   source: `isolated-run` reads the verdict from the same module.
2. **Nothing else, unless phase 2 finds a gap.** Whatever the family's
   tests need that the kit lacks is added here, in phase 1, and
   released, rather than copied there.

The family's Google Cloud stubs (today `tests/harness.py`'s `_clouds()`,
lines 183-232: the network map, provider-image and image queries, the
session command and the retag) move into
`cs_image_system.gcloud_runtime.testing`, a module of the family's own
package, exported as docker's `docker_runtime.testing` is, and handed
to the kit as a stub function.

**Rests on** (**read**): docker's pipeline tests take
`kit.Run(tmp_path, monkeypatch, fixture=..., stubs=(docker_testing.stub,
roots_testing.stub))`; the kit names no provider.

**Alternatives considered**:
- *Copy `scripts/isolated-run` into the family's repository.* Rejected:
  it builds every wheel of one workspace and refuses anything of ours
  from the index (its stray check), so it would need a rewrite, and two
  copies of the verdict drift (Constitution VIII). The family's
  isolation is its fresh clone and its locked environment from the
  index; the strict session is the part worth sharing.
- *A separate test-kit distribution.* Rejected in spec 001 (research
  R2) and again here: the kit's home is `cs-image-system-system`.

## R7. The family's fixture and golden reproduce the shared suite's Google Cloud emission

**Decision** (**chosen**): the family's fixture is the Google Cloud part
of today's shared fixture, and its golden is what the family emits for
it. Before phase 3 removes anything, the two are compared file by file.

- **The declarations** (**read**): five wholly-GCP fixture files
  (`cfg/state-gcm.yml`, `storages/gce.yaml`, three `overlays/gce-cycle-*`)
  and the GCP blocks of eleven mixed files (the `gcloud-east1` runtime,
  `pckr-gce-ans`, `tofu-gce`, `gcp-pd`, `gcp-gcs`, the `gcp-my-rh10`
  OS entry and base image, the image's GCE runtime entry, `gce-test`,
  `gcloud` in executables).
- **The state backend** (**decided** by the operator, 2026-11-19: "bind
  GCE to gcs"): today the GCE roots keep their state in the AWS
  family's S3 backend. The family's fixture binds them to its own `gcs`
  backend instead, which the shared fixture declares but binds to
  nothing. Every other declaration is unchanged. The reference
  configuration is not affected: its GCE roots stay on S3.
- **The golden** (**read**): 31 files in the GCE roots' own directories
  (`base-image/pckr-gce-ans`, `instance-image/pckr-gce-ans`,
  `instance-image/tofu-gce`, `storage/gcp-gcs`, `storage/gcp-pd`) and
  the GCE lines of 6 shared files (the three run scripts and three
  meta-state files).
- **The comparison** (FR-008, SC-005): each of the 31 files in the
  family's golden is compared with the shared golden's file of the same
  path, and each of the 6 shared files' GCE lines with the family's
  lines; every difference is read and must be a consequence of the
  state backend (the backend block of a root, its `state-locations`
  entry). The comparison, with its result, is a record in `tasks.md`.

**Alternatives considered**:
- *Keep the S3 backend, with the AWS family's state plugin as a test
  dependency of the Google Cloud family.* Rejected: it makes one
  provider family's tests depend on another's release (Constitution
  VI), and the AWS family is the next to leave. It would give a
  byte-identical golden; the price is the coupling the move removes.
- *The core's `local` backend.* Rejected: the family has a backend of
  its own that no pipeline test drives today; binding the roots to it
  gains that proof at no cost.

## R8. Versions and how an operator installs the family

**Decision** (**decided** for the extras; **chosen** for the numbers):

- The family takes a version line of its own, starting at **0.2.0**:
  above every version the index holds (0.1.10 is the newest), and the
  middle number marks the line as the family's own. The three
  distributions release together, under one number; `tf-gcp-plugin`
  pins `gcloud-runtime-plugin` exactly at that number, as it does
  today.
- The family's ranges: `cs-image-system-contract>=0.5,<0.6`,
  `cs-image-system-base>=0.2,<0.3`, `cs-image-system-hashicorp-utils>=0.2,<0.3`,
  `cs-image-system-tofu-roots>=0.2,<0.3` (tf-gcp only); its `test`
  extra names `cs-image-system-system[testing]` by a range starting at
  phase 1's release, and the core plugins its fixture declares (packer,
  ansible, bash-mod, default-os, posix-identity, local-state) likewise.
- The umbrella's `gcloud` and `all` extras name the three by
  `>=0.2,<0.3` (**decided**: kept, by a range). They are ranges, so the
  workspace bump's `=={current_version}` rule never moves them.

**Rests on** (**read**): `scripts/release.py`, `publish-dist` and
`publish-target-ready` glob `packages/*/pyproject.toml`; once the
directories leave, nothing here builds, probes or uploads the family
(FR-011) without a change to the tooling.

## R9. This repository's tests: what leaves, what is re-hosted, what is trimmed

**Decision** (**chosen**), by the inventory of 2026-11-19 (**read**: 81
of 172 top-level test files name the family's words, and every test
that uses `tests/harness.py` needs the family installed, because the
harness imports it unconditionally):

| Class | Files | Tests | What happens |
| --- | --- | --- | --- |
| The family's own package tests | 3 packages | 26 | Move with the packages. `test_gcs_backend.py` loses its use of the AWS state plugin; `test_gcp_only_storage.py` moves off `tests/harness.py` onto the test kit |
| Google Cloud only | 4 | 59 | Move to the family's `tests/` (R4 carries their history): `test_gcp_runtime`, `test_gce_cycle`, `test_bootstrap_gcp`, `test_mount_verification` |
| A core behaviour through GCE | 13 | 102 | **Re-hosted here** on the AWS runtime of the shared fixture (or docker where the behaviour is a container's), keeping what each asserts; a GCE-specific assertion among them moves to the family |
| Mixed | 50 | 604 | The Google Cloud part is removed here; where it proves the family's behaviour it is carried to the family, else dropped with a reason |
| In passing | 14 | 102 | Corrected where the mention becomes false |

Helpers other files import from Google Cloud test modules are moved to
where their users are first (`private_plugin_cache` from
`test_gcp_runtime.py`; `_facts`, `_project`, `_tree` from
`test_bootstrap_gcp.py`; `GCE_RT` and `_seed_converged` from
`test_convergent_bakes.py`; `stub_networks_from` in
`test_docs_examples.py`).

`tests/harness.py` loses its Google Cloud stubs (R6); `tests/conftest.py`
keeps its credential isolation (it names an environment variable, not
the family).

**Alternatives considered**: *move the 13 re-hostable files to the
family.* Rejected: they test the core (bakes, fingerprints, retention,
decommission, detach, ephemeral runs, runtime facts); with GCE gone
here they would prove the core only from another repository, and the
core's bar would stop guarding them (Constitution VI cuts both ways).

## R10. The shared suite after the move

**Decision** (**decided**): the shared fixture keeps AWS and docker;
its Google Cloud declarations leave (R7). The golden loses its 31 GCE
files and the GCE lines of 6 shared files, and every one of those
changes is read file by file (Constitution IV), with the record in
`tasks.md`. No other golden file may move.

## R11. Starters

**Decision** (**chosen**): the starters stay where they are, in the
system's data, so `init-config --from standard-gce` and
`--from complete` work as before for an adopting team (spec story 3).

- **Here**, a test that renders every starter renders the ones whose
  `type:` words this workspace's plugins register, selected by what
  each starter declares (the rule `src/cs_image_system/extras.py`
  already applies), not by a skip.
- **There**, the family's bar renders `standard-gce`, validates it and
  dry-runs it with the system from the index and the family from its
  checkout (spec story 3, scenario 4).
- `complete`, which declares every provider, is rendered and dry-run
  in the family's `full-test` with the AWS and docker families from
  the index.
- `just publish-starters` (this repository, on a final release) writes
  each starter's modules from the installed plugins, so its CI step
  installs the family by the `gcloud` extra from the index, as an
  operator does.

**Alternatives considered**: *a starter entry-point group, so the
family ships `standard-gce` itself.* Rejected for this specification:
it is a contract addition (its middle number, every range again) for a
problem the selection rule already solves. A later specification may
take it when a second family leaves.

## R12. The reference configuration and the live cost

**Decision** (**chosen**):
- The reference configuration installs `cs-image-system[aws,gcloud,docker,okta]`
  by its one pin (`.csis-version`), as now (**read**: `just extras`
  maps its `type:` words to extras). The family's version floats within
  the extra's range; its drift check (`just cli config-drift`) is the
  proof that nothing moved (SC-003), and the materialised modules'
  stamps (`plugin:`, `release:`) are refreshed by its own
  `init-config --force`.
- **No live Google Cloud cycle by default** (SC-006, Constitution
  "Google Cloud spending"): the family's code does not change, and the
  drift check over the reference compares the full emission. One GCE
  cycle from the family's repository is the operator's decision, after
  phase 2, and is torn down.

**Rests on** (**read**): the reference's CI keeps GCE out of its
`perform` job by cost (`GUARD_RUNTIME: gcloud-east1`); this
repository's `fixture-live` asks Google Cloud only to validate the
frozen fixture's network (`validate --online`), which leaves with the
fixture's GCP declarations, together with the two workflows' GCP
identity steps.

## R13. What stays here that names Google Cloud

**Decision** (**read**, kept):
- `src/cs_image_system/extras.py`: the umbrella's table of which extra
  installs which words. It is the umbrella's own data.
- The packer plugin's `packer-gce` type word and `PackerGceImageBuilder`:
  the core's packer plugin, not the family's.
- `ci/runner-image`: the CI image every configuration's CI runs in
  carries the `gcloud` tool; the reference needs it.
- History documents (`docs/CHANGES.md`, `docs/INCIDENTS.md`) keep what
  they say; their links into the family's files are pointed at the
  family's repository.
- The guard regex of `tests/test_core_names_no_runtime.py`, which
  keeps the core from naming any runtime.
