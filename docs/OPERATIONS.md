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
tofu init -input=false -reconfigure [-backend-config=<root>.tfbackend.hcl]                                                    (a migrating root instead: state-migration begin, then init -migrate-state -force-copy)
cs-image-system state-migration backup --workspace <root> ...                                                                   (only before a pre-plan state rm)
tofu state rm <address>                                                                                                         (only an unmanaged group's module)
cs-image-system prune-attachments --builder <group builder> ...                                                                 (identity roots only, every run)
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
  id; found 2026-09-22), an instance that was decommissioned (removed from
  the YAML, or undeclared for the invocation), a storage whose requested
  state is `destroyed` or `archived` or that is no longer declared, and an
  attachment whose detach was unmounted first. `--require-unmounted` refuses (exit 3, `DETACH NOT
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
is how the records used to lie about a stopped machine.

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

### A canonical hostname is claimed once

The name an instance is given at boot (`hostnamectl set-hostname`) is the
name it enrolls in OPA under, and `sft ssh <name>` resolves against that
registry. Three rules keep one name meaning one machine (stage 55):

**The registration goes with the machine.** A decommission already drops
the instance's pin and launch parameters; it now retires its OPA server
registration too -- the third record of the same launch, and the one that
used to outlive the machine (three `coops-model` entries stood in
`coops_rg_login` on 2026-09-21, one of them live). A retirement that fails
is an ERROR naming the hostname, never a silent skip: the forget still
happens, but the log says a stale server will answer to that name until it
is deregistered by hand.

**A run that can launch refuses a claimed name.** Before the instance-image
lifecycle applies, every declared instance's hostname is checked against
its group's registry. An unlaunched instance whose name is already
registered is refused, naming the record; a launched one with more than one
registration is refused too, because `sft ssh` cannot choose between them.
The check runs ONLY when a launch is actually possible -- the lifecycle
requested and `apply_instances` on -- so a dry run never makes the call.
And an unreachable registry is a refusal saying the claim *could not be
checked*: silence is not a free name (the same rule the power-state query
follows), and an unreachable OPA is exactly when a duplicate would
otherwise slip through.

**A name the machine cannot take is refused at validate.** RFC 1123 caps a
hostname label at 63 characters of letters, digits and hyphens, not
starting or ending with one; Okta documents no limit of its own. Nothing
checked this before, and the failure was silent -- the boot line ends in
`|| true`, so an invalid name left the machine under the hyperscaler's
name (`ip-10-26-34-156`), enrolled in OPA as that, and `sft ssh` found
nothing while every step reported success.

**The canonical name carries the generation** (stage 55 step 4): a new
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
launched before the suffix existed -- `coops-model`, adopted as generation
1, stays `coops-model` until its first sanctioned replacement, and then
becomes `coops-model-002`.

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
with nothing configured (settled live, 2026-09-21). The one name that does
NOT resolve is the provider's own hostname, `ip-10-26-34-156`, because the
launch script overwrites it with the declared name before sftd enrolls.

**The system gives that name back after launch** (stage 58): an
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
closes when THAT machine is destroyed; storage has had the same word for the
same thing since stage 10.12. `meta-state/instance-state.yaml` holds, per
instance name, two counters (`durable`, `ephemeral`), the open generation --
its number, kind, the run that opened it, the provider's instance id once
seen, and a SNAPSHOT of the launch parameters it booted with -- and a
history nothing is ever deleted from. `launch-params.yaml` keeps holding
what the current machine booted with; the two files divide exactly as
`storage.yaml` and `storage-state.yaml` do, and the counter is never in the
launch-params record (it would read as a changed launch parameter and refuse
the very replacement that bumped it).

**The machine decides.** A launch that applied opens a generation marked
`inferred`. After the apply the system asks the provider which machine
bears the name: the same id confirms it (`observed`); a DIFFERENT id means
the machine you knew is gone and another stands -- the generation closes as
`replaced-out-of-band` and the next opens, with a warning saying nothing in
this system did it. A sanctioned replacement (`upgrade`, a follow) closes
the generation as `replaced` and opens the next in the same run. A
decommission closes it as `decommission`, an ephemeral teardown as
`ephemeral` -- an ephemeral machine existed, booted and enrolled, and its
generation is the record that lets stage 55 deregister it honestly.

**What is not a new generation**: a reboot; a stop and start (a stopped
machine is the same machine); a mount detach; an image pin that moved but
was not applied; and an identity query that returned nothing -- "cannot
read the id" is never "the id changed", and a stopped instance may well
fail the query.

**What stood before the ledger is adopted, not invented.** A machine that
was already launched when this record began becomes generation 1 marked
`adopted` -- the first generation of the RECORD, not of the name. Its
predecessors are visible only in `pins.yaml.upgrades`. The state report
shows each launched machine's generation beside its provider identity under
`reality.instances`.


### CI logs in through the policy the system manages

Verifying an instance through SSM proves the box is healthy; it says
nothing about access. Stage 56 makes CI log in the way a scientist does --
`sft ssh`, a short-lived OPA certificate, no static key -- and makes that
login depend on the policy the system manages, so the proof is of the
policy.

CI is a **workload**: the GitHub Actions run presents GitHub's own OIDC
token to the team's **workload connection**, which maps it to the team's
one **workload role**. Both are the operator's, made by hand once in the
OPA console and named on the okta-tf group builder
(`workload_connection`, `workload_role`); the checklist with the values,
the impersonation cases (what a name pin trusts) and the relocation order
(what to edit, in which order, when the repository moves) is
[WORKLOAD_CONNECTION.md](../WORKLOAD_CONNECTION.md) until the proof has
run, after which it folds in here. `just sft-install` puts Okta's client on
an apt runner; `just opa-workload-probe` (the dispatch-only `OPA workload
probe` workflow) presents a run's token to the connection and reports the
client's verdict, masking both tokens -- the test to run against a draft
connection before activating it.

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
`cloud-verify`). For each standing instance -- launched, not ephemeral --
of a group whose builder names the workload objects it checks, in order:
the machine is RUNNING (a stopped one is skipped and never started, stage
57); exactly one server answers to the canonical hostname in the group's
registry (stage 55: a second one would make `sft ssh` reach an arbitrary
machine); the client resolves the name; `id` runs over `sft ssh`. Each
verdict, with the Unix account the login landed in, goes to
`meta-state/login-proofs.yaml`. With `OPA_TOKEN` in the environment the
login is the workload's (`scripts/opa-workload-token` mints it from the
Actions run's OIDC token; the recipe does this itself inside a job); run by
hand without one, the enrolled client logs in as you and the record says
`as: client`. In CI the `perform` job runs it on `main` after the
performing step, under the read-only role, and the closing record commits
the verdicts. What must turn it red: the group's CI policy deactivated or
absent, the role's condition not matching the run, a machine that never
enrolled, a duplicate hostname -- and deactivating one group's policy
fails that group's proof alone.


### A model image, end to end: the second release

The coops model's image had its second release on 2026-09-22, and the
path is now a procedure. It takes one durable instance (`coops-model`, a
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
   sequence, what were five hand steps until 2026-09-23:
   - *the pin*: `upgrade instance` moves it to the series head and leaves
     the pending-replacement marker; the strict state query now reports
     the booted image behind the pin as a `note`, not drift;
   - *the replace*: `cloud-launch`. The plan carries `-replace` for the
     instance and the gate whitelists it AND its volume attachments (the
     attachment binds the volume to the instance's id). The new machine
     boots as `coops-model-002` (stage 55 step 4); generation 1 closes as
     replaced and 2 opens on the new instance id (stage 60); the replaced
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
     in the same run gets them in that run, after it answers and enrolls.

   `config.require_released_builds` stays `true` the whole way. Until
   2026-09-23 it had to be switched off for the middle steps: an instance
   pinned to an unreleased build made every run refuse, and for a durable
   instance whose volume allows one attachment no proof instance can
   mount what the post-bake spec requires, so the proof can only run on
   the instance itself. The release grace (above, under `release`) admits
   the series head while its own proof is under way and refuses the
   moment the proof fails; nothing is edited by hand.
4. **The login.** `just ci-login-proof coops-model` logs in by name.

**The standing cost** of the model node, from the on-demand price this
account cannot query (no `pricing:GetProducts`): a `c5n.4xlarge` at about
$0.86 an hour, some $620 a month while it stands, plus the 100 GiB `gp3`
volume and the EFS filesystem. Switching it off (the operator's, stage
57) stops the instance charge and keeps the volume's.


### A pool of names, each spent once

`meta-state/aliases.txt` in the configuration is a pool of memorable,
pre-approved names, hand-written in advance, one per line. When a NEW
machine of a durable instance is about to be launched -- never launched
before, or a pending or follow replacement -- the run that can launch it
takes the first line that is not commented out, records it as the
machine's `alias` in its launch parameters, and comments that line out
IN PLACE with what took it and when:

```text
# bright-otter  -- instance coops-model as coops-model-003 2026-09-22T15:04:11Z run 2026_09_22t15_04_11_004213
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
  shrinks, and the operator refills it by appending.
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
construction: every recipe that may execute the roots (`v2-dry-run`,
`cloud-bake`, `cloud-cycle`, `cloud-launch`, `gce-decommission` and
their `gce-*` aliases) goes through `scripts/with-tofu-lock`, which holds
`.tofu-plugin-cache/.lock` for the command and refuses with exit 75 and
the holder's pid while another has it. Dry runs enumerate and never
start tofu, so `config-drift`, `cloud-preflight` and the bar take no
lock; the suite's one real-tofu test uses a private cache under its
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
| `state-locations.yaml` | every workspace's resolved state location (type, container, key) and the record of every move | every run, dry runs included, after generation |

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
emitted, and none of what follows applies.

Three backend types exist (stage 47): `s3` -- a bucket, `s3://<bucket>/<key>`
-- `local` -- a file on disk, `local://<directory>/<root>.tfstate`, the
directory relative to the configuration root, needing no credentials -- and
`gcs` -- a Google Cloud Storage bucket, `gcs://<bucket>/<prefix>/<root>/default.tfstate`,
declared in the fixture and in the live tree (commented out) and bound to
nothing, since the GCE roots stay on S3 by the standing decision. A
type is a plugin (a model and a kind that renders the location, the backend
file and a consumer's data source; the S3 plugin's README has the recipe),
and the collector names no field of any type. The fixture's identity roots
use `local` and its storage roots a second S3 bucket, so its roots read
each other's state across types and buckets; the live configuration keeps
every root on its default S3 backend by the standing decision.

The backend a root uses resolves through a chain (stage 46): its own
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

Every run records each generated root's resolved location in
`meta-state/state-locations.yaml` (the record, not the emission, is the
memory: `generated/` can be pruned or regenerated). A later run whose
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
`bake_plan`. The pre-run state query writes `generated/state-report.json`.
Both are **run-local**: the emitted `generated/.gitignore` names them, a
`--commit` run never stages them, and a run whose configuration
repository tracked them from an older tree removes them from the index
(the files stay on disk). `generated/final_execution.sh` and
`meta-state/runs.yaml` are records and are committed.

| Command | Exit | Meaning |
| --- | --- | --- |
| `run` | 1 | any failure (validation, generation, apply, hard drift, an expired session before the load) |
| `run` | 2 | no or unknown lifecycle; unknown `--apply-runtime`/`--only-runtime` |
| `validate` | 1 | any rule fails; generates nothing |
| `preflight` | 2 | a session absent or expired (the configuration could not load), or a credential-shaped environment variable (`AWS_*`, `GOOGLE_*`, `OKTA_*`, `TF_VAR_*`, `CSIS_*`) that is set but EMPTY -- reported by name, never by value |
| `preflight --strict` | 1 | a session expires within `config.preflight.expected_run_minutes` (default 30) |
| `state query` | 1 | hard drift |
| `state query --strict` | 1 | hard drift; any drift class but `stale`; `unavailable` (a provider that could not answer); a session expiring within the window |
| `gate-plan` | 3 | destroy not whitelisted, stale or missing planfile, detach not unmounted; 2 with no plan input |
| `apply-check` | 3 | the flag is off now, no `cfg/_config.yml` found, or an overlay is gone |
| `public-safe` | 1 | a finding; 2 when `--staged` is used outside a git repository |
| `mask`, `materialize` | 1 | the identity cannot open a marker (`materialize`); `mask` prints nothing and exits 0 without an identity today, which a code stage names |
| `verify login` | 1 | the login proof failed (registration count, resolve, login); 2 with no standing instance |
| `forget instance` | 2 | the instance is still declared |
| `workload describe --env` | 2 | the builder names no workload connection or role |
| `state-migration`, `prune-attachments` | 1 | the step failed (a pull, a list or a removal); 2 on a wrong action or an unknown builder |
| `run --migrate-state` under a dry run | 2 | a move needs `--no-dry-run` |
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

A managed group the identity provider could not be ASKED about -- a
lapsed or unsourced key pair (`HTTP 401`), no network -- is an
`unavailable:` line naming the group and the error, never a `missing`
group: the provider made no claim. Only an answered absence (a 404) is
`missing … [HARD]`. The strict query refuses either way (only `stale` is
tolerated), but for the stated reason, and a plain run warns and goes on
as it does for an unreachable cloud.

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
before the configuration even loads. An `sso-session` profile (the live
`noaa`) reports no fixed expiry -- its access token renews itself while
the portal session lives, and the portal's end is written nowhere the
system can read -- so a session that lapses mid-run is environmental, not
a defect: it costs the legs that were running, and the repair is `aws sso
login --profile <p>` then `just full-test-legs` (never the whole bar).

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
There is no looser recipe: the contract test asserts that a
`ci` recipe with a non-blocking type-check stays gone.

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

### `just build`, `just release`, `just publish`, `just publish-tree`

`just build` packages the system and every workspace member (sdist +
wheel: thirty-four files) under `dist/`; no tests. The builds are
reproducible -- two builds of one tree are byte-identical -- which is what
lets CI check a tag against the index instead of uploading it again.

`just release <target> [test|pypi] [yes]` (stage 41) cuts a release and
publishes it. `<target>` is a part for `bump-my-version` -- `patch`,
`minor` or `major` open the next version as its first development
release (`0.1.0` → `0.1.1.dev1`), `dev` is the next development release
of the same version (`0.1.1.dev1` → `0.1.1.dev2`), `stage` finalises it
(`0.1.1.dev2` → `0.1.1`) -- or an explicit version. The index is `test`
(TestPyPI, the default) or `pypi`. `yes` as the third argument is the dry
form: the probes and the version, nothing changed. The real form, in
order:

1. the probes, before anything changes: the token is set
   (`UV_PUBLISH_TOKEN`, else `TEST_PYPI_TOKEN` / `PYPI_TOKEN`); the
   index does not know the version (`scripts/index-knows` reads the
   simple index; a version is never re-cut, because a deleted version's
   files can never be uploaded again); no `v<version>` tag exists here
   (the local record of a version that was cut, deleted from the index
   or not); `dev` on a final version is refused (open the next version
   with `patch` first);
2. a clean working tree, then the gate: for TestPyPI the bar
   (`just test`); for PyPI `just full-test`, the modification-test
   evidence at `<config_root>/meta-state/mod-tests.yaml` (written by
   `full-test` with docker in the LIVE configuration) and a live checkout
   clean apart from it;
3. `bump-my-version bump <part>` (or `--new-version`): every `version =`
   line and every `== <version>` pin between the packages, in one move
   (`[tool.bumpversion]` in the root `pyproject.toml`); then `uv lock`;
4. `just publish <index>` -- BEFORE the commit and the tag, so a failed
   upload leaves an uncommitted bump to discard
   (`git checkout -- pyproject.toml packages/*/pyproject.toml uv.lock`)
   and never a tagged, unpublished version;
5. for PyPI, the mod-test evidence committed in the live repository
   (`release <v>: modification-test evidence`); then `pyproject.toml`,
   `packages/*/pyproject.toml` and `uv.lock` committed here
   (`release <v>`) and the annotated tag `v<version>`.

Nothing is pushed: `git push --follow-tags` is the operator's act, and
the pushed tag makes CI's `publish` job check the release against the
index (it uploads nothing the index already holds).

`just publish [test|pypi]` builds and uploads the version in the tree:
`dist/` cleaned, `just build`, then `uv publish --index <name>`. The
endpoints are the `[[tool.uv.index]]` entries in the root
`pyproject.toml` -- `testpypi` uploads to `https://test.pypi.org/legacy/`
and is checked against `https://test.pypi.org/simple/`; `pypi` uploads to
`https://upload.pypi.org/legacy/` -- both `explicit`, so neither takes
part in resolving the workspace. The index's `url` is the check URL (uv
refuses an explicit `--check-url` beside `--index`; the first release
attempt stopped on exactly that, before anything was uploaded, committed
or tagged). Files the index already holds with the
same content are skipped, so a re-run after a partial failure uploads
what is missing and nothing twice. The credential is `UV_PUBLISH_TOKEN`
from the environment or, absent that, the index's own name --
`TEST_PYPI_TOKEN` or `PYPI_TOKEN`, the repository secrets' names, so one
`.envrc` line serves the shell and CI alike -- and never in the Justfile:
while versions are being deleted and re-cut, an account-scoped TestPyPI
token; trusted publishing
(a pending publisher per project name, seventeen registrations) waits until
the names are stable, and is then the CI job's credential.

