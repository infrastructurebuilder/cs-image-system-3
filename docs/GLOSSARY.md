# Glossary

*The house words, each in one paragraph, for the person meeting the
documents for the first time: what the word means here, what it does not
mean where a newcomer would guess wrong, and where to read more. Every
term links to the page and section that owns the concept; this page
defines, it never rules.*

Terms are alphabetical by their key word ("the bar" under B). Every
heading is a plain anchor, so a page can link a term as
`GLOSSARY.md#the-bar`.

### the bar

The bar is `just test`: lint (ruff), the type check (pyright, zero
errors) and the fast suite over the frozen fixture, the golden included,
every leg blocking. It is the local acceptance test for a change: a
change is not done until the bar passes, and the system's CI runs the
same recipe as its `verify` job. It is not `just full-test`, which adds
the slow legs (the modification tests under docker, a dry run and a
strict query over a copy of the reference) and is owed before a release
or a hand-made performing run; and it is not `just test-one`, which runs
one file so that proving a single change does not cost a full suite.
There is no looser recipe by design: a test asserts that a `ci` recipe
with a non-blocking type check stays gone. Read
[OPERATIONS.md, "The bar: `just test`"](OPERATIONS.md#the-bar-just-test)
and [README.md, "The Justfile contract"](../README.md#the-justfile-contract).

### box

A box is one pasteable command block in a walk: a fenced block whose
first line is a comment of the form `# <step> -- box N of M -- vN`, so a
person typing from the page always knows which step they are in, how
many blocks the step has, and whether the block has been rewritten since
they last read it (a rewrite bumps the version). A box ends with the one
command whose output must be checked; the next action starts a new box.
A box is not a recipe: a recipe is what the box runs, and a walk is
judged partly by how few boxes it needs. Read the frozen
[walk](history/WALK-2026-10.md) for the form in use, and
[the walk](#the-walk) below.

### bundle (hygiene bundle)

A hygiene bundle is the open stage that collects small, non-blocking
findings as they are found: each item its own commit on the bundle's
branch, the bundle landed as one squash when it closes, and the next one
opened. A defect that is not worth a stage of its own goes into the
existing open bundle, never into a new stage; "the open bundle" is the
one the Open list in [INPROGRESS/TODO.md](../INPROGRESS/TODO.md) names.
It is not a backlog in the loose sense: every item is a concrete
finding with a fix, and the bundle's file is its plan. Read the open
bundle's file from the TODO's Open list, and
[DAILY_DRIVER.md, "The daily habits"](DAILY_DRIVER.md#8-the-daily-habits)
for when a failure goes there.

### contract

The contract is the package `cs-image-system-contract`
(`cs_image_system.contract`): the protocols, constants, field helpers and
lifecycle vocabulary a plugin is written against, carrying no
implementation and depending on nothing in the core. The core conforms
to it, never the reverse, and a test holds that direction; a class that
satisfies a protocol structurally is a first-class plugin. The word is
also used for two other agreements a newcomer meets early: the Justfile
contract (the five reserved recipe names every repository carries) and
the README contract (the four closing sections every package README ends
with); the page in hand makes clear which. Read
[DESIGN.md, "The plugin contract"](DESIGN.md#p-the-plugin-contract),
[packages/contract/README.md](../packages/contract/README.md) and
[PLUGINS.md](PLUGINS.md).

### dry run

A dry run is the default form of every run: it generates everything,
initialises every terraform root without a backend (providers and
validation only, the remote state never touched), computes and logs the
bake plans, and only enumerates what each runner script would execute.
Pins move nothing and records are not forgotten. `--no-dry-run` performs
the run instead. A dry run is not a no-op and not a test: it is the same
generation a real run makes, and its emission is what the record
commits; it is also not a `tofu plan`, which only a real run (or the
runner script it writes) performs. Read
[OPERATIONS.md, "Dry run and real run"](OPERATIONS.md#dry-run-and-real-run).

### emission

The emission is what a run writes under `generated/<lifecycle>/`: the
packer sources and build blocks, the terraform roots, the read-models and
each lifecycle's runner script. It is an honest intermediate
representation, meant to be read, committed and reviewed; a byte-identical
emission is the acceptance proof for a refactor, and the golden is one
emission pinned. The emission carries ciphertext only (`ENC[age:…]`
markers), never a decrypted value; execution runs through the private
mirror. It is not the records: `meta-state/` lives outside `generated/`
and survives every wipe. Read
[OPERATIONS.md, "Generation versus finalization"](OPERATIONS.md#generation-versus-finalization),
[GOLDEN.md](../GOLDEN.md) and
[CONFIGURATION.md, "What a run writes"](CONFIGURATION.md#13-what-a-run-writes).

### engine

The engine is the planned name for the half of the core that only the
system runs: the commands, the orchestrator, the loader and finalizer,
meta-state, the state query, releases and retention, the generators. The
other half, the kit, is what a plugin needs. The split is a plan, not a
package that exists today: `base` still holds both, and the
decomposition stages describe where the line falls and how it is
measured (the transitive closure of what the plugins import). The engine
is not the `system` package, which is the CLI, and not the contract,
which is the leaf everything is written against. Read
[INPROGRESS/STAGE-113.md](../INPROGRESS/STAGE-113.md) and
[the stage index](CHANGES.md#s124).

### finding

A finding is one numbered observation from a walk or a review, written
`F<nn>`: something the documents said too little about, a
recipe that refused where it could have acted, a defect met on the way.
A finding is raised where it is met, counted in the walk's or review's
table, and then becomes either a stage of its own or an item of the open
hygiene bundle; the frozen walk keeps the table it came from. The word
has a second, narrower use: the public-safe scanner reports "a finding"
when a file holds something that must never be public, named by path and
rule, never by value. Read the frozen
[walk](history/WALK-2026-10.md) for the findings table and
[OPERATIONS.md, "Public-safe and the hook"](OPERATIONS.md#public-safe-and-the-hook)
for the scanner's.

### fixture

The fixture (the frozen fixture) is the configuration tree under
`tests/fixtures/config/` that the tests own: synthetic personas on
example domains, its own committed TEST age identity, no `meta-state/`
and no generated output. Every test runs over a private copy of it with
every cloud, Okta and tool execution stubbed; the system's `live` job
proves the same fixture against the real accounts read-only. It is not
the reference configuration, which is a real repository beside this one,
and nothing under `tests/` reads the reference. Never put a real name in
the fixture, the golden or a test. Read
[OPERATIONS.md, "The frozen fixture and the reference configuration"](OPERATIONS.md#the-frozen-fixture-and-the-reference-configuration)
and [tests/fixtures/config/README.md](../tests/fixtures/config/README.md).

### the gate

The gate is the step between a terraform plan and its apply:
`gate-plan` reads the plan file and refuses (exit 3) any destroy that is
not whitelisted by name, a stale plan file, and a detach whose unmount
has no receipt; `apply-check` then re-reads the apply flags at execution
time so a script written under yesterday's flags cannot apply under
today's. The pages also say "the gate" of other refusals that stand
between a change and reality: the public-safe scanner before a commit
(the commit gate), the CI secrets gate, the index probe before a
release. The sense is always a check that refuses rather than warns.
Read [OPERATIONS.md, "The apply gate"](OPERATIONS.md#the-apply-gate)
and [DESCRIPTION.md, "How it works"](DESCRIPTION.md#how-it-works).

### generation

Two different things share this word, and the pages keep them apart by
context. In a run, generation is the first half: writing the emission
and the read-models, as opposed to finalization, the apply step. For an
instance or a storage, a generation is one machine or one volume: it
opens when that thing comes into being, closes when it is destroyed, and
is numbered (`<name>-003` is the third machine to bear the name); the
system observes generations from the provider rather than inferring them.
Read [OPERATIONS.md, "Generation versus finalization"](OPERATIONS.md#generation-versus-finalization)
for the first sense and
[OPERATIONS.md, "Instance generations"](OPERATIONS.md#instance-generations)
for the second.

### golden

The golden is the pinned, committed emission of the frozen fixture under
`tests/fixtures/v2_golden/`: exactly what `run --all` writes over the
fixture plus three meta-state read-models. The bar regenerates it in
memory and reports every removed, added or changed file, so every change
to the code is asked one question: did it change what the system
produces? When a change is meant to move the emission, `just
golden-regen` rewrites it, the diff is read, and the commit message says
the move is intended; regenerating to make a test pass is how a defect
becomes the expected output. Read [GOLDEN.md](../GOLDEN.md) and
[OPERATIONS.md, "The golden"](OPERATIONS.md#the-golden).

### guard

A guard is a check that refuses before anything is changed, and three
carry the name. The config guard (`config-guard`) is the recipe every
reference-reading recipe depends on; it exits with the clone command when
the reference is absent, and `just test` never needs it. The guarded
runtime (`GUARD_RUNTIME`) is a runtime CI must never bake on: the
`perform` job compares that runtime's emission in the record just pushed
with the previous record and fails before anything performs. The take's
catch-up guard is `take`'s first act: `develop` fast-forwarded to
`origin/main` before a release is taken. A guard is not the gate: the
gate stands inside a run, a guard in front of a recipe. Read
[OPERATIONS.md, "A configuration repository: the `perform` job"](OPERATIONS.md#a-configuration-repository-the-perform-job)
and [the take](#the-take).

### kit

The kit is the planned name for the half of the core a plugin needs:
the base classes, the models, the registry, lineage, encryption, the
public-safe scanner, capabilities, materialisation and the declaration
vocabulary. The plan keeps the package name `base` and its import paths
for the kit, so no plugin changes an import, and moves the rest out as
the engine. Like the engine it is a planned name, not a package that
exists today; the decomposition stages measure the line and may move it.
The kit is not the contract: the contract is what a plugin is written
against, the kit is what it imports beyond that. Read
[INPROGRESS/STAGE-113.md](../INPROGRESS/STAGE-113.md) and
[the stage index](CHANGES.md#s124).

### the ledger

The ledger is an append-only record nothing is ever deleted from, and
the pages use the word for two files in `meta-state/`:
`instance-state.yaml`, which holds per instance name the open generation
and the history of closed generations and resize events in one ordered
list, and `aliases.txt`, the pool of memorable names a launch comments
out one by one (its git history is the ledger of who took what). A
ledger is read to adopt what stood before, never to invent it. It is not
the run journal (`runs.yaml`, bounded to the last two hundred runs) and
not the lineage record. Read
[OPERATIONS.md, "Instance generations"](OPERATIONS.md#instance-generations)
and
[OPERATIONS.md, "A pool of names, each spent once"](OPERATIONS.md#a-pool-of-names-each-spent-once).

### lifecycle

A lifecycle is one of the ordered stages a run drives: `identity`,
`storage`, `base-image`, `instance-image` (the four built-ins), then the
registered `release` and `retention`. Each regenerates only its own
`generated/<lifecycle>/`, writes its own runner script, and inside it the
runner walks phases with each builder's before and after hooks. A
lifecycle is not a storage's declared `lifecycle:` (its intended state
transitions) and not a machine's life (a generation); when a page says
"the lifecycle's apply flag" it means `apply_<lifecycle>` in
`cfg/_config.yml`. Read
[OPERATIONS.md, "Lifecycles"](OPERATIONS.md#lifecycles) and
[DESIGN.md, "Lifecycle decomposition"](DESIGN.md#a-lifecycle-decomposition-the-structural-core).

### lineage

Lineage is the record of every built image: its build id, series, parent,
input fingerprint, stamped capabilities and modifications, kept in
`meta-state/lineage.yaml` and carried on the cloud image as tags. The
fingerprint hashes what determines a build's content, so a bake is due
when it differs from the series head's; the YAML declares intent for
future builds, the lineage record is truth for existing ones. Lineage is
not the pin: lineage says what was built from what, a pin says which
build an instance or child image is bound to. Read
[packages/base/README.md, "Lineage"](../packages/base/README.md#lineage)
and
[DESIGN.md, "Image lifecycles"](DESIGN.md#f-image-lifecycles-group-type-capability-the-access-loop-and-lineage).

### live

"Live" means against the real accounts rather than stubs. The live
configuration is the reference repository beside this one, with its real
`meta-state/`; `just fixture-live` proves the frozen fixture against the
real accounts; the `live` CI job is the read-only job that validates, dry
runs and strictly queries against the clouds and OPA with federated
read-only identities, and never plans against remote state. Live is not
performing: a live job changes nothing, and `perform` is the one job with
a write identity. Read
[OPERATIONS.md, "This repository: the `live` job"](OPERATIONS.md#this-repository-the-live-job)
and the opening of [OPERATIONS.md](OPERATIONS.md) for the two trees.

### materialise

To materialise a generated root is to copy it into the private mirror
(`_private/`, beside `generated/` at the same depth) with every
`ENC[age:…]` marker replaced by its plaintext, so that a deferred command
runs against readable code while the committed emission carries only
ciphertext. It happens incrementally before each deferred command of a
root, needs the identity in `CSIS_CONFIG_IDENTITY`, and copies only
`.terraform.lock.hcl` back. `cs-image-system materialize <dir>` does it
by hand for debugging emitted code. It is not decryption of the tree:
the tree on disk never changes. Read
[OPERATIONS.md, "Encrypted values"](OPERATIONS.md#encrypted-values) and
[CONFIGURATION.md, "Encrypted values"](CONFIGURATION.md#13-encrypted-values).

### meta-state

Meta-state is the directory `<config root>/meta-state/`: the committed,
human-readable, public-safe records a run leaves for the next one, the
identity and storage read-models, lineage, pins, launch parameters, the
run journal, verifications, releases, generations and the rest. It lives
outside `generated/`, survives every wipe, and a reality-claiming record
is written only when the lifecycle's apply flag was on, so a recorder
never claims reality no apply produced. It is not terraform state, which
lives in each root's backend. Read
[packages/base/README.md, "Meta-state"](../packages/base/README.md#meta-state)
and [OPERATIONS.md, "Where state lives"](OPERATIONS.md#where-state-lives).

### mirror

The mirror (the private mirror) is `_private/`, the materialised copy of
`generated/` that every deferred command runs through and that the
packer and terraform tools write into between runs. It is never
committed (`ensure_ignored` keeps it in `.gitignore`), `just
mirror-clean` removes it, and a CI job removes it last even on failure.
The pages also say that a CI policy "mirrors" a user policy, meaning it
is derived from it rule by rule; that is a different sense. Read
[OPERATIONS.md, "Encrypted values"](OPERATIONS.md#encrypted-values) and
[materialise](#materialise).

### modification

A modification (a mod) is a declared change baked into an image after
the OS: an ansible playbook, a script, a list of scripts, or an `ensure`
line, declared under an image's `modifications:` and carried out by a
mod builder. Each mod is hashed by content, so the hash is part of the
image's fingerprint and a changed comment re-bakes; the modification
tests (`just test-mods --strict`) apply each mod twice in a container,
once to apply and once to prove idempotence, before any bake. A mod is
not a base image's vendor source or update policy. Read
[CONFIGURATION.md, "The modification item"](CONFIGURATION.md#73-the-modification-item-inside-an-images-modifications)
and [OPERATIONS.md, "The modification tests"](OPERATIONS.md#the-modification-tests).

### overlay

An overlay is a YAML file merged over the configuration tree for one
invocation, named with the global `--overlay <file>`; the tree on disk
never changes. It can override `config:` keys (typically an `apply_*`
list), update a declared entry key by key, add a transient entry, or
`undeclare: true` one so that the run treats it as if it had left the
YAML. The reference configuration carries no overlays: a transient
declaration is the run's, not the tree's. Read
[CONFIGURATION.md, "Overlays"](CONFIGURATION.md#12-overlays).

### perform

To perform is to change reality: a real run (`--no-dry-run`) of the
lifecycles with their apply flags on, scoped to one runtime. `just
cloud-perform <rt>` is the performing run of the cloud change cycle, and
the `perform` CI job of a configuration repository is where `main`
records, performs on the runtime `PERFORM_RUNTIME` names, and records
again, with the write identity for that one step. Everything else in CI
is read-only; a dispatch enumerates unless it asks to record. Read
[OPERATIONS.md, "A configuration repository: the `perform` job"](OPERATIONS.md#a-configuration-repository-the-perform-job)
and [OPERATIONS.md, "The cloud change cycle"](OPERATIONS.md#the-cloud-change-cycle).

### pin

A pin binds a consumer to one build: an instance to a build of its
image's series, a child image to a build of its parent's series on a
runtime (the pin key is `<image>@<runtime>`). A consumer binds once, to
the series head, and stays pinned; only `upgrade`, a `follow` policy,
disposal or decommission moves a pin, one edge at a time, and every move
is journaled in `meta-state/pins.yaml`. The word also names
`.csis-version`, the release pin a configuration repository carries so
CI installs the same release the team took. A pin is not lineage, which
records what was built. Read
[packages/base/README.md, "Lineage"](../packages/base/README.md#lineage)
and
[DESIGN.md, "pins as truth"](DESIGN.md#2e-rulings-type-level-prerequisites-pins-as-truth-admin-keys-n10n12).

### public-safe

Public-safe is the property that nothing committed to either repository
holds what must never be public, and the scanner that proves it: refused
file names (plans, state, tfvars, keys), hard rules everywhere (a token,
a key body, an identity), soft rules outside prose and tests (an
address, a long base64 string), and an allow list kept by decision with
the reason. It runs in the pre-commit hook, in a `--commit` run, as
`just public-safe` and in CI's `verify` job, and every meta-state write
passes it. Both repositories are public by design. A value is allowed by
decision, never by bypassing the hook. Read
[OPERATIONS.md, "Public-safe and the hook"](OPERATIONS.md#public-safe-and-the-hook).

### the record

The record is `just record`: a dry run of every lifecycle, unscoped, its
emission and meta-state committed in the configuration repository (the
operator pushes). It is what the `perform` job makes first and last, so
that a record exists whatever happens in between, and what a failed real
run leaves on disk for the next record to commit. "The records" without
the article is `meta-state/` as a whole, and "a record" is one entry in
it. The record is not the golden (the tests' pinned emission) and not a
real run: it performs nothing. Read the `record` recipe in a starter
tree's [Justfile](examples/standard-gce/Justfile) and
[OPERATIONS.md, "A configuration repository: the `perform` job"](OPERATIONS.md#a-configuration-repository-the-perform-job).

### the reference

The reference (the reference configuration, the live configuration) is
the real configuration repository checked out beside this one as
`cs-image-system-testconfig`: a team's repository like any other, with
its own Justfile, workflows and `meta-state/`, whose cycles run from its
own checkout. This repository reads it only for its own live proofs
(`just cli …`, the copy legs of `full-test`), never for `just test`. It is
not the frozen fixture, which the tests own and which no run commits
into. A change that touches the reference is committed and pushed on its
`develop` as part of the same piece of work; its `main` is what its CI
performs on. Read
[OPERATIONS.md, "The frozen fixture and the reference configuration"](OPERATIONS.md#the-frozen-fixture-and-the-reference-configuration).

### release

Two releases share the word. A release of the system is a version of
the `cs-image-system` packages cut to the index (`just release <part>
[test|pypi]`), tagged `v<version>`, which a configuration repository then
takes. A release of an image is the `release` lifecycle: an image that
declares `release: {model}` is marked the current released build for
that model once its post-bake tests have a passing record, and
`require_released_builds` makes `validate` refuse an unreleased pin. The
page in hand makes clear which; a starter's `just release <runtime>` is
the performing run that makes image releases. Read
[OPERATIONS.md, "Post-bake tests and releases"](OPERATIONS.md#post-bake-tests-and-releases)
and
[OPERATIONS.md, "`just build`, `just release`, `just publish`"](OPERATIONS.md#just-build-just-release-just-publish-just-publish-tree).

### retention

Retention is the closing lifecycle that disposes of builds the
declarations no longer keep: `retention: {keep: N}` on an image keeps the
newest N builds of a series per runtime, an ephemeral runtime keeps
nothing baked there, and the one deferred step, `dispose image
--retention`, recomputes the plan at execution and disposes through the
sanctioned path. A build an instance is pinned to or was launched from is
retention debt: kept and reported. Retention never touches a declared
storage. Read
[OPERATIONS.md, "Retention and disposal"](OPERATIONS.md#retention-and-disposal).

### runtime

A runtime is a place images are baked and instances launched: an AWS
account, region and VPC; a GCP project and zone; or a container host's
daemon. Declared in `cfg/runtime-builders.yml` with a `type` the runtime
plugin registers, a runtime carries its credentials, its network facts,
its retention and whether it is ephemeral; a run is scoped to one
(`--only-runtime`, `--apply-runtime`) and the cloud change cycle acts on
one. A runtime is not a cloud: one cloud may hold several runtimes. Read
[CONFIGURATION.md, "`cfg/runtime-builders.yml`"](CONFIGURATION.md#4-cfgruntime-buildersyml)
and [DAILY_DRIVER.md, "What you are driving"](DAILY_DRIVER.md#0-what-you-are-driving).

### stage

A stage is the unit of planned work: one file `INPROGRESS/STAGE-<n>.md`,
numbered, holding what the stage does, its decisions marked for the
operator, what is out of scope and what acceptance is. A stage is a plan
until the operator says "do N"; it is executed on its own feature
branch, landed as one squash-merge whose message is the record, and its
file is then removed. A stage is not a release and not a bundle: a
bundle is the one stage that stays open to take small findings. Read
[INPROGRESS/TODO.md](../INPROGRESS/TODO.md) and
[OPERATIONS.md, "Branches"](OPERATIONS.md#branches).

### starter

A starter is one of the template configuration trees under
`docs/examples/` (`standard-aws`, `standard-gce`, `standard-docker`,
`standard-aws-posix`, `complete`): a Justfile, workflows, hook, guides,
`tfmodules/` and example declarations, shipped inside the release and
written into a new configuration repository by `cs-image-system
init-config`. Each is also published as a template repository at a final
release's tag. The starters are the source the release is built from and
the tests hold the built wheel to them. A starter is not the reference,
which is a real repository that once came from one. Read
[DAILY_DRIVER.md, "The configuration repository, from scratch"](DAILY_DRIVER.md#19-the-configuration-repository-from-scratch)
and [OPERATIONS.md, "Installing a release"](OPERATIONS.md#installing-a-release).

### the strict query

The strict query is `state query --strict`: every plugin asks its
provider what the system manages (images by lineage tag, storages by
name, groups by gid, memberships by API) and the result is diffed against
`meta-state/`; in strict form any drift class but `stale` refuses, and a
provider that cannot answer (`unavailable:`) refuses too, because it
cannot vouch. Every run executes the plain query first and refuses on
hard drift; the strict query runs before any cycle step and as the
`live` job's and `perform` job's post-condition. The report is expected
empty apart from `unavailable:` lines: every line is actionable, none is
known benign. Read it whole, never its tail. Read
[OPERATIONS.md, "The state query"](OPERATIONS.md#the-state-query).

### the take

The take is `just take <version>` in a configuration repository: the
whole walk of moving that tree onto a release in one box. Its first act
is the catch-up guard; then the release is installed, the files the
release owns are listed against the previous release, and the recipe
stops if any changed, because refreshing them stays by hand
(`init-config --force`, read the diff, `just take <version> patched`).
With nothing to patch it writes `.csis-version`, runs `just init` and
`just validate`, commits "Take <version>" and pushes `develop`; pushing
`develop` to `main` is its own act, because `main` performs. The take is
not the release: the release is cut here, the take is a team's act in
its own repository. Read the `take` recipe in a starter tree's
[Justfile](examples/standard-gce/Justfile) and
[DAILY_DRIVER.md, "The release, and how it reaches you"](DAILY_DRIVER.md#11-the-release-and-how-it-reaches-you).

### verify

Verify is used in four places, each a proof. `just verify` is an alias
of the bar. The `verify` CI job is the no-secret job of either
repository: the bar and public-safe here, an install, a parsing Justfile
and public-safe in a configuration repository. `verify instance` (`just
cloud-verify`) is the post-bake proof on a launched machine, whose
verdict lands in `meta-state/verifications.yaml` and which a release
requires. `verify login` is the login proof as a client or as a
workload. The sense is always a check whose verdict is recorded, never a
change. Read
[OPERATIONS.md, "This repository: the `verify` job"](OPERATIONS.md#this-repository-the-verify-job)
and [DAILY_DRIVER.md, "What specifies, and what tests it"](DAILY_DRIVER.md#5-what-specifies-and-what-tests-it).

### the walk

A walk is a document executed by a person typing from it, box by box,
to prove that the page says enough: the daily driver was walked from
nothing to running and back to nothing, and a release is walked through
its recipes. Where the page says too little the walker records a
finding, and the findings become stages and bundle items; the walk's
page is then frozen under `docs/history/` as evidence, not documentation.
A walk is not a test suite: it proves the words, the suite proves the
code. Read
[DAILY_DRIVER.md](DAILY_DRIVER.md) (the text that is walked) and the
frozen [walk](history/WALK-2026-10.md).

### workload

A workload is a non-human identity that logs in: CI presents GitHub's
OIDC token to the team's workload connection in Okta Privileged Access,
which maps it to the team's one workload role, and the identity lifecycle
makes a CI policy per managed group that mirrors the user policy. The
connection and the role are made by hand once and named in the group
builder (`workload_connection`, `workload_role`); `just ci-login-proof`
proves the login as a workload and `just opa-workload-probe` proves a
connection before it is activated. A workload is not a user: it has no
home, no keys and no roster entry. Read
[OPERATIONS.md, "CI logs in through the policy the system manages"](OPERATIONS.md#ci-logs-in-through-the-policy-the-system-manages)
and
[OPERATIONS.md, "A configuration repository: the workload probe"](OPERATIONS.md#a-configuration-repository-the-workload-probe).
