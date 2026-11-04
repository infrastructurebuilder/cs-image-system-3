# Incidents

This is the one place incidents are recorded: what was seen in a live run,
what it meant, and what the system does about it now. Every incident has
one entry here, however many pages once told it. The "When it fails"
sections of the other pages (the daily driver, the package READMEs) keep
the symptom, its meaning and the action to take, and link here for the
story. An entry is identified by its heading and its date, not by the
piece of work that fixed it. Together with [CHANGES.md](CHANGES.md) this
is one of the two current pages that carry dates.

The page is append-only, newest first: a new incident goes at the top,
and an old entry is never rewritten, only corrected in place when a fact
in it turns out wrong.

Each entry has the same five parts. **Symptom**: what the operator saw.
**Cause**: what it meant. **Fix**: what the system does now, in the
present tense. **Date**: when it was found or fixed, ISO. **Where it was
told**: the pages the entry was merged from, so a reader of an older copy
can find the current one.

## Entries

"Where it was told" names each source section as it stood when the entry
was written; most of those sections have since become short tables that
link here, so a title may no longer be found on the page it names.

### Podman spelled the tags with a registry the system did not expect

**Symptom.** On the first run of the docker cycle against a Podman host,
the strict state query reported `parent: lineage=<id> tag=series:<name>`
for a build whose parent had just been bound after its bake: the movable
tags that carry the lineage facts (the parent bound after a bake, a
release) were read as absent, although `docker image inspect` showed them
on the image. Before that, on the rootless host, the very first image pull
failed with `insufficient UIDs or GIDs available in user namespace ...
lchown /var/spool/mail: invalid argument`.

**Cause.** Podman's compatibility API reports an unqualified repository
`csis/x:tag` as `docker.io/csis/x:tag` in `RepoTags`, where Docker keeps
it as written; the runtime compared the repository part as written and so
ignored every tag the daemon reported with the registry it implied. The
pull failure was the host's: a rootless Podman user needs `/etc/subuid`
and `/etc/subgid` ranges, and the OrbStack machine's user had none.

**Fix.** The docker runtime compares repositories through
`same_repository`, which accepts `docker.io/`, `index.docker.io/` and
`localhost/` in front of its own repository name; a unit test holds it,
and the Podman leg (`just test-podman-cycle`, and
`just test-podman-desktop-cycle` for Podman Desktop on macOS) refuses to
pass on a daemon that does not say it is Podman. A release before this
date shows the drift line on a Podman daemon; take a later release, there
is nothing to repair on the daemon. The subordinate-id ranges are the
host's setup, not the system's: `usermod --add-subuids ... --add-subgids
...` then `podman system migrate`, as the proof procedure in
[OPERATIONS.md](OPERATIONS.md) ("Podman as the daemon") shows.

**Date.** 2026-11-01.

**Where it was told.** [OPERATIONS.md](OPERATIONS.md) section 5, "Podman
as the daemon" ("What differed");
[../packages/docker-runtime-plugin/README.md](../packages/docker-runtime-plugin/README.md)
"When it fails" (the `parent: lineage=` row).

### GitHub refused a workflow whose credential was an empty string

**Symptom.** A workflow that named the runner image's registry
credentials from a repository variable and secret was refused before any
job started: `Unexpected value ''`.

**Cause.** The `credentials:` of a container job cannot be the empty
string. A team that leaves the variable and the secret unset must not
produce `''` for them.

**Fix.** Every job's `credentials:` default to the job's actor and token
(`${{ vars.CSIS_RUNNER_IMAGE_USERNAME || github.actor }}` and the secret
with `github.token`), the login the runner makes for `ghcr.io` by itself;
a team that uses another registry sets both.

**Date.** 2026-10-24.

**Where it was told.** [CI_RUNNER.md](CI_RUNNER.md) ("A team's own
image").

### The reference tree's identity objects were rewritten by another configuration

**Symptom.** The state query on the reference tree reported `resource
group '<g>_rg' is not what the identity module makes` (and the same for
the user and admin policies) for a group nobody had touched in this tree.

**Cause.** Another configuration, living in its own repository, held the
same OPA objects in its own tofu state and had applied over them. Two
configurations managing one object rewrite each other's work.

**Fix.** The report names the object and the difference; the repair is
that the other configuration lets go first (`tofu state rm` there, never a
destroy, since the object is live), and then `just run identity` puts the
object back as the module makes it. Such a line is never hard drift, so
the tree keeps running while the owner is sorted out.

**Date.** 2026-10-19.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`resource group '<g>_rg' is not what the identity module makes` row).

### The CI runner image took four builds, and its first pull was refused

**Symptom.** A job failed in "Initialize containers" before any step of
the workflow: `denied`, `unauthorized` or `manifest unknown` pulling
`ghcr.io/<owner>/csis-ci:alma10-<date>`. On the same day the `verify` job
pulled the image while `live` was refused it.

**Cause.** Three things, each found in turn. The image itself needed four
builds on its first day: the first lacked git's `safe.directory` for a
checkout owned by another user, the second the `libatomic` that pyright's
node needs, the third the `community.docker` collection whose `docker`
connection the modification tests use (GitHub's Ubuntu image carries it
with its full `ansible`); `.4` is the first that ran the live proof. The
pull was refused because a job that declares a `permissions:` block gets
only what the block names, so a block without `packages: read` pulls as
nobody (`verify` declared no block and got the default; `live` declared
one and was denied). And the first publish came out PRIVATE, because the
organisation had disabled public packages, so a repository outside the
organisation could not pull it at all.

**Fix.** A published tag is never rebuilt; a second image on one day is
`alma10-<YYYYMMDD>.2`, and the tree pins the tag in `ci/runner-image/TAG`
with the workflows' lines held equal by a test. Every job of every
workflow carries `packages: read`, and a test holds that line. The
package is public for the template repositories; a private package is
still usable by every repository of the same organisation through the
package's "Manage Actions access" page with the Read role. A missing tag
means the Runner image workflow has not published the date the workflow
pins; a credential in the workflow is never the answer.

**Date.** 2026-10-16.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
"Initialize containers" row); [CI_RUNNER.md](CI_RUNNER.md) ("Who may pull
the image is two settings, and both bit on the first day", and the
paragraph on the four builds above it).

### The CI apply role could not read the storage it had applied

**Symptom.** A `perform` run printed `unavailable: storages/<s3>: REFUSED
(the identity lacks a permission, ...): An error occurred (AccessDenied)
when calling the GetBucketTagging operation: User:
...assumed-role/csis-github-apply/... is not authorized`, and the job
stayed green.

**Cause.** The applied role's document lagged the release's bootstrap
module: the WRITE role carried no `StorageReality` statement at all, so
every performing run read its own S3 storage as unavailable, and an
`unavailable` line is never a failure.

**Fix.** The bootstrap module's WRITE role carries the read the state
query makes. The repair in a tree that applied the older document is to
take the release and apply the bootstrap root again (the Apply block of
the CI setup guide; IAM writes are the operator's). A `REFUSED` line is a
permission, never a retry.

**Date.** 2026-10-14.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`unavailable: storages/<s3>: REFUSED` row).

### A dry run spent a group's release

**Symptom.** Several `DESTROY NOT WHITELISTED: <address>` lines under
`module.group_<name>` (gate, exit 3) for a group the operator had marked
`unmanaged: true`, after a dry run or a `just record`.

**Cause.** Releasing a group from management is a one-time act the
identity lifecycle carries out; on a release before 0.1.1.dev23 a dry run
or a record consumed that act without applying it, so the next real run
found the group still managed in state and planned to destroy its
objects. The gate was right, and nothing was destroyed.

**Fix.** A dry run and a record leave the release pending until an
applying identity run carries it out. A tree still on the older release
takes the release and runs the identity lifecycle again.

**Date.** 2026-10-13.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`DESTROY NOT WHITELISTED` row).

### A failed applying run lost its record, and a cancelled one was journalled as a success

**Symptom.** Two shapes. A decommission that failed on another cloud's
plan, after its own root had applied, left the machine gone and the
records still describing it; and a run cancelled with Ctrl-C was journalled
in `meta-state/runs.yaml` as `ok: true`.

**Cause.** The run's record was committed only on success, so what the
after-apply hooks had already recorded was lost with the failure; and a
`KeyboardInterrupt` was not an error to the journal.

**Fix.** Since 0.1.1.dev25 an applying run that fails after a root has
applied commits its record as `cs-image-system run (FAILED) <id>`, after
the after-apply hooks have run, so what applied is not lost;
`meta-state/runs.yaml` holds the error. A cancelled run is journalled
`ok: false` with `error: interrupted (KeyboardInterrupt) during
<lifecycle>`; nothing after that point ran, and what ran before stands as
its own commands left it (a generation can simply be run again; an
interrupted apply is read in the root's state first).

**Date.** 2026-10-13 (the failed decommission); 2026-10-09 (the cancelled
run).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`cs-image-system run (FAILED) <id>` row and the `interrupted
(KeyboardInterrupt)` row).

### The vendor's newest image moved under a base this tree had not baked

**Symptom.** A scheduled `config-drift` job went red with `BEHIND ... (1
files)` that no rerun could make green; on the guarded runtime the
`runtime-unchanged` guard read the same move as `CHANGED` and failed
`perform`, although nothing in the tree had changed.

**Cause.** The emission of a base with no build yet names the vendor
image of the day it was generated; when the vendor publishes a new image,
the committed emission and a fresh generation disagree without any change
of the operator's. The guard compared emissions and could not tell a
vendor move from a declaration move.

**Fix.** `config-drift` reports the case as its own line, `the vendor's
newest image moved under a base this tree has not baked`, exit 0, and
`just record` plus a commit takes the move. The guard reads the same move
as `unchanged since <ref> (...), but the vendor's newest image moved ...`,
exit 0, and the job's record takes it; on 0.1.2 and before the record the
job had pushed already held the move, so the next push to `main` passed.

**Date.** 2026-10-12.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`config-drift: ... the vendor's newest image moved` row and the
`runtime-unchanged: ... unchanged since <ref>` row).

### Static keys lapsed under a green session preflight

**Symptom.** `preflight` said `every session present` in green, and the
next command failed with `the configuration cannot load: AWS refused the
credentials (RequestExpired)` (earlier, `Error reading config file : AWS
Error ... Request has expired` under a traceback). `aws sso login` did
nothing for it.

**Cause.** The credentials were temporary keys pasted into the shell or a
credentials file. A session preflight reads no expiry for keys, because it
makes no cloud call by design, so present was all it could say, and it
said it in green over keys that had already lapsed. `RequestExpired` is
what such keys say when they lapse.

**Fix.** `preflight` reports keys it can see but not time as `N
session(s) present; 1 NOT JUDGED (no expiry readable: ...)` in yellow,
exit 0, and a lapse is a plain refusal naming `RequestExpired`, not a
traceback. The repair is fresh keys for pasted ones and `aws sso login
--profile <p>` for an SSO profile. A session that lapses mid-run is
environmental, not a defect.

**Date.** 2026-10-09.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`preflight: a session has EXPIRED` row and the `NOT JUDGED` row).

### Docker Hub did not answer and the modification tests could not start a container

**Symptom.** CI's `live` job failed in `test-mods` with
`CalledProcessError` under eighty lines of traceback, docker's own words
lost; three runs in forty-five minutes while Docker Hub's sign-in service
did not answer. `perform` waits behind `live`, so every bake stopped too.

**Cause.** Every `live` run pulls its test image from Docker Hub, without
an account, at that moment; the registry (or the daemon) did not answer.
Nothing about the modification was tested, so it was not a failed
modification, but it read as one.

**Fix.** The pull is retried three times over about half a minute; a pull
that still fails is `CANNOT START <image>/<mod>: cannot start a container
from almalinux:10: docker pull (after 3 attempts) exited 1: ... context
deadline exceeded`, exit 1, and the record says `unstarted`. The run's
log says which modification it is on and which image it waits for; a pull
from your own machine tells the registry from the daemon; wait and rerun
(`gh run rerun <run> --failed`).

**Date.** 2026-10-09.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`CANNOT START <image>/<mod>` row).

### A storage type added for one cloud re-baked the other cloud's base

**Symptom.** A base shown DUE on AWS after a `pd` storage was declared for
a GCE disk; nothing on AWS had changed.

**Cause.** The capability stamp in a base's input fingerprint counted
every storage type the tree declared, not the ones that apply on that
base's runtime, so a type one cloud cannot use moved the other cloud's
fingerprint.

**Fix.** A storage type added for one cloud re-bakes the base only where
that type applies. A field every runtime shares (`admin_user`, the admin
keys, `update`, the vendor source) still re-bakes everywhere by design;
the run's reason for the bake says which.

