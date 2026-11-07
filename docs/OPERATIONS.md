# Operations

How to run cs-image-system and how to work on it. The first half describes
a run and the operator's cycles; the second half the developer's bar, CI,
and the rules. The [Justfile](../Justfile) and the CLI
([cli.py](../packages/system/src/cs_image_system/system/cli.py)) are the
authority; when this text and they disagree, they win. The operator's
half has been walked from nothing, step by step, against a released
system, so every recipe in it is one that has run. The stage index is
[CHANGES.md](CHANGES.md); the incidents are [INCIDENTS.md](INCIDENTS.md);
the vocabulary is [GLOSSARY.md](GLOSSARY.md).

Two trees matter everywhere below:

- **The live configuration** is its own repository,
  `cs-image-system-testconfig`, checked out beside this one. The Justfile
  reaches it at `../cs-image-system-testconfig`; `CSIS_CONFIG_ROOT`
  overrides. It stands alone: its `module_source_base` is its own
  `tfmodules`, a directory `init-config` writes into it from the release,
  so nothing in it reaches into this checkout. The side-by-side layout
  serves this repository's own proofs (`just cli ...`, `full-test`'s copy
  legs), not the configuration.
- **The frozen fixture** under
  [tests/fixtures/config/](../tests/fixtures/config/README.md) is owned by
  the tests. Nothing under `tests/` reads the live tree
  (`tests/test_fixture_independence.py` enforces it), and no run ever
  commits into the fixture. Its people are synthetic personas on example
  domains.

**Contents**