The version lives in eighteen places -- seventeen `version =` lines and the
`== <version>` pins between the packages -- and `bump-my-version` is the
one thing that changes them (`uv version` bumps the lines but never a
pin, so it is not used). The scheme is `MAJOR.MINOR.PATCH[.devN]`; every
version goes to TestPyPI first, and versions there are deleted as
development goes on, so an increment must be cheap: `just release dev`
is one. `tests/test_v2_package_metadata.py` bumps a copy of the tree and
asserts nothing of the old version is left.

### Installing a release

The seventeen packages are on the index as `cs-image-system` (the whole
system: no sources, a `==` pin on every package) and
`cs-image-system-<package>`. TestPyPI does not carry the third-party
dependencies, so an install from it names PyPI as the extra index (in
`uv`, `--extra-index-url` takes priority over `--index-url`, so the
third-party packages come from PyPI and only the `cs-image-system` names
fall through to TestPyPI):

```sh
uv venv .venv
uv pip install --python .venv/bin/python \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  cs-image-system==<version>
.venv/bin/cs-image-system --help
.venv/bin/cs-image-system decrypt --help
```

A final version on PyPI installs with `uv pip install
cs-image-system==<version>` alone. Python 3.13 or later. The tools the
system drives (`tofu`, `packer`, `gcloud`, `ansible-playbook`, docker) are
not Python packages and are not installed by this; the configuration's
`cfg/executables.yml` pins where they are. The same install from the
built files, without an index, is `uv pip install --find-links dist
cs-image-system==<version>` after `just build`; the seventeen wheels
installed that way into a fresh virtualenv run `cs-image-system --help`
and `decrypt`, which is the proof that every package declares what it
imports.