**Date.** 2026-10-09.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
"a base shown DUE on a cloud you changed nothing for" row).

### Refusals that surfaced as tracebacks

**Symptom.** Four refusals a fresh shell or a fresh tree meets came out as
Python tracebacks: `MissingIdentityError` when `.envrc` had not been
sourced in a tree holding an encrypted value; `ReservedNameError` when a
name was a reserved word; a traceback under `Okta builder <b> is missing a
key value` when the `TF_VAR_<team>_key` pair was absent; and the AWS
`Request has expired` traceback of the entry above.

**Cause.** Each was a load-time error the CLI did not catch, so the
operator read a stack instead of the one line that mattered.

**Fix.** Each is one line and an exit code: `the configuration cannot
load: <tree>/cfg: ...: an encrypted value is present but
CSIS_CONFIG_IDENTITY is not set` (exit 2, before anything is asked of a
cloud; `source .envrc` or `direnv allow`); ` - <file>:
instances[0].name: a name may not be 'none'` under `Validation failed
with 1 error(s).` (exit 1; rename it); `the configuration cannot load:
Okta builder <b> is missing a key value. Expected to find environment
variable TF_VAR_<team>_key ...` (the pair is needed by `validate` and dry
runs too, not only at apply); and the `RequestExpired` refusal.

**Date.** 2026-10-09.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`CSIS_CONFIG_IDENTITY is not set` row, the `a name may not be 'none'` row,
the `missing a key value` row).

### The instance root planned before its storage root had ever applied

**Symptom.** `Unable to find remote state ... No stored state was found`
planning an instance root, right after the bakes of the first `perform`.

**Cause.** The instance root reads its storage root's state, and that
root had never applied: `apply_storage: false` stood from the first commit
and the first `perform` ran before any storage run.

**Fix.** The strict state query says it beforehand as a note (`mounts
storage ... whose root has no state yet`); the order is the storage
lifecycle with `apply_storage` first, then instances.

**Date.** 2026-10-07.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`Unable to find remote state` row).

### The apply's verdict could not be read in the log