- [1. What a run is](#1-what-a-run-is)
  - [The command](#the-command)
  - [Lifecycles](#lifecycles)
  - [Phases and hooks](#phases-and-hooks)
  - [Generation versus finalization](#generation-versus-finalization)
  - [Dry run and real run](#dry-run-and-real-run)
  - [The runner scripts](#the-runner-scripts)
  - [The apply gate](#the-apply-gate)
  - [Scoping a run](#scoping-a-run)
  - [Transient declarations](#transient-declarations)
  - [When an image bakes](#when-an-image-bakes)
  - [How an image is named](#how-an-image-is-named)
  - [Where a vendor image comes from](#where-a-vendor-image-comes-from)
  - [When a bake fails](#when-a-bake-fails)
  - [Parent and image policies](#parent-and-image-policies)
  - [The power state belongs to the operator](#the-power-state-belongs-to-the-operator)
  - [A canonical hostname is claimed once](#a-canonical-hostname-is-claimed-once)
  - [What a machine answers to](#what-a-machine-answers-to)
  - [Instance generations](#instance-generations)
  - [CI logs in through the policy the system manages](#ci-logs-in-through-the-policy-the-system-manages)
  - [A model image, end to end: the second release](#a-model-image-end-to-end-the-second-release)
  - [Resizing a durable instance in place](#resizing-a-durable-instance-in-place)
  - [Replacing a durable instance: decommission and redeclare](#replacing-a-durable-instance-decommission-and-redeclare)
  - [A pool of names, each spent once](#a-pool-of-names-each-spent-once)
  - [Ephemeral instances](#ephemeral-instances)
  - [Post-bake tests and releases](#post-bake-tests-and-releases)
  - [Retention and disposal](#retention-and-disposal)
  - [Storages](#storages)
  - [`--commit`](#--commit)
  - [Meta-state (`<config root>/meta-state/`)](#meta-state-config-rootmeta-state)
  - [Where state lives](#where-state-lives)
  - [Run outputs and exit codes](#run-outputs-and-exit-codes)
  - [The state query](#the-state-query)
- [2. The developer workflow](#2-the-developer-workflow)
  - [Setting up](#setting-up)
  - [The bar: `just test`](#the-bar-just-test)
  - [`just full-test`](#just-full-test)
  - [The golden](#the-golden)
  - [What a run's log shows of the commands it ran](#what-a-runs-log-shows-of-the-commands-it-ran)
  - [`config-drift` and `fixture-live`](#config-drift-and-fixture-live)
  - [Public-safe and the hook](#public-safe-and-the-hook)
  - [The frozen fixture and the reference configuration](#the-frozen-fixture-and-the-reference-configuration)
  - [Branches](#branches)
  - [`just build`, `just release`, `just publish`, `just publish-tree`](#just-build-just-release-just-publish-just-publish-tree)
  - [Installing a release](#installing-a-release)
  - [The modification tests](#the-modification-tests)
  - [Writing a plugin](#writing-a-plugin)
  - [Recipe catalogue](#recipe-catalogue)
- [3. CI](#3-ci)
  - [The bootstrap: what CI needs, as terraform from an interview](#the-bootstrap-what-ci-needs-as-terraform-from-an-interview)
  - [This repository: the `verify` job](#this-repository-the-verify-job)
  - [This repository: the `live` job](#this-repository-the-live-job)
  - [This repository: the `publish` job](#this-repository-the-publish-job)
  - [A configuration repository: the `verify` job](#a-configuration-repository-the-verify-job)
  - [A configuration repository: the `live` job](#a-configuration-repository-the-live-job)
  - [A configuration repository: the `perform` job](#a-configuration-repository-the-perform-job)
  - [A configuration repository: the workload probe](#a-configuration-repository-the-workload-probe)
  - [The `[noaa]` profile shim](#the-noaa-profile-shim)
  - [Repository secrets](#repository-secrets)
- [4. The operator's cycles](#4-the-operators-cycles)
  - [Credentials contract](#credentials-contract)
  - [Encrypted values](#encrypted-values)
  - [`just cloud-preflight`](#just-cloud-preflight)
  - [The cloud change cycle](#the-cloud-change-cycle)
  - [GCE cost discipline](#gce-cost-discipline)
  - [Other CLI commands](#other-cli-commands)
  - [The gid shim](#the-gid-shim)
  - [Instance access and sizing](#instance-access-and-sizing)
  - [IAP sessions on GCE (`session_mechanism: iap`)](#iap-sessions-on-gce-session_mechanism-iap)
  - [Procedures](#procedures)
- [5. Rules](#5-rules)
  - [Identity](#identity)
  - [Applies](#applies)
  - [Network](#network)
  - [Secrets and publicness](#secrets-and-publicness)
  - [Configuration and tests](#configuration-and-tests)
  - [Container hosts](#container-hosts)
  - [Podman as the daemon](#podman-as-the-daemon)
  - [Cost](#cost)
- [6. Where things are](#6-where-things-are)

## 1. What a run is

### The command

```sh
cs-image-system --root-dir <config root> [--dry-run | --no-dry-run] \
    [--overlay <file>]... [--undeclare <kind>:<name>]... \
    run [identity] [storage] [base-image] [instance-image] [release] [retention] | --all \
    [--apply | --no-apply] [--commit | --no-commit] [--state-query | --no-state-query] \
    [--only <image>]... [--only-runtime <rt>] [--apply-runtime <rt>] \
    [--force-bake <image>]... [--allow-unscoped-bakes]
```

`just cli run …` runs the same command against the live configuration.
Nothing in a run waits on a terminal; every run is headless.

### Lifecycles

A run drives **lifecycles**, always in this order whatever order they are
named:

| Lifecycle | Generates | Its runner script applies |
| --- | --- | --- |
| `identity` | the identity roots: user lookups, OPA groups, policies, memberships, enrollment tokens | `apply_identity` |
| `storage` | one terraform root per storage builder | `apply_storage` |
| `base-image` | packer sources and build blocks for base images | bakes (no flag; see the bake rules) |
| `instance-image` | packer blocks for instance images, then the instance roots | bakes; `apply_instances` |
| `release` | the release read-model; one deferred `release --declared` step when an image declares `release:` | the declared-release step in any real run; the cloud-side marking of current releases under `apply_release` |
| `retention` | one deferred `dispose image --retention` step | runs last |

The four built-ins are an enum; `release` and `retention` are registered
lifecycles (`LifecycleSpec`, positioned `after` an existing one). A
plugin may register more. `--all` (or the name `all`) selects every
lifecycle, registered ones included.

Each requested lifecycle is wiped and regenerated under
`generated/<lifecycle>/`; every other directory is untouched, so a run of
`storage` alone leaves yesterday's `base-image` emission where it was.

### Phases and hooks

Inside a lifecycle the runner walks that lifecycle's **phases**: the
built-ins claim the five generation phases (user, group, storage, image,
instance) plus resolution before each. For every phase the runner fires
each builder's before hook, the phase's generation function, then each
builder's after hook. The phase enum (`ExecutionLifecyclePhase`) carries
more members than the built-ins use (`pre-`/`post-` variants, test,
commit, execution, verify, cleanup): they are extension points a
registered lifecycle may claim, and the runner script orders every
lifecycle's deferred commands by the enum's position.

Every builder emits files under `generated/<lifecycle>/` plus commands
split into **run-now** (`fmt`, `init`, `validate`) and **deferred**
(packer builds, `tofu plan`, the gate, `tofu apply`). The deferred
commands become the lifecycle's runner script.

### Generation versus finalization

Generation writes the emission and the read-models. Finalization is the
apply step: for each REQUESTED lifecycle, `generated/<lc>/run-<lc>.sh`
runs **iff it exists**. A lifecycle that deferred nothing leaves no
script and is a no-op (`no-script` in the summary). A script left behind
by an earlier run of an UNREQUESTED lifecycle is skipped loudly
(`stale-script-skipped`), never executed, because bare-bash execution
bypasses the builders' hooks and would change reality with no lineage or
meta-state record. `--no-apply` skips finalization entirely.

Under `--no-dry-run` a lifecycle generated in this run is executed
in-process with its builders' pre- and post-finalize hooks around each
phase; that is where packer manifests become image ids and instance
variables. The committed script is the faithful record of what
finalization executes.

The deferred steps that are the system's own commands (`cs-image-system
gate-plan`, `apply-check`, `prune-attachments`, `release --declared`, the
`state-migration`, `verify`, `dispose`, `unmount` and `identity-attributes`
steps) are executed by the running process **in that process**, over the
configuration it loaded at its start: a run loads the configuration once,
not once more per step. The `--root-dir`, `--no-dry-run` and `--overlay`
arguments such a line carries describe that very configuration and are
parsed and ignored in process. The committed script keeps the same lines
so a hand run of `run-<lc>.sh` still works; there, each `cs-image-system`
line is a process of its own and loads the configuration once per step,
as it always did. The one deferred step the running process still spawns
as a process of its own is the transient-storage teardown at the end of a
decommission (`run storage --only none --no-state-query --no-commit`): it
is a nested run under a *different* overlay set (the overlays that
declared the transient storages are left out, so the storages undeclare
and destroy through the gate), and a different overlay set is a different
configuration, which the loaded one cannot stand in for. A command's own
output (the gate's `Plan passes the apply gate.`, `released: ...`) prints
as it did; what differs is that it is no longer a captured child's
output.

### Dry run and real run

The global `--dry-run` is **on by default**. A dry run generates
everything, initialises every terraform root with `init -backend=false`
(providers and validation only; the remote state, which holds decrypted
values, is never touched), and the apply step only *enumerates* what each
runner script would execute. Bake plans are computed and logged; pins
move nothing; records are not forgotten. `--no-dry-run` performs it.

A real run's `init` is `init -reconfigure -backend-config=<file>` when a
backend is registered for the root: the state is remote, so there is
nothing to migrate.

### The runner scripts

`generated/<lifecycle>/run-<lifecycle>.sh` is self-contained:

- it `cd`s to its own directory and defines `CSIS_ROOT` as the
  configuration root **relative to the script**; every root-based
  argument (`--root-dir`, `--overlay`) is rendered as `"$CSIS_ROOT"` or
  `"$CSIS_ROOT/<rel>"`, so a committed script names no machine's absolute
  path and runs from any clone;
- it performs its own `init -input=false -reconfigure [-backend-config=…]`
  before each plan, so a fresh clone with no `.terraform/` can run it;
- it runs under `set -euo pipefail`; the first failure stops it.

The scripts are the record of what changed reality. Nothing changes a
recorded resource by hand.

### The apply gate

Every terraform root's deferred sequence is:

```text
rm -f tfplan
tofu init -input=false -reconfigure [-backend-config=<root>.tfbackend.hcl]                                                    (a migrating root instead: state-migration begin, then init -migrate-state -force-copy)
cs-image-system prune-attachments --builder <group builder> ...                                                                 (identity roots only, every run: it asks the state, and after its own backup removes from it an unmanaged group's module and the attachments OPA no longer holds)
tofu plan -input=false -out=tfplan [-replace=…] [-var=…]
cs-image-system gate-plan --planfile tfplan --tofu <tofu> [--allow-destroy <addr>]... [--require-unmounted <inst>:<storage>]...
cs-image-system state-migration finish --workspace <root> ...                                                                   (a migrating root only, after the gate)
cs-image-system apply-check --lifecycle <key> --root <root> --root-alias <runtime> [--overlay <file>]... [--apply-runtime <rt>]   (only when an apply is emitted)
tofu apply -input=false tfplan                                                                                                   (only when an apply is emitted)
```

- `rm -f tfplan` first, and `gate-plan` refuses a planfile older than the
  root's newest `*.tf` (exit 3, `STALE PLANFILE`): a failed plan can never
  hand the gate a previous sequence's file.
- `gate-plan` fails (exit 3, `DESTROY NOT WHITELISTED`) unless every
  planned destroy is whitelisted by `--allow-destroy`. The only
  whitelisted destroys are operation-driven: an instance replacement from
  `upgrade instance` or a `follow` policy, together with the replaced
  instance's volume attachments (they bind the volume to the instance's
  id, so the instance cannot be replaced while they stand), an instance
  that was decommissioned (removed from the YAML, or undeclared for the
  invocation), a storage whose requested state is `destroyed` or
  `archived` or that is no longer declared, and an attachment whose
  detach was unmounted first. `--require-unmounted` refuses (exit 3,
  `DETACH NOT UNMOUNTED`) without a successful receipt.
- `apply-check` re-reads `cfg/_config.yml` (and the run's overlays) at
  EXECUTION time and exits 3 when the flag is off *now*, so a script
  generated under yesterday's flags cannot apply under today's. A
  vanished overlay is a refusal.
- `apply` runs the very plan file the gate passed.
- A deferred command that exits non-zero or raises is logged as
  `[<lifecycle>/<phase>] command failed` or `command returned <rc>`,
  marks the lifecycle's apply `failed` in the summary and the journal,
  and the run exits 1; later lifecycles are not attempted.
- The deferred system-CLI steps verify as they go: `verify instance`
  (the runtime's checks, the booted image against the pin or the series,
  the declared post-bake tests; a failed one stops the runner unless
  `--record-only`), `verify assert` (the last verdict must be ok),
  `unmount storage` (a receipt, and a raise on failure), `release
  --declared` (each target re-evaluated at execution), `dispose image
  --retention` (recomputed at execution; debt logged),
  `prune-attachments` and the state backup (an uninitialised root, a
  failed pull or a location with no state stops the runner before any
  `state rm`), `state-migration begin` (the new location must be empty
  or hold this lineage) and `finish`.
- After a real apply, and never in a dry run, the lifecycle's after-apply
  hooks run in order, each gated on its lifecycle's apply flag:
  `record_storage_transitions` (requested states become authoritative
  for the roots that applied), `mark_launched` (the `launched` marker; a
  generation opens `inferred`; a replaced machine's old registration is
  retired), `forget_decommissioned` (pin, launch parameters and
  registration of an undeclared instance whose root applied; generation
  closed `decommission`), `forget_ephemerals` (generation closed
  `ephemeral`; a `teardown` policy's failed verdict raises here),
  `record_detachments`, `register_provider_aliases`,
  `reconcile_generations` (the provider's instance id confirms, adopts
  or replaces the open generation) and `reconcile_workload_access` (the
  CI login policy per managed group; a failure is an ERROR, never
  fatal). Every outcome is a log line and a meta-state write.

Applies are opt-in per lifecycle in `cfg/_config.yml`:

```yaml
config:
  apply_identity: false    # identity roots (OPA groups/policies/membership)
  apply_storage: false     # storage roots
  apply_instances: false   # instance roots (launches machines)
  apply_release: false     # the release lifecycle's artifact marking
```

Each flag is `true` (every root of the lifecycle applies), `false`, or a
**list of root names and/or runtime names** that scopes the apply to
those roots; the other roots of the lifecycle still plan and gate:

```yaml
config:
  apply_storage: [gcp-pd]            # by storage builder name
  apply_instances: [gcloud-east1]    # by runtime: the tofu-gce root only
```

`run --apply-runtime <rt>` sets `apply_storage` and `apply_instances` to
`[<rt>]` for the run and the generated `apply-check` carries
`--apply-runtime <rt>`. Bakes have no apply flag: the bake selector is the
bake control.

### Scoping a run

- `--only <image>` (repeatable) restricts the BAKE surface to the named
  images: sources, build blocks and bake scripts exist for nothing else.
  Unknown names fail loudly. `--only none` bakes nothing: the terraform
  roots alone, for a launch or teardown that must not re-bake.
- `--only-runtime <rt>` generates and plans **no other runtime's** storage
  or instance root (their plans can only fail or waste time). Alone, it
  makes the bake surface every image baked on that runtime. Beside
  `--only` it **narrows**: the bake surface is the named images on that
  runtime and nothing else, and a name it cannot honour -- not baked on
  that runtime, written `@` another runtime, or `none` beside names -- is
  refused before anything is generated (exit 2), every such name listed
  at once. The pair narrows rather than unions, so a run naming two
  images bakes those two and no other due image of the runtime
  ([INCIDENTS.md](INCIDENTS.md#a-run-naming-images-also-planned-every-due-image-of-the-runtime)).
  A list-valued
  `apply_*` flag alone is not such a scope: under it every root still
  plans and gates.
- `--apply-runtime <rt>` lets that runtime's storage and instance roots
  apply **and implies `--only-runtime <rt>`** unless `--only` or
  `--only-runtime` is given; the bake plan then reads
  `skip: outside the apply scope` for the other runtimes.
- The run's **apply scope** is the set of runtimes named by
  `--apply-runtime` and by list-valued `apply_*` flags (a root name counts
  as its runtime; `true` means the whole lifecycle, no scope; a pure bake
  run has no scope). When the scope is a proper subset and the bake plan
  would still bake outside it, a `--no-dry-run` run **refuses before any
  bake**, naming the images and the way out (`--allow-unscoped-bakes`, or
  an explicit `--only`/`--only-runtime`); a dry run warns. Bakes are
  additive and never gated by apply flags; this is a scope check.
- The terraform roots are never filtered by `--only`: every non-destroyed
  instance exists in its runtime's root because that is what the
  declarative configuration says. Decommission by editing the YAML (or
  `--undeclare`).
- `--base-only` (global; on `build-all` and `generate`) selects the
  base-image lifecycle alone, the same as `run base-image`.
- `--force-bake <image>` (repeatable; `all` = the run's whole surface)
  bakes even when current.

Baking a few named images on one runtime, with only that runtime's roots
planned, is the two flags together (the dry form first, as always):

```sh
just cli --locked --dry-run run base-image instance-image \
  --only basic-rh-10-posix --only imgfile-posix-proof --only-runtime aws-east2-runtime
just cli --locked --no-dry-run run base-image instance-image \
  --only basic-rh-10-posix --only imgfile-posix-proof --only-runtime aws-east2-runtime --commit
```

The bake plan then says `bake:` for the two series and `skip: not
selected (--only)` for everything else. The per-runtime spelling
`--only <image>@aws-east2-runtime` alone bakes the same two but plans
every runtime's roots.

### Transient declarations

`--overlay <file>` (global, repeatable) merges a file over the
configuration tree for that invocation only: its `config:` keys override
`cfg/_config.yml`, its `instances:`/`storages:` entries update the
same-named declaration key by key or add one, and an entry
`{name: X, undeclare: true}` removes the tree's declaration for that
invocation. The tree on disk is never changed; the run summary records the
overlay paths; the generated `apply-check` carries `--overlay <file>` so
the script re-reads the same overlay at execution, and a vanished overlay
refuses. `--undeclare <kind>:<name>` (global, repeatable) is the undeclare
form as a flag, e.g. `--undeclare instance:gce-test`: the instance
decommissions through the gate exactly as if its entry had left the YAML.

The live configuration carries **no overlays**: an overlay does nothing
unless an invocation names it, a missing one is a refusal, and no recipe
names one. The overlays the tests use live in the frozen fixture
(`tests/fixtures/config/overlays/`); the overlays of past live proofs are
kept as evidence under [history/overlays/](history/overlays/README.md).

### When an image bakes

A run bakes an image on a runtime only for one of these reasons, and the
bake plan (logged, and in `run-summary.json`) names it per
`<series>@<runtime>`:

- no build of the series on that runtime yet;
- its **inputs changed**: the recorded `input_fingerprint` of the series
  head differs from the one the tree computes now. The fingerprint covers
  the series, the parent image's own fingerprint (its content on that
  runtime, computed from the tree, never the parent's build id: on an
  ephemeral runtime retention disposes the base build every cycle, so a
  fingerprint over the build id would make the plan and the record
  disagree and the child re-bake every cycle;
  [INCIDENTS.md](INCIDENTS.md#a-follow-image-re-baked-every-cycle-on-the-ephemeral-runtime)),
  the capability stamp, every
  modification's content hash, the in-bake tests and the bake disk size;
  for base images also the declared vendor source, the admin user and
  keys, and the update policy. It excludes machine type, preemptible, IAP,
  ssh username, run ids and timestamps, and which BUILD of the parent the
  bake is from: that is the pin's business, and a moved pin is the next
  reason. Vendor-family *movement* is excluded too: the declared reference
  is hashed, not what it resolves to today. A build adopted with `state
  import` records only the first 16 characters of the fingerprint (its
  tag's) and counts as current when they match, so an adopted series is
  not re-baked on every run;
- its **parent moved** under `parent_policy: follow` (the pin behind the
  parent series' head, the condition the state query reports as `stale`):
  judged before the fingerprint, so a parent re-baked from identical
  inputs (a `refresh_days` refresh) is still followed; a parent that bakes
  in the same run counts as a move (`parent … re-bakes this run`);
- `update.refresh_days` on the OS builder is due: the head is at least
  that many days old (package updates are invisible to the fingerprint);
- `--force-bake` named it.

Otherwise the plan says `skip: current (build …)` and the image leaves no
bake surface: a second `run --all` on a converged tree bakes nothing.

After a change to the fingerprint recipe itself,
`lineage restamp --runtime <rt> [--series <s>]... [--commit]` records the
tree's current fingerprint on each series head whose recorded one predates
the change (the previous value kept under `fingerprint_restamped`) and
re-tags the cloud image, so unchanged images are not re-baked once.

### How an image is named

A tree can say what its builds are called. Every build of
an image on a runtime is named `<prefix>-<timestamp>`: the timestamp is
the run's in the tree's `dateformat`, and the prefix is the image's
`output_image_name` on that runtime when one is declared (its own
`runtimes[]` entry; for a base image the OS builder's entry, else the OS
builder itself; CONFIGURATION 5.5 has the precedence and the rules), else
the default shape: `<image>-<image builder>`, and for
a base image `<OS builder>-<runtime>`. The packer source writes the full
name (`ami_name`; on GCE `image_name` after GCE's rules), and the deferred
image lookup finds a build that has not happened yet by `<prefix>*`: an
instance root's `ami_name_pattern` when no pin stands, and an instance
image's parent lookup. Nothing else reads the name: lineage, pins,
release, retention, disposal and the state query go by the `csis_series`
tag and the recorded build ids, which is why a declared name changes no
record and re-bakes nothing by itself. `validate` refuses a prefix that
carries the run's timestamp, two prefixes on one runtime of which one
begins the other as the runtime makes them, and a full name the runtime
cannot take, and prints one line per image and runtime with the prefix
and whether it was declared. A declaration renames every future build on
that runtime; on a guarded runtime the packer source moves, so the record
that lands it needs the operator's own `just record` before `main` moves
(DAILY_DRIVER, `runtime-unchanged`).

### Where a vendor image comes from

A base image's vendor source is resolved through the
image-source catalog (CONFIGURATION 5a): the release's catalog for every
family the plugins serve, the tree's `cfg/image-sources*.yml` landing on it
by family and version, the OS builder's own `query` and its runtime entry's
landing on that, key by key, all in the system's query vocabulary, and the
runtime translating the result to its own words last. `validate` refuses an
unknown key, an entry with no source for its runtime's type, and a key the
runtime cannot translate, naming the entry each time, and prints one line
per entry with the query in both vocabularies, so what will be asked is on
screen before anything runs. The fingerprint hashes the effective query,
so a source that moves in the catalog re-bakes the base, as a moved
declaration does. A tree whose records predate the catalog sees every
base's fingerprint move once, and `lineage restamp` re-stamps its
standing builds without a bake ([CHANGES.md](CHANGES.md#s106)). What a
family IS (`is:` in the catalog) is what the bake user, the
session agent, the in-bake tests and the modification tests' stand-in
container read: `alma-linux` is baked as `rhel` and tested on
`almalinux:<version>`.

### When a bake fails

A packer build that fails stops its lifecycle: the run ends `Apply
failed for lifecycle <lifecycle>` and exits 1, and nothing after the
failed command runs. The builds that completed before it are kept
anyway. Packer writes a build into its block's manifest only
after the build -- its in-bake tests included -- succeeded, so after the
failure every builder records what its manifests hold, exactly as a
successful phase would. A warning names them:

```text
<image builder>: the phase failed; recorded the <n> build(s) that completed before it did: <image> -> <build id>, ...
```

The failed series gets no build and stays due, so the next run bakes it
again; nothing is left foreign. Each bake first removes the manifests
earlier runs left in its block directories -- the private mirror keeps
what the tools wrote between runs, and a failed block writes no new
manifest -- so an old run's artifacts can never be recorded as this
run's.

A failed run does not commit: its records are in `meta-state/` on disk,
and `just record` (in CI, the `perform` job's closing record) commits
them, as after any run.

The completed builds are recorded because an image that stands in the
cloud unrecorded is `foreign` to the state query, and a `foreign` line
refuses every strict preflight until it is dealt with
([INCIDENTS.md](INCIDENTS.md#orphan-amis-from-failed-and-unrequested-bakes)).
The way out for an image that does stand unrecorded (baked by hand, or
by a run that died before recording) is `state import` ("The state
query"), which adopts it; an adopted build of today's inputs then
counts as current and is not baked again.

### Parent and image policies

An instance image declares `parent_policy: pinned` (default: it bakes from
its pinned parent build until an explicit `upgrade image`) or `follow` (a
newer parent head re-bakes it in the same run and moves the pin, logged as
`op: follow`; the pin moves when the bake is recorded, never in a dry
run). An instance declares `image_policy: pinned` (default) or `follow` (a
newer image head plans the gated replacement; the pin moves after the
apply). A pinned child whose parent head has moved is reported by the
state query as `stale`: informational, never hard.

### The power state belongs to the operator

An instance is CREATED running -- that is what applying the IaC means --
and after that the system never forces it back to running. If you switch a
machine off, nothing here switches it on again behind your back, and
nothing calls it drifted for being off. Its pinned build, its mounts and
its OPA registration are all still true; they simply cannot be re-read
while it is off, and the state report says so in those words:

    note: instances/coops-model: STOPPED (switched off; not drift); its
    pinned build ami-078... mounts and registration all still stand and
    are simply not readable while it is off

That line is a `note`, a third category beside `drift` and `unavailable`.
It is deliberately none of the others: `unavailable` means a provider
could not answer, and reporting your own decision as a failure to answer
would be the records lying about a stopped machine
([INCIDENTS.md](INCIDENTS.md#a-stopped-machine-was-reported-as-the-provider-could-not-answer)).
A builder that cannot be asked at all (its plugin has no lookup) is
`unavailable` too, as `<kind>/<builder>: cannot be queried (...)`, never
left out of the report in silence, because a storage nobody can ask (a
Filestore, say) could otherwise never read as missing.

**"Cannot answer" is not "stopped."** The runtime hook
`query_instance_power_state` returns the system's own vocabulary --
`running`, `stopped`, `suspended`, `starting`, `stopping`, `absent`,
`unknown` -- or `None`, which means only that this runtime could not find
out. Nothing infers a state from `None`. Each cloud's spellings are mapped
inside its plugin, which matters more than it sounds: GCE's `TERMINATED`
means STOPPED and the machine can be started again, while EC2's
`terminated` means the machine is gone. No caller reads a provider's word.

**Starting a machine is a bounded exception.** Only work that NEEDS a
running machine may start one -- verification and the post-bake tests; a
bake does not -- and when it does, it says so:

    coops-model is STOPPED (switched off; not drift); STARTING it because
    verifying instance coops-model. It will be stopped again when that is done.
    ...
    coops-model: work finished (verifying instance coops-model); stopping it
    again, which is how it was found.

It waits for the machine to be genuinely reachable rather than trusting
the provider's `running`, and it puts the machine back whether the work
passed, failed or raised. If the restore itself fails you get an ERROR
naming the machine and saying it is now running and must be stopped by
hand -- the one case where you are left with something to do.

If a machine is off and its runtime cannot start it, the work is SKIPPED,
not failed, and nothing is recorded: no verdict was reached. A skipped
verification does not overwrite the last real one.

**On a docker runtime** the same rule is a property of how the container
is declared, not of a hook alone. The instance root declares the container
with `must_run = false`, so an apply that finds it stopped leaves it
stopped, and with the restart policy `unless-stopped`, so a daemon that
restarts brings back what was running and nothing else. The runtime's
power vocabulary is mapped inside its plugin as the clouds' are: `running`
is running; `exited` and `created` are stopped; `paused` is suspended;
`restarting` is starting; `removing` is stopping; absent is absent. The
note for a stopped container is the same `note: ... STOPPED (switched off;
not drift)`, and a run that finds one says `waits for a run that finds it
running` for the things only a running container can answer (the launch
marker, the mounts, the accounts). Verification may start it and stops it
again, as above.

### A canonical hostname is claimed once

The name an instance is given at boot (`hostnamectl set-hostname`) is the
name it enrolls in OPA under, and `sft ssh <name>` resolves against that
registry. These rules keep one name meaning one machine:

**The registration goes with the machine.** A decommission drops the
instance's pin and launch parameters and retires its OPA server
registration too -- the third record of the same launch, and the one
that would otherwise outlive the machine and leave several entries
answering to one name, only one of them live
([INCIDENTS.md](INCIDENTS.md#three-registrations-of-one-hostname-in-opa-one-live)).
A retirement that fails
is an ERROR naming the hostname, never a silent skip: the forget still
happens, but the log says a stale server will answer to that name until it
is deregistered by hand.

**A run that can launch refuses a claimed name.** Before the instance-image
lifecycle applies, every declared instance's hostname is checked against
its group's registry. An unlaunched instance whose name is already
registered is refused, naming the record; a launched one with more than one
registration is refused too, because `sft ssh` cannot choose between them.
The check runs ONLY when a launch is actually possible -- the lifecycle
requested, `apply_instances` on, and not a dry run -- so a dry run never
makes the call and cannot refuse on the registry's silence
([INCIDENTS.md](INCIDENTS.md#a-dry-run-asked-the-hostname-registry)).
And an unreachable registry is a refusal saying the claim *could not be
checked*: silence is not a free name (the same rule the power-state query
follows), and an unreachable OPA is exactly when a duplicate would
otherwise slip through.

**A name the machine cannot take is refused at validate.** RFC 1123 caps a
hostname label at 63 characters of letters, digits and hyphens, not
starting or ending with one; Okta documents no limit of its own. Without
the check the failure is silent -- the boot line ends in `|| true`, so an
invalid name would leave the machine under the hyperscaler's name
(`ip-10-26-34-156`), enrolled in OPA as that, and `sft ssh` would find
nothing while every step reported success
([INCIDENTS.md](INCIDENTS.md#an-invalid-hostname-failed-silently-at-boot)).

**The canonical name carries the generation**: a new
machine is named `<declared>-NNN`, the declared name plus its generation
zero-padded to three digits -- `coops-model-001`, `coops-model-054`,
`coops-model-256`; the pad is a minimum width, so generation 1000 renders
`-1000`. An ephemeral instance counts on its own counter, so a standing
machine's number never moves because a throwaway was spun up under the same
name. The number is decided ONCE, at render time -- the durable count plus
one when this run launches a new machine (never launched, decommissioned,
or being replaced by an `upgrade` or a follow) -- and the ledger opens
exactly that generation after the apply.

**A machine that stands keeps the name it booted with.** Nothing renames a
running machine: the name changes only inside a replacement, which is
exactly when immutability lets it change. That also grandfathers a machine
launched by an older tree, before the suffix existed -- `coops-model`,
adopted as generation 1, stays `coops-model` until its first sanctioned
replacement, and then becomes `coops-model-002`.

The bare declared name comes back as an `AltNames` alias on the new
machine, so `sft ssh coops-model` keeps working; it resolves to the machine
that stands once the previous generation's registration is retired, and the
suffixed canonical name works regardless. The state report notes a machine
whose registered name is not the one its generation booted with -- the
silent `hostnamectl ... || true` failure, made visible.

To deregister by hand, servers live under the RESOURCE GROUP:
`/v1/teams/<team>/resource_groups/<rg>/projects/<project>/servers/<id>`
(`DELETE` answers 204). The team-level `/projects/...` path answers
`401 Missing capability`, and the printed name `coops_rg_login` is not the
project id.

### What a machine answers to

`sft ssh` resolves a name against the OPA registry in a fixed order: the
server id or canonical name, then the **cloud instance id**, then the
hostname, then `AltNames`, then the address. Two of those come for free --
sftd reads the instance id from IMDS at enrollment, so `sft ssh
i-0169f82844f4cc08d` and `sft ssh 10.26.34.156` both reach `coops-model`
with nothing configured. The one name that does
NOT resolve is the provider's own hostname, `ip-10-26-34-156`, because the
launch script overwrites it with the declared name before sftd enrolls.

**The system gives that name back after launch**: an
applies-on instance-image run finds each launched, RUNNING instance's
provider hostname from the cloud, checks the label against every name the
group's registry already answers to (hostnames, canonical names, alt names)
and every name the configuration declares, and writes it as an `AltNames`
entry in `/etc/sft/sftd.yaml` over the runtime's session command, restarting
sftd only when the block actually changed. The log says which alias went
on, or why it did not:

    Instance coops-model: now also answers to ['ip-10-26-34-156'] (sftd restarted)
    Instance coops-model: alias 'ip-10-26-34-156' SKIPPED -- already claimed by 772d4058…

A collision is always skipped, because OPA ranks a record's hostname above
another record's alt names: a colliding alias would resolve to a dead
machine, or make the name ambiguous and refuse -- worse for both than no
alias. A machine that is off is left off (an alias is not worth starting one
for); the alias goes on at the next run that finds it running. A registry
that could not be asked skips every alias that run: silence is not a free
name.

The state report shows what each machine answers to under `reality.instances`
(`instance_id`, `provider_hostname`, `registered_as`, `alt_names`) and notes
a running machine whose alias is not yet there. Nothing about aliases is
written to the launch parameters -- they are discovered after boot, and the
registry entry is the record.

**When `sft ssh` fails, `sft resolve` first.** A name that resolves with an
old `LastSeen` is a machine that is switched off, and `sft` reports that no
more helpfully than an unknown name; `state query` says "STOPPED (switched
off; not drift)" in words.

### Instance generations

A generation is one machine. It opens when a machine comes into being and
closes when THAT machine is destroyed; storage uses the same word for the
same thing. `meta-state/instance-state.yaml` holds, per
instance name, two counters (`durable`, `ephemeral`), the open generation --
its number, kind, the run that opened it, the provider's instance id once
seen, and a SNAPSHOT of the launch parameters it booted with -- and a
history nothing is ever deleted from. `launch-params.yaml` keeps holding
what the current machine booted with; the two files divide exactly as
`storage.yaml` and `storage-state.yaml` do, and the counter is never in the
launch-params record (it would read as a changed launch parameter and refuse
the very replacement that bumped it).

**A container's identity is its id.** On a docker runtime the provider's
identity for the machine is the container id the daemon reports, read by
`docker container inspect` after the apply, and the canonical hostname is
`<name>-NNN` as on the clouds. A container that is re-created (an upgrade, a
`-replace`) is a new generation with a new id; one that is only stopped and
started is the same generation. A container of another configuration, or
one that carries none of this configuration's labels, is never taken for
yours: a name that another configuration holds reads as absent here.

**The machine decides.** A launch that applied opens a generation marked
`inferred`. After the apply the system asks the provider which machine
bears the name: the same id confirms it (`observed`); a DIFFERENT id means
the machine you knew is gone and another stands -- the generation closes as
`replaced-out-of-band` and the next opens, with a warning saying nothing in
this system did it. A sanctioned replacement (`upgrade`, a follow) closes
the generation as `replaced` and opens the next in the same run. A
decommission closes it as `decommission`, an ephemeral teardown as
`ephemeral` -- an ephemeral machine existed, booted and enrolled, and its
generation is the record that lets the teardown deregister it honestly.

**What is not a new generation**: a reboot; a stop and start (a stopped
machine is the same machine); a mount detach; a resize applied in place;
an image pin that moved but was not applied; and an identity query that
returned nothing -- "cannot read the id" is never "the id changed", and a
stopped instance may well fail the query.

**A resize is the same machine.** The machine type is a launch parameter
(`machine_type` in the record and in the generation's snapshot, the
instance's own or the runtime's default), and the one that may change in
place: a launched instance whose declaration names another type passes
`validate`, and the next applying run has the provider stop the machine,
change its type and start it again -- the same instance id, so the same
generation. The record keeps the type the machine RUNS on until that apply
(a dry run changes nothing but the emission), and then the record and the
open generation's snapshot take the new type and the ledger's history
gains a `resized` event (`from`, `to`, `run`) beside the closed
generations. A record written before the key existed adopts it on the
first run that sees it; any other launch-parameter change riding along
with the type is refused as before. To replace the machine instead --
a new id, a new generation, the old root volume gone -- decommission and
redeclare, or `upgrade`; a resize never does that.

**What stood before the ledger is adopted, not invented.** A machine that
was already launched when this record began becomes generation 1 marked
`adopted` -- the first generation of the RECORD, not of the name. Its
predecessors are visible only in `pins.yaml.upgrades`. The state report
shows each launched machine's generation beside its provider identity under
`reality.instances`.


### CI logs in through the policy the system manages

Verifying an instance through SSM proves the box is healthy; it says
nothing about access. CI logs in the way a scientist does -- `sft ssh`,
a short-lived OPA certificate, no static key -- and that login depends
on the policy the system manages, so the proof is of the policy.

CI is a **workload**: the GitHub Actions run presents GitHub's own OIDC
token to the team's **workload connection**, which maps it to the team's
one **workload role**. Both are the operator's, made by hand once in the
OPA console and named on the okta-tf group builder
(`workload_connection`, `workload_role`); the checklist with the values,
the impersonation cases (what a name pin trusts) and the relocation order
(what to edit, in which order, when the repository moves) are in the
CI setup guide every starter tree carries,
[CI_SETUP.md, section 3.5](examples/_skeleton/CI_SETUP.md#35-okta-and-okta-privileged-access).
`just sft-install` puts Okta's client on an apt runner; `just
opa-workload-probe` (the dispatch-only `OPA workload probe` workflow,
`cs-image-system workload probe`) presents a run's token to the
connection and reports the client's verdict, masking both tokens -- the
test to run against a draft connection before activating it -- and, with
the token it was issued, whether the ROLE reaches a standing machine of a
managed group (`role <name>: granted` / `not granted`): the one proof of
the role's branch pin, read once from `main` and once from another
branch.

What grants the role reach is **one CI login policy per managed group**,
`<group>_v1_security_policy_ci`, kept beside the user policy the terraform
module emits. The Terraform provider cannot name a workload role as a
principal (okta/oktapam 0.7.1 accepts only groups), so the policy travels
through the OPA API, after the identity lifecycle's apply and under the
same `apply_identity` gate: it is DERIVED from the standing user policy
record on every reconcile -- same resource group, the rule verbatim,
admin-level forced off, the role as the only principal -- created, updated
or left alone, and the outcome recorded under the group in
`meta-state/identity.yaml` beside what the configuration expects. That
derivation is what makes "mirrors the user policy" structural: a rule
change in the module propagates on the next identity run. A group released
from management is left as it stands, like its user policy; the identity
lifecycle never destroys.

The state query reads all three objects. An absent role is drift that
names the checklist (the operator's object); an absent or diverged CI
policy is drift that names the apply (the system's object); a connection
that is present but still a draft is a `note`, because activating it is
the operator's act. None of it is HARD: the validator refuses a run on
hard drift, and the run that repairs these is the identity apply itself.
A strict state query still fails on them. A silent OPA says nothing, as
everywhere else.

**The proof itself** is `cs-image-system verify login [<instance>...]
[--runtime <rt>]` (`just ci-login-proof`, and the `sft` leg of
`cloud-verify`). Both `verify login` and the `workload` commands are the
okta-opa plugin's: it mounts them on the command line through the command
entry-point group ([PLUGINS.md](PLUGINS.md#what-a-plugin-adds-to-the-command-line)),
so they exist when that plugin is installed and are absent from a tree
without it; the driver behind `verify login` (which instances are
targets, the skips, the record) is the core's, and every identity
plugin's checks run through it. For each standing instance -- launched, not ephemeral --
of a group whose builder names the workload objects it checks, in order:
the machine is RUNNING (a stopped one is skipped and never started,
because the power state is the operator's); exactly one server answers
to the canonical hostname in the group's registry (a second one would
make `sft ssh` reach an arbitrary machine); the client resolves the
name; `id` runs over `sft ssh`. Each verdict, with the Unix account the
login landed in, goes to `meta-state/login-proofs.yaml`. With `OPA_TOKEN` in the environment the
login is the workload's (`cs-image-system workload token` mints it from
the Actions run's OIDC token; the recipe does this itself inside a job); run by
hand without one, the enrolled client logs in as you and the record says
`as: client`. As the workload the client has no `~/.config/ScaleFT` of
its own, so `verify login` lays the group builder's `team` and
`api_host` over the client's environment (`SFT_TEAM`, `OPA_ADDR`) for
`resolve` and `ssh` alike, the environment's own values winning when set.
A job need not export either: a client with neither name set fails `sft
resolve --quiet` with exit 1 and no message, which is why the token mint
and the login both take their names from the configuration. In CI the
`perform` job runs it on `main` after the performing step, under the
read-only role, and the closing record commits the verdicts. What must
turn it red: the group's CI policy deactivated or absent, the role's
condition not matching the run, a machine that never enrolled, a
duplicate hostname -- and deactivating one group's policy fails that
group's proof alone.


### A model image, end to end: the second release

Taking a model image from one released build to the next is a
procedure. It takes one durable instance (`coops-model`, a
`c5n.4xlarge` that stands 24/7 and owns the single-attachment `mnt_data`
volume) from one released build to the next in four steps, all from the
code repository, all but the edits through `just`:

1. **The change.** A modification on the image (here an ansible playbook
   under the configuration's `playbooks/`), the proof of it in the
   image's `tests:` and `tests.post_bake`, `just cli validate`, then
   `just test-mods --strict` (the bundle runs twice in an AlmaLinux 10
   container: apply and idempotence). Commit the configuration.
2. **The build.** `just cli --no-dry-run run base-image instance-image
   release retention --only-runtime aws-east2-runtime --commit`. The
   change makes the bake due (`--force-bake <image>` bakes an unchanged
   one). `release` does NOT release the build yet: it wants the
   post-bake record, which only a launched machine can produce.
3. **The upgrade.** `just cloud-upgrade aws-east2-runtime coops-model`
   (`to=<build>` for other than the series head) runs, as one gated
   sequence, the steps that are never done by hand
   ([INCIDENTS.md](INCIDENTS.md#the-first-live-replacement-four-traps-in-one-afternoon)):
   - *the pin*: `upgrade instance` moves it to the series head and leaves
     the pending-replacement marker; the strict state query now reports
     the booted image behind the pin as a `note`, not drift;
   - *the replace*: `cloud-launch`. The plan carries `-replace` for the
     instance and the gate whitelists it AND its volume attachments (the
     attachment binds the volume to the instance's id). The new machine
     boots as `coops-model-002`; generation 1 closes as replaced and 2
     opens on the new instance id; the replaced
     machine's registration under the old name is retired by the launch
     that replaced it. The data volume is detached and re-attached; the
     root disk is lost. About ten minutes down;
   - *the proof*: `cloud-verify`: the booted image, both mounts, the
     post-bake assertions, recorded for the new build;
   - *the release*: `run release --only-runtime aws-east2-runtime
     --commit` records the build as the model's current release; the
     previous release stays in the ledger;
   - *the names*: one more `cloud-launch` (no changes) gives the machine
     back its bare name and `ip-…` label as AltNames; a machine launched
     in the same run gets them in that run, after it answers and enrolls;
   - *the record*: `just record`, the full dry generation committed. The
     launches regenerate the instance lifecycle alone, so the release
     read-model the release run moved is in the committed emission only
     after it; without this step `config-drift` on `main` fails until a
     record is made by hand.

   `config.require_released_builds` stays `true` the whole way. It is
   never switched off for the middle steps, although an instance pinned
   to an unreleased build would otherwise make every run refuse, and for
   a durable instance whose volume allows one attachment no proof
   instance can mount what the post-bake spec requires, so the proof can
   only run on the instance itself: the release grace (above, under
   `release`) admits the series head while its own proof is under way
   and refuses the moment the proof fails; nothing is edited by hand
   ([INCIDENTS.md](INCIDENTS.md#the-release-flag-had-to-be-switched-off-by-hand-mid-release)).
4. **The login.** `just ci-login-proof coops-model` logs in by name.

**The standing cost** of the model node, from the on-demand price this
account cannot query (no `pricing:GetProducts`): a `c5n.4xlarge` at about
$0.86 an hour, some $620 a month while it stands, plus the 100 GiB `gp3`
volume and the EFS filesystem. Switching it off (the operator's act;
nothing switches it back on) stops the instance charge and keeps the
volume's.


### Resizing a durable instance in place

The one launch parameter that may change on a standing machine is its
type ("A resize is the same machine" above). The procedure, with
`coops-model` going from `c5n.4xlarge` to `t3.xlarge` as the example:

1. Read the machine first, so there is something to compare against:
   `just preflight`, `just state-query --strict`, and over `sft ssh` the
   instance id and type from the metadata endpoint (IMDSv2: a token
   first), a digest of a file on each mount, `df -h` of the mounts.
2. The one edit: `machine_type:` in `instances/`. `just validate` passes
   (the type is excluded from the immutability comparison), `just record`
   commits the dry generation -- the instance `.tf` moves in exactly one
   place, `instance_type`; the launch record keeps the type the machine
   RUNS on.
3. `just cloud-launch <rt> yes` to see the command list (no
   `--allow-destroy`: nothing is destroyed), then `just cloud-launch <rt>`.
   The log shows `Plan: 0 to add, 1 to change, 0 to destroy` and one
   `~ instance_type` on the `aws_instance`; the provider stops the
   machine, changes it and starts it (a minute); then `resized in place
   <from> -> <to> (the same machine; its generation stands, the event is
   in the history)`.
4. The proof: the same instance id and the new type from the metadata
   endpoint, the mounts back with the same digests (the EBS device letter
   may move across the restart -- `nvme0n1` became `nvme1n1`; the fstab
   mounts by id, so nothing cares), the record at the new type, the open
   generation's snapshot at the new type with a `resized` event in the
   history, `just state-query --strict` green, `just ci-login-proof
   <name>` green (the registration survives a stop/start). `just record`,
   push.

Anything running on the machine stops for the minutes the resize takes;
nothing on its disks is touched. The old type's cost stops with it.

### Replacing a durable instance: decommission and redeclare

The sanctioned replacement that needs no code and no new build, for when
the machine itself must go (a different machine type class, a damaged
root volume, the "is it really rebuilt from nothing?" question): the
declared storages persist, everything else about the machine is new.
The procedure, with `coops-model-003` becoming `coops-model-004` as the
example:

1. Read the machine (as in the resize, step 1) and the records: the pin,
   the open generation's number and id, the pool's next free name.
   Confirm nothing outside the declared mounts is wanted: the root
   volume goes with the machine.
2. `just cloud-decommission <rt> <name> yes` (the `gate-plan` line
   carries `--allow-destroy module.instance_<name>`), then `just
   cloud-decommission <rt> <name>`: `Plan: 0 to add, 0 to change, 2 to
   destroy` (the instance and its volume attachment); the generation
   closes `decommission`, the registration is retired, the pin and the
   launch record are dropped. The EFS filesystem and the EBS volume stand
   (`aws efs describe-file-systems`, `aws ec2 describe-volumes`:
   `available`). Push `develop` only (see "The cloud change cycle").
3. Nothing to edit: the declaration never left the tree (the decommission
   was `--undeclare` for one invocation). `just validate`, `just record`:
   the instance module is re-emitted, the pin first-binds to the series
   head again -- with `require_released_builds` true, the newest RELEASED
   build, the same one unless something was released in between (then
   stop and decide: the old build is a release-grace question) -- and the
   hostname is the next generation's.
4. `just cloud-launch <rt> yes` ("would take alias `x` from the pool for
   `<name>-NNN` (dry run; nothing drawn)"), then `just cloud-launch <rt>`:
   `2 to add`; the generation opens inferred, the alias is drawn, and
   once the machine answers the id confirms it (`observed`); the names
   are written in the same run when `sftd` is up in time, otherwise one
   more `cloud-launch` writes them. `just cloud-verify <rt> <name>`,
   `just ci-login-proof <name>`, `just record`, push `develop`, then
   `main`.
5. The proof: a NEW id from the metadata endpoint, the same mounts with
   the same digests (a declared storage persists), the ledger with the
   new generation open and the old one closed `decommission`, the pool's
   line commented out with the draw, and every name (`<name>`, the alias,
   `<name>-NNN`) resolving to the one registration.

A first launch attempt can die at `tofu init` downloading a provider
(`hashicorp/aws` from GitHub, "giving up after 3 attempt(s)"); that is
environmental -- retry. The retry draws the same alias again: a draw
whose run aborted before the launch record existed goes back to the pool
at the run's end.

### A pool of names, each spent once

`meta-state/aliases.txt` in the configuration is a pool of memorable,
pre-approved names, hand-written in advance, one per line. When a NEW
machine of a durable instance is about to be launched -- never launched
before, or a pending or follow replacement -- the run that can launch it
takes the first line that is not commented out, records it as the
machine's `alias` in its launch parameters, and comments that line out
IN PLACE with what took it and when:

```text
# bright-otter  -- instance coops-model as coops-model-003 <ISO time> run <run id>
```

The name is therefore spent exactly once, permanently, and the file is
both the supply and the ledger: `git log -p meta-state/aliases.txt` is
the history of who was called what. The name reaches the machine through
the alias pass ("What a machine answers to"): it becomes an `AltNames`
entry beside the bare declared name and the `ip-…` label, so `sft ssh
bright-otter` reaches that machine and no other, and the state report
lists it among what the machine answers to.

**The division of bytes.** The directory's README says nothing here is
edited by hand, and this file is the one exception, stated as a division
rather than a file: **a human only ever APPENDS lines; the system only
ever comments out lines that are already there.** Neither writer touches
what the other wrote, so two checkouts that both draw merge trivially.

**What holds:**

- **The burn is the claim, and it comes first.** The line is rewritten at
  generation, before the apply. A run that dies in between costs one name
  out of a list one appended line refills -- the cheap direction to fail
  in, against two machines answering to one name.
- **A dry run draws nothing** and logs the name it would take. A run
  whose instance roots may not apply draws nothing either. Ephemeral
  instances draw nothing: a proof machine that comes and goes each cycle
  would drain the pool for nobody.
- **Two drawers at once.** The draw re-reads the file under an exclusive
  lock (`aliases.txt.lock`) and writes it temp-then-replace. Across
  checkouts only the push settles it: push the burn promptly, and treat a
  rejected push on this file as "someone else took that name" -- re-read,
  draw again, never force.
- **Spent is spent.** A decommission returns nothing; the pool only ever
  shrinks, and the operator refills it by appending. One exception, which
  is not a return: a name is drawn at generation and GIVEN only when the
  apply launches the machine and the launch record carries it. A run that
  aborts between the two (a `tofu init` that cannot download a provider,
  a failed plan) has drawn a name for a machine that never came to exist,
  and the run's end puts that line back as it was -- the pool file shows
  no trace, and the retry draws the same name again, so the pool never
  names a machine that never was.
- **Running out is a warning, not a failure.** `validate` reports how many
  names remain; an empty pool means the launch proceeds without an alias
  and says so.
- **Not the canonical name.** The alias is a name beside the canonical
  one, which stays `<declared>-NNN`; a person can still guess it.

`validate` refuses a free line that is not a legal hostname label (RFC
1123, at most 63 characters), that repeats another free line, or that is
a name the configuration already gives an instance -- a typo to fix, not
a surprise at launch. Optional by construction: no file, no aliases, no
error.

### Ephemeral instances

`instances[].ephemeral: true` declares an instance that exists to be
verified. Its root's sequence is launch → `verify instance <name>` (on
GCE: the serial console until the startup scripts finish with no failure
line, the booted image against the expected build, the kernel's clean
mounts against the declared data disks; on AWS: over SSM, reading
`/var/lib/csis/launch-applied`, the mounts under `/mnt` and the AMI) → a
second plan with `-var=ephemeral_present=false` → gate → apply-check →
apply. The verdict is recorded in `meta-state/verifications.yaml`; after a
real run the launch record and pin are forgotten. A failed verification
stops the runner with the instance STANDING for inspection and the run
fails; the state query reports it until it is decommissioned.

Failure policy: `on_failure: keep` (default) leaves a failed ephemeral
standing and fails the run; `teardown` records the verdict
(`verify instance --record-only`), tears it down anyway, forgets the
launch record, and only then fails the run (`verify assert`), so the
records never describe an instance that no longer exists.
`teardown_after: <duration>` (`30m`, `2h`, `1d`) keeps it now and lets a
run after the due time tear it down without re-verifying. Runtimes carry
defaults; instances override.

`userdata:` lines on an instance run as the last act of its startup
script under the same `set -e`, before the completion marker; they are
launch parameters (immutable after launch). A failing line is a failed
startup, which `verify instance` reports; `userdata: "false"` on an
ephemeral instance is the sanctioned way to exercise the failure policy.

### Post-bake tests and releases

An image may declare `tests.post_bake`: the in-bake vocabulary (`files`,
`packages`, `commands`, `services_enabled`, `users`) plus `mounts`
(absolute mount points that must be mounted). `verify instance` runs the
suite on the launched instance over the runtime's session command as one
more check and records the result per BUILD in
`meta-state/image-tests.yaml`; a build never launched has no record.

`release <image> [--build <id>] [--model <m>] [--note …] [--runtime <rt>]`
marks a build released for a model in `meta-state/releases.yaml`. It
refuses a build whose image declares post-bake tests but has no passing
record (`config.require_image_tests`, default on) and a build with a
failed mod test on record (a missing one is tolerated unless
`config.require_mod_tests` is true). `config.require_released_builds:
true` lets an instance pin only to a released build of its image, with
one grace: the head of the image's series on its runtime, verified in
bake, is admitted while its own proof is under way -- the instance is a
pending replacement onto it, or stands on it (the open generation booted
with that build) with no FAILED post-bake record. The grace ends when the
release is recorded or the proof fails, and the refusal names what is
missing. It exists for the durable instance that can only be proved on
itself (`cloud-upgrade`).

An image may declare `release: {model: <m>}`: the `release` lifecycle,
ordered between `instance-image` and `retention`, emits one deferred step
(`release --declared`) that releases each runtime's series head whose
post-bake tests PASSED and which is not yet the model's current release.
The step recomputes its targets at execution and runs in any real run;
the cloud-side marking of every current release (the runtime's release
tags) is deferred separately and applies only under `apply_release`.
This exists because on an ephemeral runtime the operator has no moment
between the verification and the closing phase to release by hand.

A RELEASED build is kept by decision: retention and an ephemeral runtime's
disposal report it as debt instead of disposing it, `empty --runtime`
counts it as declared, and only an explicit `dispose image <id>` removes
it.

### Retention and disposal

`images[].retention: {keep: N}` (or a runtime's `retention_keep`) keeps the
newest N builds of a series per runtime; `runtime_builders[].ephemeral:
true` keeps nothing baked there. The closing `retention` lifecycle's one
deferred step, `dispose image --retention`, recomputes the plan at
execution (after this run's bakes and ephemeral teardowns) and disposes
through the sanctioned path. A build an instance is pinned to or was
launched from is retention debt: kept and reported. Declared storages are
never touched by retention.

`dispose image <build-id>... | --runtime <rt> --all [--commit]` is the
sanctioned removal of a RECORDED image: the cloud image is deleted through
the runtime's `dispose_image` hook (GCE deletes the image; AWS deregisters
the AMI and its snapshots), the lineage record is dropped and any image
pin at that build is removed (logged as `op: dispose`, so the next child
bake first-binds to the series head again). It refuses an unrecorded
build (adopt it with `state import` or leave it; never delete blind), a
build an instance is pinned to or was launched from (decommission first),
and a runtime that cannot dispose. Under `--dry-run` it prints the plan.

Cheaper bakes: a GCE runtime with `bake_preemptible: true` bakes on a
preemptible build VM; a preempted bake re-runs. The Justfile exports
`TF_PLUGIN_CACHE_DIR` (`.tofu-plugin-cache/`, gitignored) so every
`tofu init` reuses downloaded providers; with a root's kept
`.terraform.lock.hcl` the init needs no network. Runs started outside
`just` need the variable in their environment to benefit. The cache is
not safe under concurrent `init`, so one tofu process runs at a time by
construction: every recipe of a configuration repository's Justfile
that may execute the roots (`run`, `release`, `cloud-bake`, `cloud-cycle`,
`cloud-stand`, `cloud-launch`, `cloud-decommission`, `cloud-upgrade`,
`cloud-perform`) passes `--locked` to the command, which holds
`.tofu-plugin-cache/.lock` for the command and refuses with exit 75 and
the holder's pid while another has it. Dry runs enumerate and never
start tofu, so `record`, `config-drift`, `cloud-preflight` and the bar
take no lock; the suite's one real-tofu test uses a private cache under its
temporary directory, seeded by copying the providers it needs, and never
contends with an operator's run.

### Storages

**A storage exists exactly as long as it is declared.** An entry under
`storages/` means "this exists": the storage lifecycle creates and keeps
it. Deleting the entry is its demise: the next storage run plans the
whitelisted destroy of the undeclared storage (its root is still emitted;
a bucket is wiped first) and records the tombstone with action
`undeclared`. A tombstone keeps history, not the name: a re-declared name
is a new *generation* (`generation: 2` in `storage-state.yaml`, action
`regenerate`). `state: destroyed` remains as a staging device; `archived`
is explicit. A single-attach storage attached by several instances is a
configuration error naming the multi-host builders on that runtime.

**Detaching.** Removing a storage from a launched instance's `storages:`
is the one in-place launch-parameter change allowed. The instance root
first runs `unmount storage --instance … --storage … --mount-point …` ON
the instance through the runtime's session mechanism (GCE: IAP-tunnelled
ssh; AWS: SSM) and writes a receipt into the workspace
(`unmount-receipts/<instance>__<storage>.json`); `gate-plan
--require-unmounted <instance>:<storage>` refuses the plan without a
successful receipt. `unmount storage --confirm …` records the operator's
word instead. Where the attachment is a resource (AWS) its destroy is
whitelisted as the detach; on GCE it is an in-place update. The launch
record drops the mount only after the apply. Adding a mount back is a
replacement.

**Moving a mount is a replacement.** A launched instance whose
`storages:` entry names a DIFFERENT storage at the same mount point (or
the same storage at another mount point) is refused by immutability: only
a removal is an in-place change. The way is decommission, edit,
redeclare (the worked example: the coops model moving from
`efs-storage` to a second, empty EFS filesystem `efs-scratch` at the
same `/mnt/efs`). The ORDER matters twice. The decommission goes
first, so the instance is unlaunched when the mount edit is validated.
And the storage root applies BEFORE the instance launch (`just run
storage`, with `apply_storage` true, after the two edits): the instance
root reads the filesystem and access-point ids from the storage root's
state (`data "terraform_remote_state"`), so a launch against an unapplied
storage fails at plan naming a missing output -- loudly, not wrongly, but
a wasted apply. The storage left behind keeps its data: nothing mounts it,
it is still declared, and a declared storage is never destroyed by a
cycle; its retirement is the deliberate act of deleting its entry, which
destroys the filesystem and everything on it in one gated run. The proof
that a machine mounts exactly what its declaration names is one line on
the new machine: the mount point exists on the NEW filesystem id and the
file that was on the old one is absent (`ls: cannot access ...: No such
file or directory`) while the old filesystem still shows its bytes on the
account. Its mirror image -- the SAME storage persisting across a
destroy-and-recreate of the machine -- is "Replacing a durable
instance" above: a declared
storage comes back to the next generation with its data because the
declaration still names it, not because anything remembered the machine.

**Archiving.** `state: archived` on a storage whose builder can archive
(GCE pd and AWS EBS; S3, EFS, GCS and Filestore refuse it at validation)
snapshots it as `csis-<name>-archive` (a GCE snapshot name, or the Name
tag of an EBS snapshot) before the whitelisted destroy of the live
resource; the record keeps the archive name and the state query expects
the disk absent and the snapshot present. Declaring it `active` again
creates the disk *from* that snapshot (on EBS the module resolves the
snapshot by its Name tag at plan time) and deletes the snapshot after the
apply; `destroyed` from `archived` deletes the archive. The storage must
be unattached first. The EBS scripts use the runtime's `--region` and
`--profile` with credentials from the environment; the S3 wipe passes
`--profile` alone.

**Data lifecycles.** A storage may declare a `lifecycle:` its builder
realizes on the resource: S3 `{transition_days, storage_class,
expire_days, prefix}` becomes one bucket lifecycle rule (`STANDARD_IA`,
`ONEZONE_IA`, `INTELLIGENT_TIERING`, `GLACIER_IR`, `GLACIER`,
`DEEP_ARCHIVE`; `storage_class` needs `transition_days`; at least one of
`transition_days`/`expire_days`); EFS `{ia_days, archive_days}` becomes
the filesystem's lifecycle policies (`AFTER_N_DAYS`; only on a filesystem
the module creates). EBS, pd, GCS and Filestore refuse the key. The state
query marks an active storage whose declared lifecycle the resource does
not carry yet as `stale` (run `storage`).

**Builder `variables:`.** A storage builder may declare inputs to its
module call: on EBS `volume_type`, `encrypted`, `tags`; on EFS
`performance_mode`, `encrypted`, `tags`; on S3 `force_destroy`, `tags`;
on the GCP builders `tags` (emitted as labels). The set is typed per
provider from the module's `variables.tf`, so a misspelt key is refused
at load. Precedence: what the builder computes from the item (name,
groups, lifecycle, the restore snapshot, placement) wins; declared
variables win over module defaults; `tags` merge with the item's over the
builder's. Sizing knobs stay builder fields (`size`, `disk_type`, `tier`,
`capacity_gb`, `location`). `parameters` is retired and refused with the
replacement named. On EBS `volume_type` and `size` force REPLACEMENT:
declare what exists unless an archive/restore cycle is intended.

**Transient storages.** A storage declared through an overlay on an
ephemeral runtime is destroyed by the same run's closing phase: the
`retention` lifecycle runs `run storage --only none --no-state-query
--no-commit` once more without the declaring overlay (config-only
overlays and `--apply-runtime` carry over), so it is undeclared there and
goes through the gate.

### `--commit`

`--commit` makes the run's single meta-state commit in the configuration
repository after the run. It stages `meta-state/` and the run's
`generated/` tree **by pathspec** and commits exactly those paths, so
whatever an operator had staged by hand is never swept into a
`cs-image-system run` commit. Before the index is touched:

- files matching `tfplan`, `*.tfplan`, `*.tfstate`, `*.tfstate.*`,
  `*.tfvars`, `*.tfvars.json`, `.envrc`, `*.pem`, `.private_key.*`,
  `.public_key.json` are never staged, whatever the ignore policy says
  (the run warns and excludes them by pathspec at any depth): plans and
  state hold decrypted values;
- every file about to be staged passes the public-safe scanner with the
  configuration's allow list; one finding refuses the whole commit.

A gitignored tree (this repository ignores the fixture's `generated/`) is
skipped with a warning; a root outside a git repository skips the commit.
The message is templated (`cs-image-system run <id>: <lifecycles>`, or
`dry-run generation` for a dry run). Every run stamps its id into the
emission, so a bare `git status` after a run says only that a run
happened.

### Meta-state (`<config root>/meta-state/`)

Committed, human-readable, public-safe: every write passes the scanner's
hard rules and is refused otherwise. It lives outside `generated/` and
survives every wipe. Reality-claiming records (storage transitions, the
`launched` marker, release marks, post-apply pin binds) are written only
when the lifecycle's apply flag was on for the run: a recorder never
claims reality that no apply produced. The one exception is
`state import`, which records reality the query just observed. Reads are
lazy and cached; writes are atomic per file.

| File | Holds | Written by |
| --- | --- | --- |
| `identity.yaml` | the identity read-model: `run`; `groups` (per group: `builder`, `identity_type`, `gid_policy`, `managed`, `is_root`, `members`, `admins`, and under `workload` the outcome of the CI login policy's reconcile); `users`; `user_builders`. Structural facts only: gids travel by terraform reference | identity lifecycle; the workload reconcile after a real identity apply |
| `storage.yaml` | the storage read-model: per storage `builder`, `type`, `plugin`, `attachment_cardinality`, `allowed_groups`, `public_read`, `share_mode`, `posix`, `requested_state` vs `current_state`, `generation`, `attachments`, declared `lifecycle` | storage lifecycle, and after a real storage apply |
| `storage-state.yaml` | the authoritative storage state machine: per storage `state`, `generation`, `facts` and a transition `history` (`from`, `to`, `run`, `generation`, `action`); a destroyed-to-active transition increments the generation | after a real storage apply |
| `lineage.yaml` | every built artifact: `build_id`, `series`, `runtime`, `name`, `parent`, `input_fingerprint` (and `fingerprint_restamped` after a restamp), `run`, stamped `capabilities`, `mods` (name, type, operation, idempotent, content hash, run), `local_mods`, `tests` (`in_bake`, `assertions`), `update`, `chain`; an adopted build carries `imported: true`; a disposal removes the record | after packer builds (manifests); `state import`; `lineage restamp`; `dispose image` |
| `pins.yaml` | `instances` (instance → build) and `images` (`<image>@<runtime>` → parent build), `upgrades` (every move: `kind`, `name`, `from`, `to`, `run`, `op` -- bind, upgrade, follow, dispose, decommission) and `pending_replacements` | first bind, `upgrade`, follow, decommission, dispose |
| `launch-params.yaml` | per instance the recorded launch parameters (mounts, group, enrollment kind, session, machine type), `user_data_sha256`, `run`, the `launched` marker and `launched_run` | instance-image lifecycle; the marker after a real instance apply |
| `runs.yaml` | the run journal (bounded to the last 200 runs; git history is the full record): `run`, `requested`, `dry_run`, `ok`, per-lifecycle `apply` status, `error` | every run |
| `verifications.yaml` | instance verification verdicts, ephemeral and durable (last 500) | `verify instance` |
| `instance-state.yaml` | per name, the durable and ephemeral `generation` counters, `current` (the open generation: `number`, `kind`, `how` -- `observed`, `inferred` or `adopted` -- `opened_run`, `opened_at`, `instance_id`, `provider_hostname`, a `launch_params` snapshot) and an append-only `history` -- closed generations (with `why`, `closed_run`, `closed_at`) and `resized` events (`event: resized`, `from`, `to`, `run`, `at`, on the generation they happened to) in ONE list, in order; nothing is ever deleted from it | `mark_launched` after a real instance apply, the after-apply observation, decommission and the forgets |
| `login-proofs.yaml` | every login proof (last 500): `instance`, `runtime`, `hostname`, `group`, `run`, `as` (client or workload), `time`, `ok`, `skipped`, `checks`, `evidence` | `verify login`, `just ci-login-proof`, the CI job |
| `runtime-facts.yaml` | per runtime (`runtimes.<name>`) what its account answered the networking declaration with: `network` (the VPC id or network name a `default` resolved to), `subnets` and, on AWS, `security_groups` (the declared ids that were checked -- never the account's inventory), `checked_at`. Every load adopts it offline: a `default` network becomes the recorded one, and a declaration the record does not cover (nothing recorded, a subnet or security group never checked, a network that changed since) is a validation error naming `validate --online` | `validate --online` and every real run, before validation; a dry run, `validate`, `config-drift` and `state query` only read it |
| `aliases.txt` | not a record but a pool of memorable names, one free name per line: a person appends lines, a launch that can run comments the first free one out as `# <name>  -- instance <i> as <hostname> <time> run <run>`; absent means no aliases and no error | the run that launches a new durable machine |
| `image-tests.yaml` | the latest post-bake test result per build: `ok`, `run`, `instance`, `runtime`, `time`, `checks` | `verify instance` for images with `tests.post_bake` |
| `releases.yaml` | `releases` (every release ever made: `image`, `build_id`, `model`, `run`, `note`, `name`, `capabilities`) and `current` (per model, the current released build of each series) | `release` |
| `mod-tests.yaml` | modification test results keyed by the mod's content hash (apply + idempotence), so an unchanged mod is not re-tested | `test-mods` |
| `state-locations.yaml` | `workspaces` (per root: the backend's name, `type`, `location`, the settings its `.tfbackend.hcl` carried, `run`) and `migrations` (every performed move: `workspace`, `from`, `to`, `run`, `at`, `serial`, `backup`); the record, not the emission, is what the move guard compares against | every run that generates a terraform root, dry runs included, after generation; `state-migration finish` |

Files under `generated/` are not meta-state: `run-summary.json`,
`state-report.json`, `identity/attributes-plan.json`,
`release/releases.yaml` (a read-model of the current releases) and the
runner scripts. The unmount receipts live in the root's workspace, not in
`meta-state/`.

### Where state lives

Every terraform root keeps its state in exactly one *location*: the tuple
(backend type, container, key), the key normalised (repeated slashes
collapsed, leading and trailing ones stripped, case kept). A root's
location is readable from its `.tfbackend.hcl` beside the root -- for
`s3` the `bucket`, `key`, `region` and the profile; for `local` the `path`;
for `gcs` the `bucket` and `prefix` -- and every lifecycle runner's header
lists them (`# state: workspace <ws> -> s3://…`, `local://…`, `gcs://…`).
A `local` state file never travels with the repository (it is ignored and
never staged), so a real run from another checkout plans against an empty
state and nothing in the system refuses that; keep such roots to one
machine or move them with `--migrate-state`. The
whole mechanism is gated by `use_state_backends` in `cfg/_config.yml`:
off, no backend block, no backend file and no remote-state datasource is
emitted, and none of what follows applies. Off is refused by `validate`
whenever a root would read another's outputs (an instance root reads the
storage and identity roots, a storage root with group gids reads the
identity root), because those references are written either way and
would name data sources the root never declares. In
practice every tree that launches anything runs with it on.

Three backend types exist: `s3` -- a bucket, `s3://<bucket>/<key>`
-- `local` -- a file on disk, `local://<directory>/<root>.tfstate`, the
directory relative to the configuration root, needing no credentials -- and
`gcs` -- a Google Cloud Storage bucket, `gcs://<bucket>/<prefix>/<root>/default.tfstate`,
declared in the fixture and in the live tree (commented out) and bound to
nothing, since the reference keeps its GCE roots on S3 for now (its
choice, not a rule of the system). A
type is a plugin (a model and a kind that renders the location, the backend
file and a consumer's data source; the S3 plugin's README has the recipe),
and the collector names no field of any type. The fixture's identity roots
use `local` and its storage roots a second S3 bucket, so its roots read
each other's state across types and buckets; the live configuration keeps
every root on its default S3 backend, which is that configuration's
choice: a tree declares its managers and may spread its roots over
several.

The backend a root uses resolves through a chain: its own
`state_configuration` when it names a backend, else its runtime's, else
the one backend marked `is_default`. `validate` (and every run, before
anything is emitted) resolves every root's location from the declarations
and refuses two roots that would share one state object -- the same bucket
and normalised prefix under two backend names, two root names that
collapse under the state-file naming, a `//` against a `/` -- naming both
roots and the object. A consumer root reading a producer's state across
backends (an instance root reading a storage root's, a storage root
reading the identity root's) emits a `terraform_remote_state` datasource
carrying the producer's bucket, key and region, whichever backend it is
in.

Both the check and the record are the tofu-roots hook plugin's, installed
through the run hooks whenever the package is present: the core itself
knows no state backend. Every run records each generated root's resolved
location in `meta-state/state-locations.yaml` (the record, not the
emission, is the memory: `generated/` can be pruned or regenerated). A later run whose
resolution differs from the record is refused while the records show live
resources in that root -- a storage not destroyed, a group or user the
identity read-model attributes to the root after an applied identity run,
an instance pinned to a build -- because the new location is empty, so the
next plan would create everything again and strand the old state. The
refusal names the root, both locations, what stands in it and both ways
out. A root with nothing deployed moves freely, with one INFO line.

**Moving a root's state** is an operation, never an override:

```sh
just cli --no-dry-run run storage --migrate-state aws-efs
```

`--migrate-state <root>` (repeatable) makes that root's runner, in order:
`state-migration begin` (the previous location from the record is written
beside the root as `<root>.tfbackend.previous.hcl`; the new location must
be empty -- one that holds state of another lineage is a collision and is
refused; the old state is pulled to `<root>.backup-<run>.tfstate`, which is
kept and never deleted by the operation; the root is left initialised
against the previous location), then `init -input=false -migrate-state
-force-copy -backend-config=<root>.tfbackend.hcl` (tofu copies the state;
every normal run emits `-reconfigure`, which means "do NOT migrate", so
this cannot be done by hand under the system's own flags), then
`plan -detailed-exitcode` (the move is accepted only when the plan at the
new location reports no changes: a change stops the runner there), the
gate, and `state-migration finish`, which records the move in meta-state
(from, to, when, the state serial, the backup) and moves the root's
location record. A move that already happened (the new location holds the
same lineage) is recognised and recorded without copying. A dry run
refuses the flag; CI never migrates (its records are dry and no recipe
carries the flag). Giving resources up is a different act: correct the
records through the state query's import and forget paths, never rebind
past the guard.

### Run outputs and exit codes

A run ends with `generated/run-summary.json`: `run_id`, `requested`,
`dry_run`, `ok`, `validation_errors`, per-lifecycle results, `apply`
(per lifecycle: `executed`, `dry-run`, `no-script`, `failed`,
`not-attempted`, `stale-script-skipped`), `meta_state_commit`, `error`,
`state` (the pre-run state query's counts), `overlays`, `undeclared`,
`bake_plan`, `state_bindings` (per lifecycle, each terraform root and
the state file it binds to: the state-isolation evidence the tofu-roots
hook plugin answers; every lifecycle is named, bound to nothing where no
plugin answers). The pre-run state query writes `generated/state-report.json`.
Both are **run-local**: the emitted `generated/.gitignore` names them, a
`--commit` run never stages them, and a run whose configuration
repository tracked them from an older tree removes them from the index
(the files stay on disk). `generated/final_execution.sh` and
`meta-state/runs.yaml` are records and are committed.

Every command exits 0 on success. The classes are: 1, the operation
failed or was refused; 2, usage (a missing argument, nothing selected, a
name the command does not know); 3, a gate refused; 4, a write that is
switched off; 75, "not now" (`EX_TEMPFAIL`: try again later, nothing
changed).

| Command | Exit | Meaning |
| --- | --- | --- |
| `run` | 1 | any failure (validation, generation, apply, hard drift, a runtime's online networking check refused -- a lapsed session included, since a real run checks the networking before it validates); a configuration that fails to LOAD exits 1 too, as `Error reading config file : <e>` followed by the traceback |
| `run` | 2 | no or unknown lifecycle; unknown `--apply-runtime`/`--only-runtime`; an `--only` name that `--only-runtime` cannot honour (not baked on that runtime, written `@` another, or `none` beside names) |
| `validate` | 1 | any rule fails; generates nothing |
| `preflight` | 2 | a session absent or expired (the configuration loads without it -- a load reaches no cloud -- but a run, `validate --online` and the deferred steps cannot use it), no runtimes, or a credential-shaped environment variable (`TF_VAR_*`, `CSIS_*`, plus every prefix the installed runtimes and identity plugins declare: `AWS_*`, `GOOGLE_*`, `CLOUDSDK_*`, `DOCKER_*`, `OKTA_*`) that is set but EMPTY -- reported by name, never by value. A configuration that fails to load is the loader's one line and exit code, before any session verdict |
| `validate --online` | 2 | a runtime's online networking check could not run: a lapsed session (the same one line a load-time failure used to get, with the renew command); 1 when the check itself refuses the declaration (a subnet outside the VPC) or any rule fails afterwards |
| `preflight --strict` | 1 | a session expires within `config.preflight.expected_run_minutes` (default 30) |
| `state query` | 1 | hard drift |
| `state query --strict` | 1 | hard drift; any drift class but `stale`; `unavailable` (a provider that could not answer); a session expiring within the window |
| `gate-plan` | 3 | destroy not whitelisted, stale or missing planfile, detach not unmounted; 2 with no plan input |
| `apply-check` | 3 | the flag is off now, no `cfg/_config.yml` found, or an overlay is gone |
| `public-safe` | 1 | a finding; 2 when `--staged` is used outside a git repository |
| `mask`, `materialize` | 1 | the identity cannot open a marker, a file does not parse or a marker is malformed; `mask` ends with exit 1 naming the file for every per-file failure, a missing identity included, so a masking pass never passes silently |
| `verify login` (the okta-opa plugin's command) | 1 | the login proof failed (registration count, resolve, login); 2 with no standing instance |
| `forget instance` | 2 | the instance is still declared |
| `workload describe --env` (the okta-opa plugin's command) | 2 | the builder names no workload connection or role |
| `workload token` (the okta-opa plugin's command) | 1 | the connection issued nothing; 2 outside an Actions job, or with a connection or role name it cannot find |
| `state-migration`, `prune-attachments` | 1 | the step failed (a pull, a list or a removal); the runner stops; 2 on a wrong action, a step without its inputs, or an unknown builder |
| `run --migrate-state` under a dry run | 2 | a move needs `--no-dry-run` |
| `--locked` (global) | 75 | another command holds the tofu lock (`.tofu-plugin-cache/.lock`); the holder's pid is named; 2 without `TF_PLUGIN_CACHE_DIR` in the environment |
| `empty --runtime` | 1 | a leftover or drift; 2 when the runtime cannot answer |
| `test-mods` | 1 | a failed or non-idempotent mod; with `--strict`, any skip |
| `release` | 1 | refused (evidence missing); 2 with no image and no `--declared` |
| `dispose`, `upgrade`, `verify`, `unmount`, `lineage *`, `decrypt`, `reencrypt`, `runtime describe` | 1 | refused or failed |
| `config-drift` | 1 | the committed emission is BEHIND the declarations (the diff is printed); 2 when nothing is committed under `generated/` or the dry run itself fails |
| `runtime-unchanged` | 1 | the runtime's emission changed since the ref (the diff is printed); 0 when only the vendor's newest image moved under a base not yet baked; 2 for an unknown runtime |
| `init-config` | 1 | a release-owned file differs and `--force` was not given; 2 for an unknown starter |
| `identity-attributes` | 4 | attribute writes are disabled (`--apply`); 3 on an invalid plan or a provider conflict |
| `test`, `cleanup` | 2 | retired names; the message names the replacement |
| `scripts/publish-target-ready`, `just index-ready`, `just publish` | 75 | the index cannot take an upload now (an endpoint or a project page down; PyPI's limit on new projects) -- nothing changed, try again later; `publish-target-ready` exits 2 for a target it has no checker for and, with `--all-held`, 1 unless every project holds the version |

### The state query

`state query [--strict] [--json]` asks every plugin for its provider's
view of what the system manages (images by lineage tags, storages by
name, groups by gid, memberships and enrollment tokens by API, and each
managed group's resource group and policies against what the identity
module makes) and diffs it against meta-state. It touches nothing and writes
`generated/state-report.json`. Every `run` executes it first
(`--no-state-query` keeps the existing report) and refuses on `[HARD]`
drift. Drift classes:

| Class | Meaning | Hard when |
| --- | --- | --- |
| `missing` | recorded but not found | the record claims liveness: an active storage, a managed group, an enrollment token, a pin to a build lineage does not record |
| `stale` | a pin behind its series head; an active storage lacking its declared lifecycle | never (a policy state, not drift) |
| `changed` | an image's lineage tags disagree with its record; an instance booted a different image; a standing ephemeral (the line says whether `teardown_after` has elapsed or what the policy expects) | never |
| `foreign` | exists, carries our tags, not in the records (e.g. AMIs from failed bakes) | never |
| `unavailable:` | a provider could not answer; no claim is made | never |

The report is expected EMPTY apart from `unavailable:` lines: every line
is actionable, none is "known benign". A run re-tags its own builds after
every bake so lineage tags stay resolved. `changed` on an image means the
tags disagree with the record; the record is the truth (written after the
bake), so `lineage relabel --runtime <rt> [--build <id>]...` re-tags
every recorded build whose real tags differ through the runtime's retag
hook (AWS `create-tags`, GCE `setLabels`), with no meta-state change.
`restamp` fixes the record side, `relabel` the tag side. `relabel`
(without `--build`) also gives the configuration's id, `csis_config`,
to every declared storage and every launched machine on the runtime
that stands without it -- the volumes, filesystems, buckets, disks,
shares and machines made by an older tree, before everything the
system makes carried the id -- through each
storage builder's retag hook and the runtime's; a thing that already
carries another configuration's id is never touched.

An enrollment token deleted out of band is HARD drift, and because the
oktapam provider ERRORS on refresh rather than planning a recreate, the
message names the repair: `tofu state rm` the token, then a gated
identity apply.

**A group's OPA objects rewritten in place** are `changed` drift.
Another configuration that holds the same objects in its own tofu state
can rewrite them keeping their ids -- the resource group's delegated
admin, the policies' rule name and descriptions -- and a query that read
only the CI policy would see no more than that it no longer mirrors the
user policy
([INCIDENTS.md](INCIDENTS.md#the-reference-trees-identity-objects-were-rewritten-by-another-configuration)).
So the query reads each managed group's resource group
(`<g>_rg`) and its user and admin policies back from OPA and compares
them with what `tfmodules/okta_opa_module` makes for that group: the
descriptions, the delegated admin (the group's own `<g>_admin`), each
policy's principal, rule name, ssh privilege, gateway conditions and
server labels (`sftd.tx.group=<g>`, `system.os_type=linux`, compared
whole, so an added label counts). A difference is `changed` and names
each field (`delegated_admins: ['admin_admin'] != ['basic_admin']`); an
absent object is `missing`; neither is hard, because the identity apply
that repairs them is the run a hard drift would refuse. A test holds the
expectations to the module's text. If another configuration manages the
same objects, the identity apply puts them back and that configuration's
next apply undoes it again: that side must let go first, with `tofu
state rm` there and never a destroy. The query does not plan: CI's read
role holds no state object, by design.

A managed group the identity provider could not be ASKED about -- a
lapsed or unsourced key pair (`HTTP 401`), no network -- is an
`unavailable:` line naming the group and the error, never a `missing`
group: the provider made no claim. Only an answered absence (a 404) is
`missing … [HARD]`. The strict query refuses either way (only `stale` is
tolerated), but for the stated reason, and a plain run warns and goes on
as it does for an unreachable cloud.

`state import [--no-images] [--no-storages]` adopts *foreign* artifacts
into meta-state. It writes meta-state only, never the cloud, OPA or tofu
state; importing into tofu state stays a deliberate human step. An
adopted image's lineage record is built from its tags (`imported:
true`): series, run, parent and the first 16 characters of the input
fingerprint, with no mods and no in-bake record. It counts as current
when that prefix matches the tree's fingerprint today, so adopting a
build of today's inputs stops it being baked again; it is not covered
by the release grace, which needs the in-bake record, so a durable
instance is upgraded onto a baked build, not an adopted one.
Adopting is also the way out for an image that stands unrecorded for
any other reason ("When a bake fails").

**Sessions.** `state query`, every run, `preflight` and `just
cloud-preflight` print one `session:` line per credential source, naming
every runtime and state backend that uses it. The core reads no credential
cache itself: each runtime plugin and each state-backend plugin answers
the contract's session hook (`session_status`) with what it read, a fixed
expiry when one is readable, whether the credential renews itself, and
the command that renews it; the core prints and judges the answer. Never
a credential value. The AWS runtime reads an SSO profile's token expiry
from `~/.aws/sso/cache` (static keys and non-SSO profiles have no
readable expiry and are present but NOT JUDGED); the GCP runtime reads
whether Application Default Credentials exist; the docker runtime asks
its daemon `docker version`; the `s3` and `gcs` backends reach the same
reading through their runtime's class, so a backend's bucket credentials
are preflighted too. A session that is expired or expires within
`config.preflight.expected_run_minutes` (default 30) is flagged; the
strict query refuses on it and a run warns. Loading the configuration
needs no session at all: a load reaches no cloud (the runtimes'
networking facts come from `meta-state/runtime-facts.yaml`), so
`validate`, a dry run, `config-drift` and `preflight` itself work on an
expired session, and what refuses on one is what actually calls the
provider -- a real run (its networking check runs before validation),
`validate --online`, the state query and the deferred steps. The
`preflight` command loads the tree and reads the sessions from the
loaded builders, so it needs the age identity (`.envrc`) like every
other command and prints the loader's one line when the tree does not
load. An `sso-session` profile (the live
`noaa`) holds a one-hour access token and a refresh token. While the
access token has not lapsed the AWS plugin reports it present and
self-renewing (it asks the cloud nothing); once it has lapsed the plugin
makes ONE read-only call (`aws sts get-caller-identity --profile <p>`),
which refreshes the cache when the refresh token still works and says so
when it does not: a lapsed token the CLI cannot refresh is EXPIRED, exit
2, with the login command, because a token that answers `Token has
expired and refresh failed` is not one that "refreshes itself", and
`preflight` must never say so of it. A session that lapses mid-run is
environmental, not a defect: it costs the legs that were running, and
the repair is the renew command the session line names (for the AWS
profile, `aws sso login --profile <p>`) then `just full-test-legs`
(never the whole bar).

## 2. The developer workflow

### Setting up

`just init` runs `uv sync --all-extras` and installs the pre-commit hook
(`git config core.hooksPath .githooks`). It is idempotent. Python is run
as `uv run python`; the CLI as `uv run cs-image-system` (what every recipe
does). The Justfile here is the DEVELOPER's:
the contract, the bar's parts, the golden, the release, and `just cli ...`
against the reference configuration for the system's own live proofs. The
cycle recipes (`cloud-*`, `ci-login-proof`, `sft-install`) belong to a
configuration repository's own Justfile, which the release ships and
`cs-image-system init-config` writes; the reference configuration has one
and its cycles run from there (section 4).

### The bar: `just test`

`just test` is the local acceptance bar, every check blocking: `lint`
(ruff over `packages` and `tests`), `typecheck` (pyright, basic mode, 0
errors), `pytest` (the unit tests, the golden emission included). `just
verify` is its alias. It needs no live configuration and no credentials:
the tests own the frozen fixture and export its TEST identity themselves.
There is no looser recipe: the contract test asserts that a
`ci` recipe with a non-blocking type-check stays gone.

The tests run over private copies of the fixture with every cloud, Okta
and tool execution stubbed; `just v2-test` runs the gate tests alone
(`tests/test_v2_*.py`).

### `just full-test`

Everything `test` does plus the slow and external legs:

1. the modification tests under docker (`just test-mods --strict`), when
   `docker info` succeeds;
2. only when the reference configuration is present AND `just preflight`
   finds every runtime session present: a headless dry `run --all` over a
   private copy of it (its `.git`, `generated/`, `_private/` and
   `.tofu-plugin-cache/` excluded; the copy's `tofu init`s use this
   repository's own provider cache, so the gigabytes of the
   configuration's are never copied; it carries its own `tfmodules/`,
   so nothing is copied beside it), followed by
   `state query --strict` over the copy. A configuration repository's
   own `full-test` copies it the same way.

A leg whose prerequisite is absent reports `SKIPPED` loudly with its
reason and does not fail the run; a leg that runs and fails does.
Identity credentials (`OKTA_API_*`, `TF_VAR_<team>_*`) are not gated: a
dry run without them warns and skips the identity roots' plan. Run it
before declaring a phase done and before any release.

### The golden

[GOLDEN.md](../GOLDEN.md) describes it in full. `tests/fixtures/v2_golden/`
is exactly what `run --all` emits over the frozen fixture plus three
meta-state files (`identity.yaml`, `storage.yaml`, `launch-params.yaml`);
`tests/test_v2_golden.py` regenerates the emission in memory and reports
a removed file, an added file, and a unified diff per changed file.

A byte-identical golden is the acceptance proof for a refactor. When a
change is meant to move the emission, run `just golden-regen`
(`uv run python tests/golden.py`), **read the diff**, and say in the commit
message that the move is intended. Regenerating to make a test pass is
how a defect becomes the expected output. Two traps: provisioned content
(playbooks, scripts) is hashed, so a comment change there moves
`content_hash` and `csis_fingerprint` and would re-bake images; a copy of
the configuration needs the modules beside it (`cs-image-system modules
--write <copy>/../tfmodules` writes them from the installed plugins).

### What a run's log shows of the commands it ran

Every command the running process spawns in place of a script line
(`tofu init`/`plan`/`apply`, a packer build, the nested teardown run) has
its captured output in the log: the last 40 lines of stdout and of stderr
at INFO under the command's name, the whole of it at DEBUG, colour codes
stripped. That is where tofu's `Plan: 0 to add, 1 to change, 0 to
destroy` and `Apply complete!` are read during an applying run, so the
apply's verdict is readable in the log and not only a failure's
([INCIDENTS.md](INCIDENTS.md#the-applys-verdict-could-not-be-read-in-the-log));
`tofu show tfplan` in the root is still a way to read the plan
afterwards, since the runner leaves the plan file behind. The deferred
steps that are the system's own commands (`gate-plan`, `apply-check`,
`prune-attachments`, `release --declared`, ...) run in the process
itself, so their output is not captured and tailed: a verdict line such
as `Plan passes the apply gate.` or `released: ...` prints where it is
produced, on the run's own stdout or stderr, ahead of the step that
follows it. A script run by hand (`run-*.sh`) shows everything.

### `config-drift` and `fixture-live`

Is the committed emission current with the declarations? `cs-image-system
config-drift` (`just config-drift` in a configuration repository and
`just cli config-drift` here) runs a headless dry `run --all` in a
process of its own over a private copy of the configuration and compares
it with the `generated/` tree committed at its HEAD. The copy leaves out
`.git`, `generated/`, `_private/` and the provider cache
(`.tofu-plugin-cache`, or wherever `TF_PLUGIN_CACHE_DIR` points inside
the tree): the copy's run reads the original's cache through that
variable, because copying it (gigabytes) can fill a disk. The run takes
minutes, nearly all of it a `tofu init` per root, so the command says on
stderr what it is doing as it goes -- the copy with its size and time,
each lifecycle as it starts, each root's `init`, the comparison, the
total -- and never looks stuck. Tool residue (`.terraform`,
`.terraform.lock.hcl`, `tfplan`, `temp_assets`), the run-local files
(`run-summary.json`, `state-report.json`, `generated/release/release`,
`generated/retention/retention`), run ids and the run's date stamp in
image names are normalised, and the runner scripts lose the two lines
per root that only an APPLYING run emits (`apply-check` and `tofu apply`;
an applying run commits the script it executed, and those lines are a
function of the invocation, not of the configuration, so an applying
run's commit never fails the next `config-drift` as "BEHIND"); nothing
else legitimately differs, so a machine's absolute
path appearing in the emission IS drift. Exit 0 when
current, 1 with the diff when the committed emission is BEHIND the
declarations, 2 when nothing is committed under `generated/` or the dry
run itself fails. A dry run's `init` skips the backend, so no state
access is needed. `cs-image-system runtime-unchanged <rt> [--ref REF]`
is the same comparison for one runtime's emission directories across
records (what CI's guard uses), and it reads the vendor's newest image
moving under a base with no build yet the same way: named, and exit 0,
because a vendor move alone gives the guard nothing to apply
([INCIDENTS.md](INCIDENTS.md#the-vendors-newest-image-moved-under-a-base-this-tree-had-not-baked)).
A diff too long to show whole is never read as a vendor move, by either
command.

`just fixture-live` is the system's own live proof and what
this repository's CI `live` job runs: with real sessions (the frozen
fixture names the real account's networks, project and OPA team) and the
fixture's committed TEST identity, `validate` over the fixture, a headless
dry `run --all --no-state-query` over a private copy with the installed
modules written beside it (`cs-image-system modules --write`; the state
query is off because the fixture's declarations are
synthetic and reality would read as drift), then `test-mods --strict`
over the copy under docker (skipped loudly without docker).

### Public-safe and the hook

Both repositories are public by design, so one scanner
([public_safe.py](../packages/base/src/cs_image_system/base/public_safe.py))
sits wherever a commit happens and reads bytes (a zipped `tfplan` is
opened and its members scanned):

- **refused by name** at any depth: `tfplan`, `*.tfplan`, `*.tfstate`,
  `*.tfstate.*`, `*.tfvars`, `*.tfvars.json`, `.envrc`, `*.pem`,
  `.private_key.*`, `.public_key.json`;
- **hard rules**, everywhere including prose and tests: a JWT, a PEM
  private-key body, an AWS access key, a GCP service-account file, a Slack
  or GitHub token, an age identity, a `TF_VAR_*=` assignment with a
  literal value;
- **soft rules**, skipped in `*.md`, `docs/` and Python test modules: an
  email address (example domains excepted) and a long mixed-case base64
  string;
- **public by structure**, blanked before the rules run: `ENC[age:…]`
  ciphertext, age public keys, lock-file hashes, SSH public keys,
  scp-style git URLs.

Everything else accepted as public is listed **by decision, with the
reason**, in `cfg/_config.yml` `public_safe.allow`: a substring, or
`path:<glob>` for a file accepted whole (the fixture's TEST identity).
A finding names the path, the rule and the first characters of the value,
never the value.

Where it runs: a `--commit` run scans every file it is about to stage;
the plain [.githooks/pre-commit](../.githooks/pre-commit) runs
`public-safe --staged` on every hand commit in both repositories (`just
hooks` installs it here, `just init` (or `just hooks`) in a configuration
repository, whose Justfile the release ships; the hook
finds `cs-image-system` on `PATH` or in either checkout's `.venv`); `just
public-safe` scans this checkout (tracked files plus untracked files that
are not ignored, with the fixture's allow list) and CI's `verify` job
runs it; a configuration repository's `just public-safe` scans its tree with its
own allow list, and runs before any publication. Allow a value by
decision, never by bypassing the hook.

### The frozen fixture and the reference configuration

Every recipe that reads the reference configuration (`cli`, `test-mods`,
`preflight`, `reuse-live`, `full-test-legs`) depends on the private
`config-guard` recipe, which exits 2 with the clone command when
`<config_root>/cfg/_config.yml` is missing. `just test` never needs it.
The reference configuration stands alone: its own `Justfile`,
workflows, hook, `.gitignore`, `tfmodules/` and `.csis-version` come
from the release through `init-config`, its
`module_source_base` is its own `tfmodules`, and its cycles run from its
checkout (`cd ../cs-image-system-testconfig && just cloud-cycle
gcloud-east1`, with `CSIS` in its `.envrc` pointing at this checkout's
venv while the system is developed). `just cli ...` here reads it for the
system's own proofs and nothing more.

The fixture carries no `meta-state/` and no generated output; its instance
subjects (`test`, `test2`, `gce-test`) are declared in its own
`instances/instances.yaml`; its rosters are encrypted entry by entry to
the fixture's own committed TEST identity (`.age-identity`, public key
`.age-recipient`), which the harness exports as `CSIS_CONFIG_IDENTITY`.
`tests/test_fixture_personas.py` pins that a real roster cannot return;
the fixture's allow list names no real domain. Never put a real name in
the fixture, the golden or a test.

A change that touches the reference configuration is committed and
pushed on that repository's `develop` branch as part of the same piece
of work; its `main` is what its own CI performs on.

### Branches

Every piece of work happens on its own feature branch
(`git flow feature start <name>` with git-flow-next, or
`git checkout -b feature/<name>` from `develop`) and finishes with a
**squash-merge** into `develop`; the feature branch is **kept** and
pushed, never deleted:

```sh
git flow feature finish <name> --squash --keep --push --squash-message "<summary>"
git diff develop feature/<name>    # must be empty
```

The squash keeps `develop` readable as one commit per piece of work; the
kept branch preserves the step-by-step history. Never commit directly to
`develop` or `main`; never force-push a shared branch. A
documentation-only change skips the bar but not the tests that read the
documents, which run alone for such a change (`just test-one
tests/test_docs_contract.py ...`; say so). Four tests are about the
documents: `tests/test_docs_contract.py` reads
[DAILY_DRIVER.md](DAILY_DRIVER.md), the root `README.md`,
[PLUGINS.md](PLUGINS.md), every package `README.md` and every starter's
`CI_SETUP.md` (the README contract, every relative link);
`tests/test_docs_examples.py` reads every starter as a team holds it
(rendered from `docs/examples/_skeleton/` and the starter's own directory,
the installed plugins' modules under `tfmodules/`), its `README.md` and
`CI_SETUP.md` included, and holds the built wheel equal to the source;
`tests/test_docs_image_sources.py` reads every runtime plugin's
`README.md` image-query table and the contract README against the
code; `tests/test_v2_ci_runner.py` reads [CI_RUNNER.md](CI_RUNNER.md)'s
tool table against the runner image's Dockerfile and probe and the
starters' `executables.yml`. Others pin a phrase or a count in this
page, [CONFIGURATION.md](CONFIGURATION.md) and the daily driver
(`tests/test_v2_stage_103.py`, `test_v2_stage_105.py`,
`test_v2_stage_107.py`, `test_v2_hygiene_xii_decisions.py`,
`test_v2_hygiene_xx.py`, `test_v2_dev_pin_install.py`), so a change to
one of those three pages runs them too; `grep -l '<page>.md' tests/*.py`
names the set.

### `just build`, `just release`, `just publish`, `just publish-tree`

`just build` packages the system and every workspace member (sdist +
wheel: forty-four files) under `dist/`; no tests. The builds are
reproducible -- two builds of one tree are byte-identical -- which is what
lets CI check a tag against the index instead of uploading it again.

`just release <target> [test|pypi] [yes]` cuts a release and
publishes it. `<target>` is a part for `bump-my-version` -- `patch`,
`minor` or `major` open the next version as its first development
release (`0.1.0` → `0.1.1.dev1`), `dev` is the next development release
of the same version (`0.1.1.dev1` → `0.1.1.dev2`), `stage` finalises it
(`0.1.1.dev2` → `0.1.1`) -- or an explicit version. The index is `test`
(TestPyPI, the default) or `pypi`. `yes` as the third argument is the dry
form: the probes and the version, nothing changed. The real form, in
order:

1. the probes, before anything changes: the checkout is on `main`
   (every release, development or final, is cut there, so a version can
   never be cut from a working branch; the Justfile's `release_branch`
   names it once) and `develop` is an ancestor of it, so a release never
   leaves landed work behind; or the checkout is on a maintenance branch
   `release/<major.minor>`, an old version's fix cut while `develop` is
   past it, which skips the ancestor check; the index can take an upload and
   holds the version for no project (`scripts/publish-target-ready`,
   below; a version is never re-cut, because a deleted version's files
   can never be uploaded again); the token is set
   (`UV_PUBLISH_TOKEN`, else `TEST_PYPI_TOKEN` / `PYPI_TOKEN`); no
   `v<version>` tag exists here (the local record of a version that was
   cut, deleted from the index or not); `dev` on a final version is
   refused (open the next version with `patch` first);
2. the probes (`_release-probes`, one line each, before
   anything changes; the dry form prints the same verdicts): the venv is
   in step with the lock (`uv sync --all-extras --check`, because every
   recipe runs `uv run --no-sync` and a venv behind the checkout answers
   with stale metadata) and, for PyPI, docker answers and every runtime
   session of the live configuration is present (`just preflight`; a
   `full-test` without them would skip its live legs, which a release
   cannot accept), said with the minutes the soonest-expiring session has left
   (`scripts/session-minutes-left`, which reads each plugin's own expiry
   -- for an SSO profile the cached access token's `expiresAt` -- even
   where the session renews itself, because the CLI's refresh can fail
   on a lapsed token). A
   PyPI release takes about an hour, start to commit, and an SSO login
   lasts one, so under an hour left the line says to log in again from
   a second terminal about halfway (a running run picks the new token
   up). Said, not refused on; a token that has already lapsed (which
   `preflight` judges too) is refused, naming `aws sso login`. A refusal
   names its remedy and changes nothing;
   then a clean working tree (the refusal names the remedy; the IDE's
   workspace file is untracked, so the editor rewriting it cannot dirty
   the tree), then the gate: for TestPyPI the bar
   (`just test`); for PyPI `just full-test`, the modification-test
   evidence at `<config_root>/meta-state/mod-tests.yaml` (written by
   `full-test` with docker in the LIVE configuration) and a live checkout
   clean apart from it; then the index is asked AGAIN, since the bar
   takes twenty minutes and an index that went down meanwhile should
   leave a clean tree, not a bump to discard;
3. `bump-my-version bump <part>` (or `--new-version`): every `version =`
   line and every `== <version>` pin between the packages, in one move
   (`[tool.bumpversion]` in the root `pyproject.toml`); then `uv lock`;
4. `just publish <index>` -- BEFORE the commit and the tag, so a failed
   upload never leaves a tagged, unpublished version. What to do with
   the uncommitted bump depends on how far the upload got, and the
   release says which:
   - **no project holds the version:** discard the bump
     (`git checkout -- pyproject.toml packages/*/pyproject.toml uv.lock`);
   - **some projects hold it** (the upload stopped part-way): KEEP the
     bump, because those files can never be uploaded again under
     another version. Run `just publish <index>` until every project
     holds it (a day apart when PyPI's limit on new projects stopped it,
     below), then `just release-finish <index>`, which makes step 5's
     commits and the tag;
5. for PyPI, the mod-test evidence committed in the live repository
   (`release <v>: modification-test evidence`); then `pyproject.toml`,
   `packages/*/pyproject.toml` and `uv.lock` committed here
   (`release <v>`) and the annotated tag `v<version>`.

Nothing is pushed. The closing line names the operator's two acts: `git
push --follow-tags origin main`, whose tag makes CI's `publish` job check
the release against the index (it uploads nothing the index already
holds), and then `develop` taking `main` back by fast-forward (`git
checkout develop && git merge --ff-only main && git push origin
develop`).

**The release branch.** `develop` is where work is done and
`main` is where releases live. `main` is always `develop` plus release
commits and moves only by fast-forward: before a release `main` takes
`develop` (`git checkout main && git merge --ff-only develop`), the
release commit and the tag land on `main`, and `develop` takes `main`
back the same way, so both carry the release and both histories stay
linear. `develop` may be ahead of `main` for as long as it likes and is
behind it only between the release commit and the fast-forward back. If
a stage landed on `develop` during a release the fast-forward back
refuses; the fallback is one merge commit of `main` into `develop`,
never a rebase of pushed commits. A failed release leaves its evidence
on `main` alone: an uncommitted bump in `main`'s checkout, or `main` at
`develop`'s HEAD without a tag when the release was abandoned after the
fast-forward. `git flow release` is not used (its finish makes a merge
commit and a back-merge). A maintenance branch `release/<major.minor>`
is accepted by both recipes for the day a tree needs a fix to an old
version without taking the work since (0.1.5 cut from 0.1.4 plus one
fix while `develop` is past it); the index refuses a re-cut and
`bump-my-version` takes an explicit version, so nothing else is built
for it until one is needed. A tree older than 0.1.6 cut its releases on
`develop` and left `main` unused ([CHANGES.md](CHANGES.md#s107)).

**Finishing a release by hand: `just release-finish <index>`.** For a
release whose upload stopped part-way and was completed with `just
publish`. On `main` (or a maintenance branch), with the bump uncommitted
and nothing else changed, it asks the venv probe above, then asks the index whether every project holds the version
(`scripts/publish-target-ready --all-held`; the index's pages lag an
upload by minutes, so a count just after one can be short), and only
then makes the evidence commit in the live repository (PyPI), the
`release <v>` commit and the tag. It pushes nothing.

**A first release to PyPI takes days.** Production PyPI lets an account
create only a few NEW projects a day. A first release of many projects
is refused at the fifth new project of each run with `429 Too many new
projects created`: a retry an hour and a half later is still refused
and one a day later works, so such a release goes up four projects a
day. Warehouse's published
default (20 an hour) is not what production enforces. `just publish`
reads that 429 as exit 75, "not now", names the projects left, and says
to run it again in a day; nothing is wrong with the release, and the
bump stays uncommitted until `release-finish`. A later release creates
no new project and is not limited. To go faster, a maintainer can ask
PyPI's administrators for a one-time lift through PyPI's support tracker
(github.com/pypi/support), naming the account, the projects and why.

**The index is asked first.** `scripts/publish-target-ready
<test|pypi>` (and `just index-ready [test|pypi]`, the probe alone, one
line per endpoint) reads the target's `[[tool.uv.index]]` entry and
asks two things of it: the upload endpoint (`publish-url`) answers
below 500 to a request that uploads nothing, and the simple index
answers for EVERY project a release uploads -- the root project and each
`packages/*` member, twenty-three today -- with 200, or 404 for a project
it has never seen. With `--version` it also says which projects already
hold that version: none (a fresh release), all, or some (a partial
upload, which `just publish` completes). Exit 0 is ready; **75 is "not
now"**, the code `--locked` uses for "try again later": the index's
condition, not the release's, with nothing changed; 2 is a target it
has no checker for, which is refused by name, never passed (a new
publish target owes its checker in the change that adds it). The pages it
reads are cached, so a count taken minutes after an upload can lag it,
and it says so; `--all-held` (release-finish's form) exits 1 unless
every project holds the version. What it cannot check is that the token
will be accepted: the index has no call that says so without an upload,
and the probe says so -- `just publish` proves it (below). `just
index-ready test wait` probes every minute until the index is ready,
two hours at most, one line per attempt, for the night the index's
upload endpoint and most project pages answer 503 for hours while one
page still answers 200; asking one page alone would let a release run
its whole bar before the upload failed
([INCIDENTS.md](INCIDENTS.md#testpypi-was-down-and-a-release-found-it-only-at-the-upload)).
`release` asks before its other probes and again after the bar;
`publish` asks first, and reports a partial upload rather than refusing
it.

`just publish [test|pypi]` builds and uploads the version in the tree:
the index asked first (above), `dist/` cleaned, `just build`, then
`scripts/publish-dist`, which runs `uv publish --index <name>` once per
project:

- **one project at a time, its sdist and wheel together, in dependency
  order** -- the base first, then the plugins, `cs-image-system-system`,
  and `cs-image-system` last -- so an upload that is cut off leaves only
  complete projects, and the top-level package appears only when
  everything it needs is there (an upload that sends the top-level
  package before its dependencies leaves `pip install
  cs-image-system==<version>` unable to resolve until the rest arrive);
- **a failure shows its cause**: the `error:` and `cause:` lines uv
  wrote, without the index's HTML page, and the file that holds the
  whole output (a resumed run's "already exists" lines would otherwise
  push the cause out of a summary of the first eight lines);
- **PyPI's 429** ("Too many new projects created") is exit 75 with the
  projects left (above);
- **the token is proved even when nothing was uploaded.** A file the
  index already holds is skipped without credentials, so a repository
  secret that is not a working token could otherwise go unseen for
  weeks. When every file was already there,
  one file is sent again without the check: the index checks the
  credentials before it looks for a duplicate (Warehouse's upload view)
  and answers an identical file with 200, storing nothing, so 200 -- or
  400 "File already exists" -- proves the token and 403 refuses it.

The
endpoints are the `[[tool.uv.index]]` entries in the root
`pyproject.toml` -- `testpypi` uploads to `https://test.pypi.org/legacy/`
and is checked against `https://test.pypi.org/simple/`; `pypi` uploads to
`https://upload.pypi.org/legacy/` -- both `explicit`, so neither takes
part in resolving the workspace. The index's `url` is the check URL (uv
refuses an explicit `--check-url` beside `--index`). Files the index
already holds with the
same content are skipped, so a re-run after a partial failure uploads
what is missing and nothing twice. The credential is `UV_PUBLISH_TOKEN`
from the environment or, absent that, the index's own name --
`TEST_PYPI_TOKEN` or `PYPI_TOKEN`, the repository secrets' names, so one
`.envrc` line serves the shell and CI alike -- and never in the Justfile:
while versions are being deleted and re-cut, an account-scoped TestPyPI
token; trusted publishing
(a pending publisher per project name, twenty-one registrations: the
umbrella and the twenty published packages) waits until
the names are stable, and is then the CI job's credential.

The version lives in twenty-three `version =` lines -- the root's and the
twenty-two workspace packages', the two private ones included -- and in
every `== <version>` pin between the packages (the root's dependencies,
its extras and its dev group alike), and `bump-my-version` is the
one thing that changes them (`uv version` bumps the lines but never a
pin, so it is not used). The scheme is `MAJOR.MINOR.PATCH[.devN]`; every
version goes to TestPyPI first, and versions there are deleted as
development goes on, so an increment must be cheap: `just release dev`
is one. `tests/test_v2_package_metadata.py` bumps a copy of the tree and
asserts nothing of the old version is left.

### Installing a release

Twenty packages are on the index: `cs-image-system`, the umbrella (no
sources of its own; its dependencies are the core at a `==` pin, and
each provider is an extra), and `cs-image-system-<package>` for the
nineteen others. The bare install carries no runtime:

```sh
uv tool install cs-image-system               # the CLI, the engine, the OS families, packer,
                                              # ansible, bash, posix identity, the local state
uv tool install 'cs-image-system[aws]'        # + the aws runtime, its roots (tofu, tf-aws-*), s3 state
uv tool install 'cs-image-system[gcloud]'     # + the gcloud runtime, its roots (tofu-gce, tf-gcp-*), gcs
uv tool install 'cs-image-system[docker]'     # + the docker runtime, its roots (tofu-docker, tf-docker-volume)
uv tool install 'cs-image-system[okta]'       # + Okta users and OPA groups (okta-tf, okta-tf-ro)
uv tool install 'cs-image-system[aws,okta]'   # any combination, in one line
uv tool install 'cs-image-system[all]'        # every provider: what the reference configuration installs
```

A configuration repository's `Justfile` reads the extras its tree needs
from the `type:` words under `cfg/` (`just extras` prints them, as
`aws,okta`), and `just take <version>` and every CI job install
`cs-image-system[<extras>]==<version>` with that answer, so a tree that
adds a provider edits no install line. The table from a `type:` word to
its extra is the umbrella's one module (`cs_image_system.extras`); a tree
that declares a word whose plugin is not installed does not get a
traceback: `validate` prints one configuration line and exits 1,

```text
 - runtime type 'gcloud' is registered by no installed plugin: install the extra: uv tool install 'cs-image-system[gcloud]'
Validation failed with 1 error(s).
```

and for a word no extra carries, that it is unknown and which words the
installed plugins register under that classification. Two workspace
packages are never on the index: `cs-image-system-dummy-plugin` (the
extension template and test double) and
`cs-image-system-contract-example-plugin` (the contract's proof). They
carry the classifier `Private :: Do Not Upload`, which an index refuses,
the release tooling leaves them out, and the workspace installs them
through the root's `dev` dependency group, so the suite and the dry runs
see them and a consumer never does.

TestPyPI does not carry the third-party
dependencies, so an install from it names PyPI as the extra index. In
`uv`, `--extra-index-url` takes priority over `--index-url`, so the
third-party packages come from PyPI; and `--index-strategy
unsafe-first-match` lets a name fall through to TestPyPI when PyPI has
no version that satisfies it -- only the pinned `.dev` packages. Without
it uv stops at the first index that carries a name at all, so once a
final version is on PyPI every development pin fails to resolve. The
fall-through
reaches TestPyPI for nothing PyPI can satisfy, so no third-party
package comes from it:

```sh
uv venv .venv
uv pip install --python .venv/bin/python \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  --index-strategy unsafe-first-match \
  cs-image-system==<version>
.venv/bin/cs-image-system --help
.venv/bin/cs-image-system decrypt --help
```

A final version on PyPI installs with `uv pip install
cs-image-system==<version>` alone, and `uv tool install cs-image-system`
puts the command on `PATH` (the umbrella package declares the
console script itself, because uv exposes only the requested package's
executables, and `uv tool install` of a package with none ends with
"Failed to install entrypoints"). A configuration
repository's `Justfile` and workflow install it that way, with the
tree's extras. Python 3.13 or
later. The tools the
system drives (`tofu`, `packer`, `gcloud`, `ansible-playbook`, docker) are
not Python packages and are not installed by this; the configuration's
`cfg/executables.yml` pins where they are. The same install from the
built files, without an index, is `uv pip install --find-links dist
'cs-image-system[all]==<version>'` after `just build`; the twenty wheels
installed that way into a fresh virtualenv run `cs-image-system --help`
and `decrypt`, which is the proof that every package declares what it
imports (`just build` builds the two private wheels too; nothing installs
or uploads them).

`just publish-tree <root> <dest>` builds what a public repository will
hold: the TRACKED files of `<root>` at HEAD (`git archive`; nothing
ignored can enter), minus `PUBLISH_EXCLUDE="path/one path/two"` (default
none), gated by `public-safe` with the root's own allow list (or the
fixture's when the root is this repository), the destination's
`.gitignore` checked line by line for `.envrc`, `.private_key.pem`,
`.private_key.json`, `.public_key.json`, `*.pem`, `tfplan`, `*.tfstate`,
`*.tfstate.backup`, then ONE commit on `main` carrying the SOURCE
repository's `user.name` and `user.email` (its local values, else the
global ones, because a fresh `git init` knows only the global identity
and a push under the wrong one is refused) (`PUBLISH_MESSAGE`,
default `Initial public release`). It refuses a dirty root, a finding, a
missing ignore line or an existing `<dest>`, and never pushes.

`just publish-starters [yes]` publishes the five template
repositories, `infrastructurebuilder/cs-image-system-starter-<starter>`,
from which a team makes its configuration repository with GitHub's "Use
this template". `docs/examples/` stays the one place a starter is
edited; a template repository is generated from it and never edited
there. For each starter (`scripts/starter-tree --list`):

- **the tree** is `scripts/starter-tree <starter> <version>`: what
  `init-config` writes into an empty directory (`starters.write_starter`:
  the skeleton `docs/examples/_skeleton/` under the starter's own
  directory, and the installed plugins' terraform modules materialised
  into `tfmodules/` with their `.csis-module` stamps), `.csis-version`,
  a generated README header (where it comes from, that it takes no pull
  requests, and that the TEST age identity must be replaced before any
  real value is stored), and every Markdown link that leaves the starter
  pointed at this repository at the release's tag; a test holds the tree
  to exactly that. The modules a template carries are those of the
  plugins installed where the script runs, so it runs from the
  workspace, which installs every plugin;
- **the gate** is `public-safe` with the starter's own allow list;
- **the commit** is one, `cs-image-system <version>`, on `main`, with the
  tag `v<version>`, so a repository's history is one line per release.

It refuses a development version (a template names a version teams
install from PyPI), a dirty tree, a checkout that is not the version's
tag (its links point there), a missing `STARTER_PUSH_TOKEN`, and a
version any of the four already holds -- every repository is read and
every tree built and gated before the first push, so one refusal stops
all four. `yes` is the dry form: it builds and gates every tree and says
what each repository would take, also before the repositories exist,
and pushes nothing. CI's `publish` job runs it after PyPI for a final
tag (below).

### The modification tests

`just test-mods [--image <img>]... [--force] [--strict]` runs every
modification against a throwaway local container, twice (apply, then
idempotence), and records the results in the live configuration's
`meta-state/mod-tests.yaml` keyed by the mod's content hash. The container
image follows the instance image's OS family and version (`almalinux:<v>`
for the EL images). `--strict` exits 1 when a test is skipped (no docker,
an unsupported family); `--force` re-tests mods that already passed. It
needs docker and the live configuration, no cloud credentials.

### Writing a plugin

A plugin is written against one package, `cs-image-system-contract`:
the protocols a model and a builder satisfy, the constants
and field helpers a model is declared with, the lifecycle phases a hook
keys on, and the data carriers a hook returns. It depends on nothing of
the system, and `base` depends on it, never the reverse: the contract is
upstream, and a new hook is a contract change first. The core's base
classes implement every protocol with a default for every hook, so the
convenient plugin subclasses them; a plugin that satisfies the protocols
structurally is a first-class plugin, and
`cs_image_system.contract.testing.assert_conforms` is the check that says
so (the core's own bar runs it over every base class and every built-in
plugin). The recipe, step by step, with what to depend on and what to
return from the entry point, is "Writing a plugin" in
[packages/contract/README.md](../packages/contract/README.md); the
[contract example plugin](../packages/contract-example-plugin/README.md)
is the proof and the worked example (OpenTofu's `inmem` state backend,
written against the contract alone, subclassing nothing of the core), the
[local state plugin](../packages/local-state-plugin/README.md) the same
kind written the convenient way on the base classes, and the
[dummy plugin](../packages/dummy-plugin/README.md) the template for a
group or user builder and for a hook plugin. The run context is in the
contract (`RunContextProtocol`, handed to a builder at `bind(ctx)` and
read back through `_get_context()`), and so are the run's services
(`ctx.services.lineage`, `launch`, `secrets`, `files`, `commands`,
`images`, `identity`, `storage`, `workspaces`, `scope`, `cli`,
`lifecycles`, `meta_state`), the hooks entry point (`contract.hooks`) and
the bootstrap vocabulary (`contract.bootstrap`). What a plugin may import
from `base` is its base classes (`cs_image_system.base.basic`), its models
(`cs_image_system.base.models`) and the two metadata abstractions, nothing
else; `tests/test_plugin_imports.py` holds that rule over every installed
plugin. A plugin written outside this repository needs the two packages
from the index, `cs-image-system-contract` (pinned `>=0.1,<0.2`; the
contract has its own version, 0.x until it is declared stable) and, if it
subclasses the base classes, `cs-image-system-base`; it tests itself with
`assert_conforms` against the protocol of its kind and is refused at load
by name if it falls short.

### Recipe catalogue

`just` alone lists the recipes in file order, the contract first. This
Justfile is the developer's; the second table is a configuration
repository's, which the release ships.

| Recipe | What it does | Needs |
| --- | --- | --- |
| `init` | `uv sync --all-extras`, then `hooks` | nothing |
| `build` | sdist + wheel of every workspace member under `dist/` (the system package carries the five starter trees) | nothing |
| `test` | lint → typecheck → pytest, all blocking (the bar) | nothing |
| `full-test` | `test`, then `full-test-legs`: the dev-pin resolution check (`scripts/dev-pin-resolves`), the docker legs (`test-mods --strict`, `test-posix-accounts`, `test-bake-steps`, `runner-image`, `test-docker-bake`, `test-docker-cycle`, `test-podman-cycle`, `test-podman-desktop-cycle`) and, gated on `preflight`, a dry `run --all` and `state query --strict` over a copy of the reference configuration | docker, the network, reference configuration, runtime sessions; each leg skips loudly |
| `release <part\|version> [test\|pypi] [yes]` | probe (branch `main` with `develop` an ancestor, or `release/<major.minor>`; the index ready and free of the version; token; tag), the bar or `full-test`, the index again, `bump-my-version`, `uv lock`, `publish`, commit, tag `v<version>`; `yes` = dry | `UV_PUBLISH_TOKEN`; for `pypi`: clean trees, mod-test evidence, `full-test`'s needs |
| `publish [test\|pypi]` | the index asked first, clean `dist/`, `build`, then `scripts/publish-dist`: one project at a time (sdist with wheel, dependencies first, `cs-image-system` last), skip what is there, exit 75 on PyPI's limit on new projects, prove the token when nothing went up | `UV_PUBLISH_TOKEN` |
| `release-finish [test\|pypi]` | after a release's upload stopped part-way and `publish` completed it: on `main` (or a maintenance branch), the bump uncommitted and nothing else, every project holding the version -- then the evidence commit (PyPI), the commit and the tag; pushes nothing | the index, `develop` |
| `index-ready [test\|pypi] [wait]` | can the index take an upload now: the upload endpoint and every project page, one line each; exit 0 ready, 75 not now; `wait` probes every minute, two hours at most | the network |
| `full-test-legs` | `full-test` without `test`: the dev-pin check, every docker leg above, then a headless dry run `--all` and a `state query --strict` over a private copy of the reference configuration; re-run these after a session renewal instead of the whole `full-test` | `preflight` gates the two copy legs |
| `format` | `ruff format packages tests` | nothing |
| `lint` / `lint-fix` / `lint-unsafe-fix` | ruff check and the REUSE lint; with safe / unsafe fixes | nothing |
| `headers` | the SPDX header on every source file that lacks one | nothing |
| `reuse-live` | the REUSE lint over the reference configuration | reference configuration |
| `typecheck` | pyright | nothing |
| `pytest` | the unit tests alone | nothing |
| `test-one *ARGS` / `v2-test` | one pytest expression / `tests/test_v2_*.py` alone | nothing |
| `test-mods *ARGS` | the modification tests in a container over the reference configuration | docker, reference configuration |
| `test-posix-accounts *ARGS` | the posix accounts script on AlmaLinux 10 and Debian 12 under docker, run twice: against an equal and a differing pre-existing group, a member with no account yet, sudo through visudo; a leg of `full-test`, skipped under `just test` | docker |
| `test-bake-steps *ARGS` | a bake's settle step and step runner on AlmaLinux 10 and Debian 12 under docker, with the package database REALLY held by another process (rpm's transaction lock, dpkg's frontend lock); a leg of `full-test`, skipped under `just test` | docker |
| `runner-image [tag]` | build the CI runner image (`ci/runner-image/`: AlmaLinux 10, every tool pinned) for amd64 and run its probe, which asks every tool its version from where `cfg/executables.yml` pins it; a leg of `full-test`; the Runner image workflow builds and publishes the same | docker |
| `test-docker-bake *ARGS` | the docker runtime's cycle on the local daemon: a tree of nothing but a docker runtime is written from the fixture's pieces, its AlmaLinux 10 and Debian 12 base images and a posix-owned instance image are BAKED (packer's docker plugin, ansible through the daemon), the lineage and the tags are checked, the images disposed; several minutes; a leg of `full-test` | docker, packer with the docker and ansible plugins, `ansible-playbook` |
| `test-docker-cycle *ARGS` | the docker runtime's CHANGE CYCLE on the local daemon, from nothing to nothing: the bake above, then two containers launched on one volume through tofu, verified, their accounts reconciled; one stopped and left stopped by the next apply, then started; one upgraded to a new build (a new generation); both decommissioned, the volume destroyed, the images disposed; several minutes more; a leg of `full-test` | what `test-docker-bake` needs, plus tofu |
| `test-podman-cycle *ARGS` | the cycle above against PODMAN'S API SERVICE instead of the environment's docker daemon; `CSIS_PODMAN_HOST` is the `DOCKER_HOST` URL of a running service (`podman system service`, a `podman machine`, or an `ssh://` URL to a host that has one) -- unset, the leg is SKIPPED, said so, and exits 0; it refuses to pass on a daemon that does not say it is Podman; what differs from docker is recorded under "Container hosts" | `CSIS_PODMAN_HOST` |
| `test-podman-desktop-cycle *ARGS` | `test-podman-cycle` against Podman Desktop's machine on macOS, its address read from `podman machine` rather than typed (`CSIS_PODMAN_MACHINE` names one of several); the leg never creates, starts or stops the machine -- with no podman, no machine, a stopped or an ambiguous one it is SKIPPED with the reason and exits 0; on an Intel host it proves Podman 5.8 (Podman 6 dropped them) until June 2027 | a running Podman Desktop machine |
| `preflight` | the reference configuration's runtime sessions from the caches over the loaded tree -- the load reaches no cloud (0 / 2) | reference configuration, its age identity |
| `golden-regen` | rewrite `tests/fixtures/v2_golden` from the fixture | nothing; review the diff |
| `public-safe *ARGS` | scan this checkout with the fixture's allow list | nothing |
| `publish-tree <root> <dest>` | a publishable copy: tracked files, gate, one commit on `main` | a clean root |
| `publish-starters [yes]` | the five template repositories from `docs/examples/` at a final version's tag: the trees, the gate, one commit and the tag each; `yes` = dry | the tag, `STARTER_PUSH_TOKEN` |
| `hooks` | `core.hooksPath .githooks` here | nothing |
| `verify` | alias of `test` | nothing |
| `clean` / `clean-venv` / `clean-all` | build residue / `.venv` / both plus `uv.lock` | nothing |
| `fixture-live` | the system's live proof over the frozen fixture: validate, a dry run `--all` with the state query off over a private copy, the modification tests under docker (0 / 1) | real sessions, docker for the last leg |
| `cli *ARGS` | the CLI against the reference configuration, e.g. `just cli validate`, `just cli config-drift`, `just cli state query --strict` | reference configuration; whatever the command needs |

The configuration repository's Justfile (the starter's, byte for byte,
in `docs/examples/*/Justfile`; `CSIS` names the command, default
`cs-image-system` on `PATH`; `TF_PLUGIN_CACHE_DIR` is its own
`.tofu-plugin-cache/`):

| Recipe | What it does | Needs |
| --- | --- | --- |
| `init` | the command runs, the hook is installed, the plugin cache exists | a release |
| `build` | a dry run of every lifecycle (`run --all`) | sessions |
| `test` | `validate` and `public-safe` | sessions |
| `full-test` | `test` + `test-mods --strict` (docker) + a dry run `--all` and `state query --strict` over a private copy | docker, sessions |
| `release <rt>` | the performing run on one runtime, gated on `full-test`, records committed | write credentials |
| `validate` / `dry [LIFECYCLES]` / `run +LIFECYCLES` | every rule / a dry run / a REAL run (`--locked --no-dry-run ... --commit`) | sessions; write credentials for `run` |
| `record` | a dry run of EVERY lifecycle, its emission and meta-state committed (what CI's perform job makes first and last) | sessions |
| `preflight` / `state-query *ARGS` / `cloud-preflight` | the sessions, read over the loaded tree without a cloud call / the state query / `state query --strict` | the age identity / sessions / sessions |
| `cloud-describe <rt>` | the configuration's facts about a runtime as JSON | sessions |
| `cloud-bake <rt> [yes]` | `run base-image instance-image --only-runtime <rt> --commit`; the roots plan and gate only | `cloud-preflight`; write credentials |
| `cloud-perform <rt>` | the performing run (what CI does on `main`): `--no-dry-run run base-image instance-image release retention --only-runtime <rt> --commit` | `cloud-preflight`; write credentials |
| `cloud-cycle <rt> [yes]` / `cloud-stand <rt> [yes]` | `run --all --only-runtime <rt> --apply-runtime <rt> --commit`, then `cloud-empty` (cycle) or not (stand, for standing instances) | `cloud-preflight`; write credentials |
| `cloud-launch <rt> [yes]` | `run instance-image --only none --apply-runtime <rt> --commit` | `cloud-preflight`; write credentials |
| `cloud-decommission <rt> <instance> [yes]` | `--undeclare instance:<name> run instance-image --only none --apply-runtime <rt> --commit`: a leftover standing machine destroyed through the gate | `cloud-preflight`; write credentials |
| `cloud-verify <rt> <instance> [serial\|sft]` | `verify instance <i> --timeout 600`; `sft` adds the login proof | sessions |
| `cloud-upgrade <rt> <instance> [to]` | pin, replace (`cloud-launch`), proof (`cloud-verify`), `run release`, `cloud-launch` again for the names, `record`; `require_released_builds` stays true | `cloud-preflight`; write credentials |
| `cloud-empty <rt>` / `cloud-dispose-images <rt> [yes]` / `cloud-relabel <rt> [no]` | `empty` / `dispose image --all` / `lineage relabel` (dry by default) | sessions; write credentials to dispose or relabel |
| `ci-login-proof *ARGS` | `workload token` into `OPA_TOKEN` inside an Actions job, then `verify login` | `sft`; a job with `id-token: write` for the workload form |
| `opa-workload-probe` | `workload probe`: the token presented and discarded, then `role: granted` or `not granted` by resolving a standing machine as the workload | a job with `id-token: write`; `sft` |
| `sft-install` | the OPA client from Okta's apt repository | apt |
| `test-mods *ARGS` / `public-safe *ARGS` | in a container / the gate over this tree | docker / nothing |
| `config-drift` / `runtime-unchanged <rt> [ref]` | the commands of those names | sessions, `CSIS_CONFIG_IDENTITY` |
| `mirror-clean` / `hooks` / `cli *ARGS` | remove `_private/` / install the hook / any command against this tree | nothing |

The second positional `yes` on a cloud recipe means dry run (enumerate,
plan and gate; nothing executes); `cloud-relabel` is dry by default and
takes `no` to apply. The system's Justfile has no cloud recipe of its
own: the reference configuration's operator runs `just cloud-cycle
gcloud-east1`, `just cloud-decommission gcloud-east1 gce-test` and `just
cloud-dispose-images gcloud-east1` from that repository.

## 3. CI

Three workflows in this repository, and one in a configuration
repository. This repository's [ci.yml](../.github/workflows/ci.yml)
proves the SYSTEM: `verify` is the bar, `live` proves the frozen fixture
against the real accounts read-only, `publish` uploads a pushed `v*` tag
to the index. Every job of it runs inside the **runner
image** (`container:` -- `ghcr.io/infrastructurebuilder/csis-ci:<tag>`,
AlmaLinux 10 with every tool a job calls at a pinned version, built from
[ci/runner-image/](../ci/runner-image/) and described by
[CI_RUNNER.md](CI_RUNNER.md); the variable `CSIS_RUNNER_IMAGE` names a
team's own build) with the host's docker socket mounted, so no job
installs a tool: a checkout, `just init` and the targets are the steps.
[ci-from-scratch.yml](../.github/workflows/ci-from-scratch.yml) is the
same `verify` and `live` on GitHub's own Ubuntu runner with every tool
installed by a step (setup-just, setup-uv, setup-opentofu, setup-packer,
and the tools placed where the fixture's `executables.yml` pins them),
on `develop`, weekly and on dispatch, publishing nothing: the proof that
a runner with no image of its own can meet CI_RUNNER.md step by step.
[runner-image.yml](../.github/workflows/runner-image.yml) builds the
runner image (`just runner-image`, its probe included) and publishes it
to ghcr.io: a push that changes `ci/runner-image/` publishes the tag the
tree pins (`ci/runner-image/TAG`), and the monthly schedule publishes
today's date as a candidate. A configuration repository's `ci.yml`,
which the release ships in every starter tree and `init-config` writes,
proves and performs the CONFIGURATION: `verify`, `live`, `perform`, each
inside the same runner image and installing only the released system.
This repository's workflow never checks the reference configuration
out, records it or performs on it: that is the reference configuration's
own workflow, which is the starter's with the team's values. Every
command in any of them is a `just` target of its
repository, so CI and a person's shell run the same thing.
`tests/test_v2_ci_workflow.py` pins this repository's workflow;
`tests/test_docs_examples.py` pins the starter's, jobs and perform
sequence included; `tests/test_v2_ci_runner.py` holds the image, the
from-scratch workflow and CI_RUNNER.md to one list of tools.

### The bootstrap: what CI needs, as terraform from an interview

A configuration repository's CI needs things made before it can run --
the repository's settings, the federation trusts, the secrets -- and
CI_SETUP.md says how to make them by hand. `cs-image-system bootstrap`
(`just bootstrap` in a configuration repository) turns the
guide's sections into terraform the team applies once, from answers it
gives once. It loads no configuration: the sessions and federation it
makes may not exist yet, so it reads the checkout (`git remote`, `gh api`
for the repository and owner ids when `gh` is there) and the raw
`cfg/*.yml` (plain YAML, never templated) for the interview's defaults.
Each section opens with "Do you want the X section?"; a question shows
its default, which is the earlier answer when there is one (a second
interview re-asks only what a person wants to change); `--quiet` takes
every default and REFUSES by name a question whose default cannot be
derived (a repository with no GitHub remote, say) rather than guess;
`--section` interviews only the named sections and keeps the others'
answers untouched.

The answers go to `bootstrap.yaml` at the root of the tree, beside
`cfg/` -- hand-editable, committed, the source. `generated/bootstrap/` is
generated from it: `main.tf` calling `tfmodules/bootstrap_<section>` for
each wanted section, `providers.tf` (local state for the first apply, the
provider blocks), `variables.tf`, `outputs.tf`, `bootstrap.auto.tfvars`
with every answer that feeds a variable, `set-secrets.sh` (the `gh
secret set` lines, each reading its value from a file named after the
secret under the directory the interview named, or from an output of the
applied root -- no secret value in the tfvars or the state, decision
D2), `README.md` (what was generated, what remains by hand, the apply
commands) and a `.gitignore` (tool residue, plans and state out; the
tfvars in -- the one tfvars this system commits, exempted by path from
the public-safe refusal and scanned like any file, decision D3). Every
run, dry or real, regenerates the directory from the answers before the
lifecycles -- generation only, never a plan or an apply (decision D7) --
and prunes it when the answers file is absent -- in both cases leaving
what a person's own `tofu` left there (`.terraform/`, the lock file, a
saved plan, and the STATE of a root still on the local backend: a
lifecycle's directory is wiped whole because its state is remote, but
this root's may be right there;
[INCIDENTS.md](INCIDENTS.md#a-run-would-have-wiped-the-bootstrap-roots-local-state))
-- so a `--commit` run
commits it with the rest of the emission (the tfvars added by name after
the pathspec-limited commit, since a pathspec cannot say "except this
one"), `config-drift` reports a stale or hand-edited root as drift, and a
clone regenerates it without an interview. Applying is the operator's act
in that directory, the same as every other IAM write in this system. The
generated README's "Apply" block opens with the credentials each wanted
section needs, as `export` lines -- `GITHUB_TOKEN=$(gh auth token)`,
`AWS_PROFILE=<the profile the interview probed as>`,
`GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)` -- so
terraform acts as the same identities the interview asked as. That
matters most on GCP: application-default credentials are often something
else (on the reference machine they impersonate a runtime's service
account, which can read no IAM, so a plan under them fails with 403 on
every Google data source).

Sections: GitHub lives in base (the default branch, a ruleset on the
production branch -- no deletion, no force push; an ordinary push, which
is all `perform` ever does, is unaffected, so no bypass actor is named (GitHub
refuses the built-in Actions app as one) -- Actions
enabled with read-only workflow permissions, the Actions variables that
are not secret, and the secrets script); the clouds' sections come from
their plugins through the `cs_image_system.bootstrap` entry-point group,
each owning the questions and the module for its cloud. The core names no
cloud's secret: it knows its own two (`CSIS_CONFIG_IDENTITY`, the age
identity CI decrypts with, and `CSIS_PROOF_SSH_KEY`, a posix group's
proof user's key), and each section declares the repository secrets its
part of the workflow reads (`Section.secrets`: the AWS role ARNs, the GCP
provider and service accounts, the Okta key and the OPA service user's
pair, a docker host's ssh key and `known_hosts` line). The script sets the
union -- the core's first, then each installed section's in section-name
order, whether or not the section was wanted at the interview, since the
workflow reads the same names either way -- each from a file named after
it, except where a wanted section's applied root yields the value as an
output (the AWS ARNs, the GCP addresses), which the script reads from the
output instead. A plugin that is not installed contributes nothing, so
the script lists exactly what this install's CI can read. The Actions
variables that are not secret follow the same pattern: the core declares
`PERFORM_RUNTIME` and `GUARD_RUNTIME` from its own answers, a cloud's
section declares what its workflow steps read (the AWS section's
`AWS_REGION`, valued by its `region` answer), and the GitHub module sets
the union of every wanted section's non-empty answers. The framework and the GitHub section are
the core's (decision D1); the AWS, GCP, Okta and container-host sections
are below, and the guide's table in 3.0 says what each does and what
stays by hand. A section's gate ("Do you want the X section?") defaults to
what the tree says: the AWS section is wanted where the tree declares an
AWS runtime or keeps its state in S3, so a GCE-only tree's quiet
interview is not refused on AWS questions.

The AWS section (the AWS runtime plugin, module
`tfmodules/bootstrap_aws`) writes CI_SETUP.md 3.3 as terraform: the
GitHub OIDC identity provider, the READ-ONLY role (any ref of the
repository) and the WRITE role (the production branch alone) with the
guide's trust and permission documents -- the module's statements are the
guide's, Sid for Sid, and a test holds them together -- and, only when
the account lacks them, the state buckets (versioned, encrypted, private)
and the Session Manager instance profile (a role with
`AmazonSSMManagedInstanceCore`). Every declared S3 backend is covered:
the default one through the bucket questions, and
every OTHER one through "the tree's other S3 backends' buckets this root
makes", whose default lists each that is bound to a root (some builder's
or runtime's `state_configuration` names it) and that the account says
is absent, as `bucket=prefix`; the module makes one bucket set per
entry, and the WRITE role's `StatePrefix` statement covers each prefix.
A backend bound to no root is left out and the README says so (BY HAND:
bind a root to it and re-run, or drop the backend). The answer is a
choice, not an observation, so the second interview keeps it and a
bucket the root made never leaves the plan. Every "existing" question is a fork
whose default is a PROBE of the account, asked as the profile the runtime
names: found means a data source (the provider, the instance profile),
nothing made (the bucket), or an `import` block in the root that ADOPTS
it (the two roles, so their trust is maintained from then on rather than
left to drift). Adoption never narrows a role silently: the interview
reads an existing role's trust and offers every subject that is not this
repository's as "other subjects the role keeps trusting" -- kept by
default, shown at the prompt so a person can drop them, refused under
`--quiet` when the trust cannot be read. (A role often serves more than
one repository's CI -- the reference account's READ-ONLY role also
serves the system's own -- and a module trusting one repository alone
would plan to remove the others.) The account saying "no such entity" means the resource;
an account that cannot be asked (no session, no `aws`) means no default,
which the interactive interview asks and `--quiet` refuses by name. A
starter's placeholders (`REPLACE-ME`, the example account id) are no
defaults either. The subject forms the roles trust follow what is known:
both the plain and the id-bearing form when `gh` gave the ids, the plain
form alone otherwise (and the id questions are then not asked). The two
role ARNs become outputs the secrets script reads, replacing the files.
The network is never touched. The root's state binds to the tree's
declared S3 backend at `<prefix>/bootstrap.tfstate` when the bucket
exists (decision D8); when the bootstrap makes the bucket, the first
apply is local and a second interview, the bucket now standing, binds
it (`tofu init -migrate-state`).

The GCP section (the gcloud runtime plugin, module
`tfmodules/bootstrap_gcp`) writes CI_SETUP.md 3.4 as terraform: the
workload identity pool and its GitHub provider (the guide's attribute
mapping, and a condition admitting this repository alone -- by its id
when `gh` gave it, by its name otherwise), the READ-ONLY service account
with the project roles a load and the state query read, the WRITE
service account when CI performs on a GCE runtime (by default, when the
tree's default runtime is one), and the `workloadIdentityUser` bindings,
the write one narrowed to the production branch. It differs from AWS in
one deliberate way: what exists is READ, never managed. An existing
pool, provider or service account becomes a data source, not an import,
because a provider's attribute condition is a single expression that
other repositories may share -- the reference project's admits two -- and
a root that managed it would have to own everyone's access. So an
existing provider's condition is shown at the prompt as it stands and
never rewritten; the bindings name an attribute the provider actually
maps (`repository_id` only when it maps it); and when the condition does
not name this repository, the generated README says so as a step by
hand. Every role and binding is a single-member resource
(`google_project_iam_member`, `google_service_account_iam_member`; a test
refuses the authoritative forms), so no existing grant is replaced. The
probes run through `gcloud` as the active account (the project number,
the pool, the provider with its condition and mapping, the service
accounts, the bucket); unaskable means no default, refused by name under
`--quiet`. The three GCP secrets become outputs the script reads; with
no WRITE account `GCP_APPLY_SERVICE_ACCOUNT` is the READ-ONLY address,
the guide's first choice. A tree whose state is in GCS binds the root to
that bucket at `<prefix>/bootstrap` when it stands; when it does not, the
section MAKES it: `google_storage_bucket` with versioning, uniform access and
public access prevention, in the location the interview asked (the GCE
runtime's zone's region by default), labelled, with object access for
the READ-ONLY account (`objectViewer`) and the WRITE one (`objectAdmin`)
as single members added -- with the managed-or-read fork the AWS
section has (`state_bucket_managed`, a choice recorded once), so the
first apply is local and a second interview, the bucket now standing,
binds the root to it. `provider` is a reserved variable name inside a
module, which is why the module calls it `provider_id`.

The Okta and OPA section (the okta-opa plugin, no module) creates
nothing, by decision: the OPA workload connection and
role are console acts of a DevOps and a security admin, the Okta API
services app belongs to the org's Okta admins, and the OPA service user
and its key pair are made by hand. What it does instead is look. It
names the connection and role from the `okta-tf` group builder, or finds
them by what they require (the connection whose conditions name this
repository, the role bound to it), or suggests `github-<repo>` and
`<repo>-ci`; it reads them through the OPA API the system already uses
and checks that the connection exists, is ACTIVE and requires
`repository` and `repository_owner`, and that the role is bound to it
and pinned to the production branch's `ref`; and it asks the Okta token
endpoint for a token as the services app, signing a private-key JWT with
`OKTA_API_PRIVATE_KEY` for exactly `OKTA_API_SCOPES`, as the `okta`
provider does. A token proves the app, its key and its scopes; whether
it also holds a `*.manage` scope or another auth method is visible only
with `okta.apps.read`, so when its own record is not readable that
becomes a confirmation to ask of the org's Okta admins, never a guess.
Every check is an OBSERVED question -- asked of the world on every
interview, the recorded answer only the fallback when the world cannot
be asked, refused by name under `--quiet` when neither is there -- and
each one that fails becomes its step of CI_SETUP.md 3.5 under "By hand,
still". None refuses the interview: a draft connection is a normal state
on the way. The bootstrap never edits `cfg/`; names the group builder
lacks are printed as the two lines to add.

The container-host section (the docker runtime plugin, no module)
creates nothing either, because a docker daemon is a host
somebody runs and the system never installs or configures one. It reads
the tree's docker runtime from the raw `cfg/` (never loading it, and never
printing an address: a `host:` may be an `ENC[age:…]` marker) and asks the
one question the rest of the bootstrap needs, whether CI can reach the
daemon. The workflow reaches an `ssh://` host, or the environment's own
daemon whose address the workflow supplies (the `standard-docker`
starter's runtime names none), with a key kept as the secret
`DOCKER_HOST_SSH_KEY` and the host's `known_hosts` line as
`DOCKER_HOST_KNOWN_HOSTS`; both are the container-host section's own
secrets, set from files by the GitHub section's script like the rest. A socket, a context, a
`tcp://` host or an address kept as a marker is not something that
workflow logs in to, so the runtime is one CI must never bake on, and the
GitHub section's `GUARD_RUNTIME` default names the first runtime CI
cannot reach (it defaults empty when every runtime is reachable). The
GitHub section assumes no cloud: its `PERFORM_RUNTIME` default is the
runtime marked `is_default`, else the first one CI can reach, never an
AWS runtime by name. The section's audit lines
are all BY HAND (the daemon and its host, the network it names, CI's key)
or READ (the docker CLI the runner image carries).

**What the bootstrap covers, and what stays by hand.** The operator's
principle: the bootstrap produces a working set for
every underlying resource a tree declares; what stands is read, what is
absent is made, and what the system must never make is named as a step
by hand, by decision, never by omission. Every section renders its
audit, and the generated README tabulates it ("What this root covers":
section, resource, MADE / READ / ADOPTED / BY HAND, and the reason). The
standing audit, for a tree declaring both clouds and OPA groups:

| Resource the declarations imply | The bootstrap | Why |
| --- | --- | --- |
| the repository, its default branch, Actions permissions, the ruleset, the Actions variables | READ / MADE | the GitHub section; the repository itself is read, never created |
| the secrets' values | BY HAND | one file per secret, set by the script; a value never enters the tfvars or the state (D2) |
| the age identity for CI | BY HAND | made on your machine; the system never makes a key |
| the GitHub OIDC provider (AWS), the pool and provider (GCP) | READ / MADE | read when the account has them, made when it lacks them; a provider's condition is never rewritten |
| the READ-ONLY and WRITE roles (AWS) | ADOPTED / MADE | an existing role is adopted by import so its trust is maintained; its other subjects are kept |
| the READ-ONLY and WRITE service accounts (GCP) | READ / MADE | read as they stand, granted only the roles you named |
| the default S3 backend's bucket | READ / MADE | made when absent, managed from then on |
| every other declared S3 backend's bucket | MADE / READ / BY HAND | made when bound to a root and absent; read when it stands; BY HAND when bound to no root |
| the GCS state bucket | READ / MADE | made when absent, the CI identities' object access included |
| the Session Manager instance profile | READ / MADE | read when the account has it |
| the OPA workload connection and role, the per-group CI policies | BY HAND | console acts of a DevOps and a security admin (D4); the identity lifecycle makes the policies once the builder names them |
| the Okta API services app | BY HAND | the org's Okta admins' (D5, D9) |
| the OPA service user and its key pair | BY HAND | made by hand in the OPA console (D10); the script reads them from files |
| a docker daemon and its host | BY HAND | a host somebody runs; the system never installs or configures one, and whoever reaches it is root there |
| CI's ssh key to the docker host and its `known_hosts` line | BY HAND | made on your machine; the script sets the secrets from files |
| the network: VPC, subnets, security groups, the gateway, firewall rules | BY HAND | the team's, by decision (the network rule, section 5): never created or modified |
| the bake hosts' route to SSM and the package repositories | BY HAND | part of the network |

Preflight checks the session of every runtime a run reaches and of
every state manager one reaches as well, and a docker runtime by one
line (`docker version` against its daemon).

The
modules ship inside their plugin's package like every module
(`cs-image-system modules` lists them; `init-config` writes them into
the tree); `tests/test_v2_bootstrap_gcp.py` holds the GCP section (the
tree-derived gates across both clouds, the probes and refusals, a fresh
project and a shared provider, the by-hand note, the additive-only
module held to the guide's mapping, a real `tofu validate`),
`tests/test_v2_bootstrap_aws.py` holds the AWS section (the
probes, the refusals, the forks, the imports, the backend, the guide's
statements, a real `tofu validate` of both sections together) and
`tests/test_v2_bootstrap.py` holds the question model, the quiet
interview, the root (a real `tofu validate`), the regeneration inside a
run, the commit, `config-drift`, the secrets script, the starters' parts
and the command; `tests/test_v2_hygiene_xx.py` holds the other S3
backends' buckets, the GCS bucket, the audit table and the two validate
lines.

### This repository: the `verify` job

Runs on every push and pull request, with no configuration and no
credentials, inside the runner image.

| Step | Proves |
| --- | --- |
| `actions/checkout` | the checkout; the toolchain (just, uv, Python) is the image's, and no step installs one |
| `just init` | the workspace syncs (the editable build copies the starter trees into the system package) |
| `just verify` | the bar: ruff, pyright (blocking), the suite with the golden, over the frozen fixture; the built wheel is held to `docs/examples/` |
| `just public-safe` | the checkout holds nothing that must never be public |

### This repository: the `live` job

Runs after `verify` on pushes and the nightly schedule, never on pull
requests (forks carry no secrets), inside the runner image. It reads only
and never plans against remote state. The frozen fixture names the real
account's networks and project and the real OPA team, so with the
read-only identities the system is proved against reality without
touching the reference configuration.

| Step | What it does |
| --- | --- |
| Gate on the live secrets | none configured: `live: SKIPPED`, `ready=false`, a job-summary line (a green conclusion is not proof that anything ran); some configured and some missing or EMPTY: `live: FAILED -- ... missing or EMPTY: <names>`, exit 1 |
| Check out the system | one checkout; no second repository |
| Federated AWS credentials; the `[noaa]` shim | `AWS_ROLE_ARN`, the read-only role, via OIDC; the profile the fixture's runtimes name |
| Federated GCP credentials | `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_SERVICE_ACCOUNT`, read-only |
| No install step: the runner image carries just, uv, OpenTofu, Packer, gcloud, ansible and the docker client at the paths the fixture's `executables.yml` pins (`/usr/local/bin`) | `validate` checks every declared tool at its path and version; the from-scratch workflow installs the same tools by steps and places them there |
| `just init` | |
| `just fixture-live` | `validate` over the fixture with its committed TEST identity, a dry `run --all --no-state-query` over a private copy with the installed modules written beside it (`modules --write`), `test-mods --strict` over the copy under docker |

No identity secret: the fixture's age identity is committed beside it. No
mirror to remove: the copy is under the runner's temporary directory and
removed by the recipe.

### This repository: the `publish` job

Runs after `verify` on a pushed `v*` tag and nowhere else. It checks out
the tag, `just init`, checks that the tag names the version in the tree
(`bump-my-version show current_version`), then `just publish test` with
`TEST_PYPI_TOKEN` as `UV_PUBLISH_TOKEN` and, when the tag is not a
development version (no `.dev` in its name), `just publish pypi` with
`PYPI_TOKEN`. `just publish` skips every file the index already holds
with the same content, so a release the operator published locally with
`just release` is checked here and uploaded nowhere twice; a tag pushed
without a local publish is uploaded here. Either way each token is
proved: when every file was already there, `publish` sends one again,
which the index answers only after it has checked the credentials (a
tag that uploads nothing would otherwise never notice a secret that is
not a working token). The gate follows the other
jobs' rule: no token configured is `publish: SKIPPED` with a job-summary
line; a tag that needs a token which is missing or EMPTY fails by name
(a development tag needs TestPyPI's token alone; a final tag both). For
a final tag it then runs `just publish-starters` with
`STARTER_PUSH_TOKEN`: the template repositories take the
release; without that secret the step is SKIPPED, said in the job
summary. It holds no cloud credential and no `id-token` permission:
trusted publishing waits until the package names are stable.

### A configuration repository: the `verify` job

Every push and pull request, no secret, inside the runner image: the
release named in `.csis-version` (else the latest on the index; a
development version from TestPyPI with PyPI as the extra index and
`--index-strategy unsafe-first-match`) is installed with `uv tool
install` -- the one thing any job installs -- the `Justfile` parses, and
`just public-safe` passes.

### A configuration repository: the `live` job

After `verify`, on pushes and the nightly schedule, never on pull
requests, inside the runner image. Gated on the repository's secrets
with the same rule as above (none: SKIPPED and said in the summary;
some: FAILED by name). Then the release is installed (OpenTofu, Packer,
gcloud and the rest are the image's, at the paths `cfg/executables.yml`
pins), the read-only cloud identities are federated (the AWS profile the
runtimes name is written from them; GCP through the auth action), the
age identity is written to a file and `cs-image-system mask` hides every
encrypted value in the log, and then: `just validate`, `just
config-drift`, `just state-query --strict`, `just test-mods --strict`;
`just mirror-clean` runs last, even on failure. The Okta key and the
team's `TF_VAR_<team>_key` / `_secret` are job-level environment from
the secrets.

### A configuration repository: the `perform` job

`main` records, performs on the runtime `PERFORM_RUNTIME` names, and
records again. It runs after `live`, only when the ref is `main` or the
run was dispatched by hand, never twice at once (`concurrency: perform`,
never cancelling a run in flight), with `contents: write` so the records
push back with the job's own token. A dispatch enumerates unless it asks
to record, and recording is honoured only on `main`; the gate requires
the write identity (`AWS_APPLY_ROLE_ARN`, and on GCE
`GCP_APPLY_SERVICE_ACCOUNT`) only when recording.

**A record must exist whatever happens**: the committer is named, write access is proved with
`git push --dry-run` (remembering HEAD as `before`), then `just record`
(a full, unscoped dry run, committed) and the push. **A runtime CI must
never bake on** (`GUARD_RUNTIME`, empty for none, or several names
separated by spaces; the reference configuration names `gcloud-east1`,
the operator's own money): `just runtime-unchanged <name> <before>`, for
each name, compares that runtime's emission in the record just pushed
with the previous record and fails the job before anything performs.
Then the WRITE identity for one step and `just cloud-perform
"$PERFORM_RUNTIME"` (what a bake and the proof need -- the Session
Manager plugin on AWS, `ansible-core`, the OPA client `sft` -- the runner
image carries; no step installs them).
**A bake that happened must never go unrecorded**: the push of what the
performing run committed, the read-only identity again, `just
ci-login-proof --runtime "$PERFORM_RUNTIME"` (the login proof as a
workload; skipped after a failed performing step), `just record` again
and its push all run `always()` once the first record was made; a
failure before it has nothing to close. `just state-query --strict` is
the post-condition and `just mirror-clean` the last step.

**Cost.** The performing step can leave resources standing on
`PERFORM_RUNTIME`: the AMI and snapshot of a bake, and what a release
keeps. Retention disposes what the declarations no longer keep, on that
runtime alone. The guarded runtime never receives a write identity from
CI.

### A configuration repository: the workload probe

`opa-workload-probe.yml`, dispatch only, presents that repository's OIDC
token to the team's workload connection through `just
opa-workload-probe` (`cs-image-system workload probe`) and stops; against
a draft connection OPA accepts the token and issues one in reply, which
the probe reports and discards (a draft connection does issue a usable
token). The probe's second line says whether
the issued token carries the role, by resolving a standing machine of a
managed group as the workload, and so proves the role's branch pin from
two branches. It is how a connection is proved before it is activated
(CI_SETUP.md, section 3.5), and the repository that logs in as a
workload is the configuration repository, so the probe lives there and
the connection's claims name it.

### The `[noaa]` profile shim

The runtimes declare `credentials.profile_name: noaa`. botocore drops the
environment credential provider whenever a profile is named explicitly,
so the profile itself must carry the federated keys the AWS action
exported (temporary, one hour); the preflight reads a static-key profile
as present. Both workflows write it; the starter's reads the profile name
from `cfg/runtime-builders.yml`.

### Repository secrets

How a configuration repository's secrets and federated identities are
made from nothing is the guide every starter tree carries,
[CI_SETUP.md](examples/_skeleton/CI_SETUP.md); the tables below say
what each secret is for.

This repository:

| Secret | What reads it | Job |
| --- | --- | --- |
| `AWS_ROLE_ARN` | the federated-credentials action, then the `[noaa]` shim; a READ-ONLY role (EC2 describes for the fixture's load) | live |
| `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT` | the GCP auth action: the application-default credentials the gcloud runtime's network discovery uses; read-only | live |
| `OKTA_API_PRIVATE_KEY` | the load's check that the okta provider can authenticate | live |
| `TF_VAR_NOS_KEY`, `TF_VAR_NOS_SECRET` → exported as `TF_VAR_nos_coastal_modeling_cloud_sandbox_key` / `_secret` | the load's `_require_tfvar` assertion (the fixture names the real team) | live |
| `TEST_PYPI_TOKEN`, `PYPI_TOKEN` | `just publish test` / `pypi`, as `UV_PUBLISH_TOKEN` | publish |
| `STARTER_PUSH_TOKEN` | `just publish-starters`: a fine-grained token with Contents and Workflows read/write on the five template repositories alone (pushing `.github/workflows/` needs Workflows) | publish |

Set a token secret from the value your `.envrc` holds, with no newline
added (a stray newline, space or quote is refused by the index as
"Invalid or non-existent authentication information"):

```sh
printf '%s' "$TEST_PYPI_TOKEN" | gh secret set TEST_PYPI_TOKEN --repo <owner>/<repository>
printf '%s' "$PYPI_TOKEN" | gh secret set PYPI_TOKEN --repo <owner>/<repository>
gh secret set STARTER_PUSH_TOKEN --repo <owner>/<repository>   # prompts; paste the fine-grained token
```

`AWS_APPLY_ROLE_ARN`, `CSIS_CONFIG_IDENTITY` and `CSIS_CONFIG_PUSH_TOKEN`
on this repository are read by nothing: this repository performs on no
configuration.

A configuration repository (the starter's names; the reference
configuration uses them):

| Secret | What reads it | Job |
| --- | --- | --- |
| `AWS_ROLE_ARN` / `GCP_WORKLOAD_IDENTITY_PROVIDER` + `GCP_SERVICE_ACCOUNT` | the read-only cloud identities, for the load, the state query and the records | live, perform |
| `AWS_APPLY_ROLE_ARN` / `GCP_APPLY_SERVICE_ACCOUNT` | the WRITE identity, for the performing step and the login proof straight after it (a posix proof opens a session through the runtime, which the read-only identity may not); trusts `main` alone | perform (recording) |
| `OKTA_API_PRIVATE_KEY`, `TF_VAR_KEY`, `TF_VAR_SECRET` | the Okta key and the OPA API pair, exported under the team's `TF_VAR_<team>_*` names | live, perform |
| `CSIS_CONFIG_IDENTITY` | the age identity that opens the tree's `ENC[age:...]` values, written to a file on the runner | live, perform |

The gate cannot tell a missing secret from an empty one (both read as
`''`), so it decides on the set: with none configured the job skips and
says so in its summary; with some configured, every missing or empty one
is named and the job fails. A `live` run can be green having run
nothing when a secret holds the empty string (a value read from a file
the checkout did not have); a job's conclusion is never proof that its
steps ran
([INCIDENTS.md](INCIDENTS.md#three-green-ci-jobs-ran-nothing)). A
federated identity trusts the OIDC claims of the repository it was made
for; admitting a configuration repository (both AWS roles' trust
policies, the GCP provider's attribute condition, the OPA workload
connection's claims) is the operator's act, and the starters'
CI_SETUP.md alone is enough to do it: a workload connection and role
named for the configuration repository, its probe green, the identity
lifecycle reconciling the CI policies to the new role, the nine secrets
set, its `live` job green with every step run, and its first performing
run on `main` green end to end with the login proof recorded `as:
workload`.

## 4. The operator's cycles

### Credentials contract

No plaintext credential ever enters the configuration tree, the emission
or meta-state. Everything arrives through the environment of the process
that runs the scripts, or as an `ENC[age:…]` value that only an identity
in that environment can open.

| Lifecycle / step | Needs | Variables or session |
| --- | --- | --- |
| identity: okta/okta provider (user lookups) | Okta API services app, key-based auth | `OKTA_API_CLIENT_ID`, `OKTA_API_SCOPES`, `OKTA_API_PRIVATE_KEY`, `OKTA_API_PRIVATE_KEY_ID` (or `OKTA_API_TOKEN`) |
| identity: okta/oktapam provider (OPA groups) and the gid shim | OPA team key pair | `TF_VAR_<team>_key`, `TF_VAR_<team>_secret`, the team name with non-alphanumerics → `_` (the live team is `nos_coastal_modeling_cloud_sandbox`); the shim also accepts `OKTAPAM_KEY`/`OKTAPAM_SECRET` |
| storage and instance roots (terraform), bakes (packer) on AWS; every terraform root's S3 state backend, GCE roots included | AWS | the profile the runtime names: `aws sso login --profile noaa`; or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN` |
| bakes and roots on GCE, the GCP state query | GCP Application Default Credentials, impersonated | one-time `gcloud auth application-default login --impersonate-service-account=csis-runner@<project>.iam.gserviceaccount.com` (needs Token Creator on the runner); no key files |
| bakes, roots and the state query on a docker runtime | the daemon, reached by the `docker` CLI; nothing else (state is `local`) | whatever the runtime's `host:` or `context:` names, else the caller's `DOCKER_HOST`; the system exports `DOCKER_HOST`/`DOCKER_CONTEXT` (and the TLS pair) into every tofu and packer process it runs, an `ENC[age:…]` host opened where the line runs. Reaching a daemon IS root on its host (section 5, Container hosts) |
| every configuration load | the age identity that opens `ENC[age:…]` values | `CSIS_CONFIG_IDENTITY`: the `AGE-SECRET-KEY-1…` string, an identity file, or a directory of `*.age-identity` files |
| instance launch: identity enrollment | none by default: the identity root mints one enrollment token per project and the instance root reads it by sensitive remote-state reference | `TF_VAR_sft_enrollment_token` is an explicit override and the fallback for identity plugins that mint no token; with neither, instances launch un-enrolled |

`OKTA_API_SCOPES` stays at the read scopes; DPoP stays off; the `*.manage`
scopes stay ungranted. `OKTA_ORG`, `OKTA_TEAM` and `OKTA_RESOURCE_GROUP`
are exported by `.envrc` and read by nothing; `TF_VAR_oktapam_key` /
`TF_VAR_oktapam_secret` match nothing (the code reads the team-specific
pair, with `OKTAPAM_KEY`/`OKTAPAM_SECRET` as its generic fallback).

Each checkout has a gitignored `.envrc` (never committed; the public-safe
scanner refuses the name). The system checkout's exports the Okta and
`TF_VAR_<team>_*` names, `CSIS_CONFIG_IDENTITY`, and the CI names
(`GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`); the live
checkout's exports the Okta and
`TF_VAR_<team>_*` names. Whatever runs a configuration load needs
`CSIS_CONFIG_IDENTITY` in its environment: the recipe shell has no direnv,
so `source .envrc` in a subshell or set it inline. Because terraform runs
the decrypt program itself, `cs-image-system` must be on `PATH` and
`CSIS_CONFIG_IDENTITY` in the environment of whoever plans; `just` and
`uv run` provide the former, and a hand `tofu plan` in a generated root
needs both.

A GCE lifecycle needs a live AWS session as well: the GCE roots' state is
in S3.

An operator's live cycle, outside the recipes:

```sh
aws sso login --profile noaa                 # or export static credentials
gcloud auth application-default login --impersonate-service-account=csis-runner@<project>.iam.gserviceaccount.com
source .envrc                                # Okta/OPA credentials, CSIS_CONFIG_IDENTITY
just cli validate                            # exit 1 on any rule
just cloud-preflight                         # reality matches the records
just cli run --all --no-dry-run --commit
```

### Encrypted values

A value anywhere in the tree may be committed as
`ENC[age:<base64 of a standard age-encryption.org/v1 file>]`, encrypted to
every recipient in `cfg/_config.yml` `encryption.recipients` (age X25519
public keys, one per holder: a person or CI). **Any value decrypts at load**
with the identity in `CSIS_CONFIG_IDENTITY`, and a marked value with no
identity refuses at load, naming both the variable and the value's path;
an unmarked value passes through. Encryption is element-level, so a
roster is encrypted entry by entry, a diff shows which entry changed, and
one entry rotates alone. A decrypted value is a `str` with a repr that
hides it.

The rules -- where a marker may not stand (a mapping key, part of a
longer string, the keys read before the configuration loads), what
`EncryptedStr` fields exist, and the three forms `CSIS_CONFIG_IDENTITY`
takes -- are [CONFIGURATION.md, section 13](CONFIGURATION.md#13-encrypted-values).
Each is a named refusal, and the check itself needs no identity. This
section is the operating side: how to encrypt, rotate, mask and
materialise.

Tools (no configuration load; no identity needed except to decrypt, to mask
and to materialize):

- `just cli encrypt <value>` (or `-` for stdin) prints one marker;
- `just cli encrypt --file F --field NAME…` encrypts fields in place,
  textually, comments preserved;
- `just cli decrypt <marker>` prints the plaintext for the operator, never
  for a script that logs; `decrypt --json` is the terraform `external`
  program;
- `just cli reencrypt [--dry-run]` rotates every value under the root to
  the CURRENT recipients after one is added or removed; nothing is
  written unless every value opens; a removed identity can no longer open
  the tree;
- `just cli decrypt --file F --field NAME…` writes those fields back in clear,
  in place, comments preserved -- the inverse of `encrypt --file`, for a value
  whose encryption bought nothing;
- `just cli materialize <dir>` writes the private mirror of a generated root
  and prints where — what every deferred command runs through, and what to
  read when debugging emitted code that carries ciphertext;
- [bin/gen_age.sh](../bin/gen_age.sh), [bin/crypt_age.sh](../bin/crypt_age.sh),
  [bin/rotate_age.sh](../bin/rotate_age.sh) do the same in the `age` CLI's
  format.

Identities are never committed. Operators keep theirs under
`~/.config/cs-image-system/age/`; the CI identity is the
`CSIS_CONFIG_IDENTITY` repository secret; the live recipients are the
operators' identities and CI's. The frozen fixture ships its own TEST
identity so the suite needs nothing from the environment.

**In the emission, and at execution.** A decrypted value never reaches
`generated/` in clear. The emitted artifact — packer and terraform alike —
carries the SAME `ENC[age:…]` ciphertext the configuration carries, because
age is randomised and re-encrypting would move every emitted byte on every
run. `cs-image-system materialize` copies a root to `_private/<the same
relative path>` under the configuration root with every marker replaced by
its plaintext and prints where, and it is the one thing that makes the
mirror: a command list that must read plaintext at generation time (the
identity roots' plan) begins with an explicit `materialize .` step and
binds the commands after it to the mirror it made, and every line of a
committed runner script enters the mirror through `cd "$(cs-image-system
materialize . --root-dir "$CSIS_ROOT")"` before its command. The executor
adds no materialisation of its own around a command: a deferred command
runs where it was recorded, and what it needs in clear reaches it by
reference (below):

- the mirror is **never committed** — refused by path as a whole subtree,
  named in the emitted `.gitignore`, skipped by the scanner, and excluded from
  the run's `git add` by pathspec;
- it is **incremental**: materialising a root again (a hand-run script
  does it on every line) never removes what the mirror already holds, so
  `.terraform/` and the `tfplan` that `plan` wrote survive for `apply`;
- the only thing that ever travels back out is the provider lock file, which
  `init` writes where it runs and which the emission must carry; a plan, a
  state file and packer's manifest hold plaintext and stay in the mirror;
- it is left in place after a local run, so the operator can read what
  actually ran. CI removes it in a step of its own that runs even when the
  build failed.

Terraform's older by-reference path still stands for the okta roots: one
`data "external" "sensitive"` block per root, program
`cs-image-system decrypt --json`, wrapped as `local.sensitive[...]` with
`sensitive()`. The rule that a marker may not be embedded in a longer
string is a rule about the CONFIGURATION: a declared value is a whole
marker or clear. The EMISSION is different: a derived address carries
its marker inside the string (`avery.alpha@ENC[age:...]`)
and both the by-reference program and `materialize` substitute markers
wherever they stand in a text.

**What a green bake proves.** An image's `tests:` become `inline` lines in a
packer shell provisioner behind `set -e`, so each assertion must be able to
ABORT that script -- exiting nonzero is not enough. POSIX suppresses errexit
for a command inside an AND-OR list, so an assertion ending in `|| { ... }`
cannot fail a build however false it is: a `packages:` entry written
`rpm -q P || { ... dpkg -s P ... }` bakes green on a package the image
does not have, and the instance launched from that build then fails the
same check
([INCIDENTS.md](INCIDENTS.md#a-false-in-bake-assertion-could-not-stop-the-bake)).
Package assertions therefore test and `exit 1` for themselves, naming
the package on stderr. Because a failing assertion stops
the build, a build that EXISTS is one whose in-bake assertions passed, which
is what makes `tests: {assertions: N, in_bake: true}` in its lineage record
worth reading -- the number is the count that ran, and the record's existence
is the verdict.

**What the committed emission covers.** `generated/` describes the bakes a run
would DO, not every image declared: an image whose bake decision is `skip:
current` has no packer block in the emission at all, and gets one back when it
is next due. So the absence of an image under `generated/` is not drift, and
`config-drift` compares like with like because it regenerates from the same
declarations before diffing.

**Availability zones.** A subnet, a storage and an instance may declare
`availability_zone`, and `validate` refuses a set that is not compatible: more
than one distinct zone across an instance, its ZONAL storages (EBS, GCP
persistent disk — EFS, S3 and GCS are regional and constrain nothing) and its
runtime's subnet. An unset value constrains nothing, which is why the rule is
compatible rather than identical. Refused early because a zone forces
replacement: a runtime pointed at another zone does not fail to attach a
volume, it plans to DESTROY and recreate it. The plan gate catches that as an
unwhitelisted destroy, but only at apply time and naming the volume rather than
the reason. The live subnets and `mnt_data` declare their zones.
An EBS storage's own zone is what its module call carries, and a GCP
persistent disk's is the same: its own `availability_zone` wins over the
runtime's `zone` in the module call, the state query's lookup and the
archive script, and the runtime's `zone` is the fallback when the storage
declares none -- so declaring a zone pins the disk rather than decorating
the file.

**In the records.** A meta-state write says what it READ: a value
that came from a marker is recorded as that marker, so a record and the
configuration hold the same ciphertext and one `reencrypt` moves both (it
already walks every `*.yaml` under the root except `generated/`). A read opens
them again, so every recorded-vs-declared comparison is between plaintexts --
two markers for one value differ after a rotation, and comparing those would
report drift that is not there. The exception is a value public BY DECISION: a
username is written in clear, because the identity read-model's rosters are the
join key between a roster and an access grant and ciphertext there would defeat
the file's purpose. A record with no marker needs no identity to read.

**The guard does not guess.** The system knows every plaintext it opened, so
`validate` and every commit search `generated/` and `meta-state/` for those
exact strings (whole tokens, three characters or more) and refuse naming the
file and line. The shape rules remain the backstop for material that was never
a marker. A rotation is `reencrypt` plus regeneration.

**A derived value inherits its inputs' encryption**: an address
built from `default_user_email_template` carries a ciphertext assembled from
the pieces it was built from, so it reaches the emission as
`blake.bravo@ENC[age:…]` rather than in clear. Encrypting a first and last name
bought little while the address derived from them named the person and the
organisation both, so what is hidden is the address's DOMAIN: `email_domain` is
its own value on the user builder, the template reads
`"{{ user.name }}@{{ builder.email_domain }}"`, and one marker serves every
user. A username remains public by decision — it is the join key between a
roster and an access grant — so a value read only under `name`, `members` or
`admins` is emitted in clear.

### `just cloud-preflight`

The recipes of this section are a configuration repository's (the
release ships its Justfile; the reference configuration's operator runs
them from `../cs-image-system-testconfig`, whose `.envrc` points `CSIS`
at this checkout's venv while the system is developed).

`state query --strict` over both clouds. It refuses (exit 1) on hard
drift, on any drift class but `stale`, and on a session that expires
within `config.preflight.expected_run_minutes`. Every cycle step
(`cloud-bake`, `cloud-cycle`, `cloud-launch`, `cloud-decommission`)
depends on it, so a cycle never starts on a false belief or a lapsing
session. `just preflight` is the lighter form: the sessions alone, read
from the caches over the loaded configuration, which asks no cloud
anything (exit 2 when one is absent or expired; `--strict` exits 1 on
one expiring within the window).

### The cloud change cycle

The `cloud-*` recipes build → verify → converge to what the configuration
declares, on ONE runtime, with every fact read from the configuration
(`runtime describe <rt>`: project and zone, ephemerality, retention, the
images baked there, the declared storages with their cloud names, the
instances). Every recipe wraps sanctioned commands only.

- `just cloud-cycle <rt>` is the whole cycle as ONE run of every
  lifecycle, scoped and applied to the runtime: storages converge, the
  bakes that changed run, ephemeral instances launch, verify and tear
  down, declared releases are made, retention disposes; then `cloud-empty`
  asserts the runtime holds nothing beyond its declared storages (no
  instances, no custom images, no other disks or buckets) and that the
  strict state query agrees. Runtime inventory is implemented on GCE.
- `just cloud-bake <rt>` bakes only what changed on the runtime; the
  storage and instance roots plan and gate only.
- `just cloud-launch <rt>` launches the runtime's instances alone
  (`--only none`: nothing re-bakes); an ephemeral instance launches,
  verifies and tears down in one sequence.
- `just cloud-verify <rt> <instance> [iap]` verifies a standing instance
- `just cloud-upgrade <rt> <instance> [to]` moves a durable instance to
  its image's next build: pin, replace, proof, release, names, record
  through the system; `iap` adds `gcloud compute ssh --tunnel-through-iap
  --command 'findmnt -n /mnt && id'` with the project and zone read from
  `runtime describe`.
- `just cloud-decommission <rt> <instance>` destroys a leftover standing
  instance through the gate (`--undeclare instance:<name>`) instead of
  re-verifying it; a dry run keeps the record. `just cloud-dispose-images
  <rt>` after it is the runtime's full teardown.
- `just cloud-relabel <rt> no` re-tags images whose tags disagree with
  lineage, and gives `csis_config` to standing storages and machines
  that lack it; `just cloud-dispose-images <rt>` disposes of
  every recorded image on the runtime through the recorded path.

Three rules of these recipes, each the kind of thing that is obvious
afterwards:

- **A dry launch plans nothing.** `just cloud-launch <rt> yes` (and the
  dry form of every `cloud-*` recipe) regenerates and lists the deferred
  commands; it never runs `tofu plan` against remote state, by design
  (`-backend=false`, no generation-time plan). What to read in the dry
  form is the command list itself -- a `gate-plan` line carrying
  `--allow-destroy module.instance_<name>` is a decommission or a
  replacement, one without it is a launch or an in-place change -- and
  the emission and records the dry run commits (the instance `.tf`, the
  pin, "would take alias `x`"). The plan is read in the REAL run: the
  runner logs tofu's plan summary, the gate's verdict and the apply
  summary, and the plan file stays in the root
  afterwards (`cd generated/<lifecycle>/<root> && tofu show tfplan`). The
  protection against a plan that does more than expected was never the
  dry run; it is the gate, which refuses any destroy nothing whitelisted.
- **An applying run commits the script it executed.** With `apply-check`
  and `tofu apply` lines in it, which a resting generation does not emit.
  `config-drift` ignores those lines, so CI does not fail on such a
  commit; `just record` after an applying run,
  before the push, is still the tidy habit (the committed script then
  describes a resting generation, and the run journal gets its closing
  entry).
- **Between a decommission and the relaunch, push `develop` only.** A push
  to `main` runs the `perform` job, whose "the runtime performs" step
  applies the instance root under the write role: with the instance
  decommissioned but still declared, CI would launch the new machine
  itself, draw the alias and write the names -- correct, but not the walk
  you were in the middle of. `main` takes the whole of a replacement at
  its end.

**On a docker runtime** the `cloud-*` recipes take the runtime's name
unchanged (`just cloud-launch docker-main`, `just cloud-upgrade docker-main
<instance>`), and the cycle is the same sequence with a container for a
machine: the bake commits an image into the daemon, the launch creates the
container, uploads the launch script into it and runs it once by `exec`, the
accounts are reconciled the same way, and `cloud-verify` reads the launch
marker, the mounts and the booted image by `exec`. There is no `iap` or
`ssm` form and no login proof; a person reaches a container with `docker
exec -it -u <user> <name> bash`. The leg that proves it from nothing to
nothing, on the local daemon, is `just test-docker-cycle` (a leg of
`just full-test`; the same cycle for the `standard-docker` starter as it
stands is in it). Builds that a recipe disposes of are removed from the
daemon's store with `docker image rm`, refused while a container uses them.

`just cloud-cycle gcloud-east1 yes` is the dry form of the GCE cycle (the
`empty` assertion is skipped in a dry run). Every real cycle run passes
`--locked` to the command: one tofu process at a time on a machine.

### GCE cost discipline

GCP is the operator's own money. A change that touches it is proven with
one live cycle and leaves nothing behind beyond the declared storages
(`cloud-empty` is the cycle's last word). A run that ends with a billable
GCP resource STANDING says so explicitly: what it is, its id, and what it
costs. Two configurations may share a project: everything the
system makes carries `csis_config`, so `cloud-empty` counts this
configuration's things alone and says how many of another's it left
alone (`empty: left alone on <rt>: 2 disks of configuration '<id>'`),
and the state query reads a disk or bucket of our name that is theirs as
absent for us, with a note naming whose it is. A thing with no id at all
(made by an older tree) is still ours to answer for, listed as
`(no csis_config)` until `cloud-relabel` gives it the id. Ephemeral resources torn down within the run are not durable and
need no such note. By decision exactly one released image stands on GCE
(a released build is kept); everything else baked on the ephemeral GCE
runtime is disposed by retention. A change is not tested on GCP unless it
is likely to break the GCE code path; then one live cycle, torn down.

### Other CLI commands

`just cli <command>` runs any CLI command against the live tree.

| Command | Does |
| --- | --- |
| `validate` | loads the tree and applies every rule -- unique names, every declared executable present at its path and within its version requirement, every foreign key resolving, every root's state location sound; generates nothing |
| `run … --migrate-state <root>` (repeatable, `--no-dry-run`) | MOVES that root's state to the backend it now resolves to: backup, copy, a clean plan at the new location, the move recorded ("Where state lives") |
| `state-migration begin\|finish\|backup --workspace <root> --run <id>` | the two steps of a migration, emitted into the root's runner by `--migrate-state`, and the state backup a runner takes before a pre-plan `state rm`; never a by-hand command |
| `prune-attachments --builder <group builder> --run <id>` | the identity runner's step between init and plan: membership attachments the declaration dropped and OPA no longer holds leave state after a backup; never a by-hand command |
| `generate` / `build-all` | aliases: every lifecycle without / with the apply step (`--base-only`: base-image alone) |
| `upgrade instance <name> [--to <build>]` | moves that instance's pin (default: the series head); the next `instance-image` plans `-replace` and the gate whitelists it |
| `upgrade image <name> [--to <base build>] [--runtime <rt>]` | moves an instance image's base pin (per runtime); the next `instance-image` bakes a new build; no instance moves |
| `release …` | marks a build released (above) |
| `dispose image …` | removes a recorded image (above) |
| `verify instance <name> [--expect-build] [--timeout] [--record-only]`, `verify assert <name>` | the runtime's verification; the closing check of the `teardown` policy |
| `unmount storage --instance --storage --mount-point [--workdir] [--confirm] [--timeout]` | the unmount receipt before a detach |
| `workload describe\|token\|probe`, `verify login` | the okta-opa plugin's commands, present only while it is installed (a plugin mounts commands through the `cs_image_system.commands` entry-point group): what CI's workload login needs, the token for an Actions run, the probe of the role's reach, and the login proof ("CI logs in" above) |
| `state query [--strict] [--json]`, `state import` | reality versus records; adopt foreign artifacts |
| `lineage restamp`, `lineage relabel` | the record side and the tag side of the fingerprint |
| `runtime describe <rt>`, `empty --runtime <rt>` | the configuration's facts; the end-of-cycle assertion |
| `preflight [--strict]` | the sessions, over the loaded tree (no cloud call) |
| `validate [--online]` | every rule; `--online` first checks the runtimes' networking against their accounts and records `meta-state/runtime-facts.yaml` |
| `encrypt`, `decrypt`, `reencrypt`, `public-safe` | the value tools and the scanner |
| `test-mods` | the modification tests |
| `mask` | a `::add-mask::` line for every value the configuration carries encrypted, so a CI log never shows one; a configuration repository's `live` and `perform` jobs run it before anything prints |
| `materialize <source> [<destination>]` | copy a generated root into the private mirror (`_private/`), every ENC marker substituted with its plaintext, and print where it landed ("Encrypted values" above) |
| `init-config <destination> [--from <starter>] [--force] [--changes-since <dir>]` | write a starter configuration repository from this release: an empty destination takes the whole starter (the YAML, the Justfile, the workflow, the hook, `.gitignore`, `tfmodules/` written from the installed plugins and stamped, `.csis-version`), an existing one only the parts the release owns, its module copies refreshed by their stamps (an edited copy is kept and named); `--force` overwrites a release-owned file that differs, never an edited module; `--changes-since` lists what this release changed against the previous release's starters (either layout) and writes nothing |
| `bootstrap [--quiet] [--answers <file>] [--section <name>]...` | the one-time initialisation as terraform, from an interview, run in a configuration repository ("The bootstrap" above); loads no configuration |
| `config-drift` | is the committed emission current with the declarations? ("`config-drift` and `fixture-live`" above) |
| `runtime-unchanged <rt> [--ref <ref>]` | has that runtime's emission changed since the ref (default `HEAD`)? 0 unchanged, or only the vendor's newest image moved under a base not yet baked; 1 with the diff; 2 for an unknown runtime; CI's performing job asks it of each `GUARD_RUNTIME` |
| `workload describe [--env]`, `workload token`, `workload probe` | what CI's workload login needs from the configuration (the team's connection and role, the team, the API address; `--env` as shell exports); this Actions run's OIDC token presented to the team; the probe ("the workload probe" above) |
| `forget instance <name>` | drop a destroyed instance's pin and launch parameters when a decommission outside the gate left the records behind; refused (exit 2) while the instance is still declared |
| `identity-attributes [--probe] [--dry-run-apply] [--json]` | the identity attribute plan; writing is switched off (`--apply` exits 4) |
| `identity export-gids`, `gate-plan`, `apply-check` | programs the emission and the runner scripts call; no configuration load |

### The gid shim

The identity root publishes `output "group_gids"` (group → unix gid) for
`terraform_remote_state` consumers. The oktapam provider exposes no group
gid, so the root carries a `data "external"` block whose program is
`cs-image-system identity export-gids`; terraform runs it read-only at
plan and apply time with the credentials above. The shim reads each
group's server group (`<group>_user`) through the OPA Attributes API
(`GET /v1/teams/{team}/groups/{group}/attributes`, attribute `unix_gid`).
A group without the attribute fails the shim loudly, naming it. Consumers
never invent gids.

### Instance access and sizing

Instances launch in the runtime's private subnet with **no public IPs**
(the VPC has no internet gateway) and wear a root-created
`csis-instances` security group. The rest is configuration on the
runtime's `networking:` block; ids are never code literals:

```yaml
networking:
  ssh_ingress_security_group_ids: [sg-...]  # who may SSH in (the Okta gateway's SG);
                                            # SG-source only, never a CIDR of the shared networks
  addl_security_groups: [sg-...]            # existing groups every instance also wears
                                            # (the gateway relay requires OKTA-GATEWAY on the target); never modified
```

Per-instance sizing is `machine_type:` on the instance entry, with the
runtime default as the fallback (a 1 GB `t2.micro` is too small to keep
the SSM agent alive beside the package manager;
[INCIDENTS.md](INCIDENTS.md#a-1-gb-bake-host-starved-the-package-manager-and-the-ssm-agent)).
Launch user-data pins sftd's `AccessAddress` to the private IP and
resolves EBS devices by Nitro by-id names, because the legacy
`/dev/xvdX` never appears on a Nitro instance
([INCIDENTS.md](INCIDENTS.md#the-ebs-device-never-appeared-as-xvdf-on-a-nitro-instance)).
AWS sessions use SSM (`session_mechanism: ssm`;
the runtime's instance profile is operator wiring).

### IAP sessions on GCE (`session_mechanism: iap`)

The system generates **no IAM changes**, so IAP access is operator wiring:

- a firewall rule allowing `tcp:22` from IAP's range `35.235.240.0/20` on
  the instances' network:
  `gcloud compute firewall-rules create allow-iap-ssh --project <project>
  --network <network> --direction INGRESS --action ALLOW --rules tcp:22
  --source-ranges 35.235.240.0/20`;
- `roles/iap.tunnelResourceAccessor` for each operator's **own Google
  user** (the tunnel authenticates as the gcloud user, not the
  impersonated runner):
  `gcloud projects add-iam-policy-binding <project> --member="user:<address>"
  --role="roles/iap.tunnelResourceAccessor"`;
- the same role for the runner service account, because bakes on an IAP
  runtime tunnel too (`use_iap = true` on the googlecompute source) and
  packer runs as the impersonated runner; without it every bake times out
  "waiting for SSH".

The session: `gcloud compute ssh <instance> --project <project> --zone
<zone> --tunnel-through-iap`; `gcloud compute start-iap-tunnel <instance>
22 --local-host-port=localhost:2222 …` isolates the tunnel leg when
debugging. GCE images bake a runtime finalization step so the guest
agent's first-boot cleanup of the bake's ssh user cannot abort metadata
key provisioning. IAP sessions need an agent-loaded or passphrase-less
operator key: nothing in a run can prompt.

### Procedures

- **Move a root's state to another backend**: change its
  `state_configuration` (or its runtime's), then
  `just cli --no-dry-run run <lifecycle> --migrate-state <root>`; the
  guard refuses a plain run while resources stand in the root, and the
  operation backs the old state up, copies it and accepts only a clean plan
  ("Where state lives"). Nothing deployed: the binding moves on its own.
- **Upgrade an instance**: `just cli upgrade instance <name> [--to <build>]`
  (default: the series head in lineage), then run `instance-image` with
  the instance root allowed to apply. The plan carries `-replace` for that
  instance and the gate whitelists it. Nothing else moves.
- **Upgrade an instance image's base**: `just cli upgrade image <name>
  [--to <base build>]`, then run `instance-image` (a new build in the
  series); no instance moves until each is upgraded itself.
- **Decommission an instance**: remove it from `instances.yaml` (or
  `--undeclare instance:<name>` for one invocation) and run
  `instance-image` with the root allowed to apply. A recorded instance
  that is no longer declared is whitelisted at its root's gate
  (`--allow-destroy module.instance_<name>`), the plan carries exactly its
  destroy, and the after-apply hook forgets its launch parameters and pin.
  The runtime's root is still emitted when the LAST instance on it is
  undeclared, and a DRY run never forgets the record, so a decommission
  can be dry-run as often as needed. Storages are never touched by it.
- **Retire a storage**: detach it (remove it from every instance's
  `storages`, run), then set `state: archived` or `state: destroyed` and
  run `storage` with the root allowed to apply; or delete the entry and
  let the next storage run plan the undeclared destroy. A destroyed
  storage's tombstone stays in `storage-state.yaml`.
- **Stop managing a group**: keep the entry, add `unmanaged: true`; the
  identity runner removes it from state (`state rm`) and never destroys
  it. Removing a managed group's entry is a hard validation failure.
  The removal is the runner's pre-plan step's (`prune-attachments`), and
  it is decided by what the state holds when the step runs: whatever is
  still there under the group's module leaves, after a backup. Nothing
  made before the run changes that -- a dry run, a `just record`, an
  earlier run that failed -- and a tree whose release was once missed is
  healed by its next identity run. The decision is never made at
  generation from `meta-state/identity.yaml`, which every dry run
  rewrites: decided there, a real run after a dry run or a record would
  plan the DESTROY of the group, its project, its enrolment token and
  its policies, with only the gate in the way
  ([INCIDENTS.md](INCIDENTS.md#a-dry-run-spent-a-groups-release)).
- **Drop a membership**: remove the user from the group's `members` or
  `admins`. When OPA still holds the membership the plan shows the
  destroy of its attachment and the gate sees it. When OPA no longer
  holds it (the roster was conformed to OPA by hand, or the person was
  removed there first), the provider would ERROR on refresh (`user "x"
  is not present within group "g"`) instead of planning the destroy. So
  every identity runner carries a `prune-attachments` step between its
  `init` and its plan: it lists the state it is bound to, keeps every
  attachment the declaration still has, asks OPA about each one it
  dropped, and removes -- after a state backup -- only those OPA no
  longer holds. A silent or unreachable OPA removes nothing and the plan
  decides; a failed backup stops the runner before anything leaves
  state. The run log names each attachment and why. The generation-time
  plan of the group root is a preview that does not refresh
  (`-refresh=false`), so it never trips on such an entry; the runner's
  plan is the one the gate reads.
- **Rotate the admin key**: add the new public key to
  `config.admin_public_keys` (or the base image's override), run
  `base-image` then `instance-image` (new builds), `upgrade instance` for
  every instance that should move, run `instance-image` with the apply
  allowed, then remove the old key and repeat.
- **Emergency revocation**: out of band through the runtime's session
  mechanism (SSM on AWS, IAP on GCE); revoke only, then reconcile with the
  rotation above.
- **Adopt out-of-band group membership**: mirror the live members and
  admins into the group declaration and `users.yaml`, regenerate, then
  `tofu import` each live attachment before any apply. The
  `oktapam_user_group_attachment` import id is `<group>|<username>` (a
  `/` separator is rejected). The plan must then read "No changes"; run
  `identity` with `apply_identity: true` for the gated no-op apply and
  the records. Never let a plan *create* an attachment that already
  exists.
- **Adopt a foreign image or storage**: `just cli state import`
  (meta-state only); importing into tofu state is a hand step.
- **After a fingerprint-recipe change**: `just cli --no-dry-run lineage
  restamp --runtime <rt> --commit`.
- **Release by hand**: `just cli release <image> [--build <id>] --model
  <m>`; on an ephemeral runtime declare `release: {model: <m>}` on the
  image instead, so the run releases the verified head before retention.

## 5. Rules

Each rule states its reason. They hold everywhere; a change that needs an
exception is a decision to record, not a bypass.

### Identity

- Never destroy OPA groups (server gids) or users (uids); membership
  removals only by explicit decision. Identity is human-owned; the system
  owns access.
- Users are looked up, not created by the system; a person makes them in
  the Okta admin console.
- Removing a managed group's entry is a validation failure; `unmanaged:
  true` removes it from state without destroying it.
- DPoP stays OFF on the Okta API services app: the okta/okta provider
  does not support it.
- The `*.manage` Okta scopes stay ungranted; `OKTA_API_SCOPES` holds the
  read scopes. The design is read-only against Okta.
- Discovery before any OPA reconciliation enumerates security policies
  and group memberships, not only groups, users and resource groups (the
  state query does memberships, and each managed group's resource group
  and policies against the module; other policies are enumerated by
  hand).
- Never let a plan create an attachment that already exists; import it
  first.
- Attribute writes on identities stay disabled until the stakeholder
  decides otherwise.
- The CI login policy (`<group>_v1_security_policy_ci`) is the
  system's and is rewritten from the user policy on every identity apply;
  edit the module's rule, never the copy. The workload connection and role
  it names are the operator's and are never written by the system.
- **POSIX groups and accounts.** A posix group's `gid:` and a
  posix user's `uid:` are the configuration's and the same on every
  machine (storage is owned by number); `validate` refuses one name with
  two ids, two names with one id, an id below 1024, and a posix group's
  member with no posix account.
- The accounts script never deletes an account or a group. It adopts
  what stands equal, stops (exit 3, both ids named) on what stands
  different, and rewrites only what it owns: a managed group's member
  list, the files under `/etc/csis/`, its
  `/etc/sudoers.d/60-csis-<group>`.
- Every `okta-tf` group builder writes `posix:` -- a posix group
  builder, or `none`. With a delegate, each applying instance run makes
  the groups exist on their running machines with OPA's gid and installs
  the login hook; a machine that is off waits for a run that finds it
  running. With `none`, `validate` and the state query note what stays
  off the machines.
- Membership beside Okta is applied at LOGIN (the PAM hook), never only
  at apply: OPA's agent makes each account at a login and `userdel`
  drops its groups. A member added to the YAML joins at their next login
  after the next applying run. One removed leaves the list: the next
  applying run takes them out of the group if their account stands then,
  and the hook never adds them again (the hook itself only ever adds).
- A posix group's login proof logs in as its proof user over ssh through
  the runtime's session tunnel (SSM's `AWS-StartSSHSession`, IAP on
  GCE): no public address is ever needed. The proof key
  (`CSIS_PROOF_SSH_KEY`) is made for the proof user alone and is a CI
  secret; rotating it is a new key pair, the public half in
  `public_keys:` and an applying run.

### Applies

- An apply is the gated apply of a fresh plan file: explicit go (the
  `apply_*` flag or `--apply-runtime`), `rm -f tfplan`, `plan -out`,
  `gate-plan`, `apply-check`, `apply tfplan`. A hand apply against the
  identity state additionally takes a same-day backup of the S3 state
  first, because those resources are never recreated -- and a runner
  takes the same backup itself before any `state rm` it decided on
  (an unmanaged group's module, a pruned attachment):
  `_private/state-backups/<workspace>.backup-<run>.tfstate` under the
  configuration root, never committed, outside every directory a run
  wipes. The step refuses, and the runner stops before anything leaves
  state, when the root it runs from is not initialised or its location
  holds no state.
- Nothing irreversible happens by default: dry run is the default, and a
  runner script generated under one flag never applies under another.
- Only operation-driven destroys are whitelisted; every other destroy
  fails the gate.
- The run scripts are the record: reality changes only through them, and
  nothing deletes a recorded resource by hand. A script of an unrequested
  lifecycle is never executed.
- A recorder never claims reality no apply produced; `state import` is the
  one exception.
- A released build is kept; only an explicit `dispose image <id>` removes
  it.
- Declared storages are never destroyed by retention or by a change
  cycle; a storage leaves only when its declaration does.
- One tofu process at a time on a machine, by construction: the shared
  `TF_PLUGIN_CACHE_DIR` is not safe under concurrent `init`, and two runs
  would race on the same roots and records. The recipes that may execute
  the roots hold `.tofu-plugin-cache/.lock` (`cs-image-system --locked`)
  and a second one refuses; the suite never shares the cache.

### Network

- Never modify existing network configuration: existing security groups,
  subnets and routes are untouchable. Creating NEW security groups is
  fine; instances may wear existing groups by configuration.
- Never open ingress to the shared networks' address space. SSH ingress
  is granted by security-group reference only
  (`ssh_ingress_security_group_ids`).
- Instances launch in the private subnet with no public IPs; sftd
  advertises the private address because the VPC has no internet gateway.
- Environment-specific identifiers (security-group ids, subnet ids,
  machine types, projects, zones) are configuration, never code literals;
  test stubs accept any configured value. Recipes read facts from
  `runtime describe`, never hardcode them.
- The system generates no IAM changes; IAP, SSM and impersonation are
  operator wiring.

### Secrets and publicness

- Both repositories are public by design. No plaintext credential, plan,
  state, tfvars, `.envrc` or key material is ever committed; the scanner
  refuses them by name and by shape, and a `--commit` run excludes them
  by pathspec.
- Never print key material; the NAMES of secrets and variables are fine
  and required in documentation.
- Allow a value by decision, with its reason, in `public_safe.allow`;
  never by bypassing the hook.
- Identities are never committed; each holder keeps their own, and CI's is
  a repository secret. A removed recipient is followed by `reencrypt`.
- A derived email is public by construction; an address that must not be
  public is declared encrypted.

### Configuration and tests

- The frozen fixture is test-owned: never applied, never committed into by
  a run, never carrying meta-state, never holding a real person. The live
  tree is never read by a test.
- The live configuration carries no overlays; a transient declaration is
  a test device or an invocation flag.
- `just test` is the acceptance bar and every check in it blocks; a
  looser target is not the bar. `just full-test` precedes "done" and
  every release.
- A moved golden is read and justified, never accepted.
- Work goes through the Justfile, not the underlying tools; a missing
  check gets a recipe.
- One feature branch per piece of work, squash-merged into `develop`, the
  branch kept and pushed. Never commit to `develop` or `main` directly;
  never force-push a shared branch. Nothing in the tooling pushes: a push
  is the operator's act.
- A change that touches the live configuration commits and pushes that
  repository's `develop` as part of the work.

### Container hosts

- **Whoever can reach a docker daemon is root on its host.** Docker's API
  has no narrower grant: a client that may start a container may mount the
  host's filesystem into it. The system does not hide this and cannot
  soften it. A host that holds nothing else is the sensible one; a key
  that reaches it (CI's included) is as sensitive as root there.
- A daemon's address is never in a `.tf` or in a committed script as a
  plain value when it is private: write the `host:` as an `ENC[age:…]`
  marker and the runner scripts carry a `decrypt` call instead. TLS
  material is a path (`tls_cert_path`), never a value in the YAML.
- The system never installs, patches or configures a daemon, and never
  creates or changes a docker network: a network is referenced by name.
- The power state is the operator's here too (see "The power state belongs
  to the operator"): nothing starts a stopped container but a verification
  that needs it, and it stops it again.
- No privileged container, no init system and no sshd are built. An image
  that adds an sshd or systemd is outside the supported shape.
- On a host with several engines (OrbStack, Docker Desktop, a Podman
  machine) the `docker` command follows its active context while the
  tofu docker provider and packer read `DOCKER_HOST` and otherwise take
  `/var/run/docker.sock`, which may point at an engine that is not
  running. The docker legs of `just full-test` (`test-docker-bake`,
  `test-docker-cycle`) therefore run with `DOCKER_HOST` set to the
  active context's endpoint (`just docker-host` prints it; a
  `DOCKER_HOST` already in the shell wins), so every tool reaches the
  daemon `docker` itself uses. A tree that must name a daemon names it
  in the runtime's `host:` or `context:`.
- CI reaches a host over ssh with a key kept as a repository secret
  (CI_SETUP.md 3.4a), or it does not, in which case the runtime is named
  in `GUARD_RUNTIME` and CI never bakes on it. Without the key a job uses
  its own runner's daemon, which is gone when the job ends, so the
  workflow's `perform` job refuses to record without it.

### Podman as the daemon

Podman's API service is a daemon the docker runtime supports, by
decision: any daemon that speaks the Docker Engine API, proved rather
than keyed. This is how it was proved, so the proof can be repeated.

**The host.** Podman 5.8.2 rootless on AlmaLinux 10, as a Linux machine in
OrbStack on an Intel macOS host (`podman machine` was not used: it adds
a VM layer and Homebrew has no prebuilt Podman for that machine). In the
machine:

```sh
orb create alma:10 podman-host           # on the host
orb -m podman-host bash -c '
  sudo dnf -y install podman podman-docker
  systemctl --user enable --now podman.socket     # /run/user/<uid>/podman/podman.sock
  sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$(id -un)"
  podman system migrate'
```

**The address.** The `docker` CLI on the host reaches the socket over ssh, the
same transport the starter's workflow uses for a team's host (OrbStack's
machines answer `ssh <machine>@orb`):

```sh
export CSIS_PODMAN_HOST=ssh://podman-host@orb
DOCKER_HOST=$CSIS_PODMAN_HOST docker version     # Server: ... Podman Engine, 5.8.2
just test-podman-cycle                           # about 10 minutes
```

**What it ran.** The cycle of `test-docker-cycle` (two bakes, a volume, two
containers on it, the launch script by `exec`, the accounts, the
verification, the strict state query, one container stopped and left stopped,
started, an upgrade to a second generation, both decommissioned, the volume
destroyed, the builds disposed) and the `standard-docker` starter as it stands,
both against Podman, 572 seconds, both passed. The leg refuses to pass on a
daemon that does not say it is Podman.

**What differed.**

- **Subordinate ids.** A rootless Podman user needs `/etc/subuid` and
  `/etc/subgid` ranges (the `usermod` line above), or the first image pull
  fails with `insufficient UIDs or GIDs available in user namespace`. This
  is the host's setup, not the system's.
- **The registry Podman implies.** Podman's API reports an unqualified
  repository `csis/x:tag` as `docker.io/csis/x:tag` in `RepoTags`, where
  Docker keeps it as written, so the runtime compares repositories through
  `same_repository`, which accepts `docker.io/`, `index.docker.io/` and
  `localhost/` in front of its own; otherwise the movable tags that carry
  the lineage facts (the parent bound after a bake, a release) would be
  read as absent
  ([INCIDENTS.md](INCIDENTS.md#podman-spelled-the-tags-with-a-registry-the-system-did-not-expect)).
  A unit test holds it.
- **Nothing else.** The compatibility API answered at version 1.44 to a
  client of 1.56 (downgraded), and `must_run = false`, the restart policy,
  `--init`, the labels, the volume mount and `exec` behaved as on Docker.

**Podman Desktop on macOS.** The second proof is the daemon a developer
on macOS meets: Podman Desktop's own `podman machine`, a VM with a socket
of its own, running beside OrbStack on the same host.

- **What Desktop installs.** Podman Desktop 1.29 or later bundles Podman and
  puts it at `/opt/podman/bin/podman`, which is not on `PATH`. It makes the
  machine itself, with the Podman it bundles (5.8.9 there): one machine,
  `podman-machine-default`, 2 CPUs, 1.9 GB of memory, a 10 GB disk, and
  **rootful** (the Linux proof above was rootless). Desktop does not mark a
  machine it makes as the default one in `podman machine list`.
- **Coexistence with OrbStack.** Nothing was changed on the host's side and
  nothing needs to be. A bare `docker` keeps answering from OrbStack,
  because `/var/run/docker.sock` still points at it and `podman-mac-helper`
  is not installed (it would take that socket from OrbStack; do not install
  it, and leave Desktop's docker-compatibility option off). Desktop adds a
  docker context named `podman` and leaves the current context alone. Podman
  is reached only by its own socket, which `podman machine inspect` reports
  (a path under the temporary folder; a stable symlink to it sits at
  `~/.local/share/containers/podman/machine/podman.sock`).
- **The leg.** `just test-podman-desktop-cycle` runs `scripts/podman-machine-host`,
  which names the machine (the only one, the default of several, or the one in
  `CSIS_PODMAN_MACHINE`) and prints its socket as a `unix://` URL, then runs
  `just test-podman-cycle` with `CSIS_PODMAN_HOST` set to it. So
  `test-podman-cycle` stays the one knob for any other host. The leg never
  creates, starts or stops the machine, because the power state is the
  operator's: with no `podman`, no machine, a stopped machine, or several with
  no default it is SKIPPED with the reason and exits 0, and `full-test` names
  it in its legs and in its SKIPPED line. It still refuses a daemon that does
  not say it is Podman, and a bare `docker` is never aimed at the machine.
- **What it ran.** The same two legs as above, with OrbStack running, against
  the rootful Desktop machine: the docker cycle and the `standard-docker`
  starter, 384 seconds, both passed.
- **What differed.** Nothing. No code changed. A rootful machine needs no
  subordinate ids, and the registry Podman implies in `RepoTags` was already
  handled. OrbStack's image and container counts were the same before and
  after; the machine kept two cached base images (`almalinux:10`,
  `debian:12`), which are the legs' pulls and cost 315 MB of the 10 GB disk.
- **Limits.** The machine is small: a bake that pulls a large base image or
  several of them would need `podman machine stop` and then `podman machine
  set --memory 4096 --disk-size 20` (a disk grows and never shrinks); the
  operator does that, not the leg. Podman 6 dropped Intel Macs, so an
  Intel macOS host runs the Podman 5.8 that the installer bundles,
  supported until the second week of June 2027 ([the Podman Desktop
  team's note](https://podman-desktop.io/blog/intel-mac-podman-6-transition)).
  After that date this leg is retired from Intel hosts and the standing
  proof is the Linux host above. Apple silicon (Podman 6) is untested: no
  such machine was available.

**Not proved.** A rootless Podman machine on macOS; a `tcp://` or TLS address;
a Podman host that is not systemd's. A durable Podman host needs `loginctl
enable-linger <user>` as root so the user's socket outlives its login session;
OrbStack's machine kept it up without (the command was refused there), and a
real host should not rely on that.

### Cost

- GCP is the operator's own money: a change is proven on it only when it
  is likely to break the GCE path, with one cycle that leaves nothing
  standing beyond the declared storages and the one released image; any
  billable resource left standing is reported with its id and cost.

## 6. Where things are

| Document | Holds |
| --- | --- |
| [README.md](../README.md) | the entry point: the Justfile contract and the layout |
| [DESCRIPTION.md](DESCRIPTION.md) | what the system does: the estate, the pipeline, the posture |
| [GOALS.md](../GOALS.md) | the target goals the system is measured against |
| [GOLDEN.md](../GOLDEN.md) | the golden fixture: what it is, how it is produced and enforced |
| [CONFIGURATION.md](CONFIGURATION.md) | the configuration reference: every key of the YAML tree |
| [PLUGINS.md](PLUGINS.md) | the index of the package READMEs under `packages/` |
| [packages/contract/README.md](../packages/contract/README.md) | the plugin contract: what a plugin is written against, and how to write one |
| [PARITY.md](PARITY.md) | how the documentation and the system can diverge, and the check for each |
| [DESIGN.md](DESIGN.md) | the design record |
| [CHANGES.md](CHANGES.md) | the stage index: one row per landed stage and per release, newest first, with the anchor the other pages point at |
| [INCIDENTS.md](INCIDENTS.md) | every incident, newest first: symptom, cause, what the system does now, date |
| [GLOSSARY.md](GLOSSARY.md) | the house words, each defined once in a paragraph that links to the page owning the concept; it defines, it never rules |
| [history/](history/) | frozen: the findings ledger, the GCP readiness study and the live-proof overlays; evidence, not documentation |
| [tests/fixtures/config/README.md](../tests/fixtures/config/README.md) | the frozen fixture |
| [Justfile](../Justfile) | every recipe, with its comment |
| [.github/workflows/ci.yml](../.github/workflows/ci.yml) | the CI workflow |
| [.githooks/pre-commit](../.githooks/pre-commit) | the public-safe hook |
| `cs-image-system-testconfig` (beside this repository) | the live configuration, its `meta-state/` and committed `generated/` |
| `cs-image-system-3-archive`, `cs-image-system-testconfig-archive` (GitHub, private, archived) | every commit either repository made before it was published, including the kept feature branches and the records that are frozen here under `history/`. Read-only. Nothing from them ever reaches a public remote. |