`just publish-tree <root> <dest>` builds what a public repository will
hold: the TRACKED files of `<root>` at HEAD (`git archive`; nothing
ignored can enter), minus `PUBLISH_EXCLUDE="path/one path/two"` (default
none), gated by `public-safe` with the root's own allow list (or the
fixture's when the root is this repository), the destination's
`.gitignore` checked line by line for `.envrc`, `.private_key.pem`,
`.private_key.json`, `.public_key.json`, `*.pem`, `tfplan`, `*.tfstate`,
`*.tfstate.backup`, then ONE commit on `main` carrying the SOURCE
repository's `user.name` and `user.email` (its local values, else the
global ones -- a fresh `git init` knows only the global identity, and the
first publication push was refused for that) (`PUBLISH_MESSAGE`,
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
| `release <part\|version> [test\|pypi] [yes]` | probe (token, index, tag), the bar or `full-test`, `bump-my-version`, `uv lock`, `publish`, commit, tag `v<version>`; `yes` = dry | `UV_PUBLISH_TOKEN`; for `pypi`: clean trees, mod-test evidence, `full-test`'s needs |
| `publish [test\|pypi]` | clean `dist/`, `build`, `uv publish --index` with the check URL: upload the version in the tree, skip what is there | `UV_PUBLISH_TOKEN` |
| `format` | `ruff format packages tests` | nothing |
| `lint` / `lint-fix` / `lint-unsafe-fix` | ruff check; with safe / unsafe fixes | nothing |
| `typecheck` | pyright | nothing |
| `pytest` | the unit tests alone | nothing |
| `v2-test` | `tests/test_v2_*.py` alone | nothing |
| `test-mods *ARGS` | the modification tests in a container | docker, live tree |
| `golden-regen` | rewrite `tests/fixtures/v2_golden` from the fixture | nothing; review the diff |
| `v2-dry-run *ARGS` | `run --all` (dry) against the live tree | live tree; AWS profile for discovery |
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
| `full-test-legs` | the live legs of `full-test` alone: `test-mods --strict` under docker, a headless dry run `--all` and a `state query --strict` over a private copy of the live configuration; re-run these after a session renewal instead of the whole `full-test` | `preflight` gates the two copy legs |
| `cloud-bake <rt> [yes]` / `gce-bake [yes]` | `run base-image instance-image --only-runtime <rt> --commit`; the storage/instance roots plan and gate only | `cloud-preflight`; real bakes need write credentials |
| `cloud-cycle <rt> [yes]` / `gce-cycle [yes]` | `run --all --only-runtime <rt> --apply-runtime <rt> --commit`, then `cloud-empty` | `cloud-preflight`; write credentials |
| `cloud-perform <rt>` | the performing run CI makes on `main`: `--no-dry-run run base-image instance-image release retention --only-runtime <rt> --commit` (bakes due, releases, retention; roots plan and gate only) | `cloud-preflight`; write credentials |
| `runtime-unchanged <rt> [ref]` | is the runtime's emission (its builders' directories) unchanged since `ref` (default HEAD) in the live configuration, normalised like config-drift? exit 1 with the diff when a declaration of that runtime changed | live tree |
| `cloud-launch <rt> [yes]` / `gce-launch [yes]` | `run instance-image --only none --apply-runtime <rt> --commit` | `cloud-preflight`; write credentials |
| `cloud-upgrade <rt> <instance> [to]` | a durable instance's next build as one gated sequence: `upgrade instance` (to the series head, or `to`), `cloud-launch` (the replace), `cloud-verify`, `run release`, `cloud-launch` again (the names); `config.require_released_builds` stays true throughout | `cloud-preflight`; write credentials |
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
same thing. Four jobs: `verify` is the bar, `live` reads the live
configuration, `perform` records the full configuration on `main`,
performs on the AWS runtime under the write role and records again, and
`publish` uploads a pushed `v*` tag to the index (stage 41).
`tests/test_v2_ci_workflow.py` pins the shape below, that `verify` reads
no secret, that no job anywhere passes `--no-dry-run`, that the only
write-capable cloud credential is the write role held for the performing
step, that `perform` records full and unscoped, cannot record off `main`
and cannot record twice at once, and that `publish` is the only uploader
and runs on a tag alone.

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
read-only and a plan needs the state bucket. Performing is the `perform`
job's business, on `main` alone.