**Symptom.** The log of an apply showed the root's outputs and no `Apply
complete!` line; earlier still, a successful command's output did not
reach the log at all, and the plan that applied had to be read afterwards
with `tofu show tfplan` in the root.

**Cause.** The run kept the last 40 lines of a command's output, and tofu
prints its verdict BEFORE the outputs, so a root with many outputs pushed
the verdict out of the tail. Before that only a FAILED command's output
was logged.

**Fix.** Every command the running process executes has its captured
output in the log: the last 40 lines of stdout and stderr at INFO under
the command's name, the whole of it at DEBUG, colour codes stripped.
Since 0.1.1.dev25 every verdict line (`Plan:`, `Apply complete!`, the
gate's, a bake's `Build ... finished`) is printed ahead of the tail with
its line number. The runner still leaves the plan file behind, so `tofu
show tfplan` in the root remains a way to read it.

**Date.** 2026-10-07 (the hidden verdict); 2026-09-30 (only failures
logged).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
"no `Apply complete!` line" row); [OPERATIONS.md](OPERATIONS.md), "Run
outputs and exit codes" (the paragraph on captured output).

### TestPyPI was down, and a release found it only at the upload

**Symptom.** The `verify` job of a tree whose `.csis-version` names a
`.dev` release failed in "Install the released system" with the index
unreachable or `503`; and on the same day a release ran its whole bar and
failed at the upload.

**Cause.** A development release lives on TestPyPI and nowhere else, so
an outage there stops every job that installs one; the release checked
the index's condition only when it came to upload.

**Fix.** The job failure is environmental: wait and rerun (`gh run rerun
<run> --failed`); nothing in the tree is wrong. The release probes the
index's upload endpoint and each project page first and stops with
`release: testpypi cannot take an upload now (above) -- nothing was
changed; it is the index's condition, not the release's` (exit 75), before
the bar or after it and before the bump, so the tree is clean; `just
index-ready test wait` then the release again.

**Date.** 2026-10-05.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
"Install the released system" row and the `release: testpypi cannot take
an upload now` row).

### A 1 GB bake host starved the package manager and the SSM agent

**Symptom.** Three shapes of one lesson. On the first bakes, `dnf update`
was killed mid-provisioner with no package error, and a launched instance
stopped answering SSM minutes after boot. Later, three `perform` runs in
CI ended `Build '<image>' errored after 20 minutes ...: Timeout waiting
for SSH.` with `ssm error: ... StartSession, context canceled`: the bake
machine booted and its SSM agent was Online, but packer's SSH session
through SSM never opened. The same parent had baked on an `r5.4xlarge`,
and on a `t3.medium` once declared. A related emission fault showed
`t3.medium` bakes staying `t2.micro`.

**Cause.** A 1 GB `t2.micro` cannot keep the package manager and the SSM
agent alive at once; the OOM killer takes one of them. The image the host
boots was too large for it. The emission fault was the subconfig's
templated `machine_type` refilling itself from the runtime default
instead of keeping the resolved value.

**Fix.** The bake host's size is the image's: `machine_type` on the
image's runtime entry, else the image builder's `default_machine_type`,
else the runtime's. The starters ship `t3.medium` (4 GB) on AWS and the
reference tree's AWS runtimes default to it; the fixture bakes on
`t3.medium` and `e2-small` while its runtimes keep the free-tier
`t2.micro` and `e2-micro` for instances. The resolved value is written to
`machine_type` as well, so an emission cannot refill it. An instance
declares its own `machine_type` over the runtime default. The builds that
completed before a failed bake are recorded anyway (a warning names them).

**Date.** 2026-10-05 (the CI bake hosts, 2026-10-04 and -05); first seen
2026-08-31 to 2026-09-01.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`Timeout waiting for SSH` with `ssm error` row);
[OPERATIONS.md](OPERATIONS.md) section 5, "Network" (the per-instance
sizing sentence);
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (`t2.micro` out of memory) and its field table;
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the bake machine OOM-killed under `dnf update`);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (a `t2.micro` OOM-killed the SSM agent);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the 2026-09-02 ledger-shape item).

### An image the system tagged was not in lineage

**Symptom.** `foreign image <id>: ... tagged series=<s> run=<r> is not in
lineage` from the strict state query; on the day, `just full-test`'s
strict query raced CI's `perform`, which was still baking.

**Cause.** An image carrying the system's tags that no record names: a
bake still running in another process, or one a failed run baked before
failed runs recorded their completed builds.

**Fix.** A bake still running is waited for and records itself. An
orphan is adopted with `just cli state import --no-storages` (five images
on the day), then `just record`; the adopted build counts as current and
is not baked again. A `foreign` line is never hard drift, but every line
is actionable.

**Date.** 2026-10-04.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`foreign image <id>` row).

### A group deleted from the YAML was refused

**Symptom.** `identity: group '<g>' was managed by the system but is
missing from the YAML; groups never leave the configuration`, from
`validate`, after the posix proof's declarations were removed when the
proof was done.

**Cause.** A group the system once managed keeps its records and its gid
claimed by the name; deleting its entry would orphan both.

**Fix.** The entry goes back with `unmanaged: true`; its members may go.
The records stay, and the gid stays claimed by the name.

**Date.** 2026-10-04.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`identity: group '<g>' was managed by the system` row);
[../packages/posix-identity-plugin/README.md](../packages/posix-identity-plugin/README.md)
"When it fails" (the same row).

### A run naming images also planned every due image of the runtime

**Symptom.** A run with `--only <a> --only <b> --only-runtime <rt>`
planned and baked every due image of the runtime, not the two named.

**Cause.** The two scopes were a union, so naming the runtime widened
what `--only` had narrowed.

**Fix.** `--only-runtime` beside `--only` narrows: the bake surface is the
named images on that runtime and nothing else; a name it cannot honour
(not baked there, written `@` another runtime, or `none` beside names) is
refused before anything is generated (exit 2), every such name listed at
once.

**Date.** 2026-10-04.

**Where it was told.** [OPERATIONS.md](OPERATIONS.md) section 1 (the
`--only-runtime` bullet); [CONFIGURATION.md](CONFIGURATION.md) (the
`--only-runtime <rt>` row of the run options).

### A run would have wiped the bootstrap root's local state

**Symptom.** None reached a live tree. Found while writing the bootstrap:
the bootstrap directory is regenerated by every run, and the wipe would
have taken the state of a root still on the local backend with it.

**Cause.** A lifecycle's directory is wiped whole because its state is
remote; the bootstrap root's state may be right there in the directory.

**Fix.** A run regenerates the bootstrap directory and prunes it when the
answers file is absent, leaving what a person's own `tofu` left there
(`.terraform/`, the lock file, a saved plan, and the state of a root on
the local backend).

**Date.** 2026-10-01.

**Where it was told.** [OPERATIONS.md](OPERATIONS.md), the bootstrap
section (the sentence "until 2026-10-01 a run would have deleted it").

### A follow image re-baked every cycle on the ephemeral runtime

**Symptom.** On the ephemeral runtime, whose retention disposes the base
build every cycle, the child with `parent_policy: follow` was due on every
run, its reason `inputs changed`, although nothing had changed.

**Cause.** The input fingerprint covered the parent's BUILD id, and the
parent's build id changed every cycle by design, so the plan and the
record could never agree.

**Fix.** The fingerprint covers the parent image's own fingerprint (its
content on that runtime, computed from the tree), never which build of
the parent the bake is from; that is the pin's business, and a moved pin
is the next bake's reason by itself.

**Date.** 2026-09-26.

**Where it was told.** [OPERATIONS.md](OPERATIONS.md) section 2, the bake
plan ("its inputs changed" bullet).

### A session with exactly zero minutes left was not expired

**Symptom.** A session whose expiry had just arrived passed the preflight
as one minute left.

**Cause.** The expiry test read `(minutes_left or 1) <= 0`, so `0.0`
counted as one minute left.

**Fix.** `_expired` in the preflight calls a session expired when its
minutes left are known and `<= 0`; one whose expiry cannot be read
(`None`) is still not expired, it is `NOT JUDGED`.

**Date.** 2026-09-25.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "exactly zero minutes left" item).

### Two S3 storages on one builder reported the same bucket

**Symptom.** The state query showed the second S3 storage of a builder
with the presence and tags of the first.

**Cause.** The query read the builder's `bucket_name`, not the storage's.

**Fix.** The lookup asks for the storage's own bucket (its `bucket_name`,
else its name); a test holds it.

**Date.** 2026-09-25.

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "two S3 storages on one builder"
item).

### Every scoped run warned about images it was never going to launch

**Symptom.** Every GCE cycle logged `No resolved provider-specific images
for instances; modules will use their name-pattern fallback`, and a run
scoped to one runtime wrote an `instances.auto.tfvars` under the other
runtime's root that nothing read.

**Cause.** The AWS instance builder's finalize hook still ran for a root
the scope had left empty.

**Fix.** Both instance builders' finalize hooks return early for a root
outside the run's runtime scope; a test holds it.

**Date.** 2026-09-25.

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "every scoped run logged" item).

### A modification declared with its builder's alias failed at generation

**Symptom.** With `type: bash` on an item whose builder is declared under
another name with `bash` as an alias, the load and `validate` passed and
the run log then showed `AssertionError: No mod builder bash found in
context for <image>`; the summary was `ok: false` with no validation
errors. Found on a copy of the fixture while writing the plugin's README.

**Cause.** The item kept the alias as its `type`, and the orchestrator
looked the builder up by name.

**Fix.** The loader rewrites an alias to the builder's name; a test
generates that same fixture copy.

**Date.** 2026-09-25 (found 2026-09-23).

**Where it was told.**
[../packages/bash-mod-plugin/README.md](../packages/bash-mod-plugin/README.md)
"When it fails" (the 2026-09-23 item).

### A dry run asked the hostname registry

**Symptom.** A dry run with `apply_instances` on asked OPA whether the
canonical hostname was claimed, and could refuse on the registry's
silence, although it was never going to launch.

**Cause.** The claimed-name check ran whenever the flag was on, not only
when a launch was possible.

**Fix.** The check runs ONLY when a launch is actually possible: the
lifecycle requested, `apply_instances` on, and not a dry run. An
unreachable registry is still a refusal for a run that can launch
(silence is not a free name).

**Date.** 2026-09-24.

**Where it was told.** [OPERATIONS.md](OPERATIONS.md), "Canonical
hostnames" (the sentence "until 2026-09-24 a dry run with the flag on
asked the registry too").

### A runner step acted in the configuration root and the backup kept nothing

**Symptom.** Three live attempts on one morning. At 10:15 the identity
runner's `state-migration backup` reported no state where `tofu state
pull` in the mirror showed one, said "nothing to keep" and let the `state
rm` run unbacked. The read-model written at generation said the
membership was already gone when state still held it. And a pipe to
`tail` masked the bar's exit code.

**Cause.** The CLI's callback loads the configuration, which changes
directory to the configuration root AND replaces the context object, so
the invocation directory recorded before the load was gone when the step
read it: `state-migration begin`, `finish`, `backup` and the prune step
ran from the configuration root instead of the initialised root the
runner had entered. The identity read-model is written at generation and
outlives a failed runner, so it is no witness of state; only `tofu state
list` is.

**Fix.** The callback records the invocation directory again after the
load, and the steps use it. A directory that is not an initialised root, a
pull that fails, or a location holding no state each exit 1 with `state
backup for workspace '<ws>' REFUSED ...` and stop the runner before
anything leaves state; the backup lands in
`_private/state-backups/<ws>.backup-<run>.tfstate` and the log line names
the serial and the resource count (serial 36 at 10:46 that day). The prune
step lists the state the root is bound to, never the read-model. Seeing
`REFUSED: <dir> is not an initialised terraform root` from a runner step
means the step was invoked from the wrong directory: the step is the
system's and ran where the system put it, so report it. Pinned by two
tests named in the base README.

**Date.** 2026-09-23 (found 10:15, fixed the same day).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`state backup for workspace '...' REFUSED` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the three 2026-09-23 items);
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-23 10:15 item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("A dropped membership blocked every identity plan", the
"three live attempts" sentences).

### A stale attachment in state blocked every identity plan

**Symptom.** `user "x" is not present within group "g"` from the oktapam
provider at plan, for a membership the roster had dropped; the plan never
ran, so nothing could be reconciled.

**Cause.** A membership removed from the YAML that OPA no longer held was
still in terraform state; the provider errors on refresh instead of
planning the destroy. (A membership OPA still holds is planned as a
destroy as it should be.)

**Fix.** Every identity runner carries a `prune-attachments` step between
its `init` and its plan, backing the state up first (a silent OPA removes
nothing), and the group root's generation-time plan is a preview with
`-refresh=false`. Proved the same morning at 10:46 (backup serial 36
kept, one attachment removed, plan clean), restored through the gate at
11:00. If the error still appears, the runner did not reach that step:
read the run's output above the plan. An applying identity run's log
shows the group root's plan twice: the first is the preview made as the
run writes its files, never applied; the second, after the prune step, is
the one the gate reads.

**Date.** 2026-09-23 (found 2026-09-22).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`user "x" is not present within group "g"` row and the "plan twice" row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the 2026-09-22 stale attachment item);
[../packages/hashicorp-utils/README.md](../packages/hashicorp-utils/README.md)
"When it fails" (the 2026-09-23 item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("A dropped membership blocked every identity plan").

### The release flag had to be switched off by hand mid-release

**Symptom.** Twice, `require_released_builds` was switched off by hand for
the middle of a release, because the validator refused `instance '<name>'
is pinned to build <id> of '<image>', which is not a released build`
after `upgrade instance` had moved the pin to a build that could only be
proved on that very instance.

**Cause.** A durable instance whose volume allows one attachment can prove
a new build only on itself, after the pin has moved; the flag read the
unreleased pin as a violation with no room for the proof under way.

**Fix.** The release grace admits the series head while its own proof is
under way and refuses naming what is missing: `... not a released build
(config.require_released_builds; no grace: <reason>)`, where the reason is
one of: not the series head, no in-bake record, a failed post-bake, or
the instance neither stands on it nor is being replaced onto it. Proved
2026-09-23 12:58 to 13:11 as the model's third release with the flag never
touched. Act on the reason; never switch the flag off.

**Date.** 2026-09-23 (seen 2026-09-20 and 2026-09-22).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`is not a released build` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the 2026-09-22 `require_released_builds` item);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "2026-09-20 and 2026-09-22" item).

### The release and retention runs left a stray tfvars file

**Symptom.** A stray `instances.auto.tfvars` under `generated/release/` or
`generated/retention/`, untracked after every release run, which the
commit scanner refused by name.

**Cause.** The instance builder's finalize hook acted for every lifecycle,
and wrote the instance root's variable file under directories where no
instance root exists.

**Fix.** The hook acts for the instance-image lifecycle alone, and for a
root inside the run's runtime scope. The real file, under the instance
root, is never committed by design (`Meta-state commit: never staging
generated/.../instances.auto.tfvars` is normal); a stray copy from an
older run is deleted by hand once.

**Date.** 2026-09-23 (found 2026-09-22).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`never staging generated/.../instances.auto.tfvars` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the 2026-09-22 tfvars item);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "until 2026-09-23" tfvars item).

### The network to Google timed out under the state query

**Symptom.** `state query storages/<pd> unavailable: ...
oauth2.googleapis.com ... Read timed out`; `cloud-preflight` then exited
1 and the recipe stopped before its first step.

**Cause.** The network to Google, not the system.

**Fix.** Nothing in the tree: check `gcloud auth application-default
print-access-token`, then run the recipe again. An `unavailable` line is
never drift, and the strict query refuses on it by design.

**Date.** 2026-09-23.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`oauth2.googleapis.com ... Read timed out` row).

### sft resolve exited 126 with nothing on stderr

**Symptom.** `sft resolve ...: exit 126` and no output, in a login proof
run by hand (the registration half had passed) and again after a replace.

**Cause.** The `sft` client wanted a browser and `--quiet` forbade it: by
hand, an expired client session; as the workload, the token was missing or
refused.

**Fix.** The login proof names the cause in its `resolves` check: `the
client has no session (as the enrolled client: run sft login; as the
workload: OPA_TOKEN is missing or was refused)`. By hand, `sft login`,
then the proof again.

**Date.** 2026-09-22 (and again 2026-09-23, after a replace).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`sft resolve ...: exit 126` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the 2026-09-22 `sft resolve` item);
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-22 item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" (the `sft resolve --quiet` item).

### The first live replacement: four traps in one afternoon

**Symptom.** Replacing the model instance (`coops-model` to
`coops-model-002`) met four refusals or silences in turn: the gate refused
`module.instance_coops_model.aws_volume_attachment.this["mnt_data"]` as an
unwhitelisted destroy; the strict state query reported the booted image
behind the moved pin as `changed` and `cloud-launch`'s preflight refused
the very launch that would finish the replacement; in review, the
replaced machine's OPA registration under `<name>-001` would have outlived
it and claimed the bare alias; and the alias pass ran before the new
machine had enrolled and wrote nothing.

**Cause.** A volume attachment binds the volume to the instance id, so a
`-replace` of the instance replaces the attachment too. After `upgrade
instance` moves the pin the booted image is behind it by design until the
launch. Nothing retired the previous generation's registration. The alias
pass did not wait for a machine launched in the same run.

**Fix.** The replace plan whitelists the instance AND its volume
attachments. A pending replacement is a `note:` (`booted image <x> is
behind its pin <y>; the replacement is PENDING`), drift again without the
marker. `mark_launched` retires the registration of the hostname the
previous generation booted with when the new one differs. The alias pass
waits for a machine launched in the same run to be reachable (300 s) and
then for its registration (300 s), and gives up loudly (`not reachable
within 300s of its launch; no alias this run`, `not enrolled within
300s`); the next applies-on run gives the names back. `just
cloud-upgrade <rt> <instance>` runs the pin, the replace, the proof and
the release as one gated sequence, what were five hand steps until
2026-09-23.

**Date.** 2026-09-22.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`DESTROY NOT WHITELISTED` row's replacement sentence, the `changed
instance x: booted image` row, the `'<name>' has 2 registrations` row, the
`not enrolled within 300s` row); [OPERATIONS.md](OPERATIONS.md), "A model
image, end to end" (step 3, "what were five hand steps until
2026-09-23"); [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the four 2026-09-22 items: no alias, the
strict query refusing the upgrade, the gate and the attachment, the
replaced machine's registration);
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the two 2026-09-22 items);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "four traps" item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("A replacement's old registration claimed the new
machine's alias").

### The identity plan ran on ciphertext

**Symptom.** `no users found using search criteria: profile.login eq
"x@ENC[age:..."` for every derived address, on the first real identity run
after e-mail domains became encrypted values.

**Cause.** The generation-time plan ran in `generated/`, where a derived
address's domain is `ENC[age:...]`, and the Okta provider searched for the
ciphertext.

**Fix.** The generation-time plan materialises the root into `_private/`,
initialises there and plans there, exactly as the runner does; a dry run
plans nothing at generation time. By hand, terraform runs under
`_private/`, never `generated/`; a plan in `generated/identity/...`
reproduces the failure.

**Date.** 2026-09-22.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`no users found using search criteria` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the "identity plan ran on ciphertext" item);
[../packages/hashicorp-utils/README.md](../packages/hashicorp-utils/README.md)
"When it fails" (the 2026-09-22 item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("Every derived lookup failed on a real run").

### The first CI-policy reconcile was refused by hard drift

**Symptom.** The identity apply that would CREATE the CI login policies
could not run: their absence read as `missing [HARD]`, and a run is
refused on hard drift.

**Cause.** Workload objects were classified like groups, where an answered
absence is hard; but the policy's absence is exactly the state the apply
repairs.

**Fix.** Workload drift is never hard: `missing` for an absent role
(`workload role '...' named in the configuration is not known to OPA; the
operator creates it`) or an absent policy (`CI login policy '...' is
absent; an identity run with apply_identity creates it`), `changed` for a
policy that no longer mirrors. The strict query and the login proof still
fail on them; the identity apply is the repair.

**Date.** 2026-09-22.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`CI login policy '<g>_v1_security_policy_ci' is absent` row and the
`workload role '...' is not known to OPA` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the "first live CI-policy reconcile" item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("The first reconcile refused by hard drift").

### OPA's workload API: a hyphenated path and an error with no body

**Symptom.** `GET /v1/teams/<team>/workload_roles` answered 404; and the
first live policy write failed with `HTTP Error 400` and nothing more.

**Cause.** The path is hyphenated, `workload-roles`, as Okta's PAM SDK
carries it (the connections path is `connections/workloads`); and the
API's explanation of the 400 was in the response body, which was not
shown. A stored rule also carries `security_policy_id`, the one field on
which a copy differed from its original, so the comparison saw a change
that was OPA's bookkeeping.

**Fix.** The hyphenated paths are used; a 404 from either listing is an
`unavailable:` line in the state query and `OPA's security policies or
workload roles could not be read` from the reconcile. `_send` raises
`POST /v1/teams/.../security_policy: HTTP 400 Bad Request -- <body>`, and
the comparison strips OPA's bookkeeping ids at every depth.

**Date.** 2026-09-22.

**Where it was told.**
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" (the `workload_roles` 404 item and the `HTTP Error 400`
item).

### A lapsed OPA key read as five missing groups

**Symptom.** Under an unsourced `.envrc` the state query printed five
`missing ... [HARD]` lines, one per managed group, and refused every run;
the groups all stood in OPA.

**Cause.** The provider answered `HTTP 401` and the query reported every
group `present: false`: a group the provider could not be ASKED about was
read as a group the provider had answered for.

**Fix.** A failed call is `{present: false, error: "HTTP 401
Unauthorized"}` and the report says `unavailable: groups/<g>: HTTP 401
Unauthorized`, naming the group and the error; only an answered absence
(a 404) is `missing [HARD]`. A 401 or "no gid" means the wrong or lapsed
key pair: `source .envrc`, check which pair the environment exports (the
last export wins), rotate in the OPA console if it expired.

**Date.** 2026-09-21 (fixed 2026-09-23).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`unavailable: groups/<g>: HTTP 401` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the 2026-09-21 lapsed key item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("Five standing groups read as deleted").

### Three registrations of one hostname in OPA, one live

**Symptom.** `sft ssh coops-model` could not choose: three servers
answered to the canonical name, one of them alive. In a login proof today
the shape is `'<name>' has 2 registrations: ...`.

**Cause.** Every relaunch of one declaration enrolled another server under
the same name and nothing retired the old one. The team-level
`/v1/teams/<team>/projects/...` path answered `401 Missing capability`;
servers live only under `/resource_groups/<rg>/projects/<prj>/servers`
(`GET` 200, `DELETE` 204), which the resolver walks from the
resource-group and project NAMES (`<g>_rg`, `<g>_rg_login`) to their ids.

**Fix.** A decommission or replacement retires the registration with the
pin and the launch parameters (a failure is `Instance <n>: its OPA
registration as '<h>' was NOT retired (...); a stale server will answer to
that name until it is deregistered by hand`); a run that can launch
refuses a claimed or unreadable name (`could not check whether canonical
hostname ... is already claimed ... refusing to launch on silence`); a new
machine is named `<declared>-NNN`; and generations are observed through
the provider's instance id. The two duplicates were deleted by hand on the
day.

**Date.** 2026-09-21.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`'<name>' has 2 registrations` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the "three `coops-model` registrations" item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("Three registrations of one hostname");
[DESIGN.md](DESIGN.md) ("Why observation", which cites the date).

### An invalid hostname failed silently at boot

**Symptom.** Every step reported success, yet `sft ssh <declared>` found
nothing: the machine had enrolled under the hyperscaler's
`ip-10-26-34-156`.

**Cause.** The launch script's `hostnamectl set-hostname '<name>' || true`
swallowed an invalid name, so the machine kept its default hostname and
enrolled under it.

**Fix.** `check_canonical_hostnames` refuses at validate what the boot
swallowed (RFC 1123: at most 63 characters of letters, digits and hyphens,
not starting or ending with one), and the state report notes a machine
`registered in OPA as '<x>' but its generation booted as '<y>'`.

**Date.** 2026-09-21.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "invalid hostname failed silently"
item); [OPERATIONS.md](OPERATIONS.md), "Canonical hostnames" ("A name the
machine cannot take is refused at validate").

### An sso-session profile was read as absent for an hour

**Symptom.** The readiness check read the profile as ABSENT for an hour
and `just full-test` skipped its live legs while reporting `passed`;
earlier the same check, read against a 30-minute run, refused a full-test
on its last leg while the CLI would have refreshed the token.

**Cause.** An `sso-session` profile's `expiresAt` is the access token's,
not the portal session's; the CLI refreshes the token from the refresh
token while the portal session lives. The preflight read the token's
expiry as the session's.

**Fix.** `preflight` reports such a profile as `present; refreshes itself
from the refresh token in sso cache <id> while the portal session lives
(no fixed expiry readable)`, and readiness counts it present. A session
that lapses mid-run is environmental: `aws sso login --profile <p>`, then
`just full-test-legs`. `full-test: passed` above `SKIPPED the
credential-gated legs` is not a pass.

**Date.** 2026-09-21.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`preflight: a session has EXPIRED` row's sso-session sentence and the
`SKIPPED the credential-gated legs` row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the "sso-session profile's `expiresAt`" item);
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-21 item).

### A stopped machine was reported as "the provider could not answer"

**Symptom.** The operator's own stopped model instance read as an
unreachable cloud (`booted image (runtime <rt> could not answer)`,
`unavailable`), `run_session_command` said `no running instance` for both
cases, and a stopped ephemeral was invisible while its disks billed.

**Cause.** The boot-image probe filtered on `running`, so a stopped
machine and an unreachable cloud were indistinguishable; on GCE a
`TERMINATED` instance (which exists and is stopped) was read as absent.

**Fix.** The power-state hook separates `None` from `STOPPED` (GCE's
`TERMINATED` maps to stopped; a deleted instance is `not found` and maps
to absent). The report says `note: instances/<name>: STOPPED (switched
off; not drift) ...`, a stopped ephemeral shows as standing, and a session
command on a stopped machine fails with `cannot run a command on
'<name>': it is STOPPED (switched off; not drift)`. Confirmed live: a plan
over the stopped machine reported no changes and left it stopped. The
power state is the operator's: verification starts a stopped machine,
checks it and stops it again; the login proof starts nothing.

**Date.** 2026-09-21.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`instance <x> verified` for a switched-off machine row);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the "stopped machine was reported" item);
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the 2026-09-21 item);
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the 2026-09-21 item).

### The run's commit failed while the instance it launched was running

**Symptom.** A launch succeeded and the run's `--commit` did not: `git add
-A` exited 1 saying the private mirror's path is ignored.

**Cause.** The mirror was excluded twice: by an `:(exclude)` pathspec on
the add AND by the root's `.gitignore`; together git refused the add.

**Fix.** The pathspec is gone; the `.gitignore`, `refused_path` and the
scanner's skip keep the mirror out. The regression test runs a real `git
add`.

**Date.** 2026-09-20.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "run's commit failed" item).

### A pin outlived its instance

**Symptom.** `coops-model` was destroyed through the gate and `pins.yaml`
kept binding it, with its launch parameters; with `require_released_builds`
on, `validate` refused every run, including the one that would release the
build, so the declaration had to be commented out.

**Cause.** The forgetting mechanism is proven in the fixture, so the live
cause stays unexplained.

**Fix.** `cs-image-system forget instance <name>` drops a pin and launch
parameters that outlived their instance and records the correction; it
refuses (exit 2) while the instance is still declared. Never edit
meta-state by hand.

**Date.** 2026-09-20.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "pin outlived its instance" item);
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-20 item);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "`coops-model` was destroyed through
the gate" item).

### A false in-bake assertion could not stop the bake

**Symptom.** The first model image baked green twice while asserting
`rpm -q vim` on AlmaLinux 10, which has no package of that name (it is
`vim-enhanced`); the instance launched from that AMI then failed the same
check. A lineage record with a healthy assertion count stood behind it.

**Cause.** A `packages:` assertion was written `a || { b && c; }`, and
POSIX suppresses `set -e` for a command inside an AND-OR list, so the
provisioner ran on however false the check was. The storage and runtime
PREREQUISITE checks shared the shape, which is the likely reason an absent
EFS client went uncaught at bake time.

**Fix.** Every generated assertion tests and exits for itself, naming the
package on stderr (`package vim is not installed`); a test runs each form
under `sh -e` with a sentinel. Because a failing assertion stops the
build, a build that EXISTS is one whose in-bake assertions passed. A
`script:` line of your own that must be able to stop the bake ends in
something that exits nonzero (`|| exit 1`), not a braced group. Name the
real package (`vim-enhanced`); `amazon-efs-utils` is not in AlmaLinux's
repositories, so the reference image builds it from source.

**Date.** 2026-09-20.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`rpm -q vim fails on AlmaLinux 10` row); [OPERATIONS.md](OPERATIONS.md),
"What a green bake proves";
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the "in-bake assertion could not fail" item);
[../packages/packer-plugin/README.md](../packages/packer-plugin/README.md)
"When it fails" ("A false in-bake assertion could not stop the bake");
[../packages/bash-mod-plugin/README.md](../packages/bash-mod-plugin/README.md)
"When it fails" (the 2026-09-20 item).

### No instance could mount an EFS storage

**Symptom.** `verify instance` failed on the mount: `mount.efs` could not
even resolve the filesystem's DNS name.

**Cause.** The module made a filesystem and its access points and no
mount targets.

**Fix.** The module creates one mount target per zone and a security
group for them, and the builder passes the runtime's private subnets (one
per zone) and `addl_security_groups` as the clients. If the runtime
declares no `networking`, no private subnets, or no
`addl_security_groups`, the call carries none of the three and the
filesystem is again unmountable: check the emitted storage `.tf` for
`mount_target_subnet_ids`.

**Date.** 2026-09-20.

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "no instance in the account could
mount an EFS storage" item).

### The private mirror stood one level too deep

**Symptom.** `tofu init` in the materialised copy could not read its
module (`Module not found`, `Unreadable module directory`). Found by
probing an availability-zone change.

**Cause.** The mirror was put at `_private/generated/...`; every relative
path in an emission counts directories up to the configuration root, so
from one level deeper the module source and the local backend's
`../../../../<directory>/<workspace>.tfstate` named directories that do
not exist, and a real run would have planned against an empty state.

**Fix.** `mirror_path` replaces the generation directory's name with
`_private` instead of nesting under it, so `_private/<...>` and
`generated/<...>` stand at the same depth. If an init or plan under
`_private/` cannot find a module or reports an empty state while
`generated/` has it, compare the depth of the two directories.

**Date.** 2026-09-19.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "private mirror stood one level too
deep" item); [../packages/system/README.md](../packages/system/README.md)
"Seen live" (the 2026-09-19 item);
[../packages/local-state-plugin/README.md](../packages/local-state-plugin/README.md)
"Failures that have happened";
[../packages/hashicorp-utils/README.md](../packages/hashicorp-utils/README.md)
"When it fails" (the 2026-09-19 item).

### A zone change planned to destroy a data volume

**Symptom.** Proven against a copy of the live tree: pointing the runtime
at a subnet in another zone planned `us-east-2a -> us-east-2b # forces
replacement`, `1 to add, 1 to destroy`, on a 100 GiB volume holding data.
The gate refused it as an unwhitelisted destroy, but at apply time and
naming the volume rather than the cause.

**Cause.** A zone was inferred from the subnet and never checked against
the volumes that stand in it.

**Fix.** A subnet, a storage and an instance may declare
`availability_zone`; `check_availability_zones` refuses an incompatible
set at validate, naming every claimant, and the EBS builder passes the
declared zone to the module. The live subnets and `mnt_data` declare their
zones since.

**Date.** 2026-09-19.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "zone change planned to DESTROY" item);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "zone was inferred from the subnet"
item).

### The plaintext guard read the emission the run was about to replace

**Symptom.** The first run after a value was newly encrypted could never
regenerate the tree that made it fail: the guard ran before generation
and refused on the plaintext still in the committed emission.

**Cause.** The scan read `generated/` before the run had rewritten it.

**Fix.** The plaintext scan runs at the commit (and by hand in `validate`
as `check_no_plaintext_emitted`), never before generation.

**Date.** 2026-09-18.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the 2026-09-18 item).

### Checks that had never run: versions, foreign keys, playbooks, the manifest

**Symptom.** No declared tool version had ever been enforced; both trees
had named a non-existent image builder for months and the image silently
baked nowhere; builder-level `playbooks:` were copied beside the packer
root and never run; and packer's `manifest.json` entered commits.

**Cause.** The version checkers were registered by name while the lookup
keyed on the type in the wrong table. A foreign key that resolved to
nothing fell back to the raw id with a warning. The ansible builder's
`playbooks:` field was copied by `copy_external_assets` and referenced by
no provisioner. The manifest was not in the emitted `.gitignore`.

**Fix.** `validate` and every run check every declared tool's version
(`<tool> <found> does not meet its requirement <spec>
(cfg/executables.yml)`), and a CI failure naming a tool version means the
floor moved. `check_foreign_keys` refuses a name that resolves to nothing
(`<Model> '<image>': field 'image_builder' names '<x>', which is no
image_builder_model (declared: ...)`). The builder-level `playbooks` field
is gone (an unknown key at load); a playbook is declared on each item that
runs it. The manifest is run-local: named in the emitted `.gitignore`,
never staged by `--commit`.

**Date.** 2026-09-17.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the 2026-09-17 item);
[../packages/packer-plugin/README.md](../packages/packer-plugin/README.md)
"When it fails" (the three "fixed 2026-09-17" items);
[../packages/ansible-plugin/README.md](../packages/ansible-plugin/README.md)
"When it fails" (the two 2026-09-17 items).

### Three green CI jobs ran nothing

**Symptom.** Three green `live` runs had run nothing: the finalize
warning `no okta/okta credentials in the environment` sat in their logs.

**Cause.** `OKTA_API_PRIVATE_KEY` existed as a secret with the empty
string as its value, set from a checkout missing `.envrc`; an empty value
is exactly what "no credentials" looks like, and a job's conclusion is
never proof its steps ran.

**Fix.** The CI gate names every missing or empty secret and fails;
`preflight` lists every credential-shaped variable (`OKTA_*`, `TF_VAR_*`,
...) that is set but empty (`environment: <NAME> is set but EMPTY -- a
credential that exists with no value is a failure, not an absence`) and
exits 2. The `live` or `perform` job green with `SKIPPED` in its summary
is not a pass either: set the secrets the workflow names.

**Date.** 2026-09-16 (the okta-opa README's date; the system README
says 2026-09-17).

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
"green with `SKIPPED`" row);
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-17 item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("A secret that exists but is empty").

### A modification with only config baked nothing

**Symptom.** Two fixture items (`dask-setup2`,
`data-science-workstation-two`) rendered no provisioner, while lineage,
the on-image bundle and the modification tests recorded them as applied.

**Cause.** An ansible item with `config:` and no `playbooks:` has nothing
to modify with.

**Fix.** Refused at load: `Ansible modification '<name>' declares no
playbooks: it has nothing to modify with (config alone provisions
nothing). Give it 'playbooks:' ... or remove it.` Either way the image's
fingerprint changes and it re-bakes.

**Date.** 2026-09-16.

**Where it was told.**
[../packages/ansible-plugin/README.md](../packages/ansible-plugin/README.md)
"When it fails" (the 2026-09-16 item).

### Backend configuration changed after state encryption was switched on

**Symptom.** `tofu init` refused with "Backend configuration changed" and
asked for `-reconfigure` or `-migrate-state`, in the live tree and the
fixture.

**Cause.** `encrypt` was flipped from the accepted `false` to `true` under
roots that were already initialised.

**Fix.** Every real-run `init` carries `-reconfigure` (the state is
remote; nothing needs migrating); an existing state object is
re-encrypted server-side when next written. The message can still appear
from a hand `tofu init` in a root the system initialised: run the
system's form (`init -reconfigure -backend-config=<file>`), never
`-migrate-state` by hand, which is reserved for `run --migrate-state`.

**Date.** 2026-09-16.

**Where it was told.**
[../packages/tf-s3-state-plugin/README.md](../packages/tf-s3-state-plugin/README.md)
"When it fails" (the 2026-09-16 live-and-fixture item and the `Backend
configuration changed` row);
[../packages/hashicorp-utils/README.md](../packages/hashicorp-utils/README.md)
"When it fails" (the 2026-09-16 `encrypt: true` item).

### A fresh clone's runner failed at its first plan

**Symptom.** After a dry run (whose `.terraform/` is backend-less) or in
a fresh clone (no `.terraform/` at all), a hand-run `run-<lifecycle>.sh`
failed at its first `tofu plan`: the backend had never been initialised.
On the way, a generation-time `tofu init` run concurrently with the test
bar over the same provider plugin cache failed; alone it passed.

**Cause.** The committed script assumed an initialised root. The shared
`TF_PLUGIN_CACHE_DIR` is not safe under concurrent `init`.

**Fix.** Every root's deferred block begins with its own `tofu init
-input=false -reconfigure -backend-config=<file>`; a script from before
needs the `init` by hand. One tofu-using process at a time on a machine:
the recipes that may execute roots hold `.tofu-plugin-cache/.lock`
(`cs-image-system --locked`), a second one refuses with `--locked: another
tofu-using command holds ...` (exit 75), and the suite never shares the
cache.

**Date.** 2026-09-16.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`--locked` row);
[../packages/tf-s3-state-plugin/README.md](../packages/tf-s3-state-plugin/README.md)
"When it fails" (the "operator and fresh clone" item);
[../packages/hashicorp-utils/README.md](../packages/hashicorp-utils/README.md)
"When it fails" (the "fresh clone's runner" item);
[OPERATIONS.md](OPERATIONS.md) section 5, "Applies" (the one-tofu-process
rule).

### A dry run in CI reached S3

**Symptom.** `tofu init` failed at generation with an S3 access error,
before any plan, in a dry run under a read-only role with nothing on S3.

**Cause.** A dry run executed each root's generation-time `tofu init`
WITH the S3 backend, which needs no state at all.

**Fix.** A dry run's `init` is `init -backend=false`. A dry run that
reaches S3 is not dry: check `dry_run` in `generated/run-summary.json`.

**Date.** 2026-09-15.

**Where it was told.**
[../packages/tf-s3-state-plugin/README.md](../packages/tf-s3-state-plugin/README.md)
"When it fails" (the 2026-09-15 CI item).

### CI was red for 245 runs on a missing key pair

**Symptom.** `Okta builder <b> is missing a key value. Expected to find
environment variable TF_VAR_<team>_key ...` from three tests, in every CI
run for weeks; locally they passed.

**Cause.** Every configuration load finalizes the workspace and checks
the OPA key pair; the three tests inherited the developer's `.envrc`
locally and had nothing in CI.

**Fix.** The pair is a named CI secret (`TF_VAR_NOS_KEY` /
`TF_VAR_NOS_SECRET` in the reference workflow), and any command that
loads the tree (`validate`, `run`, `state query`, `verify`) refuses with
that one line rather than an assertion. Locally, `source .envrc`.

**Date.** 2026-09-15.

**Where it was told.**
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" (the "missing a key value" item);
[DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the `missing a key value`
row, for the current shape).

### A misspelt credentials key was silently dropped

**Symptom.** `credentials.profile_nme` in the tree left the profile unset,
and boto3 fell back to `AWS_PROFILE` or nothing.

**Cause.** `credentials` was a plain mapping, so a typo was just another
key.

**Fix.** The typed `AwsCredentials` model makes it a validation error
naming `credentials.profile_nme`.

**Date.** 2026-09-12.

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the 2026-09-12 item).

### The generated gitignore dropped a restated rule

**Symptom.** A configuration's own `.*` rule in the generated
`.gitignore` did nothing: the lock file it meant to cover stayed
unignored.

**Cause.** A first-wins dedupe kept the built-in `!.terraform.lock.hcl`
ahead of the configuration's `.*`, so the negation came first and the
later rule could not be restated.

**Fix.** The last occurrence of a rule keeps its place.

**Date.** 2026-09-11.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the 2026-09-11 item).

### The retired placeholder commands looked like successes

**Symptom.** `test` and `cleanup` printed a warning and succeeded, which
an old script would take as success; the `verify` command GROUP shadowed
the `verify` placeholder, which could never run.

**Cause.** Placeholders from the previous generation of the CLI were left
registered.

**Fix.** `verify` the placeholder is deleted; `test` and `cleanup` print
`<name>: retired in V2. ...` naming the replacement and exit 2.

**Date.** 2026-09-11.

**Where it was told.**
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-11 item).

### A run scoped to AWS failed on the GCE instance root's plan

**Symptom.** `data.google_compute_image.family` returned 404 for
`family/imgfile-basic-dask` at the GCE instance plan, and a run scoped to
the AWS runtime failed before its own bake.

**Cause.** The run still planned the GCE instance root, whose module
resolves a deferred image through its family, and the previous cycle's
retention had disposed every GCE image.

**Fix.** Under `--only-runtime` (explicit, or implied by
`--apply-runtime`) another runtime's storage and instance roots emit
nothing, and the out-of-scope instance builder's finalize hooks do nothing
either. The failure still exists on its own runtime: a root whose instance
image is deferred and whose family holds no image fails at plan with that
404. Bake the image first (the `instance-image` lifecycle bakes before it
plans), or launch with a pinned build.

**Date.** 2026-09-10.

**Where it was told.**
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-10 scoped bake item);
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the `family/imgfile-basic-dask` item);
[../packages/tf-gcp-plugin/README.md](../packages/tf-gcp-plugin/README.md)
"When it fails" (the `data.google_compute_image.family` item);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the 2026-09-10 item).

### The first live post-bake suite failed on a placeholder playbook

**Symptom.** The GCE dask bake succeeded and `python3 -c 'import dask'`
failed on the launched instance; the instance stood (`on_failure: keep`),
and the decommission recipe re-ran the ephemeral sequence because the
instance was still declared. On the re-bake, ansible's `pip` task died
with `Failed to import the required Python library (packaging)` while the
`package` task before it had passed.

**Cause.** The fixture's `setup_dask.yml` had been a placeholder (one
`debug` task) since the first bakes, and no plugin can tell an empty
playbook from a full one. Ansible's `pip` module imports `packaging` on
the target's interpreter, and the pinned
`/usr/local/bin/csis-ansible-python` (a bare `python3.N`) does not have
it.

**Fix.** The image's `tests.post_bake` is what catches an image that
installed nothing: the verdict lands in `meta-state/image-tests.yaml` (ok
false, the failing assertion named) and `release` refuses the build. The
playbook runs `pip3` through `ansible.builtin.command` guarded on an
import check; any module that needs a library on the target interpreter
has the same problem. The decommission recipe uses `--undeclare
instance:gce-test`.

**Date.** 2026-09-10.

**Where it was told.**
[../packages/ansible-plugin/README.md](../packages/ansible-plugin/README.md)
"When it fails" (the two 2026-09-10 items);
[../packages/tf-gcp-plugin/README.md](../packages/tf-gcp-plugin/README.md)
"When it fails" (the "post-bake suite failed `import dask`" item).

### A GCE bake disconnected at the last scriptlet of the update transaction

**Symptom.** `Script disconnected unexpectedly` 3 min 24 s into a GCE base
bake over the IAP tunnel, as the security-update transaction closed
(`pam`, `dbus-broker`, `libssh`, `curl`, `python3`...). Packer cleaned its
build VM; nothing was left on GCE.

**Cause.** Transient, not reproduced; a scoped retry (`run base-image
--only basic-rh-10@gcloud-east1`) baked cleanly.

**Fix.** Nothing changed. The watch item if it recurs is packer's
`expect_disconnect` or a pause on the OS-update provisioner of IAP
runtimes; read packer's log in the bake's block directory and retry the
bake alone.

**Date.** 2026-09-10.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the `Script disconnected unexpectedly` item).

### InvocationDoesNotExist right after send_command

**Symptom.** The unmount had already run on the instance when
`get_command_invocation` raised `InvocationDoesNotExist`, so no receipt
was written and the gate refused the detach.

**Cause.** SSM's invocation record lags its `send_command` by a moment.

**Fix.** The poll tolerates that code until its deadline; any other SSM
error still raises.

**Date.** 2026-09-10.

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the 2026-09-10 item).

### The modification tests had no container for EL 10

**Symptom.** The first `just full-test`'s mod-test leg could not start a
container for an EL 10 image: `docker run` failed to pull
`rockylinux:10`, and the item's test never ran.

**Cause.** Docker Hub's `rockylinux` library stops at 9.

**Fix.** The container stand-in for the Red Hat family at major 10 is
`almalinux:<version>`, from the image-sources table; a family or version
with no stand-in reports `unsupported` with `no local test image for the
root OS family`, and `local_test_image` on the OS builder names one.

**Date.** 2026-09-10.

**Where it was told.**
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the `rockylinux:10` item);
[../packages/bash-mod-plugin/README.md](../packages/bash-mod-plugin/README.md)
"When it fails" (the 2026-09-10 item).

### The first AlmaLinux 10 base was refused as an unsupported RHEL version

**Symptom.** `Unsupported RHEL version '10'` at generation.

**Cause.** The `rhel` type accepted only majors 8 and 9.

**Fix.** EL10 is accepted and emits `rhel-10-*` repository names (a no-op
on an unregistered image). Any other major is refused at load, whatever
the update policy: `Unsupported RHEL version '<v>' in OS builder <name>
(supported: 8, 9, 10)`.

**Date.** 2026-09-10.

**Where it was told.**
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the `Unsupported RHEL version '10'` item).

### An apply scoped to GCE baked two AMIs on AWS

**Symptom.** `run ... --apply-runtime gcloud-east1` without
`--only-runtime` baked two AMIs on AWS.

**Cause.** `--apply-runtime` scoped the applies, never the bakes.

**Fix.** `--apply-runtime` implies `--only-runtime` unless `--only` or
`--only-runtime` is given, and a real run whose bake plan reaches outside
its apply scope refuses before any bake: `run scope: bake(s) outside the
apply scope ['<rt>']: <series>@<rt> -- pass --allow-unscoped-bakes, or
select images with --only / --only-runtime` (exit 1, in the summary's
`error`); a dry run only warns with the same text.

**Date.** 2026-09-09.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "`--apply-runtime gcloud-east1`" item);
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-09 `--apply-runtime` item).

### The AWS session lapsed mid-cycle, and then before the preflight could say so

**Symptom.** A fifteen-minute GCE cycle failed at its GCE instance plan
with `No valid credential sources found ... backend s3 ... the SSO
session has expired` after `cloud-preflight` had passed at the start. The
next day an expired session killed the configuration load with `AWS
Error: ...` from `get_vpc_map_and_default_vpc_id` before any preflight
could report it, on GCE work too, with GCP fully authenticated.

**Cause.** The GCE roots keep their terraform state in S3 by standing
decision, and the tree's AWS runtimes validate their networking at every
load, so an AWS session is a hard dependency of every GCE lifecycle, of
`empty --runtime gcloud-east1` and of every configuration load. A session
that outlives the preflight but not the run is environmental.

**Fix.** `raw_session_infos` reads `cfg/runtime-builders.yml` before the
load, so the callback prints the sessions and exits 1 on `preflight: a
session has EXPIRED; renew it (aws sso login --profile <p>) before the
configuration can even load` before `run` and `state` load. The
preflight and the strict state query flag a session expiring within
`config.preflight.expected_run_minutes`, the blocking window. Every
OTHER loading command (`validate`, `upgrade`, `verify ...`) still dies
inside the load with an AWS error; run `preflight` first. The repair is
`aws sso login --profile <p>`, then the legs that were running; the bakes
of the failed run are recorded and not repeated.

**Date.** 2026-09-09 (the load); 2026-09-08 (the mid-cycle lapse).

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "first preflight could not report an
expired session" item);
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the "2026-09-08 and 2026-09-09" item);
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the 2026-09-08 session item);
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the 2026-09-08 `No valid credential sources` item) and
its prerequisites ("A live AWS session as well", "found live 2026-09-08");
[../packages/tf-gcp-plugin/README.md](../packages/tf-gcp-plugin/README.md)
"When it fails" (the 2026-09-08 `tofu plan` of the `tofu-gce` root item).

### A verify assert as the runner's last step failed the run after the teardown

**Symptom.** A torn-down ephemeral kept its launch record: the records
described an instance that no longer existed.

**Cause.** `verify assert` as the runner's last step failed the script
before the after-apply hook that forgets the ephemeral ran.

**Fix.** Under the `teardown` policy the runner carries `verify instance
--record-only`, and the failed verdict fails the run from
`forget_ephemerals`, after the records are consistent with reality.

**Date.** 2026-09-09.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "`verify assert` as the runner's last
step" item); [../packages/system/README.md](../packages/system/README.md)
"Seen live" (the 2026-09-09 `verify assert` item);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "torn-down ephemeral kept its launch
record" item).

### A passphrase-protected key stopped every GCE session command

**Symptom.** `read_passphrase: can't open /dev/tty` from every
`run_session_command` on GCE.

**Cause.** The operator's `google_compute_engine` key was
passphrase-protected and the session hook (`gcloud compute ssh`,
non-interactive) cannot prompt; nothing in a run can.

**Fix.** The operator's key is agent-loaded or passphrase-less; the
project's `ssh-keys` metadata was re-provisioned by the guest agent within
seconds of the change. The prerequisites say so.

**Date.** 2026-09-09.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the `read_passphrase` item) and its prerequisites ("found
live 2026-09-09").

### The ephemeral runtime had no moment to release

**Symptom.** Retention disposed the verified build before the operator
could release it.

**Cause.** On an ephemeral runtime the cycle verifies, tears down and
retains in one run; nothing in it released.

**Fix.** An image may declare `release: {model}`, and the same run carries
a `release --declared` step after the proof, before retention.

**Date.** 2026-09-09 (seen 2026-09-07 to 09).

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "ephemeral runtime had no moment to
release" item).

### A follow image baked in the same run as its parent saw no move

**Symptom.** A child with `parent_policy: follow`, baked in the same run
as its parent, was not due: the pin/head comparison saw nothing.

**Cause.** The parent's new head is not recorded at plan time, so the
comparison read the old head.

**Fix.** `_bake_reason` reads a parent that bakes this run as a move
(`parent <build> re-bakes this run (parent_policy: follow)`), kept out of
the fingerprint on purpose.

**Date.** 2026-09-08.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the 2026-09-08 follow image item).

