# Operations

How to run cs-image-system and how to work on it. The first half describes
a run and the operator's cycles; the second half the developer's bar, CI,
and the rules. The [Justfile](../Justfile) and the CLI
([cli.py](../packages/system/src/cs_image_system/system/cli.py)) are the
authority; when this text and they disagree, they win.

Two trees matter everywhere below:

- **The live configuration** is its own repository,
  `cs-image-system-testconfig`, checked out beside this one. The Justfile
  reaches it at `../cs-image-system-testconfig`; `CSIS_CONFIG_ROOT`
  overrides. Its `module_source_base` reaches this repository's
  `tfmodules/` as `../cs-image-system-3/tfmodules`, so the two checkouts
  must sit side by side.
- **The frozen fixture** under
  [tests/fixtures/config/](../tests/fixtures/config/README.md) is owned by
  the tests. Nothing under `tests/` reads the live tree
  (`tests/test_fixture_independence.py` enforces it), and no run ever
  commits into the fixture. Its people are synthetic personas on example
  domains.

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
tofu init -input=false -reconfigure [-backend-config=<root>.tfbackend.hcl]
tofu plan -input=false -out=tfplan [-replace=…] [-var=…]
cs-image-system gate-plan --planfile tfplan --tofu <tofu> [--allow-destroy <addr>]... [--require-unmounted <inst>:<storage>]...
cs-image-system apply-check --lifecycle <key> --root <root> --root-alias <runtime> [--overlay <file>]... [--apply-runtime <rt>]   (only when an apply is emitted)
tofu apply -input=false tfplan                                                                                                   (only when an apply is emitted)
```

- `rm -f tfplan` first, and `gate-plan` refuses a planfile older than the
  root's newest `*.tf` (exit 3, `STALE PLANFILE`): a failed plan can never
  hand the gate a previous sequence's file.
- `gate-plan` fails (exit 3, `DESTROY NOT WHITELISTED`) unless every
  planned destroy is whitelisted by `--allow-destroy`. The only
  whitelisted destroys are operation-driven: an instance replacement from
  `upgrade instance`, an instance that was decommissioned (removed from
  the YAML, or undeclared for the invocation), a storage whose requested
  state is `destroyed` or `archived`, and an attachment whose detach was
  unmounted first. `--require-unmounted` refuses (exit 3, `DETACH NOT
  UNMOUNTED`) without a successful receipt.
- `apply-check` re-reads `cfg/_config.yml` (and the run's overlays) at
  EXECUTION time and exits 3 when the flag is off *now*, so a script
  generated under yesterday's flags cannot apply under today's. A
  vanished overlay is a refusal.
- `apply` runs the very plan file the gate passed.

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
- `--only-runtime <rt>` restricts the bake surface to every image baked on
  that runtime, and generates and plans **no other runtime's** storage or
  instance root (their plans can only fail or waste time). A list-valued
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
  the series, the parent build the bake is from, the capability stamp,
  every modification's content hash, the in-bake tests and the bake disk
  size; for base images also the declared vendor source, the admin user
  and keys, and the update policy. It excludes machine type, preemptible,
  IAP, ssh username, run ids and timestamps. Vendor-family *movement* is
  excluded too: the declared reference is hashed, not what it resolves to
  today;
- its **parent moved** under `parent_policy: follow`; a parent that bakes
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

### Parent and image policies

An instance image declares `parent_policy: pinned` (default: it bakes from
its pinned parent build until an explicit `upgrade image`) or `follow` (a
newer parent head re-bakes it in the same run and moves the pin, logged as
`op: follow`; the pin moves when the bake is recorded, never in a dry
run). An instance declares `image_policy: pinned` (default) or `follow` (a
newer image head plans the gated replacement; the pin moves after the
apply). A pinned child whose parent head has moved is reported by the
state query as `stale`: informational, never hard.

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
true` lets an instance pin only to a released build of its image.

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
`just` need the variable in their environment to benefit.

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

**Archiving.** `state: archived` on a storage whose builder can archive
(GCE pd and AWS EBS; S3, EFS, GCS and Filestore refuse it at validation)
snapshots it as `csis-<name>-archive` (a GCE snapshot name, or the Name
tag of an EBS snapshot) before the whitelisted destroy of the live
resource; the record keeps the archive name and the state query expects
the disk absent and the snapshot present. Declaring it `active` again
creates the disk *from* that snapshot (on EBS the module resolves the
snapshot by its Name tag at plan time) and deletes the snapshot after the
apply; `destroyed` from `archived` deletes the archive. The storage must
be unattached first. The AWS scripts use the runtime's
`--region`/`--profile` with credentials from the environment.

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
`state import`, which records reality the query just observed.