| Step | What it does |
| --- | --- |
| Gate on the live-configuration secrets | evaluates the secrets below. None configured: `live: SKIPPED`, `ready=false`, and a job-summary line saying no step ran (a green conclusion is not proof that anything ran). Some configured and some missing or EMPTY: `live: FAILED -- … missing or EMPTY: <names>` and exit 1 -- a secret that exists with no value is a failure, not an absence |
| Check out the system at `cs-image-system-3` | |
| Check out the live configuration beside it at `cs-image-system-testconfig` (`develop`) | the Justfile's default root and `module_source_base` both resolve |
| Federated AWS credentials | `aws-actions/configure-aws-credentials` assumes `AWS_ROLE_ARN` in `us-east-2` via OIDC (`id-token: write`) |
| Name the federated credentials as the configuration's profile | writes `[profile noaa]` to `~/.aws/config` and `[noaa]` with the exported key, secret and session token to `~/.aws/credentials` (mode 600) |
| Federated GCP credentials | `google-github-actions/auth` with `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_SERVICE_ACCOUNT` → Application Default Credentials |
| Install just, uv (3.13), OpenTofu, Packer | |
| Place the tools where `cfg/executables.yml` pins them | symlinks `tofu`, `packer`, `gcloud`, `ansible-playbook`, `bash`, `docker` into `/usr/local/bin` |
| `just init` | |
| `just cli validate` | the live tree loads and passes every rule, with the Okta workspace's assertions and the age identity; every declared tool exists at its pinned path and meets its version requirement (stage 48.1), every foreign key resolves (48.3), every root's state location is sound (46) |
| `just config-drift` | the committed emission is current with the declarations |
| `just cloud-preflight` | reality matches the records (`state query --strict`, both clouds) |
| `just test-mods --strict` | every modification applies and is idempotent in a container |