### A follow image kept its generation-time tags

**Symptom.** `changed` drift, `fingerprint differs`, on a follow image;
the strict preflight refused the next run.

**Cause.** A child baked in the same run as its parent was tagged by
packer at generation time with a `series-...` parent and a placeholder
fingerprint; the lineage record was written after the bake; and on GCE
`retag_image` was a no-op.

**Fix.** The packer plugin calls `retag_image` after every bake (on GCE it
does `setLabels`), and `lineage relabel --runtime <rt>` (`just
cloud-relabel <rt> no`; dry by default) re-tags any build whose tags still
disagree with its record. A `create_tags` or `setLabels` refusal in
`relabel` is `could not retag <id>` and the state query keeps showing
`changed`.

**Date.** 2026-09-08.

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the 2026-09-08 tags item);
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the `fingerprint differs` item).

### The IAP tunnel lagged behind a healthy build VM

**Symptom.** `4047: Failed to lookup instance` and an SSH timeout against
a build VM whose serial console showed sshd up in 30 s; four
reproductions. The day before, a dask bake had timed out waiting for SSH
through the tunnel in a window when GitHub's release downloads were
returning 504, and its retry provisioned in about 90 s; it was later
understood as the same lag.

**Cause.** A bake that followed another build in the same run hit IAP's
instance-lookup lag for longer than packer's default 30 s tunnel wait.