| File | Holds | Written by |
| --- | --- | --- |
| `identity.yaml` | the identity read-model: groups (builder, identity type, gid policy, members, admins, `managed`), users | identity lifecycle |
| `storage.yaml` | the storage read-model: type, cardinality, allowed groups, `public_read`, share mode, requested vs current state, attachments, declared lifecycle | storage lifecycle |
| `storage-state.yaml` | the authoritative storage state, generation and transition history | after a real storage apply |
| `lineage.yaml` | every built artifact: build id, series, parent, `input_fingerprint`, stamped capabilities, mods | after packer builds (manifests) |
| `pins.yaml` | instance → build and image → base-build pins, with bind/upgrade/follow/dispose/decommission history and pending replacements | first bind, `upgrade`, decommission, dispose |
| `launch-params.yaml` | per-instance launch parameters (mounts, group, enrollment kind, session) and the `launched` marker | instance-image lifecycle; marker after a real instance apply |
| `runs.yaml` | the run journal (bounded to the last 200 runs; git history is the full record): run id, requested lifecycles, dry run or not, outcome, per-lifecycle apply status, error | every run |
| `verifications.yaml` | instance verification verdicts (last 500) | `verify instance` |
| `image-tests.yaml` | the latest post-bake test result per build | `verify instance` |
| `releases.yaml` | every release ever made and, per model, the current released build of each series | `release` |
| `mod-tests.yaml` | modification test results keyed by the mod's content hash (apply + idempotence), so an unchanged mod is not re-tested | `test-mods` |

### Run outputs and exit codes