Every step after the gate carries `if: steps.gate.outputs.ready == 'true'`;
until every secret exists the job prints its skip lines and passes.

### The `perform` job

Two record commits per push to `main` -- the record and the closing
record -- are by design (stage 48.6): each run on `main` is journaled in
`meta-state/runs.yaml`, so the closing record is never skipped for
differing only by run ids and stamps; what a run writes for itself
(`run-summary.json`, `state-report.json`, packer's `manifest.json`) is
run-local and never enters a record.

`main` records, performs on the AWS runtime, and records again. It runs
after `live`, only when the ref is `main` or the run was dispatched by
hand, and never twice at once (`concurrency: record-live`, which does not
cancel a run in flight). A dispatch enumerates unless it asks to record,
and recording is honoured only on `main`.

The shape follows from three facts. **A record must exist whatever
happens**, so the first thing the job does on `main` is a full, unscoped
dry run committed and pushed. **The GCE runtime stays out of CI** by the
cost decision, so before anything performs the job compares the GCE
emission the record just wrote with the previous record
(`just runtime-unchanged gcloud-east1 <previous>`): a declaration change on
that runtime fails the job loudly rather than bake. **A bake that happened
must never go unrecorded** (an unrecorded image is foreign drift that
refuses the next run), so the closing record and its push run even when
the performing step failed -- once the first record was made; a failure
before it has nothing to close.

The performing step is `just cloud-perform aws-east2-runtime`: a real run
of `base-image instance-image release retention` under `--only-runtime`,
committed. It bakes what is due on that runtime, releases the declared
builds and applies the declared retention there; the instance roots plan
and gate only, and identity and storage are the record's business. A run
scoped to one runtime prunes only within its scope (stage 45): the other
runtime's builder directories -- its roots, blocks and bundles -- stay
exactly as committed, and its retention command carries `--runtime`. The
runner scripts describe the scoped run; the closing full record restores
the complete emission.

| Step | What it does |
| --- | --- |
| Gate on the record secrets and decide the mode | the same rule as `live` (none configured skips and says so in the job summary; a partial set fails by name); sets `record=true` only for a push to `main` or a dispatch on `main` asking for it, and there every secret plus the push token is required -- a missing or empty one is a failure, never a green job that did nothing |
| the two checkouts, the READ-ONLY federated credentials, the `[noaa]` shim, the tools | exactly as `live` does them; the configuration checkout carries the push credential, because `actions/checkout` persists a header that would override a token in a push URL |
| Name the committer for the record | a runner has no git identity, and the RUN commits: without one `git commit` exits 128 after all the work is done. The bot identity keeps a person's address out of the configuration repository's history |
| Prove write access to the configuration repository | `git push --dry-run`, before the record is written, so a bad token stops the job early; remembers the configuration's HEAD as `before` for the GCE guard |
| `just cli run --all --commit` | the full run, recorded: generation across every lifecycle and runtime, then the commit of meta-state and emission |
| `just cli run --all` | in dry mode instead: the same full run, committing nothing |
| Push the record | the run commits, the job pushes (`HEAD:develop`); a non-fast-forward fails the job, and nothing is ever forced |
| `just runtime-unchanged gcloud-east1 <before>` | the GCE guard: the runtime's emission directories in the record, normalised like config-drift, against the previous record; a change fails the job here |
| Install what a bake needs on the runner | the Session Manager plugin (the emitted AWS sources reach their build instance through Session Manager, with no public IP) and `ansible-core` for the ansible provisioner, placed where `cfg/executables.yml` pins them; after the record is pushed and the guard passed, so a failure here leaves a record and performs nothing |
| Federated AWS credentials, the WRITE role | `AWS_APPLY_ROLE_ARN`: trusts `main` alone; the bake's EC2 and image actions, Session Manager (`ssm:StartSession` on instances and the SSH and port-forwarding documents, `iam:PassRole` for the SSM instance profile), read/write on this configuration's state prefix; the `[noaa]` shim is rewritten with it |
| `just cloud-perform aws-east2-runtime` | the performing run: bakes due on the AWS runtime, releases, retention; commits its meta-state |
| Push what the performing run committed | `always()` once the first record was made: pushed even when the step failed |
| Federated AWS credentials, the read-only role again | `always()`: the closing record and the state query read with the read-only role, which alone carries the bucket metadata reads |
| `just cli run --all --commit` | `always()`: the full run, recorded again -- the complete emission after the scoped run, and the bake's lineage |
| Push the closing record | `always()` |
| `just cloud-preflight` | the post-condition: reality matches the records |

**Cost.** The performing step can leave AWS resources standing: the AMI
and snapshot of a bake, and what a release keeps. Retention disposes what
the declarations no longer keep, on that runtime alone. No CI job holds a
credential that can create anything on GCP.

### The `publish` job

Runs after `verify` on a pushed `v*` tag and nowhere else. It checks out
the tag, `just init`, checks that the tag names the version in the tree
(`bump-my-version show current_version`), then `just publish test` with
`TEST_PYPI_TOKEN` as `UV_PUBLISH_TOKEN` and, when the tag is not a
development version (no `.dev` in its name), `just publish pypi` with
`PYPI_TOKEN`. `just publish` skips every file the index already holds
with the same content, so a release the operator published locally with
`just release` is checked here and uploaded nowhere twice; a tag pushed
without a local publish is uploaded here. The gate follows the other
jobs' rule: no token configured is `publish: SKIPPED` with a job-summary
line; a tag that needs a token which is missing or EMPTY fails by name
(a development tag needs TestPyPI's token alone; a final tag both). It
holds no cloud credential and no `id-token` permission: trusted
publishing waits until the package names are stable.

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
| `AWS_ROLE_ARN` | the federated-credentials action, then the `[noaa]` shim; a READ-ONLY role: EC2 and EFS describes, the S3 bucket tag and lifecycle reads the state query needs, and read on the state bucket for the configuration load, read on the state bucket, image and volume describes for the state query | live |
| `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT` | the GCP auth action: the application-default credentials the gcloud runtime's network discovery and the GCP state query use; read-only | live |
| `OKTA_API_PRIVATE_KEY` | the load's check that the okta provider can authenticate (`okta_tf_workspace.py`) | live |
| `TF_VAR_NOS_KEY` → exported as `TF_VAR_nos_coastal_modeling_cloud_sandbox_key` | the load's `_require_tfvar` assertion; the OPA API for gids and the state query (`opa_gids.py`) | live |
| `TF_VAR_NOS_SECRET` → exported as `TF_VAR_nos_coastal_modeling_cloud_sandbox_secret` | the same two places | live |
| `CSIS_CONFIG_IDENTITY` | the configuration load, to decrypt `ENC[age:…]` values; the CI age identity | live, perform |
| `CSIS_CONFIG_PUSH_TOKEN` | the configuration checkout and the push of what the run committed: a fine-grained token with contents:write on the configuration repository and nothing else | perform |
| `AWS_APPLY_ROLE_ARN` | the federated-credentials action for the performing step alone: the WRITE role, trusting `main` alone | perform |
| `TEST_PYPI_TOKEN` | `just publish test`, as `UV_PUBLISH_TOKEN`: an account-scoped TestPyPI API token while versions are being deleted and re-cut | publish |
| `PYPI_TOKEN` | `just publish pypi`, as `UV_PUBLISH_TOKEN`, for a final version | publish |

The gate cannot tell a missing secret from an empty one (both read as
`''`), so it decides on the set: with none configured the job skips and
says so in its summary; with some configured, every missing or empty one
is named and the job fails. Three green `live` runs once ran nothing
because `OKTA_API_PRIVATE_KEY` had been set to the empty string from a
checkout missing the file it was read from; a job's conclusion is never
proof that its steps ran. The `verify` job reads none of them. The
`perform` job reads the same set plus the push token and the write role
when recording; the `publish` job reads the two index tokens and nothing
else. The `OKTA_API_CLIENT_ID` / `OKTA_API_PRIVATE_KEY_ID` /
`OKTA_API_SCOPES` triple exists and is read by nothing: the terraform okta
provider would need it to plan the identity roots, which no CI run does.

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
public keys, one per holder: a person or CI). **Any value decrypts at load**
(stage 49) with the identity in `CSIS_CONFIG_IDENTITY`, and a marked value
with no identity refuses at load, naming both the variable and the value's
path; an unmarked value passes through. Encryption is element-level, so a
roster is encrypted entry by entry, a diff shows which entry changed, and one
entry rotates alone. A decrypted value is a `str` with a repr that hides it.

A marker may not be a mapping **key**, may not be **embedded** in a longer
string (only a whole value decrypts), and may not stand at the keys read
before the configuration loads — `encryption.recipients`,
`public_safe.allow`, a runtime builder's `name`/`type`/`profile`/
`credentials.profile_name`, `config.preflight.*`, `config.apply_*`, and any
declaration's `name`/`type`. Each is a named refusal, and the check itself
needs no identity.

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
run. Before a deferred command runs, `cs-image-system materialize` copies its
root to `_private/<the same relative path>` under the configuration root with
every marker replaced by its plaintext, and the command runs there:

- the mirror is **never committed** — refused by path as a whole subtree,
  named in the emitted `.gitignore`, skipped by the scanner, and excluded from
  the run's `git add` by pathspec;
- it is **incremental**: a root is materialised again before each of its
  commands, so `.terraform/` and the `tfplan` that `plan` wrote survive for
  `apply`;
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
marker or clear. The EMISSION is different: since stage 51 a derived
address carries its marker inside the string (`avery.alpha@ENC[age:...]`)
and both the by-reference program and `materialize` substitute markers
wherever they stand in a text.

**What a green bake proves.** An image's `tests:` become `inline` lines in a
packer shell provisioner behind `set -e`, so each assertion must be able to
ABORT that script -- exiting nonzero is not enough. POSIX suppresses errexit
for a command inside an AND-OR list, so an assertion ending in `|| { ... }`
cannot fail a build however false it is. One did: until 2026-09-20 a
`packages:` entry was written `rpm -q P || { ... dpkg -s P ... }`, and stage
19's first image baked green twice asserting `rpm -q vim` on AlmaLinux 10,
which has no package of that name; the instance launched from that AMI then
failed the same check. Package assertions now test and `exit 1` for
themselves, naming the package on stderr. Because a failing assertion stops
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
the reason. Live subnets and `mnt_data` declare their zones since 2026-09-19.
An EBS storage's own zone is what its module call carries; a GCP persistent
disk is emitted in its runtime's zone whatever the storage declares (the
declaration is validated, not emitted; a code stage names the fix).