**Fix.** IAP bakes set `iap_tunnel_launch_wait = 120` (a constant in
`gcp_packer_source.py`); `PACKER_LOG=1` shows the tunnel retries if it
recurs.

**Date.** 2026-09-08 (first seen 2026-09-07).

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the `4047: Failed to lookup instance` item and the
2026-09-07 dask bake item).

### Verification compared the booted image with the word unbound

**Symptom.** The first ephemeral verification failed on `booted image` and
left the instance standing; `state query` said `ephemeral instance <name>
is STANDING`.

**Cause.** The instance's image had been baked in the same run, so
nothing was pinned yet, the launch record said `unbound`, and the check
compared the booted image with that literal.

**Fix.** Verification requires the booted image to be a recorded build of
the instance's image series on its runtime. The recovery was the next
`instance-image` run resuming the sequence (plan no-change, verify,
teardown), which is the intended one.

**Date.** 2026-09-08.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the "launch record of `unbound`" item);
[../packages/tf-gcp-plugin/README.md](../packages/tf-gcp-plugin/README.md)
"When it fails" (the "first ephemeral verification failed" item).

### Hook plugins loaded after the lifecycle names were resolved

**Symptom.** In a fresh process `run --all` resolved to the four
built-ins, and `run release` was refused with `Unknown lifecycle
'release'; expected one of [...]` (exit 2). The registration test of the
`release` lifecycle passed only after another test had loaded the hook
plugins.