A run ends with `generated/run-summary.json`: `run_id`, `requested`,
`dry_run`, `ok`, `validation_errors`, per-lifecycle results, `apply`
(per lifecycle: `executed`, `dry-run`, `no-script`, `failed`,
`not-attempted`, `stale-script-skipped`), `meta_state_commit`, `error`,
`state` (the pre-run state query's counts), `overlays`, `undeclared`,
`bake_plan`. The pre-run state query writes `generated/state-report.json`.

| Command | Exit | Meaning |
| --- | --- | --- |
| `run` | 1 | any failure (validation, generation, apply, hard drift, an expired session before the load) |
| `run` | 2 | no or unknown lifecycle; unknown `--apply-runtime`/`--only-runtime` |
| `validate` | 1 | any rule fails; generates nothing |
| `preflight` | 2 | a session absent or expired (the configuration could not load) |
| `preflight --strict` | 1 | a session expires within `config.preflight.expected_run_minutes` (default 30) |
| `state query --strict` | 1 | hard drift; any drift class but `stale`; a session expiring within the window |
| `gate-plan` | 3 | destroy not whitelisted, stale or missing planfile, detach not unmounted; 2 with no plan input |
| `apply-check` | 3 | the flag is off now, no `cfg/_config.yml` found, or an overlay is gone |
| `public-safe` | 1 | a finding; 2 when `--staged` is used outside a git repository |
| `empty --runtime` | 1 | a leftover or drift; 2 when the runtime cannot answer |
| `test-mods` | 1 | a failed or non-idempotent mod; with `--strict`, any skip |
| `release` | 1 | refused (evidence missing); 2 with no image and no `--declared` |
| `dispose`, `upgrade`, `verify`, `unmount`, `lineage *`, `decrypt`, `reencrypt`, `runtime describe` | 1 | refused or failed |
| `identity-attributes` | 4 | attribute writes are disabled; 3 on an invalid plan |
| `test`, `cleanup` | 2 | retired names; the message names the replacement |

### The state query

`state query [--strict] [--json]` asks every plugin for its provider's
view of what the system manages (images by lineage tags, storages by
name, groups by gid, memberships and enrollment tokens by API) and diffs
it against meta-state. It touches nothing and writes
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
`restamp` fixes the record side, `relabel` the tag side.

An enrollment token deleted out of band is HARD drift, and because the
oktapam provider ERRORS on refresh rather than planning a recreate, the
message names the repair: `tofu state rm` the token, then a gated
identity apply.

`state import [--no-images] [--no-storages]` adopts *foreign* artifacts
into meta-state. It writes meta-state only, never the cloud, OPA or tofu
state; importing into tofu state stays a deliberate human step.

**Sessions.** `state query`, every run, `preflight` and `just
cloud-preflight` read the credential caches, never a credential value,
and print one `session:` line per source: an AWS SSO profile's token
expiry from `~/.aws/sso/cache` (static keys and non-SSO profiles have no
readable expiry), and whether GCP Application Default Credentials exist.
A session that is expired or expires within
`config.preflight.expected_run_minutes` (default 30) is flagged; the
strict query refuses on it, a run warns, and an expired session refuses
before the configuration even loads.

## 2. The developer workflow

### Setting up

`just init` runs `uv sync --all-extras` and installs the pre-commit hook
(`git config core.hooksPath .githooks`). It is idempotent. Python is run
as `uv run python`; the CLI as `uv run cs-image-system` (what every recipe
does).

### The bar: `just test`

`just test` is the local acceptance bar, every check blocking: `lint`
(ruff over `packages` and `tests`), `typecheck` (pyright, basic mode, 0
errors), `pytest` (the unit tests, the golden emission included). `just
verify` is its alias. It needs no live configuration and no credentials:
the tests own the frozen fixture and export its TEST identity themselves.
`just ci` (pyright non-blocking) mirrors an older workflow shape and is
not the bar.

The tests run over private copies of the fixture with every cloud, Okta
and tool execution stubbed; `just v2-test` runs the gate tests alone
(`tests/test_v2_*.py`).

### `just full-test`

Everything `test` does plus the slow and external legs:

1. the modification tests under docker (`just test-mods --strict`), when
   `docker info` succeeds;
2. only when the live configuration is present AND `just preflight` finds
   every runtime session present: a headless dry `run --all` over a
   private copy of the live configuration (its `.git` and `generated/`
   excluded, `tfmodules/` copied beside it), followed by `state query
   --strict` over the copy.

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
the configuration needs `tfmodules/` beside it.

### `just config-drift`

Is the committed emission current with the declarations? A headless dry
`run --all` over a private copy of the live configuration, compared with
the `generated/` tree committed at its HEAD. Tool residue (`.terraform`,
`.terraform.lock.hcl`, `tfplan`, `temp_assets`), the run-local files
(`run-summary.json`, `state-report.json`, `generated/release/release`,
`generated/retention/retention`), run ids and the run's date stamp in
image names are normalised; nothing else legitimately differs, so a
machine's absolute path appearing in the emission IS drift. Exit 0 when
current, 1 with the diff when the committed emission is BEHIND the
declarations, 2 when nothing is committed under `generated/` or the dry
run itself fails. A dry run's `init` skips the backend, so no state
access is needed.

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
hooks` installs it here, `just hooks-live` in the live checkout; the hook
finds `cs-image-system` on `PATH` or in either checkout's `.venv`); `just
public-safe` scans this checkout (tracked files plus untracked files that
are not ignored, with the fixture's allow list) and CI's `verify` job
runs it; `just public-safe-live` scans the live configuration with its
own allow list, and runs before any publication. Allow a value by
decision, never by bypassing the hook.

### The frozen fixture and the live sibling

Every recipe that drives a configuration (`cli`, `v2-dry-run`,
`test-mods`, `preflight`, `config-drift`, `public-safe-live`,
`hooks-live`, the `cloud-*`/`gce-*` cycle) depends on the private
`config-guard` recipe, which exits 2 with the clone command when
`<config_root>/cfg/_config.yml` is missing. `just test` never needs it.

The fixture carries no `meta-state/` and no generated output; its instance
subjects (`test`, `test2`, `gce-test`) are declared in its own
`instances/instances.yaml`; its rosters are encrypted entry by entry to
the fixture's own committed TEST identity (`.age-identity`, public key
`.age-recipient`), which the harness exports as `CSIS_CONFIG_IDENTITY`.
`tests/test_fixture_personas.py` pins that a real roster cannot return;
the fixture's allow list names no real domain. Never put a real name in
the fixture, the golden or a test.

A change that touches the live configuration is committed and pushed on
that repository's `develop` branch as part of the same piece of work.

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
`develop` or `main`; never force-push a shared branch. Documentation-only
changes skip the bar (nothing in it reads Markdown); say so.

### `just build`, `just release`, `just publish-tree`

`just build` packages every workspace member (sdist + wheel) under
`dist/`; no tests.

`just release <version> [yes]` is gated on `full-test` (the contract).
`just release 0.2.0 yes` is the dry form: `full-test`, then the version
bumps `uv version --dry-run` would make and what would follow. The real
form:

1. refuses a dirty working tree, and refuses without
   `<config_root>/meta-state/mod-tests.yaml` (the evidence that the
   released modifications passed; `full-test` with docker writes it in
   the LIVE configuration) or with any other change in the live checkout;
2. sets the version on the root and every workspace package
   (`uv version`), `uv lock`;
3. commits the mod-test evidence in the live repository
   (`release <v>: modification-test evidence`) and `pyproject.toml`,
   `packages/*/pyproject.toml`, `uv.lock` here (`release <v>`);
4. tags `v<version>` (annotated) and runs `just build`;
5. publishes with `uv publish dist/*` only when `UV_PUBLISH_URL` (and
   `UV_PUBLISH_TOKEN`) is set; otherwise the leg reports `SKIPPED` and
   **the tag is the release**.

Nothing is pushed: `git push --follow-tags` is the operator's act.

`just publish-tree <root> <dest>` builds what a public repository will
hold: the TRACKED files of `<root>` at HEAD (`git archive`; nothing
ignored can enter), minus `PUBLISH_EXCLUDE="path/one path/two"` (default
none), gated by `public-safe` with the root's own allow list (or the
fixture's when the root is this repository), the destination's
`.gitignore` checked line by line for `.envrc`, `.private_key.pem`,
`.private_key.json`, `.public_key.json`, `*.pem`, `tfplan`, `*.tfstate`,
`*.tfstate.backup`, then ONE commit on `main` (`PUBLISH_MESSAGE`,
default `Initial public release`). It refuses a dirty root, a finding, a
missing ignore line or an existing `<dest>`, and never pushes.

### The modification tests

`just test-mods [--image <img>]... [--force] [--strict]` runs every
modification against a throwaway local container, twice (apply, then
idempotence), and records the results in the live configuration's
`meta-state/mod-tests.yaml` keyed by the mod's content hash. The container
image follows the instance image's OS family and version (`almalinux:<v>`
for the EL images). `--strict` exits 1 when a test is skipped (no docker,
an unsupported family); `--force` re-tests mods that already passed. It
needs docker and the live configuration, no cloud credentials.

### Recipe catalogue

`just` alone lists the recipes in file order, the contract first.

| Recipe | What it does | Needs |
| --- | --- | --- |
| `init` | `uv sync --all-extras`, then `hooks` | nothing |
| `build` | sdist + wheel of every workspace member under `dist/` | nothing |
| `test` | lint → typecheck → pytest, all blocking (the bar) | nothing |
| `full-test` | `test` + `test-mods --strict` (docker) + dry `run --all` and `state query --strict` over a copy of the live tree (sessions) | docker, live tree, runtime sessions; each leg skips loudly |
| `release <version> [yes]` | `full-test`, version bump, commit, tag, `build`, publish when `UV_PUBLISH_URL` is set | clean trees, mod-test evidence, `full-test`'s needs |
| `format` | `ruff format packages tests` | nothing |
| `lint` / `lint-fix` / `lint-unsafe-fix` | ruff check; with safe / unsafe fixes | nothing |
| `typecheck` | pyright | nothing |
| `pytest` | the unit tests alone | nothing |
| `v2-test` | `tests/test_v2_*.py` alone | nothing |
| `test-mods *ARGS` | the modification tests in a container | docker, live tree |
| `golden-regen` | rewrite `tests/fixtures/v2_golden` from the fixture | nothing; review the diff |
| `v2-dry-run *ARGS` | `run --all` (dry) against the live tree | live tree; AWS profile for discovery |
| `ci` | lint → pyright (non-blocking) → pytest; not the bar | nothing |
| `public-safe *ARGS` | scan this checkout with the fixture's allow list | nothing |
| `public-safe-live *ARGS` | scan the live tree with its allow list | live tree |
| `publish-tree <root> <dest>` | a publishable copy: tracked files, gate, one commit on `main` | a clean root |
| `hooks` / `hooks-live` | `core.hooksPath .githooks` here / in the live checkout | (live tree) |
| `verify` | alias of `test` | nothing |
| `clean` / `clean-venv` / `clean-all` | build residue / `.venv` / both plus `uv.lock` | nothing |
| `config-drift` | is the committed emission current? (0 / 1 behind / 2 failed) | live tree, sessions, `CSIS_CONFIG_IDENTITY` |
| `cli *ARGS` | the CLI against the live tree, e.g. `just cli validate` | live tree; whatever the command needs |
| `tofu-cache-dir` | create `TF_PLUGIN_CACHE_DIR` | nothing |
| `preflight` | the runtime sessions from the caches, no load (0 / 2) | live tree |
| `cloud-preflight` / `gce-preflight` | `state query --strict` (both clouds) | live tree, AWS + GCP sessions, identity credentials, `CSIS_CONFIG_IDENTITY` |
| `cloud-describe <rt>` | the configuration's facts about a runtime as JSON | live tree, sessions |
| `cloud-bake <rt> [yes]` / `gce-bake [yes]` | `run base-image instance-image --only-runtime <rt> --commit`; the storage/instance roots plan and gate only | `cloud-preflight`; real bakes need write credentials |
| `cloud-cycle <rt> [yes]` / `gce-cycle [yes]` | `run --all --only-runtime <rt> --apply-runtime <rt> --commit`, then `cloud-empty` | `cloud-preflight`; write credentials |
| `cloud-launch <rt> [yes]` / `gce-launch [yes]` | `run instance-image --only none --apply-runtime <rt> --commit` | `cloud-preflight`; write credentials |
| `cloud-verify <rt> <instance> [serial\|iap]` / `gce-verify [leg]` | `verify instance <i> --timeout 600`; `iap` adds a `gcloud compute ssh --tunnel-through-iap` probe | live tree, sessions |
| `cloud-dispose-images <rt> [yes]` / `gce-dispose-images [yes]` | `dispose image --runtime <rt> --all --commit` | live tree; write credentials |
| `cloud-relabel <rt> [no]` / `gce-relabel [no]` | `lineage relabel --runtime <rt>`; dry by default | live tree; write credentials for `no` |
| `cloud-empty <rt>` / `gce-empty` | `empty --runtime <rt>` | live tree, sessions |
| `gce-decommission [yes]` | `--undeclare instance:gce-test run instance-image --only none --apply-runtime gcloud-east1 --commit` | live tree; write credentials |
| `gce-teardown [yes]` | `gce-decommission` then `gce-dispose-images` | as above |

The second positional `yes` on a cloud recipe means dry run (enumerate,
plan and gate; nothing executes); `cloud-relabel`/`gce-relabel` are dry
by default and take `no` to apply. `gce-*` are aliases for the
`gcloud-east1` runtime and its `gce-test` instance.

## 3. CI

[ci.yml](../.github/workflows/ci.yml) runs on every push, every pull
request, a nightly schedule (`23 6 * * *` UTC) and `workflow_dispatch`.
Every command is a `just` target, so CI and a developer's shell run the
same thing. Three jobs: `verify` is the bar, `live` reads the live
configuration, and `apply` performs a real run, on `main` alone.
`tests/test_v2_ci_workflow.py` pins the shape below, that `verify` reads
no secret, that neither `verify` nor `live` passes `--no-dry-run` or
`--commit`, and that `apply` cannot run off `main`, cannot run twice at
once, and holds no write-capable GCP identity.

### The `verify` job

Runs on every push and pull request, with no configuration and no
credentials.

| Step | Proves |
| --- | --- |
| `actions/checkout`, setup-just, setup-uv (Python 3.13) | the toolchain installs from nothing |
| `just init` | the workspace syncs |
| `just verify` | the bar: ruff, pyright (blocking), the suite with the golden, over the frozen fixture |
| `just public-safe` | the checkout holds nothing that must never be public |

It is the standing proof that the suite needs no live tree.

### The `live` job

Runs after `verify` on pushes and the nightly schedule, never on pull
requests (forks carry no secrets). It reads only: it validates, checks
drift, queries state and runs the mod tests; it never plans against
remote state and never applies, because its cloud identities are
read-only and a plan needs the state bucket. There is no applying job.

| Step | What it does |
| --- | --- |
| Gate on the live-configuration secrets | evaluates the secrets below; prints one `live: SKIPPED -- no <SECRET> (…)` line per missing item and sets `ready=false` |
| Check out the system at `cs-image-system-3` | |
| Check out the live configuration beside it at `cs-image-system-testconfig` (`develop`) | the Justfile's default root and `module_source_base` both resolve |
| Federated AWS credentials | `aws-actions/configure-aws-credentials` assumes `AWS_ROLE_ARN` in `us-east-2` via OIDC (`id-token: write`) |
| Name the federated credentials as the configuration's profile | writes `[profile noaa]` to `~/.aws/config` and `[noaa]` with the exported key, secret and session token to `~/.aws/credentials` (mode 600) |
| Federated GCP credentials | `google-github-actions/auth` with `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_SERVICE_ACCOUNT` → Application Default Credentials |
| Install just, uv (3.13), OpenTofu, Packer | |
| Place the tools where `cfg/executables.yml` pins them | symlinks `tofu`, `packer`, `gcloud`, `ansible-playbook`, `bash`, `docker` into `/usr/local/bin` |
| `just init` | |
| `just cli validate` | the live tree loads and passes every rule, with the Okta workspace's assertions and the age identity |
| `just config-drift` | the committed emission is current with the declarations |
| `just cloud-preflight` | reality matches the records (`state query --strict`, both clouds) |
| `just test-mods --strict` | every modification applies and is idempotent in a container |

Every step after the gate carries `if: steps.gate.outputs.ready == 'true'`;
until every secret exists the job prints its skip lines and passes.

### The `apply` job

The other half of the model: branches verify, `main` applies. It runs
after `live`, only when the ref is `main` or the run was dispatched by
hand, and never twice at once (`concurrency: apply-live`, which does not
cancel a run in flight). Its preparation is `live`'s, step for step, with
two differences: it assumes `AWS_APPLY_ROLE_ARN`, a write-capable role
that trusts `main` alone, and it carries the Okta client id, key id and
scopes the terraform okta provider needs to plan the identity roots.

| Step | What it does |
| --- | --- |
| Gate on the apply secrets and decide the mode | one `apply: SKIPPED -- no <SECRET> (…)` line per missing identity; sets `apply=true` only for a push to `main` or a dispatch on `main` asking for it |
| the two checkouts, the federated credentials, the `[noaa]` shim, the tools | exactly as `live` does them |
| `just cli --no-dry-run run --all --commit --only-runtime aws-east2-runtime` | the real run, in apply mode: the convergent AWS bakes, the declared releases, retention disposals, and the commit of meta-state and emission into the configuration repository |
| `just cli run --all --only-runtime aws-east2-runtime` | in dry mode instead: enumerates, commits nothing |
| Push what the run committed | the run commits, the job pushes (`HEAD:develop`); a non-fast-forward fails the job, and nothing is ever forced |
| `just cloud-preflight` | the post-condition: reality matches the records after the run |

**What it does not do, by construction.** The scope is one runtime, so
the GCE runtime is never in it; the job holds no identity that could
write to GCP, so a GCE root that slipped into scope fails at load instead
of spending money. The live configuration's `apply_*` flags are all
false and no `--apply-runtime` is passed, so the storage, instance and
identity roots plan and gate only. Post-bake tests launch an instance, so
they need `apply_instances` and do not run here.

**Cost.** No CI run can leave a billable GCP resource standing, because
no job holds an identity that could create one. On AWS a real run may
leave what convergence baked, an image and its snapshot, cents a month
each, until retention disposes them.

### The `[noaa]` profile shim

The runtimes declare `credentials.profile_name: noaa`. botocore drops the
environment credential provider whenever a profile is named explicitly,
so the profile itself must carry the federated keys the AWS action
exported (temporary, one hour); the preflight reads a static-key profile
as present. Without the shim the configuration load would find no
credentials for the named profile.

### Repository secrets

| Secret | What reads it | Job |
| --- | --- | --- |
| `AWS_ROLE_ARN` | the federated-credentials action, then the `[noaa]` shim; a READ-ONLY role: EC2 describe for the configuration load, read on the state bucket, image and volume describes for the state query | live |
| `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT` | the GCP auth action: the application-default credentials the gcloud runtime's network discovery and the GCP state query use; read-only | live |
| `OKTA_API_PRIVATE_KEY` | the load's check that the okta provider can authenticate (`okta_tf_workspace.py`) | live |
| `TF_VAR_NOS_KEY` → exported as `TF_VAR_nos_coastal_modeling_cloud_sandbox_key` | the load's `_require_tfvar` assertion; the OPA API for gids and the state query (`opa_gids.py`) | live |
| `TF_VAR_NOS_SECRET` → exported as `TF_VAR_nos_coastal_modeling_cloud_sandbox_secret` | the same two places | live |
| `CSIS_CONFIG_IDENTITY` | the configuration load, to decrypt `ENC[age:…]` values; the CI age identity | live, apply |
| `AWS_APPLY_ROLE_ARN` | the federated-credentials action in `apply`: a WRITE-capable role trusting `main` alone, with the bake's EC2 and image actions and read/write on this configuration's state prefix; deliberately no `iam:PassRole`, no volume or subnet writes, nothing outside the prefix | apply |
| `OKTA_API_CLIENT_ID`, `OKTA_API_PRIVATE_KEY_ID`, `OKTA_API_SCOPES` | the terraform okta provider, which plans the identity roots in a real run | apply |
| `CSIS_CONFIG_PUSH_TOKEN` | the push of what the run committed: a fine-grained token with contents:write on the configuration repository and nothing else | apply |

The gate requires all of `OKTA_API_PRIVATE_KEY`, `TF_VAR_NOS_KEY` and
`TF_VAR_NOS_SECRET` for the Okta item, and both GCP secrets for the GCP
item. The `verify` job reads none of them. The rows marked `apply` are
what that job adds; until every one of them exists it prints its SKIPPED
lines and passes, exactly as `live` did before its own secrets were set.

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
public keys, one per holder: a person or CI). A field declared
`EncryptedStr` decrypts at load with the identity in
`CSIS_CONFIG_IDENTITY` and refuses at load, naming the variable, when none
is set; an unmarked value passes through. Encryption is element-level (a
roster entry by entry: `members:`/`admins:` on groups; `name`,
`first_name`, `last_name`, `email` on users; the Okta workspace's
`key`/`secret`), so a diff shows which entry changed and one entry can be
rotated alone. A decrypted value is a `str` with a repr that hides it.

Tools (no configuration load, no identity needed except to decrypt):

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
- [bin/gen_age.sh](../bin/gen_age.sh), [bin/crypt_age.sh](../bin/crypt_age.sh),
  [bin/rotate_age.sh](../bin/rotate_age.sh) do the same in the `age` CLI's
  format.

Identities are never committed. Operators keep theirs under
`~/.config/cs-image-system/age/`; the CI identity is the
`CSIS_CONFIG_IDENTITY` repository secret; the live recipients are the
operators' identities and CI's. The frozen fixture ships its own TEST
identity so the suite needs nothing from the environment.

**In the emission.** A declared-encrypted value never reaches `generated/`
in clear: the emitted HCL carries the SAME `ENC[age:…]` ciphertext in one
`data "external" "sensitive"` block per terraform root, whose program is
`cs-image-system decrypt --json`, wrapped as `local.sensitive[...]` with
`sensitive()`; user lookups read `local.sensitive["email_<user>"]`, a
declared-encrypted workspace credential reaches its provider block the
same way, and the root requires `hashicorp/external`. The committed
emission is readable by anyone and decryptable only by a recipient; a
rotation is `reencrypt` plus regeneration; plans and state, which hold
the plaintext, are never committed. The rule is "no declared-encrypted
value other than a username in clear", not "no address": an email
DERIVED from `default_user_email_template` is public by construction and
is emitted in plaintext by decision; declare `email:` encrypted for any
address that must not be.

### `just cloud-preflight`

`state query --strict` over both clouds, after `tofu-cache-dir`. It
refuses (exit 1) on hard drift, on any drift class but `stale`, and on a
session that expires within `config.preflight.expected_run_minutes`.
Every cycle step (`cloud-bake`, `cloud-cycle`, `cloud-launch`) depends on
it, so a cycle never starts on a false belief or a lapsing session.
`just preflight` is the lighter form: the sessions alone, read from the
caches without loading the configuration (exit 2 when one is absent or
expired; `--strict` exits 1 on one expiring within the window).

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
  through the system; `iap` adds `gcloud compute ssh --tunnel-through-iap
  --command 'findmnt -n /mnt && id'` with the project and zone read from
  `runtime describe`.
- `just gce-decommission` destroys a leftover standing `gce-test` through
  the gate (`--undeclare instance:gce-test`) instead of re-verifying it; a
  dry run keeps the record. `just gce-teardown` follows it with
  `gce-dispose-images`.
- `just cloud-relabel <rt> no` re-tags images whose tags disagree with
  lineage; `just cloud-dispose-images <rt>` disposes of every recorded
  image on the runtime through the recorded path.

`just gce-cycle yes` is the dry form of the GCE cycle (the `empty`
assertion is skipped in a dry run).

### GCE cost discipline

GCP is the operator's own money. A change that touches it is proven with
one live cycle and leaves nothing behind beyond the declared storages
(`cloud-empty` is the cycle's last word). A run that ends with a billable
GCP resource STANDING says so explicitly: what it is, its id, and what it
costs. Ephemeral resources torn down within the run are not durable and
need no such note. By decision exactly one released image stands on GCE
(a released build is kept); everything else baked on the ephemeral GCE
runtime is disposed by retention. A change is not tested on GCP unless it
is likely to break the GCE code path; then one live cycle, torn down.

### Other CLI commands

`just cli <command>` runs any CLI command against the live tree.

| Command | Does |
| --- | --- |
| `validate` | loads the tree and applies every rule; generates nothing |
| `generate` / `build-all` | aliases: every lifecycle without / with the apply step (`--base-only`: base-image alone) |
| `upgrade instance <name> [--to <build>]` | moves that instance's pin (default: the series head); the next `instance-image` plans `-replace` and the gate whitelists it |
| `upgrade image <name> [--to <base build>] [--runtime <rt>]` | moves an instance image's base pin (per runtime); the next `instance-image` bakes a new build; no instance moves |
| `release …` | marks a build released (above) |
| `dispose image …` | removes a recorded image (above) |
| `verify instance <name> [--expect-build] [--timeout] [--record-only]`, `verify assert <name>` | the runtime's verification; the closing check of the `teardown` policy |
| `unmount storage --instance --storage --mount-point [--workdir] [--confirm] [--timeout]` | the unmount receipt before a detach |
| `state query [--strict] [--json]`, `state import` | reality versus records; adopt foreign artifacts |
| `lineage restamp`, `lineage relabel` | the record side and the tag side of the fingerprint |
| `runtime describe <rt>`, `empty --runtime <rt>` | the configuration's facts; the end-of-cycle assertion |
| `preflight [--strict]` | the sessions, without loading |
| `encrypt`, `decrypt`, `reencrypt`, `public-safe` | the value tools and the scanner |
| `test-mods` | the modification tests |
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
the SSM agent alive). Launch user-data pins sftd's `AccessAddress` to the
private IP and resolves EBS devices by Nitro by-id names when the legacy
`/dev/xvdX` never appears. AWS sessions use SSM (`session_mechanism: ssm`;
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
  state query does memberships; policies are enumerated by hand).
- Never let a plan create an attachment that already exists; import it
  first.
- Attribute writes on identities stay disabled until the stakeholder
  decides otherwise.

### Applies

- An apply is the gated apply of a fresh plan file: explicit go (the
  `apply_*` flag or `--apply-runtime`), `rm -f tfplan`, `plan -out`,
  `gate-plan`, `apply-check`, `apply tfplan`. A hand apply against the
  identity state additionally takes a same-day backup of the S3 state
  first, because those resources are never recreated.
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
- One tofu process at a time on a machine: the shared
  `TF_PLUGIN_CACHE_DIR` is not safe under concurrent `init`, and two runs
  would race on the same roots and records.

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

### Cost

- GCP is the operator's own money: a change is proven on it only when it
  is likely to break the GCE path, with one cycle that leaves nothing
  standing beyond the declared storages and the one released image; any
  billable resource left standing is reported with its id and cost.

## 6. Where things are

| Document | Holds |
| --- | --- |
| [README.md](../README.md) | the entry point: the Justfile contract and the layout |
| [DESCRIPTION.md](../DESCRIPTION.md) | what the system does: the estate, the pipeline, the posture |
| [GOALS.md](../GOALS.md) | the target goals the system is measured against |
| [GOLDEN.md](../GOLDEN.md) | the golden fixture: what it is, how it is produced and enforced |
| [CONFIGURATION.md](CONFIGURATION.md) | the configuration reference: every key of the YAML tree |
| [PLUGINS.md](PLUGINS.md) | the index of the package READMEs under `packages/` |
| [PARITY.md](../PARITY.md) | how the documentation and the system can diverge, and the check for each |
| [DESIGN.md](DESIGN.md) | the design record |
| [history/](history/) | frozen: the findings ledger, the GCP readiness study and the live-proof overlays; evidence, not documentation |
| [tests/fixtures/config/README.md](../tests/fixtures/config/README.md) | the frozen fixture |
| [Justfile](../Justfile) | every recipe, with its comment |
| [.github/workflows/ci.yml](../.github/workflows/ci.yml) | the CI workflow |
| [.githooks/pre-commit](../.githooks/pre-commit) | the public-safe hook |
| `cs-image-system-testconfig` (beside this repository) | the live configuration, its `meta-state/` and committed `generated/` |
| `cs-image-system-3-archive`, `cs-image-system-testconfig-archive` (GitHub, private, archived) | every commit either repository made before it was published, including the kept feature branches and the records that are frozen here under `history/`. Read-only. Nothing from them ever reaches a public remote. |