**In the records.** A meta-state write says what it READ (stage 50): a value
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

**A derived value inherits its inputs' encryption** (stage 51): an address
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
- `just cloud-upgrade <rt> <instance> [to]` moves a durable instance to
  its image's next build: pin, replace, proof, release, names
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
| `validate` | loads the tree and applies every rule -- unique names, every declared executable present at its path and within its version requirement, every foreign key resolving, every root's state location sound; generates nothing |
| `run … --migrate-state <root>` (repeatable, `--no-dry-run`) | MOVES that root's state to the backend it now resolves to: backup, copy, a clean plan at the new location, the move recorded ("Where state lives") |
| `state-migration begin\|finish\|backup --workspace <root> --run <id>` | the two steps of a migration, emitted into the root's runner by `--migrate-state`, and the state backup a runner takes before a pre-plan `state rm` (stage 61); never a by-hand command |
| `prune-attachments --builder <group builder> --run <id>` | the identity runner's step between init and plan: membership attachments the declaration dropped and OPA no longer holds leave state after a backup (stage 61); never a by-hand command |
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
  state query does memberships; policies are enumerated by hand).
- Never let a plan create an attachment that already exists; import it
  first.
- Attribute writes on identities stay disabled until the stakeholder
  decides otherwise.
- The CI login policy (`<group>_v1_security_policy_ci`, stage 56) is the
  system's and is rewritten from the user policy on every identity apply;
  edit the module's rule, never the copy. The workload connection and role
  it names are the operator's and are never written by the system.

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
  the roots hold `.tofu-plugin-cache/.lock` (`scripts/with-tofu-lock`) and
  a second one refuses; the suite never shares the cache.

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