**Cause.** `load_hook_plugins()` ran only inside `run_lifecycles()`,
after the names were parsed, so every plugin-registered lifecycle
(`release`, `retention`, the dummy's `notify`) was absent from `--all`.

**Fix.** The `run` command loads the hooks before parsing names, and the
test loads them itself. `Unknown lifecycle 'release'` today means the hook
entry points are not installed in the environment running the command; a
library caller must call `load_hook_plugins()` before
`parse_lifecycles()`.

**Date.** 2026-09-08.

**Where it was told.**
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the "Undated, found live: `run --all`" item);
[../packages/dummy-plugin/README.md](../packages/dummy-plugin/README.md)
"When it fails" (the 2026-09-08 item).

### The GCE verification never saw the startup script finish

**Symptom.** `gce-verify` never saw `startup-script exit status 0` on an
instance that was healthy the whole time.

**Cause.** Guest agent 20260715 logs `Finished running startup scripts`
instead.

**Fix.** The hook accepts both lines. A verification that reports `no
completion on the serial console within <timeout>s` on a newer agent
means a third spelling: read `serial_console` in the evidence
(`verifications.yaml`) and extend the pattern.

**Date.** 2026-09-07.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the `gce-verify` item).

### The GCS teardown died wiping an empty bucket

**Symptom.** `gcloud storage rm --recursive gs://<bucket>/**` exited 1 at
the end of a cycle, and the teardown stopped.

**Cause.** The command exits 1 when nothing matches, and an empty bucket
is the normal end of a cycle.

**Fix.** The wipe is `wipe-<label>.sh`, which prints `gs://<bucket> is
already empty` and exits 0 on "matched no objects", and otherwise prints
gcloud's output and exits with its status, stopping the run before
terraform's destroy. Any other message there (permission denied, no
credentials) is a real failure; the transition is not recorded until the
apply succeeds.

**Date.** 2026-09-07.

**Where it was told.**
[../packages/tf-gcp-plugin/README.md](../packages/tf-gcp-plugin/README.md)
"When it fails" (the "teardown died wiping an empty bucket" item).

### Every GCE bake timed out waiting for SSH after a firewall rule was removed

**Symptom.** `Timeout waiting for SSH` in the build log after the build
VM was created, on every bake.

**Cause.** Packer reached build VMs over their external IP on `tcp:22`,
which only worked while the default VPC's `default-allow-ssh` rule
existed; deleting it (deliberate hygiene) broke every bake.

**Fix.** An IAP runtime's packer source carries `use_iap = true` and the
bake tunnels like a session; the runner service account needs
`roles/iap.tunnelResourceAccessor` and the IAP firewall rule
(`35.235.240.0/20` on `tcp:22`) must exist. The same symptom today means
that role is missing: check the runtime's `session_mechanism`, the
project's firewall rules and the runner's IAM bindings, in that order.

**Date.** 2026-09-06.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the 2026-09-06 item);
[../packages/packer-plugin/README.md](../packages/packer-plugin/README.md)
"When it fails" ("GCE bakes timed out 'waiting for SSH' after the default
SSH firewall rule was removed").

### A pin was re-bound to a new series head without replacing the instance

**Symptom.** Meta-state claimed a build that reality did not run: the pin
had moved to the new head while the machine still booted the old build.

**Cause.** The post-finalize hook bound the pin from the plan's intent,
not from what booted.

**Fix.** The hook binds from what actually booted when the parent was
deferred, and the state query reports `booted image <x> != pinned build
<y>` as `changed` (a pending replacement is a `note`).

**Date.** 2026-09-06 (seen 2026-09-05 and 06).

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "pin was re-bound" item);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the `instance_boot_drift` clause of the ledger-shape
item).

### Decommissioning the last GCE instance planned no destroy, and a dry run erased its record

**Symptom.** Undeclaring the last instance on a runtime made its root
vanish, so nothing planned the destroy and the VM would have stayed
orphaned; and a dry run of the decommission erased the launch record
before any destroy, so the gate then had nothing to whitelist
(`gate-plan` reported `0 to destroy`; `state query` reported a `foreign`
instance right after the dry run).

**Cause.** The root was emitted only for declared instances; the forget of
the launch record ran at generation.

**Fix.** The root is still emitted for a recorded instance that is
undeclared (`_root_has_work()`), the decommission whitelist is scoped to
the root of the runtime the pinned build was baked on, and the forget is
an after-apply hook. A decommission can be dry-run as often as needed;
run it again with the record intact if the record and the plan disagree.

**Date.** 2026-09-05.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "decommissioning the last GCE
instance" item);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "tearing down the first GCE instance"
item); [../packages/tf-gcp-plugin/README.md](../packages/tf-gcp-plugin/README.md)
"When it fails" (the "undeclaring the last GCE instance" item).

### The GCE bake and boot disks were 200 GB

**Symptom.** The instance boot disk was 200 GB, about $8 a month, on a
free-tier machine.

**Cause.** The boot disk inherited the image's `disk_size`, which
inherited the OS builder's 200 GB `default_primary_disk_size` (a RHEL
vendor minimum on AWS, carried forward).

**Fix.** The GCE runtime's `default_disk_size` wins when the runtime
declares one, and every instance launched from the image has exactly that
boot disk. The fixture and the reference tree declare 10 GB, the vendor
image's floor (a boot disk cannot be smaller than its source image). The
default-os README's "40 GB on `gcloud-east1`" is stale: both trees say
10.

**Date.** 2026-09-05.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the "instance boot disk was 200 GB" item);
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the "GCE bake disk was 200 GB" item).

### Every session to a launched GCE instance was refused

**Symptom.** Every SSH/IAP session to the launched instance was refused:
no operator key had been provisioned.

**Cause.** At first boot the guest agent removes users absent from
metadata; when the bake user's `google-sudoers` membership was missing
(the agents race over it during bakes) `gpasswd` exited 3 and the agent
aborted its whole metadata-ssh-key setup.

**Fix.** The GCE runtime's `bake_finalize_commands` guarantee the
membership as the bake's last provisioner (`# runtime bake
finalization`); a test holds that it is the last one in the emitted build
file. A GCE image whose build file lacks that provisioner was generated
by an older tree: regenerate.

**Date.** 2026-09-05.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the "every SSH/IAP session ... refused" item);
[../packages/packer-plugin/README.md](../packages/packer-plugin/README.md)
"When it fails" ("First SSH to a GCE image refused after the bake").

### Ansible built its temporary directory under the wrong home

**Symptom.** Every ansible task `unreachable` with `Failed to create
temporary directory`, intermittently, on a GCE re-bake.

**Cause.** Packer's ansible provisioner defaulted `ansible_user` to the
operator's LOCAL login, never the build VM's SSH user, so ansible built
`~/.ansible/tmp` under `/home/<local-user>` on the VM. Intermittent
because packer's `use_proxy` auto-detection masked it until it flipped to
direct mode.

**Fix.** The provisioner carries `user = "<bake ssh user>"`, the one the
packer source resolves (`bake_ssh_username(image)`). If the symptom
appears on a runtime that answers `None` from that hook, the runtime needs
the hook, not the playbook.

**Date.** 2026-09-05.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the "ansible tasks died `unreachable`" item);
[../packages/ansible-plugin/README.md](../packages/ansible-plugin/README.md)
"When it fails" (the 2026-09-05 item).

### The GCE data disk was attached but never mounted

**Symptom.** `df /mnt/gce-data` resolved to the root filesystem; the
startup script's 60-iteration wait loop ended without the device, and
under `set -e` nothing after it ran either.

**Cause.** The module attached the disk as `device_name = "gce_data"`
while the launch script waited for `/dev/disk/by-id/google-gce-data` (GCE
exposes `google-<device_name>`), and GCE itself forbids `_` in device
names.

**Fix.** Both sides use `gce_name()`, one sanitisation for the module call
and the script. If a mount is missing today: the serial console (`gcloud
compute instances get-serial-port-output <name>`, or `verify instance`,
whose `data disks mounted` check reports `missing: /mnt/<x>`) shows the
wait loop; check the `device_name` in the module call against the `DEV=`
line of the user-data template. The storage's attachment in the instance
root is the other place to look.

**Date.** 2026-09-05.

**Where it was told.** [DAILY_DRIVER.md](DAILY_DRIVER.md) section 6 (the
`data disks mounted` failed row);
[../packages/tf-gcp-plugin/README.md](../packages/tf-gcp-plugin/README.md)
"When it fails" (the "pd was attached but not mounted" item);
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the `gce_data` sentence of the underscores item);
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the `_gce_device_name` clause of the ledger-shape item).

### The run's commit failed because another session moved the checkout

**Symptom.** `run --commit` failed with git exit 128 at the very end of a
run.

**Cause.** A peer session's `git flow feature start/finish` switched the
shared checkout's HEAD mid-run.

**Fix.** A `--commit` run does all its work first and fails at the very
end: the emission and meta-state are on disk, so commit them by hand or
re-run. The CI `perform` job names its committer for a related reason (a
runner has no git identity). Several sessions sharing one checkout check
the reflog before a checkout, stash or finish.

**Date.** 2026-09-05.

**Where it was told.**
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the 2026-09-05 git exit 128 item).

### The AWS VPC and security-group lookups bound the default provider

**Symptom.** A plan failed on the VPC lookup with a credentials or region
error while the module calls were fine; it had only ever worked from a
shell with ambient AWS credentials.

**Cause.** The root-level `aws_vpc` and `aws_security_group` blocks bound
the DEFAULT aws provider, which has no configuration.

**Fix.** Both carry `provider = aws.<alias>`.

**Date.** 2026-09-04.

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the 2026-09-04 item).

### dnf 5 exited 1 on a package that was already current

**Symptom.** `dnf update <pkg>` exited 1 with `No packages marked for
upgrade` on the first AlmaLinux 10 bake, where dnf 4 exited 0.

**Cause.** dnf 5 treats "nothing to do" as a failure for a targeted
update.

**Fix.** Targeted updates run only behind `dnf -q check-update <pkgs>` (100
means updates exist, 0 none, any other code is re-raised with `exit
"$rc"`). An `exit` with another code is dnf's own error; look at the
packer output just above it.

**Date.** 2026-09-04.

**Where it was told.**
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the 2026-09-04 dnf 5 item).

### One GCE chain baked its images as two different users

**Symptom.** SSH authentication failed at the instance bake of the first
Alma 10 dask chain on GCE; the build VM's serial console showed the guest
agent aborting its key setup with `not a member of google-sudoers`.

**Cause.** The base bake ran as `ec2-user` (an AWS fallback) and the
instance bake as `packer`; the new-generation guest agent removes the
other-name user at first boot and aborts its whole metadata-ssh-key setup
when that removal fails. The entry's `get_ssh_username()` was a no-op
that always returned `None`.

**Fix.** One GCE chain bakes every image as ONE user: `ssh_username` on
the OS-builder runtime entry covers the chain (and is honoured), the GCE
family default is `packer`, and `validate` refuses a chain whose images
would bake as different users.

**Date.** 2026-09-04.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the 2026-09-04 item);
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the 2026-09-04 "SSH authentication failed" item).

### The apply step executed another lifecycle's stale runner script

**Symptom.** `run storage --no-dry-run` ran the previous day's base-image
runner script, hook-lessly and by bare bash, and baked two unrecorded
AMIs. On the same days `apply-check` crashed because it loaded the
configuration: the guard failed closed, so the runner could not apply at
all.

**Cause.** The apply step executed every runner script it found under
`generated/`, not only the lifecycles requested this run; and the guard
that re-reads the apply flags loaded the whole tree to do it.

**Fix.** A script of a lifecycle not generated this run is
`stale-script-skipped` in the summary, with a warning, and never runs;
seeing that state says an older script is lying under `generated/`.
`apply-check` (with `gate-plan` and `identity export-gids`) is exempt from
the load and reads `cfg/_config.yml` as text; `apply-check: no
cfg/_config.yml found from the working directory up; refusing to apply`
(exit 3) means the step ran from a directory with no configuration root
above it (pass `--config-root`).

**Date.** 2026-09-03.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the 2026-09-03 item);
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the two 2026-09-03 items).

### Orphan AMIs from failed and unrequested bakes

**Symptom.** Eleven AMIs and twelve snapshots from the first live runs,
and two more from stale runner scripts, appeared as `foreign` in the state
query: they carried the system's tags and no record had them.

**Cause.** A failed run recorded nothing, not even the builds that had
completed; and the stale scripts of the entry above baked two more.

**Fix.** The operator deregistered them by hand that time. `state import`
adopts such an image and `dispose image` removes a recorded one; a
`foreign` line is never hard drift, but every line is actionable. The
builds that complete before a failure are recorded. The first live AWS
disposal (`dispose image <two EL8 AMIs> --no-dry-run --commit`)
deregistered both and deleted their snapshots, and `describe-images`
answered an empty list afterwards: a disposal's success is read from the
cloud, not from the log line.

**Date.** 2026-09-03 (seen 2026-09-02 and 03; the disposal 2026-09-09).

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the "orphan AMIs" item and the "first live AWS disposal"
item).

### GCE refused underscores in resource names

**Symptom.** `tofu apply` refused a disk named `gce_data`.

**Cause.** GCE resource names must match `[a-z]([-a-z0-9]*[a-z0-9])?`,
and the storage root emitted the YAML name verbatim.

**Fix.** Every resource name goes through `gce_name()`. If the provider
reports an invalid `name` again, a name reached the module call without
the sanitizer; the module call under `generated/storage/<B>/...` shows
which. Two names that differ only in characters it strips (`a_b` and
`a-b`) collide on GCE and the second fails with `already exists`: keep
names distinct in `[a-z0-9-]`.

**Date.** 2026-09-03.

**Where it was told.**
[../packages/tf-gcp-plugin/README.md](../packages/tf-gcp-plugin/README.md)
"When it fails" (the 2026-09-03 item);
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the "underscores in GCE names" item).

### A GCE bake fell through to a 1 GB machine

**Symptom.** A dask bake on GCE OOMed at 65 minutes.

**Cause.** The packer source's `machine_type` read the entry's
`machine_type`, else the runtime's default, the free-tier `e2-micro`; the
image builder's `default_machine_type` was not in the chain.

**Fix.** The bake size follows the same chain on every runtime: the
runtime entry's `machine_type`, then the image builder's
`default_machine_type`, then the runtime's. A bake that needs memory
declares it on the entry; the fixture bakes on `e2-small`.

**Date.** 2026-09-03.

**Where it was told.**
[../packages/gcloud-runtime-plugin/README.md](../packages/gcloud-runtime-plugin/README.md)
"When it fails" (the "dask bake fell through" item);
[../packages/packer-plugin/README.md](../packages/packer-plugin/README.md)
"When it fails" ("A GCE dask bake fell through to a 1 GB machine");
[CONFIGURATION.md](CONFIGURATION.md) (the `default_machine_type` and
`machine_type` rows of the image builder and runtime entry).

### A recorder claimed a reality no apply produced

**Symptom.** The state query's `missing [HARD]` caught a storage recorded
`None -> active` after a run whose apply flag was off: the fixture carried
no `apply_storage` key, so the run planned and gated with zero applies and
the transition recorder wrote the requested state anyway.

**Cause.** The reality-claiming recorders ran unconditionally after the
lifecycle.

**Fix.** Every reality-claiming after-apply hook (storage transitions, the
`launched` marker, pin binds, the forgets) runs only when the lifecycle's
apply flag was on; a dry or apply-less run leaves `storage-state.yaml`,
`launch-params.yaml` and `pins.yaml` exactly as they were. Relatedly, the
`apply_*` flags gated generation only, so a runner script generated under
a flag kept applying after the flag was turned off: every apply is now
preceded by `cs-image-system apply-check`, which re-reads `cfg/_config.yml`
and the overlays at execution and exits 3 with `apply_instances is false
NOW in <path>/cfg/_config.yml ... not applying.`

**Date.** 2026-09-02.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the 2026-09-02 recorder item);
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the 2026-09-02 `None -> active` item and
the "`apply_*` flags gated generation only" item).

### An enrollment token deleted out of band

**Symptom.** The identity plan ERRORED at refresh; the state query showed
`groups/<g>: missing ... IaC-owned launch enrollment token missing from
the identity provider ... [HARD]` and every run refused.

**Cause.** The token had been deleted in OPA outside terraform, and
oktapam 0.7.1 cannot plan the recreate.

**Fix.** The hard-drift line names the repair: `tofu state rm` the token
resource in the group's module, then a gated identity apply mints a new
one (a new value; instances launched before it keep the old token and are
not affected). The state query's `enrollment_token` probe is the only
witness.

**Date.** 2026-09-02.

**Where it was told.**
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("An enrollment token deleted out of band");
[../packages/base/README.md](../packages/base/README.md) "Failures that
have happened" (the enrollment-token clause of the ledger-shape item).

### A stale plan file passed the gate

**Symptom.** A failed `plan` left the earlier `tfplan` behind and
`gate-plan` judged the previous sequence's plan.

**Cause.** The gate read whatever planfile stood in the root.

**Fix.** Every gated sequence begins with `rm -f tfplan`, and `gate-plan
--planfile` refuses `STALE PLANFILE: <file> does not exist` or `... is
older than <newest .tf>` with exit 3. If it recurs, the plan step did not
run or did not succeed; read the runner's output above the gate line.

**Date.** 2026-09-02.

**Where it was told.**
[../packages/system/README.md](../packages/system/README.md) "Seen live"
(the first item);
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("A stale plan file passed the gate");
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "`gate-plan` accepted a stale
planfile" item); [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the `planfile_is_stale` clause of the
ledger-shape item).

### The EBS device never appeared as xvdf on a Nitro instance

**Symptom.** User-data died at `mkfs`; everything after that line never
ran and the mount was missing.

**Cause.** On Nitro instances (`t3` and later) the EBS volume never
appears as `/dev/xvdf`, and RHEL-family AMIs create no legacy symlink.

**Fix.** The launch script waits for either the declared device or the
`/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<volume id>` name. Where
to look: the instance's cloud-init/user-data log, and `verify instance`
(the completion marker `/var/lib/csis/launch-applied` is written only
when every line above it succeeded).

**Date.** 2026-09-02.

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "user-data died at `mkfs`" item);
[OPERATIONS.md](OPERATIONS.md) section 5, "Network" (the by-id
sentence); [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the `/dev/xvdf` clause of the
ledger-shape item).

### The S3 state query reported the system's own bucket as missing

**Symptom.** The state query reported the system's own bucket as
HARD-missing.

**Cause.** It looked for a `Name` tag the module never sets.

**Fix.** `_lookup` treats a reachable bucket as present; only
`NoSuchBucket`/`404` is absent, and any other error is re-raised into an
`unavailable:` line.

**Date.** 2026-09-02 (seen 2026-08-31 to 2026-09-02).

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "S3 state query reported the system's
own bucket" item).

### sft ssh hung on an instance every step had reported as launched

**Symptom.** `sft ssh` hung or was refused while every step reported
success and SSM worked.

**Cause.** Three things. The module's default public IP poisoned sftd's
advertised address in a VPC with no internet gateway. Instances wore only
the VPC default security group, which blocked the Okta gateway's inbound
SSH relay; and the relay also requires the OKTA-GATEWAY group on the
target. A delete-first replacement of the group hit `DependencyViolation`
because instances wear it.

**Fix.** The module call sets `associate_public_ip_address = false` and
the launch script pins `AccessAddress` to the private IP. The root
creates `csis-instances` with SSH ingress from
`ssh_ingress_security_group_ids` only (never a CIDR of the shared
networks), with `create_before_destroy`, and every instance also wears
`addl_security_groups`. Existing network configuration is never modified.
An instance the relay cannot reach while SSM works points at those two
lists.

**Date.** 2026-09-02 (seen 2026-09-01 to 02).

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "default public IP" item and the
"instances wore only the VPC default security group" item);
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the "`sft ssh` hung on the advertised private address"
item); [OPERATIONS.md](OPERATIONS.md) section 5, "Network" (the
no-public-IP and security-group bullets).

### The first identity plan wanted to create memberships that already existed

**Symptom.** The first identity plan wanted to CREATE
`oktapam_user_group_attachment` resources that stood in OPA already; the
provider would have errored on apply.

**Cause.** Memberships made by hand before the system managed the group
were not in state.

**Fix.** Each live attachment is imported first (`tofu import`, id
`<group>|<username>`; a `/` separator is rejected): six imports, zero OPA
writes, then a plan reading "No changes". The rule since: never let a plan
create an attachment that already exists (OPERATIONS "Adopt out-of-band
group membership").

**Date.** 2026-09-02 (seen 2026-08-31 to 2026-09-02).

**Where it was told.**
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("Memberships that already existed in OPA").

### Three small gaps of the first live runs

**Symptom.** The first successful bake's meta-state commit hit a
gitignored tree and could not stage its records; an unmount ran on the
instance and left no receipt, so the gate had nothing to read; and the
booted image was never compared with the pin, so a machine on the wrong
build was not drift.

**Cause.** Three first-time paths that had never run live.

**Fix.** A meta-state commit into a gitignored tree is skipped with a
warning; the unmount writes a receipt on success and on failure
(`write_receipt`); and the state query reports `booted image <x> !=
pinned build <y>` as `changed` (`instance_boot_drift`).

**Date.** 2026-09-02.

**Where it was told.** [../packages/base/README.md](../packages/base/README.md)
"Failures that have happened" (the "2026-09-02 onwards, the ledger's
shape" item).

### packer's AMI lookup found no credentials

**Symptom.** `No valid credential sources found` from packer's `data
"amazon-ami"` although the operator's shell was logged in.

**Cause.** packer does not read a profile it is not told about.

**Fix.** The source carries `profile = "<profile_name>"` on both the lookup
and the source. If it recurs, the runtime's `credentials.profile_name` is
unset or the profile has no live session.

**Date.** 2026-08-31.

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the first item).

### Every AWS bake timed out waiting for SSH

**Symptom.** `Timeout waiting for SSH` on every bake.

**Cause.** The VPC has no internet gateway, so packer's SSH communicator
could never reach the build instance.

**Fix.** `session_mechanism: ssm` with a profile makes packer connect
through Session Manager. The same message today means the Session Manager
plugin is missing on the baking machine, the build instance never
registered with SSM (no route to the SSM endpoints from the subnet, the
`user_data` bootstrap failed, or the profile lacks the SSM policy), the
bake ran past `ssh_timeout = "15m"`, or the host is too small (see the
1 GB bake host entry). Look at packer's log and SSM Fleet Manager.

**Date.** 2026-08-31.

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the "`Timeout waiting for SSH` on every bake" item).

### A Debian chain baked as ec2-user never authenticated

**Symptom.** `Timeout waiting for SSH` over the SSM tunnel on an AWS bake
of an image whose base is Debian.

**Cause.** The instance image baked as `ec2-user`, an account the Debian
AMI does not have; only the vendor user's `authorized_keys` receives
packer's key.

**Fix.** The bake user falls back by the chain root's `family` (`admin`
for Debian, `ubuntu` for Ubuntu, else `ec2-user`, the AWS runtime's
family default), the last step of the bake-user order every source
follows. A timeout on a family outside that map means the entry needs
`ssh_username`; a runtime or entry `ssh_username` that names the wrong
user brings it back.

**Date.** 2026-08-31.

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the "Debian chain baked as `ec2-user`" item);
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the "`Timeout waiting for SSH` on a Debian-derived bake"
item); [../packages/packer-plugin/README.md](../packages/packer-plugin/README.md)
"When it fails" ("A Debian-derived instance image baked as `ec2-user`
never authenticated").

### A baked AMI carried two root-slot volumes

**Symptom.** Instances from the `deb-11` chain never booted; the AMI
carried two volumes in the root slot.

**Cause.** The root device name was hard-coded to `/dev/sda1`; on HVM
`/dev/sda1` and `/dev/xvda` alias one slot, and a Debian root is
`/dev/xvda`.

**Fix.** The AWS runtime takes the vendor query's `RootDeviceName`, else
`/dev/xvda` for `debian`/`amazon` and `/dev/sda1` otherwise. A family the
map does not know, a query without `RootDeviceName`, or a deferred source
whose chain-root family is unknown still gets `/dev/sda1`.

**Date.** 2026-08-31.

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the "two root-slot volumes" item);
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the "two root-slot volumes" item).

### curl refused to re-download the SSM agent on Debian

**Symptom.** `curl: (23)` during the agent provisioner on Debian.

**Cause.** The `user_data` bootstrap had already left a root-owned
`/tmp/ssm.deb`, and the provisioner tried to write the same file.

**Fix.** The provisioner skips the install when the agent is present and
downloads to its own file name.

**Date.** 2026-08-31 (undated in the record; among the first bakes).

**Where it was told.**
[../packages/aws-runtime-plugin/README.md](../packages/aws-runtime-plugin/README.md)
"Seen live" (the `curl: (23)` item).

### A full upgrade severed the SSM build tunnel

**Symptom.** Packer lost the connection mid-provisioner, twice, about 27
minutes into a 599-package upgrade of `basic-rhel-8`.

**Cause.** `auto_update: true` (= `policy: full`) upgraded the session
manager's own dependencies under the tunnel.

**Fix.** The fixture moved to `policy: security` with `exclude:
["kernel*"]`, the proven-survivable shape; a `full` policy on a large base
is still that risk. Look at packer's output for the provisioner that lost
the session.

**Date.** 2026-08-31.

**Where it was told.**
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the first item).

### A cloud RHEL image said it was not registered

**Symptom.** `This system is not yet registered` from
`subscription-manager`.

**Cause.** Cloud vendor RHEL images are RHUI or pay-as-you-go, not
subscription-managed.

**Fix.** The repo enablement is guarded on `subscription-manager
identity`; the bake prints `not subscription-registered (RHUI image):
using vendor repos as-is` and continues. If you expected subscription
repositories, register the image before the bake; the plugin does not.

**Date.** 2026-08-31.

**Where it was told.**
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the `subscription-manager` item).

### A downloaded rpm vanished under dnf update

**Symptom.** `Errno 2` on a downloaded rpm during `dnf update`, seen twice
live.

**Cause.** RHUI repositories flip their cache path mid-run when the point
release moves.

**Fix.** Every dnf update command reads `<cmd> || { sudo dnf clean all;
<cmd>; }`; a second `Errno 2` after the retry is a real repository
problem. Look at the packer output for the retried line.

**Date.** 2026-08-31.

**Where it was told.**
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the `Errno 2` item).

### apt could not get the lock on a freshly booted Debian

**Symptom.** apt lock timeouts on the first Debian bakes; `E: Could not
get lock /var/lib/dpkg/lock-frontend`.

**Cause.** A concurrent `unattended-upgrades` run on a freshly booted
Debian held the lock, and no wait was set.

**Fix.** Every `apt-get` command the plugin emits carries `-o
DPkg::Lock::Timeout=600`, so a bake waits up to ten minutes for the lock
rather than fail at once. A `Could not get lock` after that wait means
the other apt process ran longer than ten minutes; re-run the bake, and
if it recurs find what runs apt at boot on that vendor image.

**Date.** 2026-08-31 (the wait added 2026-09-25).

**Where it was told.**
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the "apt lock timeouts" item and the `Could not get
lock` row).

### Debian vendor images lacked curl and gnupg

**Symptom.** The OPA prerequisite failed on a Debian vendor image before
it could fetch the sftd repository key.

**Cause.** The image had neither `curl` nor `gnupg`.

**Fix.** The apt path of `base_image_prerequisites` installs them first;
the rpm path needs nothing beyond `rpm` and `yum`.

**Date.** 2026-08-31 (undated in the record; among the first bakes).

**Where it was told.**
[../packages/okta-opa-plugin/README.md](../packages/okta-opa-plugin/README.md)
"When it fails" ("Debian vendor images without `curl` or `gnupg`").

### Ansible fact gathering died on a Python the controller no longer supports

**Symptom.** Fact gathering died with "The module interpreter..." on the
first AWS bakes on RHEL 8.

**Cause.** The target's only Python was 3.6, which the controller's
ansible-core no longer supports.

**Fix.** An emitted `provisioner "shell"` installs a newer Python and pins
it at `/usr/local/bin/csis-ansible-python`, and `-e
ansible_python_interpreter=...` names it. A family with no
`python3.12`/`3.11`/`3.9` package and no `dnf` falls back to whatever
`python3` exists; check the family's Python against the ansible-core
support matrix before blaming the playbook.

**Date.** 2026-08-31 (before 2026-09-02).

**Where it was told.**
[../packages/ansible-plugin/README.md](../packages/ansible-plugin/README.md)
"When it fails" (the "fact gathering died" item).

### The bundle upload had no directory to land in

**Symptom.** `scp: /tmp/csis-mods: Not a directory` on the local bundle
upload.

**Cause.** Packer's `file` provisioner cannot create the destination
directory.

**Fix.** A `provisioner "shell"` with `mkdir -p /tmp/csis-mods` precedes
the `file` provisioner; the three bundle provisioners stay together, in
order. If the message returns, the shell provisioner before the upload
was removed or reordered.

**Date.** before 2026-09-16 (undated in the record).

**Where it was told.**
[../packages/packer-plugin/README.md](../packages/packer-plugin/README.md)
"When it fails" (the `scp: /tmp/csis-mods` item).

### packer fmt failed on a line containing a percent brace

**Symptom.** `Command failed after phase image-generation: packer (Return
code: 1)` at generation, with an HCL parse error naming an `inline` line
that held `rpm --qf '%{NAME}'`.

**Cause.** `${` and `%{` open packer's interpolation and directive syntax
inside string literals.

**Fix.** The packer plugin's `_quote()` and the bash plugin's
`_hcl_string` write `$${` and `%%{`; the line in `generated/` reads so.
Any provisioner line that reaches a build file through another path must
escape the same two sequences; `Invalid template directive` or `Invalid
template interpolation` on a line you wrote means the escape regressed.

**Date.** before 2026-09-16 (undated in the record).

**Where it was told.**
[../packages/packer-plugin/README.md](../packages/packer-plugin/README.md)
"When it fails" (the `packer fmt` item);
[../packages/bash-mod-plugin/README.md](../packages/bash-mod-plugin/README.md)
"When it fails" ("Found live, undated, in the sibling shell emitter").

### The S3 prerequisite needed unzip on a RHEL image

**Symptom.** The S3 prerequisite bake failed on RHEL-family images.

**Cause.** `unzip` is not installed there (`curl` is), and the AWS CLI
arrives as a zip.

**Fix.** The prerequisite installs `unzip` before fetching the zip.

**Date.** before 2026-09-16 (undated in the record).

**Where it was told.**
[../packages/tf-ebs-instance-plugin/README.md](../packages/tf-ebs-instance-plugin/README.md)
"Failures that have happened" (the "S3 prerequisite bake failed on
RHEL-family images" item).

### A builder-level package assertion failed the GCE bake

**Symptom.** The builder-level `tests: packages: [nfs-utils]` failed the
GCE bake.

**Cause.** `nfs-utils` is what the EFS prerequisite installs, and EFS never
runs on GCE; a builder-level assertion applies on every runtime.

**Fix.** Per-entry `tests` replace the builder's for that runtime; the
runtime's own assertions are declared on its entry.

**Date.** before 2026-09-16 (undated in the record).

**Where it was told.**
[../packages/default-os-plugin/README.md](../packages/default-os-plugin/README.md)
"When it fails" (the "builder-level `tests: packages: [nfs-utils]`"
item).

### Three defects in the bash builder before the current generation

**Symptom.** A bash item was recorded as `ansible-default` with no
content; any real bash item failed `packer validate`; and `scripts:`
files were dropped.

**Cause.** Every item resolved to the default mod builder (the lookup used
the field name `modifications`, not the item's `type`); the bash builder
wrote raw lines and an `exit 0` straight into the build file; and
`scripts:` was not a field.

**Fix.** Items resolve by `type`, the builder emits a `provisioner
"shell"` block, and `scripts:` is a field; two tests guard it. A comment
line outside a `provisioner "shell" {` block, or `exit 0` in a build
file, means this regressed.

**Date.** 2026-08-27.

**Where it was told.**
[../packages/bash-mod-plugin/README.md](../packages/bash-mod-plugin/README.md)
"When it fails" (the 2026-08-27 item).

### The example plugin's lifecycle leaked into every run

**Symptom.** An unexpected `notify` entry in run summaries and golden
diffs: every golden and gate run grew a `generated/notify/` directory and
a fifth lifecycle.

**Cause.** The dummy plugin's hooks registered `notify` unconditionally,
and a registered lifecycle joins `run --all`.

**Fix.** The lifecycle is opt-in behind `CSIS_DUMMY_LIFECYCLE`. If `notify`
appears in a run you did not ask for it in, the variable is set in that
shell.

**Date.** 2026-08-27.

**Where it was told.**
[../packages/dummy-plugin/README.md](../packages/dummy-plugin/README.md)
"When it fails" (the 2026-08-27 item).
