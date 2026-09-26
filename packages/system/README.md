# cs-image-system-system

The command-line host of cs-image-system. It installs one console script,
`cs-image-system`, that loads the plugins, reads a configuration tree and
drives the lifecycle runner, the state tools and the value tools of
`cs-image-system-base`. The package holds no builder logic of its own:
every command delegates to the base library or to a plugin.

Licensed under Apache-2.0. Requires Python 3.13 or later. Declared
dependencies ([`pyproject.toml`](pyproject.toml)): `cs-image-system-base`
(pinned to the same version), `typer`, `rich` and `PyYAML`. The entry point
is `cs_image_system.system.cli:app` (a Typer application); `python -m
cs_image_system.system` runs the same application through a wrapper that
prints `Error: <e>` and exits 1 on any exception the application lets
through.

Source: [`src/cs_image_system/system/cli.py`](src/cs_image_system/system/cli.py).

## Contents

- [Invocation and output](#invocation-and-output)
- [Global options](#global-options)
- [What the callback does before a command](#what-the-callback-does-before-a-command)
- [Commands](#commands)
- [Credentials](#credentials)
- [Commands the generated runner scripts call](#commands-the-generated-runner-scripts-call)
- [Exit codes at a glance](#exit-codes-at-a-glance)
- [Tests](#tests)
- [Prerequisites and integration](#prerequisites-and-integration)
- [Configuration reference](#configuration-reference)
- [What it tests and verifies](#what-it-tests-and-verifies)
- [When it fails](#when-it-fails)
- [Related](#related)

## Invocation and output

```text
cs-image-system [GLOBAL OPTIONS] <command> [ARGS]
cs-image-system --help
cs-image-system <command> --help
```

`-h` and `--help` both print help. Logs go to standard error through a
rich handler; standard output is reserved for machine-readable output (the
run summary JSON, the gid shim's JSON, a decrypted value, a materialized
path). A few one-line verdicts also go to standard output: `run` follows
its JSON with `Run <id> completed: ...`, `validate` prints `Validation
successful.`, `preflight` prints its `session:` lines there. Inside the
workspace, `just cli <args>` runs the CLI against the live configuration
root (`CSIS_CONFIG_ROOT`, a Justfile variable, not one the CLI reads).

## Global options

These are options of the top-level callback and come before the command
name. Which commands honour which is in the
[configuration reference](#configuration-reference).

| Option | Default | Meaning |
| -------- | --------- | --------- |
| `--root-dir PATH` | the current directory | The configuration root: the directory holding `cfg/`, `groups/`, `storages/`, `images/`, `instances/` and `meta-state/`. A command that loads the configuration changes into it (resolved) during the load and returns to the starting directory when the command ends; the value tools, `mask`, `materialize` and `preflight` only record it; `gate-plan`, `apply-check` and `identity export-gids` ignore it. |
| `--verbose / --no-verbose` | off | Log at `DEBUG`, for every command. With a configuration load, also writes the string-stage-rendered document to `YAML_DUMP.yaml` in the directory the command was started from (it is written before the change of directory). |
| `--dry-run / --no-dry-run` | `--dry-run` | Dry run: generation is complete and runner scripts are written, but deferred finalization commands (packer builds, tofu init/plan/gate/apply, system CLI steps) are enumerated, not executed. `--no-dry-run` executes them. The same flag governs `dispose image`, `lineage restamp` and `lineage relabel`, which report a plan under a dry run, and `run --migrate-state`, which a dry run refuses. `reencrypt` has a `--dry-run` of its own and ignores the global one. |
| `--overlay FILE` (repeatable) | none | A transient declaration file merged over the tree for this invocation only. `config:` keys override; named `instances:`/`storages:` (and other item) entries update or add; an entry with `undeclare: true` removes the tree's entry. A file that does not exist, is not a mapping, has a top-level key other than `config` and the item collections, or lists an entry without a `name` is refused before anything loads. The tree on disk never changes. |
| `--undeclare KIND:NAME` (repeatable) | none | Treat a declared tree entry as absent for this invocation, for example `instance:gce-test`. `KIND` is an item collection key (`instances`, `storages`, ...); the singular is accepted; anything else is refused before the load. |
| `--base-only` | off | Makes `build-all` and `generate` select the base-image lifecycle only. The configuration is still read in full. |
| `--only-providers` | | Retired (stage 67, 2026-09-26): it was recorded, split and warned about (`Only providers ... specified but configuration will still be read in full`), and read by nothing; `--only-runtime <rt>` is the runtime filter. Passing it is `No such option`. |

There is no global `--force` (stage 63). It was "Force execution even if
the system balks", stored on the context and read by nothing; it was
removed on 2026-09-25, and passing it is now refused by the CLI parser
with `No such option: --force` (exit 2). The overrides that do something
are named for what they override and stay: `run --force-bake`,
`gate-plan --allow-destroy`, and `test-mods --force` (a different,
command-level flag that re-tests mods that already passed).

## What the callback does before a command

The callback runs first for every invocation: it configures logging
(`--verbose`), remembers the directory the command was started from,
arranges to change back to it when the command ends, and then decides,
per command, how much to load:

| Commands | Before the command runs |
| ---------- | ------------------------- |
| `test`, `cleanup` | Nothing. They are retired names and exit 2. |
| `preflight` | Records the root (`--root-dir` or the current directory) and the resolved overlays. The command reads only the raw `cfg/*.yml` files for `runtime_builders:` (every file directly under `cfg/`, as the loader does, since stage 63 item 11) and `cfg/_config.yml` (and overlays' `config:`). No plugin loads, no configuration loads, no change of directory. |
| `gate-plan`, `apply-check`, `identity export-gids` | No configuration tree loads and every global option except `--verbose` is ignored. `identity export-gids` loads plugins on demand; `apply-check` reads only `cfg/_config.yml` (and its own `--overlay` files) as text. |
| `encrypt`, `decrypt`, `reencrypt`, `public-safe`, `materialize`, `mask` | Records the configuration root (`--root-dir` or the current directory). No plugin loads, no configuration loads, no change of directory. `encrypt` and `reencrypt` read `encryption.recipients` from `cfg/_config.yml` as text; `public-safe` reads `public_safe.allow` the same way. |
| every other command | Loads plugins. For `run` and `state ...` it first prints the credential session lines read from the raw tree and exits 1 when a session has expired. Then it reads the whole configuration (`read_config_and_transform`): the string stage, decryption of every `ENC[age:...]` value, structuring, builder construction and item reading, with overlays and undeclarations applied. The load changes the process directory to the (resolved) configuration root and REPLACES the Typer context object; the callback then records the invocation directory again (`invoked_cwd`) and the `--base-only` flag on the new object, so a command that runs from a terraform root (`state-migration`, `prune-attachments`) still knows where it was started (found live 2026-09-23; see [When it fails](#when-it-fails)). A load that raises prints `Error reading config file : <e>` on standard error and re-raises: a traceback, exit 1. |

Loading the configuration constructs every runtime builder, and the cloud
runtime plugins validate their networking against the cloud during that
step. See [Credentials](#credentials).

## Commands

### `run [LIFECYCLES...]`

Run one or more lifecycles of the meta-workflow in declared order. The
lifecycle names are `identity`, `storage`, `base-image`, `instance-image`,
the registered `release` and `retention`, or `all`. Aliases: `id`,
`storages`, `base-images`, `base`, `instance-images`, `instances`. Names
resolve in declared order, never in argument order. The hook plugins that
register `release` and `retention` are loaded before the names resolve
(found live: a fresh process once resolved `--all` to the four built-ins
because the hooks loaded only inside the run).

| Option | Default | Meaning |
| -------- | --------- | --------- |
| `--all` | off | Every lifecycle, registered ones included. |
| `--apply / --no-apply` | `--apply` | After generation, execute the runner scripts that exist. Under a dry run they are enumerated. |
| `--commit / --no-commit` | `--no-commit` | Make the meta-state commit (read-models, pins, lineage, launch parameters, generated IaC) in the configuration repository after the run. A root outside a git repository, or a gitignored path, is skipped with a warning, never an error. |
| `--state-query / --no-state-query` | `--state-query` | First ask reality (read-only) and write `generated/state-report.json`; validation refuses to run on hard drift. `--no-state-query` keeps the existing report. |
| `--only NAME` (repeatable) | none | Restrict the bake surface to the named image(s), as `<image>` or `<image>@<runtime>`. Sources, build blocks and bake steps exist for nothing else; terraform roots are untouched. Unknown names fail the run (exit 1, the summary's `error` names them and the known names). `--only none` bakes nothing. |
| `--only-runtime NAME` | none | Restrict the bake surface to every image baked on that runtime. Terraform roots of other runtimes are not generated or planned. |
| `--apply-runtime NAME` | none | Let the storage and instance roots of that runtime apply, as if `apply_storage` and `apply_instances` listed it. Implies `--only-runtime NAME` unless `--only` or `--only-runtime` is given. The generated `apply-check` steps carry it. |
| `--force-bake NAME` (repeatable) | none | Bake the named image(s) even when current; `all` forces every image in the run's surface. |
| `--allow-unscoped-bakes` | off | Let a `--no-dry-run` run bake on runtimes outside its apply scope. Without it such a run refuses before any bake. |
| `--migrate-state NAME` (repeatable) | none | MOVE the named terraform workspace's state to the backend it now resolves to. Needs `--no-dry-run`: a dry run exits 2 before anything loads further. The root's runner then carries `state-migration begin`, `init -migrate-state -force-copy`, `plan -detailed-exitcode`, the gate and `state-migration finish` (see [the runner scripts](#commands-the-generated-runner-scripts-call)). There is deliberately no flag that merely proceeds past the state-location guard. |

The run summary is printed to standard output as JSON, followed by one
`Run <id> completed: <lifecycles>` line. Exit 0 on success. Exit 1 when
the run failed (validation, generation, apply or commit): the summary
carries `ok: false` and `error`, and `Run <id> FAILED: <error>` goes to
standard error. Exit 2 for an unknown lifecycle name, no lifecycle
selected, an unknown `--apply-runtime` / `--only-runtime` runtime, or
`--migrate-state` under a dry run.

### `build-all`

Alias: `run` every lifecycle with `--apply` and `--no-commit`; with
`--base-only`, the base-image lifecycle only. Exit codes as for `run`.

### `generate`

Alias: `run` every lifecycle with `--no-apply` and `--no-commit`; with
`--base-only`, the base-image lifecycle only. Exit codes as for `run`.

### `validate`

Run every validation rule (unique names, executables present and
version-compliant, lineage policies, every registered validator) and
generate nothing. Prints each error to standard error as ` - <error>`,
then `Validation failed with N error(s).`. Exit 0 when clean (`Validation
successful.` on standard output), exit 1 with errors.

### `upgrade KIND NAME [--to BUILD] [--runtime RT]`

Move exactly one pin. `KIND` is `instance` or `image`; `NAME` is the
instance or the instance image. `--to` names the target build id (default:
the head of the relevant series in lineage). `--runtime` selects which
runtime's pin moves for an image baked on several runtimes. For an
instance the move is understood as a destroy-and-recreate: the next
instance-image run plans a whitelisted replacement. Prints `<kind> <name>:
pin moved <from> -> <to>`. Exit 1 on any error (unknown kind, unknown name,
unknown build, ambiguous runtime, already pinned there, a build baked on
another runtime), with the `upgrade: ...` message on standard error.

### `preflight [--strict]`

Report the credential sessions the configuration's runtimes need (AWS SSO
profiles or static keys, GCP application default credentials), read from
the local caches without loading the configuration and without printing a
credential value. One `session:` line per credential source goes to
standard output (red when absent or expired, yellow when it expires within
the window). Exit 0 when every session is present (`preflight: every
session present` on standard error); exit 2 when no runtime is declared,
when a session is absent or expired, or when a credential-shaped
environment variable (`AWS_*`, `GOOGLE_*`, `OKTA_*`, `TF_VAR_*`, `CSIS_*`)
is set but EMPTY (reported by name, never by value); exit 1 with
`--strict` when a session expires within
`config.preflight.expected_run_minutes` (default 30). A session is expired
when its minutes left are known and zero or fewer; exactly zero minutes
left counts as expired since stage 63 (until 2026-09-25 the test read
`0.0` as one minute left), and a session whose expiry cannot be read is
never called expired.

### `encrypt [VALUE] [--file FILE ...] [--field NAME ...]`

Encrypt to the tree's `encryption.recipients`. With a `VALUE` (or `-` for
standard input) prints one `ENC[age:...]` marker. With `--file` and at
least one `--field`, encrypts in place every scalar under the named keys
and every element of a block list under them, preserving every other byte,
and reports counts on standard error. Needs no identity. Exit 2 when
`--file` is given without `--field`, or neither a value nor `--file`. A
root whose recipients cannot be read -- `cfg/_config.yml` is missing or
unreadable, or declares no `encryption.recipients` -- prints
`encrypt: <reason>` on standard error and exits 1, for example
`encrypt: <root>/cfg/_config.yml: no encryption.recipients declared`
(stage 63; until 2026-09-25 it ended in a traceback).

### `decrypt [MARKER] [--json] [--file FILE ...] [--field NAME ...]`

Decrypt one marker (or `-` for standard input) with the identity in
`CSIS_CONFIG_IDENTITY` and print the plaintext without a trailing newline.
With `--json` it speaks the terraform `external` data source protocol:
reads a JSON object of strings on standard input and prints it with every
marker decrypted and every other value passed through. With `--file` and
at least one `--field` it is the inverse of `encrypt --file`: every marker
under the named keys is written back in clear, in place, every other byte
preserved, counts on standard error. Exit 1 (`decrypt: <reason>`) on a bad
marker, a missing identity, a value none of the identities can open, a
`--json` input that is not an object, or no marker at all; exit 2 when
`--file` is given without `--field`.

### `reencrypt [--dry-run]`

Rotate every marker in every `*.yml` / `*.yaml` under the root (skipping
`.git` and `generated`) to the current `encryption.recipients`: decrypt
with `CSIS_CONFIG_IDENTITY`, re-encrypt, write in place. Nothing is
written unless every value opens. `--dry-run` (the command's own flag,
not the global one) reports what would change. Exit 1 (`reencrypt:
NOTHING written -- <file>: <reason>`) when a value cannot be opened, and
exit 1 with `reencrypt: NOTHING written -- <reason>` when the recipients
or the identity cannot be read (no `cfg/_config.yml` or no
`encryption.recipients`; `CSIS_CONFIG_IDENTITY` unset or not a usable
identity). Both are checked before any file is read (stage 63; until
2026-09-25 those two ended in a traceback).

### `mask [--min N]`

Print a `::add-mask::` line for every value the configuration carries
encrypted, so a GitHub Actions log never shows one. It opens every
`*.yml` / `*.yaml` under the root (skipping `.git`, `generated` and
`_private`) with `CSIS_CONFIG_IDENTITY` and prints every line of every
plaintext at least `--min` characters long (default 8; a short common
word would mask unrelated log text). A file that cannot be decrypted is
skipped silently (a refusal is `validate`'s to report), so with no
identity the command prints nothing and exits 0. Exit 1 on an error
(`mask: <reason>`). The CI jobs run it (`just cli mask`) before the
first step that touches the live tree.

### `materialize SOURCE [DESTINATION]`

Copy a generated root (or one file) into the private mirror
`<root>/_private/<the same relative path>` with every `ENC[age:...]`
marker replaced by its plaintext, and print where it landed (no trailing
newline, so a script can `cd "$(...)"`). `SOURCE` is relative to the
current directory and, without `DESTINATION`, must lie under the
configuration root, whose `generated/` directory name the mirror replaces
at the same depth. The copy is incremental (what the tools wrote in the
mirror survives; files the emission no longer has are removed), the
provider lock file is synced back, and the root's `.gitignore` gains
`_private/` when the root is a git repository. Needs `CSIS_CONFIG_IDENTITY`
when any marker is present; loads no configuration. Exit 1 (`materialize:
<reason>`) on a missing source, a source outside the root, an unreadable
identity or a value that cannot be opened. This is the wrapper every
deferred command in a runner script runs through.

### `public-safe [--staged] [--tree PATH] [--config FILE]`

Scan a tree (tracked plus untracked non-ignored files; default `--root-dir`
or the current directory) or, with `--staged`, the git index, for material
that must not be public: keys, tokens, PEM bodies, an age identity, a
service-account file, plans and state by name; addresses and long tokens
outside prose and tests. `--config` names the `_config.yml` whose
`public_safe.allow` applies (default: the tree's, or the frozen fixture's
inside the system repository). Prints every finding. Exit 0 when clean;
exit 1 with findings (`public-safe: REFUSED -- N finding(s) in M file(s)
(<scope>); allow a value by decision in cfg/_config.yml public_safe.allow,
never by silence`); exit 2 when `--staged` is used outside a git
repository.

### `test-mods [--image NAME ...] [--force] [--strict]`

Run every modification of the instance images against a throwaway local
container, twice (apply, then idempotence), and record the results in
`meta-state/mod-tests.yaml`. `--image` restricts to named images;
`--force` re-tests mods that already passed; `--strict` fails when tests
are skipped (no docker). Results are printed as JSON, one `FAIL
<image>/<mod>: rc=<a>/<b> idempotent=<bool> <detail>` line per failure on
standard error. Exit 1 on a failed or non-idempotent mod, or on skips
with `--strict`.

### `release [IMAGE] [--build ID] [--model NAME] [--note TEXT] [--runtime RT] [--declared]`

Mark a tested build as released for a model (default `default`). Without
`--build` the series head is used (`--runtime` picks which runtime's
head). Prints the release entry as JSON. With `--declared`, releases every
image's verified head per its declared `release: {model}`; this is the
step the release runner script invokes, and when nothing qualifies it
prints `release --declared: nothing to release (no verified head without a
current release)` and exits 0. Exit 2 when neither an image nor
`--declared` is given; exit 1 when no build is recorded (`release: no
build of '<image>' recorded in lineage`) or the release is refused
(`release refused: <reason>`: not in lineage, another series, no in-bake
verification, a failed or missing mod test under `require_mod_tests`, no
or failed post-bake tests under `require_image_tests`).

### `gate-plan [PLAN_JSON] [--planfile FILE] [--tofu BIN] [--allow-destroy ADDR ...] [--require-unmounted INSTANCE:STORAGE ...]`

The apply gate. Reads a plan as JSON (the output of `tofu show -json`) or
converts a saved plan file locally with `<tofu> show -json` (default
binary `tofu`). Every planned destroy must match an `--allow-destroy`
address exactly or as a prefix followed by `.` or `[`. Every
`--require-unmounted` pair needs a successful unmount receipt under
`./unmount-receipts` (checked first). Exit 0 when the plan passes (`Plan
passes the apply gate.`). Exit 3 on a destroy that is not whitelisted
(`DESTROY NOT WHITELISTED: <address>`, one per violation), a stale plan
file (`STALE PLANFILE: <reason>`: older than the newest `.tf` under its
root, or missing), or a missing unmount receipt (`DETACH NOT UNMOUNTED:
<pair> has no successful unmount receipt`). Exit 2 when neither a plan nor
`--planfile` is given. The staleness check applies to `--planfile` only.

### `apply-check --lifecycle NAME [--config-root PATH] [--root NAME] [--root-alias NAME ...] [--overlay FILE ...] [--apply-runtime RT]`

The execution-time apply guard. Re-reads `config.apply_<lifecycle>` from
`cfg/_config.yml` now (walking up from the working directory to the nearest
directory holding it unless `--config-root` is given), applies the
`config:` keys of every `--overlay`, and honours `--apply-runtime` for the
`storage` and `instances` lifecycles (the flag becomes `[<rt>]`). `--root`
and `--root-alias` let a list-valued flag be checked for one terraform
root: the root's builder name or any alias (its runtime) must be listed.
Exit 0 when the flag allows the apply (`apply_<lifecycle> allows [root
'<name>']; proceeding.`); exit 3 when it does not (`apply_<lifecycle> is
<value> NOW in <path>/cfg/_config.yml [for root '<name>']`, then "this
runner script was generated when it allowed the apply; not applying"),
when no `cfg/_config.yml` is found, or when an overlay file is gone.

### `identity export-gids`

The gid shim: a terraform `data "external"` program. Reads the query (a
JSON object of strings: `identity_type`, `groups` as a comma-separated
list, and provider fields such as `org`, `team`, `api_host`) on standard
input, asks the identity plugin registered for that type, and prints
`{group: gid}` as JSON. An empty `groups` answers `{}`. Credentials come
from the environment, never from the query. Exit 1 (`export-gids:
<reason>`) on any error, including a query without `identity_type`, a type
no plugin registers, missing credentials, and a group the provider cannot
answer for.

### `runtime describe NAME`

Print configuration-driven facts about a runtime as JSON: project or zone,
ephemerality, retention, the images baked there, the declared storages with
their cloud names, the instances, its `builders` (image, storage and
instance builders bound to it) and its `emission` (the
`<lifecycle>/<builder>` directories under `generated/` that hold its
emission and exist now -- what a run scoped to another runtime leaves
untouched, and what `just runtime-unchanged` compares across records).
Exit 1 for an unknown runtime (`runtime describe: unknown runtime '<name>';
known: [...]`).

### `empty --runtime NAME`

Assert the runtime holds nothing beyond its declared storages (no
instances, no custom images other than released builds, no other disks or
buckets) and that a strict state query agrees (the report is rewritten).
Names every leftover (`empty: <kind> still present on <rt>: <names>`) and
every real drift line. Exit 2 when the runtime cannot answer (unknown
runtime, or a runtime whose plugin cannot list its inventory); exit 1 on
leftovers or real drift; exit 0 when empty.

### `lineage restamp --runtime RT [--series NAME ...] [--commit/--no-commit]`

Record the current input fingerprint on series heads whose recorded one
predates the current fingerprint recipe, keeping the previous value, and
re-tag the cloud image to match. Prints the plan as JSON. Under the global
dry run it only reports (`restamp (dry run): N head(s) would be restamped;
pass --no-dry-run`). `--commit` makes the meta-state commit. Exit 1 on
error (`restamp: <reason>`, for example an unknown runtime).

### `lineage relabel --runtime RT [--build ID ...]`

Re-tag cloud images whose lineage tags disagree with their record, from
the record. No meta-state change. Prints the plan as JSON. Under the
global dry run it only reports. Exit 1 on error or when an image could not
be retagged (`relabel: could not retag [<ids>]`).

### `unmount storage --instance NAME --storage NAME --mount-point PATH [--workdir DIR] [--confirm] [--timeout SECONDS]`

Unmount a storage on a launched instance through the runtime's session
mechanism and write the receipt that `gate-plan --require-unmounted`
checks, under `<workdir>/unmount-receipts` (default: the current
directory). `--confirm` runs nothing and records the operator's assertion
instead (the operator's name from `USER` or `USERNAME`). `--timeout`
defaults to 300. Prints the receipt as JSON. Exit 1 on error (`unmount:
<reason>`: an undeclared instance, an unconfigured runtime, a failed
unmount).

### `verify instance NAME [--expect-build ID] [--timeout SECONDS] [--record-only]`

Run the runtime's verification of a launched instance (serial console,
booted image, data disks, and the image's `tests.post_bake`) and record the
verdict in `meta-state/verifications.yaml` (and `image-tests.yaml`).
`--expect-build` defaults to the instance's pin or launch record;
`--timeout` defaults to 600. Prints the record as JSON. Exit 1 on failure,
which stops a runner script and leaves an ephemeral instance standing.
With `--record-only` a failed verdict is recorded, `instance <name> FAILED
verification (recorded; teardown proceeds)` is printed, and the exit is 0,
so a teardown can proceed. Exit 1 (`verify: <reason>`) for an undeclared
instance or an unconfigured runtime.

### `verify assert NAME`

Exit 1 when the instance's last recorded verification failed (or none is
recorded), else 0.

### `verify login [NAMES...] [--runtime RT] [--timeout SECONDS] [--record-only]`

Log into each standing instance (every launched, non-ephemeral instance,
or the named ones, or those on `--runtime`) over `sft ssh` -- as the OPA
workload when `OPA_TOKEN` is set, else as the enrolled client -- after
checking that exactly one server is registered under the hostname and
that the client resolves it, and record the verdicts in
`meta-state/login-proofs.yaml`. A stopped machine, or one whose group
names no workload connection and role, is skipped (`login SKIPPED for
<names> (nothing proved)`), never started. `--timeout` (default 120) is
per client call. Prints the records as JSON. Exit 1 on a failed login or
an error (`verify login: <reason>`); with `--record-only` the verdicts are
recorded and the exit is 0.

### `workload describe [--env]`

What CI's workload login needs from the configuration: for every group
builder that names the team's workload connection and role, the builder,
`connection`, `role`, `team` and `api_host`, as JSON. Nothing secret.
`--env` prints shell exports (`OPA_WORKLOAD_CONNECTION`,
`OPA_WORKLOAD_ROLE`, `SFT_TEAM`, `OPA_ADDR`) for the first such builder,
which `just ci-login-proof` evaluates; exit 2 when none names one. This
command loads the configuration (it is deliberately not under `identity`,
whose group is exempt from loading).

### `forget instance NAME`

Drop a destroyed instance's pin and launch parameters from meta-state,
recording the correction as an `op: forget` entry in `pins.yaml`. A
decommission through the gate does this itself; this is for records that
outlived their instance. Exit 2 while the instance is still declared
(`forget: instance '<name>' is still declared -- undeclare it and let its
destroy apply`); exit 0 with `forget: nothing recorded for instance
'<name>'` when there is nothing to drop.

### `dispose image [BUILD_ID ...] [--runtime RT] [--all] [--retention] [--commit/--no-commit]`

Delete recorded images from their runtime and drop their lineage record and
any image pin at them in one operation. `--runtime` restricts to builds
baked there; with `--all`, every one of them. `--retention` applies the
declared retention instead: image `retention.keep`, runtime
`retention_keep`, everything on an ephemeral runtime. Refuses unrecorded
builds and builds an instance is pinned to or launched from. Prints the
plan as JSON. Under the global dry run nothing is deleted (`dispose (dry
run): N image(s) would be deleted; pass --no-dry-run`). Exit 1 on error
(`dispose: ...`: `--all` without `--runtime`, no build and no selector, an
unknown runtime, a build baked elsewhere, a build that records an
unconfigured runtime).

### `state query [--strict] [--json]`

Ask every plugin for its provider's view of what the system manages
(images by lineage tags, storages by name, groups by gid), diff it against
meta-state, and write `generated/state-report.json` (`state report written
to <path>` on standard error). Prints the rendered report, or JSON with
`--json`. Touches nothing. Exit 1 on hard drift; with `--strict`, also on
any `missing`, `foreign` or `changed` drift (`stale` is reported only) and
when a credential session expires within the expected run length (the
sessions read from the loaded runtimes, the same reading the callback
printed).

### `state import [--images/--no-images] [--storages/--no-storages]`

Adopt foreign artifacts (tagged as ours, unrecorded) into meta-state:
images into lineage, storages into storage-state. Writes meta-state only,
never the cloud, the identity provider or terraform state, then rewrites
the state report. Prints `imported: <line>` per adoption or `nothing
foreign to import`. Exit 0.

### `state-migration ACTION --workspace NAME --run ID [--tofu BIN] [--backend-config FILE] [--location LOC]`

One step of a state migration or a state backup, emitted into a root's
runner; never a by-hand command. It runs FROM the root the runner entered
(the private mirror), which is why the callback records the invocation
directory: the configuration load changes directory to the root and the
step must act where it was started. `ACTION` is:

- `begin`: write the previous location from meta-state beside the root as
  `<workspace>.tfbackend.previous.hcl`, refuse a non-empty new location
  that holds another lineage, recognise a move that already happened,
  pull the old state to `<workspace>.backup-<run>.tfstate` (kept), leave
  the root initialised against the previous location and write
  `<workspace>.state-migration.json`. `--backend-config` (the root's
  `.tfbackend.hcl`, the NEW location) is required; `--location` is that
  location as its type renders it. Exit 2 without `--backend-config`,
  when the file does not exist, or when meta-state records no location
  for the workspace; exit 1 when an init or state pull fails or the new
  location holds someone else's state.
- `finish`: record the move (from, to, when, serial, backup) in
  meta-state and move the workspace's location record. Exit 2 when
  `begin` did not run (no progress file).
- `backup`: pull the state at the root's location and keep it as
  `<root>/_private/state-backups/<workspace>.backup-<run>.tfstate`, before
  a pre-plan `state rm`. Exit 1 (and the runner stops) when the directory
  is not an initialised terraform root, the pull fails, or the location
  holds no state: a `state rm` is due, so there is no honest empty case.

Any other action exits 2. `--run` is the id of the run that emitted the
step; `--tofu` defaults to `tofu`.

### `prune-attachments --builder NAME --run ID [--tofu BIN]`

One step of an identity root's runner, between its `init` and its `plan`,
in the initialised root: list terraform state, keep every membership
attachment the declaration still has, ask the identity provider about
each dropped one, take a `state-migration backup`, and `state rm` only the
attachments the provider no longer holds. A silent or unreachable provider
removes nothing (the plan decides). Exit 2 when no group builder has that
name; exit 1 when `state list`, the backup or a `state rm` fails (the
runner stops before its plan). Never a by-hand command.

### `identity-attributes [--probe] [--dry-run-apply] [--apply] [--json]`

Show the identity attributes plan written by the identity lifecycle (or
compute it), probe the provider read-only with `--probe`, and preview an
apply with `--dry-run-apply` (one `would set:` line per change, or
`attributes already match`). Writing is disabled: `--apply` exits 4
whenever there is a change to write (`writing identity attributes is
disabled (DESIGN Q7 not confirmed); N change(s) were NOT applied`), and no
code path writes. Exit 3 when the provider reports attribute conflicts.
`--json` prints the plan as JSON.

### `test`, `cleanup`

Retired names. Each prints the commands that replace it (`test-mods` and
`verify instance`; the retention lifecycle and `dispose image`) and exits 2
without loading anything.

## Credentials

| Needs | Commands |
| ------- | ---------- |
| Nothing | `preflight` (reads local caches only), `gate-plan`, `apply-check`, `public-safe`, `encrypt` (recipients are read from `cfg/_config.yml` as text), `test`, `cleanup`. |
| The age identity in `CSIS_CONFIG_IDENTITY` only | `decrypt`, `reencrypt`, `mask`, `materialize` (when a marker is present). |
| Identity-provider credentials from the environment, and plugins installed | `identity export-gids`. |
| The age identity when the tree holds encrypted values, and live credentials for every declared cloud runtime | Every command that loads the configuration: `run`, `build-all`, `generate`, `validate`, `upgrade`, `test-mods`, `release`, `runtime describe`, `empty`, `lineage restamp`, `lineage relabel`, `unmount storage`, `workload describe`, `verify instance`, `verify login`, `verify assert`, `forget instance`, `dispose image`, `state query`, `state import`, `state-migration`, `prune-attachments`, `identity-attributes`. Loading constructs every runtime builder, and the cloud plugins validate networking against the cloud in that step. `run` and `state` print the session lines first and exit 1 on an expired session. |

Beyond loading, `test-mods` needs a local `docker`; `verify login` needs
`sft` (and `OPA_TOKEN` to log in as the workload); `verify instance`,
`unmount storage`, `dispose image`, `lineage relabel`, `empty`,
`prune-attachments`, `state query` and `state import` call the cloud or
the identity provider; `state-migration` and `prune-attachments` run
`tofu` against the root's state backend; a real `run` executes packer and
tofu with their own credentials.

## Commands the generated runner scripts call

A run writes `generated/<lifecycle>/run-<lifecycle>.sh` per lifecycle
with deferred work and `generated/final_execution.sh`, which runs each
script that exists. The scripts call back into this CLI by the bare name
`cs-image-system`, so it must be on the `PATH` of whoever runs them
(`just` and `uv run` provide it). Every deferred command that has a
working directory is wrapped as

```sh
( cd "<root under generated/>" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && <command> )
```

so the command runs in the private mirror of its root, where the
ciphertext the committed emission carries has been replaced by plaintext.
The commands themselves:

| Command line | Emitted where |
| -------------- | --------------- |
| `cs-image-system gate-plan --planfile tfplan --tofu <tofu> [--allow-destroy ADDR ...] [--require-unmounted PAIR ...]` | After every terraform root's `plan -out=tfplan`, in the identity, storage and instance-image runners. |
| `cs-image-system apply-check --lifecycle <identity\|storage\|instances> [--root NAME --root-alias RT] [--overlay FILE ...] [--apply-runtime RT]` | Just before `tofu apply tfplan`, only when the root is allowed to apply. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] prune-attachments --builder <group builder> --tofu <tofu> --run <run id>` | Every identity group root, after its `init` and before its `plan`. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] state-migration backup --workspace <root> --tofu <tofu> --run <run id>` | An identity group root whose runner carries a pre-plan `state rm` (a group newly declared `unmanaged: true`), after `init` and before the `rm`. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] state-migration begin --workspace <root> --tofu <tofu> --backend-config <root>.tfbackend.hcl --location <type>://... --run <run id>` and, after the gate, `... state-migration finish --workspace <root> --run <run id>` | A root named by `run --migrate-state`: `begin` before its `init -input=false -migrate-state -force-copy`, `finish` after `gate-plan`; the plan in between carries `-detailed-exitcode`. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] release --declared` | The release runner, when an image declares `release:`. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] dispose image --retention [--runtime RT]` | The retention runner, when retention or an ephemeral runtime is declared; `--runtime` when the run was scoped to one. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay <config-only overlays> ...] run storage --only none --no-state-query --no-commit [--apply-runtime RT]` | The retention runner, for transient overlay storages on an ephemeral runtime; the overlays that declared them are left out so the storages are undeclared there and destroyed through the gate. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] verify instance NAME [--record-only]` | The instance-image runner, after an ephemeral instance's launch applied (`--record-only` under the `teardown` failure policy). |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] unmount storage --instance NAME --storage NAME --mount-point PATH --workdir DIR` | The instance-image runner, before a plan that detaches a storage. |
| `cs-image-system identity-attributes --probe --dry-run-apply` | The identity runner, after the apply, when users or groups declare attributes. Emitted WITHOUT `--root-dir`; the command loads the configuration from the directory it runs in, which is the root's mirror (see [When it fails](#when-it-fails)). |

Two more are not script lines but programs terraform runs at plan time:
`cs-image-system identity export-gids` is the `data "external"` program in
an identity root that needs gids by query, and `cs-image-system decrypt
--json` is the `data "external" "sensitive"` program in every root that
references an encrypted value. Both read their query on standard input and
answer on standard output, which is why logs go to standard error.

`"$CSIS_ROOT"` is defined at the top of each runner script as the
configuration root relative to the script, so a committed script names no
absolute path. The `--run <run id>` the state steps carry is the id of the
run that generated the script (the run-start timestamp with every
separator replaced by `_`), not of the process that executes the step.

## Exit codes at a glance

| Code | Meaning |
| ------ | --------- |
| 0 | Success. |
| 1 | The operation failed or was refused: a failed run, validation errors, a refused release, a failed verification or login, hard drift, a value that cannot be decrypted or materialized, a public-safe finding, an expired session before a load, a failed load (a traceback), a `state-migration`/`prune-attachments` step that failed (the runner stops). |
| 2 | Usage: unknown lifecycle or runtime, nothing selected, a missing argument, a retired command, `--migrate-state` under a dry run, `public-safe --staged` outside git, `preflight` with an absent or expired session, an empty credential variable or no runtimes, `empty` on a runtime that cannot answer, `forget instance` on a declared instance, `workload describe --env` with nothing named, a `state-migration` step without its inputs, `prune-attachments` for an unknown builder. |
| 3 | A gate refused: `gate-plan` (destroy not whitelisted, stale plan file, missing unmount receipt), `apply-check` (flag off, no `_config.yml`, overlay gone), `identity-attributes` provider conflicts. |
| 4 | `identity-attributes --apply`: writing attributes is disabled. |

## Tests

[`tests/test_cli_dry_run.py`](tests/test_cli_dry_run.py) pins the dry-run
contract: on by default and toggled by `--dry-run/--no-dry-run`. The CLI is
exercised end to end by the workspace suite against the frozen fixture at
[`tests/fixtures/config`](../../tests/fixtures/config), whose emission is
pinned under [`tests/fixtures/v2_golden`](../../tests/fixtures/v2_golden):
[`test_v2_gate7_headless.py`](../../tests/test_v2_gate7_headless.py) (the
whole workflow through `run --all`, the aliases, the exit codes of `run`,
`validate` and `gate-plan`, the gid shim's pure-JSON standard output),
[`test_v2_justfile_contract.py`](../../tests/test_v2_justfile_contract.py)
(`preflight`), [`test_v2_hygiene_five.py`](../../tests/test_v2_hygiene_five.py)
(`state-migration backup` from the directory the runner entered),
[`test_v2_encrypted_values.py`](../../tests/test_v2_encrypted_values.py)
and [`test_v2_emit_by_reference.py`](../../tests/test_v2_emit_by_reference.py)
(`encrypt`, `decrypt`, `decrypt --json`),
[`test_v2_scoped_runs.py`](../../tests/test_v2_scoped_runs.py),
[`test_v2_gce_cycle.py`](../../tests/test_v2_gce_cycle.py) and
[`test_v2_runtime_facts.py`](../../tests/test_v2_runtime_facts.py)
(`apply-check`), [`test_v2_detach.py`](../../tests/test_v2_detach.py)
(`gate-plan --require-unmounted`),
[`test_v2_decommission.py`](../../tests/test_v2_decommission.py)
(`forget instance`), [`test_v2_post_bake_tests.py`](../../tests/test_v2_post_bake_tests.py)
(`release`), [`test_v2_defects_dead.py`](../../tests/test_v2_defects_dead.py)
(stage 63: `--force` is `No such
option`, `encrypt` without recipients is a message, a zero-minute session
is expired). [`tests/test_docs_contract.py`](../../tests/test_docs_contract.py)
holds this README to the four-section contract below and checks every
relative link in it.

## Prerequisites and integration

Everything this package needs exists outside it; it creates none of it.

**Python 3.13 and the installed workspace.** The console script is a
Python entry point; `just init` (`uv sync`) installs it into the
workspace's `.venv`. Whoever runs a generated runner script, and terraform
itself when it runs `decrypt --json` or `identity export-gids`, needs
`cs-image-system` on `PATH`: `just` and `uv run` provide that; a hand
`tofu plan` in a generated root needs the venv on the path. The base
library is pinned to the same version in
[`pyproject.toml`](pyproject.toml); `typer`, `rich` and `PyYAML` are the
only other declared dependencies.

**The plugins.** The CLI has no builder of its own; every model and
builder comes from a plugin discovered through the
`cs_image_system.plugins.<type>` entry points, and the `release` and
`retention` lifecycles (plus every validator and recorder hook) from the
`cs_image_system.plugins.hooks` group. The workspace pins all sixteen. A
missing runtime plugin surfaces at load as `No runtime providers
configured.` or `<kind> builder '<type>' specified for '<name>' not
configured`; a missing hook plugin makes `run release` an unknown
lifecycle.

**A configuration tree.** Found through `--root-dir` (else the current
directory): `cfg/_config.yml`, `cfg/runtime-builders.yml` and the other
`cfg/*.yml`, the item collections and `meta-state/`, as
[docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) describes them. Every
load writes under `<root>/generated/` (or the tree's
`generation_directory`), `<root>/meta-state/` and, at execution,
`<root>/_private/`. The live tree is the sibling
`cs-image-system-testconfig` checkout; the tests use the frozen fixture.

**Credentials, all from the environment or the local caches.** The CLI
prints the names of what it needs and never a value.

- `CSIS_CONFIG_IDENTITY`: the age identity (an `AGE-SECRET-KEY-1...`
  string, an identity file, or a directory of `*.age-identity` files) that
  opens every `ENC[age:...]` value. Read by every configuration load and by
  `decrypt`, `reencrypt`, `mask` and `materialize`. Operators keep theirs
  under `~/.config/cs-image-system/age/`; CI's is a repository secret; the
  workspace's `.envrc` exports it (the tool shell has no direnv: `source
  .envrc` in a subshell or set it inline).
- AWS: the profile each runtime names (`profile` or
  `credentials.profile_name` in `cfg/runtime-builders.yml`, else
  `AWS_PROFILE`), whose SSO token `preflight` and the `run`/`state`
  callback read from `~/.aws/sso/cache` (`CSIS_AWS_DIR` overrides the
  `~/.aws` directory); or static `AWS_ACCESS_KEY_ID` (with no profile
  named), which has no readable expiry. An expired SSO session refuses
  `run` and `state` before the load; every other loading command dies
  inside the AWS networking validation instead.
- GCP: Application Default Credentials at
  `GOOGLE_APPLICATION_CREDENTIALS` or
  `~/.config/gcloud/application_default_credentials.json`; only their
  presence is read.
- The identity provider: `TF_VAR_<team>_key` / `TF_VAR_<team>_secret`
  (the team name with non-alphanumerics replaced by `_`), or
  `OKTAPAM_KEY` / `OKTAPAM_SECRET`, for `identity export-gids`, the state
  query and `prune-attachments`; `OKTA_API_*` for the okta provider at
  plan time; `OPA_TOKEN` for `verify login` as the workload. These are the
  identity plugin's contract ([okta-opa-plugin](../okta-opa-plugin/README.md)).
- The whole environment is exposed to the configuration's templates as
  `ENV` during the load, so a `{{ ENV['X'] }}` in the tree reads any
  variable.

**Tools.** `tofu` (the binary the runner passes as `--tofu`, default
`tofu`) for `gate-plan --planfile`, `state-migration` and
`prune-attachments`; `docker` for `test-mods`; `sft` for `verify login`;
`git` for `run --commit` and `public-safe --staged`; `packer`, the cloud
CLIs and the ansible tools as `cfg/executables.yml` declares them, checked
by `validate` and by every run. The `age` implementation is a Python
dependency of the base library, not a binary.

**Network.** Every configuration load validates each cloud runtime's
networking against its cloud, so a load needs reachability to AWS and GCP
(a dry run and `validate` included). `identity export-gids`, the state
query and `prune-attachments` need the identity provider's API;
`verify login` needs the OPA gateway path `sft` uses.

**Integration points.** `just cli <args>` runs the CLI against
`CSIS_CONFIG_ROOT` (default: the sibling live checkout); the `cloud-*`
recipes wrap `runtime describe`, `state query --strict`, `run ...
--only-runtime/--apply-runtime`, `empty`, `verify instance`, `dispose
image` and `lineage relabel`; `just preflight` and `just cloud-preflight`
are `preflight` and `state query --strict`. The pre-commit hook both
repositories carry (`.githooks/pre-commit`, enabled by `just hooks` here
and `just hooks-live` in the live checkout) runs `cs-image-system
public-safe --staged --tree <top>`. CI runs `just cli mask`, `just cli validate`,
`just cloud-preflight`, `just cli run --all [--commit]`, `just
cloud-perform <rt>` and `just ci-login-proof` (which evaluates `workload
describe --env`), as [docs/OPERATIONS.md](../../docs/OPERATIONS.md)
section 3 lists. Terraform calls `identity export-gids` and `decrypt
--json` from the generated roots.

## Configuration reference

This package owns no YAML. What it reads is the command line, the
environment, and a handful of raw keys of the tree that it must read
BEFORE (or without) the model load; every modelled field belongs to the
base and the plugins ([docs/CONFIGURATION.md](../../docs/CONFIGURATION.md)).

### Global options

| Option | Type | Default | Meaning | Honoured by |
| --- | --- | --- | --- | --- |
| `--root-dir` | path | the current directory | the configuration root | every loading command (changes into it); `preflight`, `encrypt`, `decrypt`, `reencrypt`, `public-safe`, `materialize`, `mask` (recorded as the root); ignored by `gate-plan`, `apply-check`, `identity export-gids`, `test`, `cleanup` |
| `--verbose` | bool | `false` | `DEBUG` logging; `YAML_DUMP.yaml` in the starting directory when a load happens | every command (the log level); the dump only with a load |
| `--dry-run/--no-dry-run` | bool | `true` | enumerate deferred work instead of executing it | `run`, `build-all`, `generate`, `dispose image`, `lineage restamp`, `lineage relabel`; the deferred CLI steps a run emits carry `--no-dry-run` themselves; `reencrypt` has its own flag; every other command ignores it |
| `--overlay` | path, repeatable | none | a transient declaration file | every loading command; `preflight` and the `run`/`state` session check (their `config:` keys, for `preflight.expected_run_minutes`); ignored by the value tools, `gate-plan` (which has none), `apply-check` (which has its own), `identity export-gids` |
| `--undeclare` | `kind:name`, repeatable | none | treat a tree entry as absent | every loading command; ignored elsewhere |
| `--base-only` | bool | `false` | select the base-image lifecycle alone | `build-all`, `generate` |
| `--only-providers` | | | retired (stage 67): `No such option`; `--only-runtime` filters runtimes | |

### Environment variables

| Variable | Read by | Meaning |
| --- | --- | --- |
| `CSIS_CONFIG_IDENTITY` | every configuration load; `decrypt`, `reencrypt`, `mask`, `materialize` | the age identity (a key string, an identity file, or a directory of `*.age-identity` files); required only when a marker is present |
| `AWS_PROFILE` | `preflight`; the `run`/`state` session check; every load through the AWS plugin | the profile when a runtime names none |
| `AWS_ACCESS_KEY_ID` | `preflight`; the `run`/`state` session check | static keys are reported as present with no readable expiry, when no profile is named |
| `CSIS_AWS_DIR` | `preflight`; the `run`/`state` session check; `state query --strict` | the `~/.aws` directory to read `config` and `sso/cache` from |
| `GOOGLE_APPLICATION_CREDENTIALS` | `preflight`; the `run`/`state` session check; `state query --strict` | the ADC file; default `~/.config/gcloud/application_default_credentials.json` |
| `AWS_*`, `GOOGLE_*`, `OKTA_*`, `TF_VAR_*`, `CSIS_*` (any name with these prefixes) | `preflight` | a variable set to the empty string is a failure (exit 2), reported by name |
| `TF_VAR_<team>_key`, `TF_VAR_<team>_secret`, `OKTAPAM_KEY`, `OKTAPAM_SECRET` | `identity export-gids`; the state query; `prune-attachments` (through the identity plugin) | the OPA API pair |
| `OPA_TOKEN` | `verify login` | log in as the workload when set, as the enrolled client when not; the record says which |
| `USER`, `USERNAME` | `unmount storage --confirm` | the operator's name in the receipt (`unknown` when neither is set) |
| the whole environment | every load | exposed to templates as `ENV` |
| `CSIS_CONFIG_ROOT` | the Justfile, never the CLI | the live root `just cli` passes as `--root-dir` |

### Keys of the tree read raw, before or without the load

| Key | File | Type | Default | Read by |
| --- | --- | --- | --- | --- |
| `runtime_builders[].name`, `.type`, `.profile`, `.credentials.profile_name` | `cfg/runtime-builders.yml` | strings | none | `preflight`; the `run`/`state` session check. An entry without a `name` is skipped; a file that is missing or unreadable yields no sessions (`preflight` then exits 2 with `no runtimes declared`). |
| `config.preflight.expected_run_minutes` | `cfg/_config.yml`, then each `--overlay` | int | `30` | `preflight`, the `run`/`state` session check (raw); `state query --strict` (from the loaded context) |
| `config.apply_<lifecycle>` | `cfg/_config.yml`, then each `--overlay` | bool or list of root/runtime names | `false` | `apply-check` |
| `encryption.recipients` | `cfg/_config.yml` | list of age recipients | none (an error) | `encrypt`, `reencrypt` |
| `public_safe.allow` | the `--config` file, else the tree's `cfg/_config.yml`, else the fixture's inside the system repository | list | none | `public-safe` |
| `dateformat`, `working_directory`, `generation_directory` | the merged tree | strings | `%Y%m%d_%H%M%S`, `./workdir`, `generated` | the load (base). The callback always supplies a root (`--root-dir` or the current directory) as the working directory, so `working_directory` is never consulted through the CLI; `generation_directory` is resolved under that root |

Accepted, not read, anywhere in this package: `apply-check --lifecycle release` (the help lists it;
nothing emits it, and the release lifecycle's cloud marking runs under the
plugin's own commands); `sleep_before_finalization` in the tree (kept for
compatibility: the load reads it, and a real run with a non-zero value
logs `sleep_before_finalization=<n> is ignored: finalization never waits
on a terminal (DESIGN §3G)`; finalization never sleeps). The global
`--force` is gone (stage 63, see [Global options](#global-options)).

### Variations

- **Dry run (the default) versus `--no-dry-run`.** A dry run generates
  everything, writes every runner script and `final_execution.sh`, runs
  the state query and validation, and then only enumerates the deferred
  commands (`dry-run` per lifecycle in the summary); the terraform roots
  initialise with `-backend=false`; pins move nothing; `--commit` still
  commits the emission and records. `--no-dry-run` executes the scripts
  in-process with the builders' finalize hooks; the deferred CLI steps
  they carry are themselves `--no-dry-run`. `dispose image`, `lineage
  restamp` and `lineage relabel` print their plan and stop under a dry run
  and act under `--no-dry-run`. `run --migrate-state` exits 2 under a dry
  run instead of moving anything.
- **`run` versus `build-all` versus `generate`.** The aliases are `run
  --all --apply --no-commit` and `run --all --no-apply --no-commit`, with
  `--base-only` narrowing both to `base-image`; they take none of `run`'s
  options.
- **`--apply` versus `--no-apply`.** With `--no-apply` every lifecycle is
  `not-attempted` and nothing after generation runs. With `--apply`, a
  lifecycle generated this run whose script exists runs; one that deferred
  nothing is `no-script`; a script left by an earlier run of a lifecycle
  not requested now is `stale-script-skipped`, never executed.
- **`--state-query` versus `--no-state-query`.** With the query, reality
  is read first, `generated/state-report.json` is rewritten, the session
  lines are logged (a warning for a blocking one, never a refusal in a
  run) and hard drift refuses the run at validation. Without it the
  existing report stands and the validator reads that.
- **`--commit` versus `--no-commit`.** `--commit` records the run and
  makes one commit of `meta-state/` and the generated tree in the
  configuration repository (the run-local files are never staged); a root
  outside a git repository or a gitignored path is skipped with a warning
  and `meta_state_commit` stays `null`. Without it the summary and journal
  are still written.
- **Scope: `--only`, `--only-runtime`, `--apply-runtime`,
  `--allow-unscoped-bakes`.** `--only` names images (unknown names fail
  the run); `--only none` bakes nothing. `--only-runtime` expands to
  `<image>@<rt>` for every image baked there (or `none` when none is) and
  makes the other runtimes' storage and instance roots emit nothing.
  `--apply-runtime` sets both apply flags to `[<rt>]` for the run and
  implies `--only-runtime <rt>` unless `--only` or `--only-runtime` was
  given (the implication is recorded as `implied_scope`). When the apply
  scope is a proper subset of the runtimes and the bake plan would bake
  outside it, a real run refuses before any bake with `run scope: bake(s)
  outside the apply scope [...]` unless `--allow-unscoped-bakes` or an
  explicit selection was given; a dry run logs the same as a warning and
  goes on.
- **`--overlay` versus `--undeclare` versus the tree.** An overlay's
  `config:` keys override `cfg/_config.yml` for the invocation and the
  generated `apply-check` re-reads the same file at execution (a vanished
  file refuses the apply); its item entries update or add declarations,
  and the retention runner's transient-storage teardown re-passes only the
  config-only overlays. `--undeclare kind:name` removes an entry without a
  file. Neither changes the tree.
- **`preflight` versus `preflight --strict` versus `state query --strict`
  versus the `run`/`state` callback.** `preflight` reads the raw tree and
  refuses (2) on absent or expired sessions and on empty credential
  variables; `--strict` also refuses (1) on a session expiring within the
  window. The callback before `run` and `state` prints the same lines and
  refuses (1) only on EXPIRED. `state query --strict` refuses (1) on a
  session expiring within the window, from the loaded runtimes. A plain
  run warns and continues.
- **Encrypted versus clear values.** A tree with no `ENC[age:...]` marker
  loads with no identity; one marker anywhere makes every load, and
  `materialize`, require `CSIS_CONFIG_IDENTITY`. `encrypt` never needs an
  identity; `decrypt`, `reencrypt` and `mask` always do. `decrypt` takes
  a marker, or `--json` (the terraform protocol, unmarked values pass
  through), or `--file --field` (in place, the inverse of `encrypt
  --file`).
- **`release IMAGE` versus `release --declared`.** The explicit form
  releases one build (the series head, or `--build`) for `--model` and
  prints the entry; `--declared` releases every image's verified head per
  its `release: {model}` declaration, prints one `released: ...` line and
  exits 0 when nothing qualifies. Both apply the same refusals.
- **`verify instance` with and without `--record-only`; `verify login` as
  workload or client.** Without `--record-only` a failed verdict exits 1
  and stops the runner, leaving an ephemeral instance standing; with it
  (the `teardown` failure policy) the verdict is recorded, the exit is 0
  and `verify assert` fails the run afterwards. `verify login` uses the
  workload path when `OPA_TOKEN` is set and the enrolled client otherwise,
  and records `as: workload|client`.
- **`gate-plan PLAN_JSON` versus `--planfile`.** A JSON file is read as
  is; `--planfile` is converted with `<tofu> show -json` and is first
  checked for staleness against the newest `*.tf` under its root.
- **`apply-check` with and without `--config-root`, `--root`,
  `--apply-runtime`.** Without `--config-root` the nearest ancestor of the
  working directory holding `cfg/_config.yml` is the root. Without
  `--root` a list-valued flag counts as on for the lifecycle; with it the
  root's name or an alias must be listed. `--apply-runtime` replaces the
  `storage`/`instances` flag with `[<rt>]` and leaves `identity` alone.
- **`public-safe` over a tree versus `--staged`.** The tree form scans
  tracked plus untracked non-ignored files under `--tree`/`--root-dir`;
  `--staged` scans the git index of the repository containing that path
  and exits 2 when there is none.
- **`empty --runtime` on a runtime whose plugin lists inventory versus
  one that cannot.** GCE answers; a plugin without inventory makes the
  command exit 2 (`empty: <builder> cannot list its inventory`).
- **`materialize SOURCE` with and without `DESTINATION`.** Without one the
  mirror path is derived (the root's `generated/` name replaced by
  `_private/` at the same depth); with one the copy goes exactly there.
- **The console script versus `python -m cs_image_system.system`.** Both
  run the same application; the module wrapper additionally catches any
  exception the application lets through and exits 1 with `Error: <e>`.

## What it tests and verifies

The CLI verifies little of its own; it decides what runs, and reports
where the base and the plugins put their verdicts.

**Before the command (the callback).** For `run` and `state ...`: the
credential sessions from the raw `cfg/*.yml` files (every file that
declares `runtime_builders:`), one `session:` line each on standard error, and `preflight: a session has
EXPIRED; renew it (aws sso login --profile <p>) before the configuration
can even load` with exit 1 on an expired one. For every loading command:
the overlay files (existence, shape, allowed top-level keys, named
entries) and the `--undeclare` specs are validated up front, then the load
itself applies the base's checks (naming rules, structuring, foreign keys,
every `ENC[age:...]` value opened, the cloud plugins' networking
validation); a failure is `Error reading config file : <e>` and a
traceback, exit 1. Nothing else is checked at load.

**At `validate`.** Delegated whole to the base's `validate_only`: unique
names, every declared executable present at its path and within its
version requirement, every foreign key resolving, every root's state
location sound, the lineage and release policies, every registered
validator. The verdict is the ` - <error>` lines and `Validation failed
with N error(s).` on standard error, exit 1; nothing is written.

**At generation (`run`).** In order: the state query (verdict:
`generated/state-report.json` and the `state` counts in the summary), the
same validation as `validate` (verdict: `validation_errors` in
`generated/run-summary.json`, `validation: <error>` log lines, exit 1
before anything is generated), the bake plan (`bake plan: <key>:
<decision>` lines and `bake_plan` in the summary), the scope check
(`run scope: ...` refusal or warning), and the `--only` name check (the
summary's `error`). The run's verdict is `ok`, `error` and the
per-lifecycle `apply` states in the summary on standard output and in
`generated/run-summary.json`, the journal entry in `meta-state/runs.yaml`,
and the exit code.

**At apply (the runner scripts).** The steps this CLI provides and where
each verdict lands: `gate-plan` (standard error, exit 3, the runner
stops), `apply-check` (standard error, exit 3), `state-migration begin`
(`<workspace>.state-migration.json` and `<workspace>.backup-<run>.tfstate`
beside the root in the mirror; log lines; exit 1 or 2), `state-migration
backup` (`_private/state-backups/<workspace>.backup-<run>.tfstate`; a log
line naming the serial and count; exit 1 stops the runner), `state-migration
finish` (`meta-state/state-locations.yaml` and the migration record),
`prune-attachments` (log lines per attachment kept, left or removed),
`unmount storage` (the receipt under `<workdir>/unmount-receipts`),
`verify instance` (`meta-state/verifications.yaml`, `image-tests.yaml`,
the record on standard output), `release --declared` and `dispose image
--retention` (lineage, releases and pins in meta-state). A failed step
fails the lifecycle (`failed` in the summary, exit 1 of the run).

**After apply.** `verify assert` (exit 1 from `verifications.yaml`),
`verify login` (`meta-state/login-proofs.yaml`, `login proof <name>:
<check>: ok|FAILED -- <detail>` lines), `empty --runtime` (the leftovers on
standard error, the state report rewritten), `identity-attributes` (the
`would set:` lines; nothing written).

**In the state query.** `state query` writes `generated/state-report.json`
and prints the report; `--strict` turns any drift but `stale`, and a
session expiring within the window, into exit 1. `state import` rewrites
the report after adopting.

**In this package's own tests.**
[`tests/test_cli_dry_run.py`](tests/test_cli_dry_run.py) asserts the
`--dry-run` default is `True` and the flag is `--dry-run/--no-dry-run`;
everything else is proven by the workspace suite listed under
[Tests](#tests).

## When it fails

The failures this command surface produces, those that have happened
first. Dates are from [docs/OPERATIONS.md](../../docs/OPERATIONS.md),
[docs/history/LEDGER.md](../../docs/history/LEDGER.md), the tests and the
source comments.

### Seen live

- **Stage 1 (by 2026-09-02, finding 33): `gate-plan` judged the previous
  sequence's plan.** A failed `plan` left the earlier `tfplan` behind and
  the gate passed it. Every gated sequence now begins with `rm -f tfplan`
  and `gate-plan --planfile` refuses `STALE PLANFILE: <file> does not
  exist` or `... is older than <newest .tf>` with exit 3. If it recurs,
  the plan step did not run or did not succeed; read the runner's output
  above the gate line.
- **2026-09-03 (finding 34): `apply-check` crashed because it loaded the
  configuration.** The guard failed closed, but the runner could not apply
  at all. `apply-check` (with `gate-plan` and `identity export-gids`) is
  now exempt from the load and reads `cfg/_config.yml` as text; the symptom
  today would be `apply-check: no cfg/_config.yml found from the working
  directory up; refusing to apply` (exit 3), which means the step ran from
  a directory with no configuration root above it: pass `--config-root`.
- **2026-09-03 (finding 36): the apply step executed other lifecycles'
  leftover runner scripts by bare bash** and baked two unrecorded AMIs. A
  script of a lifecycle not requested in this run is now
  `stale-script-skipped` in the summary and never runs. Seeing that state
  is not an error; it says an older script is lying under `generated/`.
- **2026-09-05 (ledger 52 to 53, side lesson): `run --commit` failed with
  git exit 128** after a peer session's `git flow feature start/finish`
  switched the shared checkout's HEAD mid-run; the operator committed by
  hand. The CI `perform` job names its committer for the same reason (a
  runner has no git identity). A `--commit` run does all its work first
  and fails at the very end: the emission and meta-state are on disk;
  commit them by hand or re-run.
- **2026-09-08 (ledger 65) and 2026-09-09: the AWS SSO session lapsed
  mid-cycle, then an expired session killed the load before the preflight
  could say so.** The configuration load validates every runtime's
  networking against its cloud, so it died inside the AWS call. The
  callback now prints the sessions from the raw tree before `run` and
  `state` load and exits 1 on `preflight: a session has EXPIRED; renew it
  (aws sso login --profile <p>) before the configuration can even load`.
  Every OTHER loading command (`validate`, `upgrade`, `verify ...`) still
  dies inside the load with an AWS error; run `preflight` first.
- **2026-09-09 (ledger 68): `run ... --apply-runtime gcloud-east1` without
  `--only-runtime` baked two AMIs on AWS.** `--apply-runtime` scoped the
  applies, never the bakes. It now implies `--only-runtime` unless `--only`
  or `--only-runtime` is given, and a real run whose bake plan reaches
  outside its apply scope refuses before any bake: `run scope: bake(s)
  outside the apply scope ['<rt>']: <series>@<rt> -- pass
  --allow-unscoped-bakes, or select images with --only / --only-runtime`
  (exit 1, in the summary's `error`). A dry run only warns with the same
  text.
- **2026-09-09 (ledger 68): `verify assert` as the runner's last step
  failed the script before the after-apply hook ran**, leaving a launch
  record for an instance that no longer existed. Under the `teardown`
  policy the runner now carries `verify instance --record-only` and the
  failed verdict fails the run from the hook, after the record is
  forgotten.
- **2026-09-10 (ledger 70): a scoped AWS bake failed on the GCE instance
  root's plan** (its image-family lookup returned 404 after a cycle had
  disposed every GCE image). `--only-runtime`, explicit or implied, now
  makes the other runtimes' storage and instance roots emit nothing.
- **2026-09-11: the V1 placeholders `test`, `verify` and `cleanup`.** The
  `verify` command GROUP shadowed the placeholder, which could never run;
  `test` and `cleanup` printed a warning and succeeded, which an old script
  would take as success. `verify` was deleted; `test` and `cleanup` now
  print `<name>: retired in V2. ...` naming the replacement and exit 2.
- **2026-09-17 (stage 43): three green CI jobs ran nothing** because a
  secret existed with an empty value. `preflight` now lists every
  credential-shaped variable that is set but empty (`environment: <NAME>
  is set but EMPTY -- a credential that exists with no value is a failure,
  not an absence`) and exits 2: give it its value or unset it.
- **2026-09-19: `tofu init` in the mirror could not read its module.**
  `materialize` had nested the mirror one level deeper than the root it
  copied, and the relative module source and `local` state path counted
  one directory too many. The mirror now replaces the `generated/` name at
  the same depth. If a materialized root cannot find `../tfmodules` or its
  local state, compare the depth of `_private/<...>` with
  `generated/<...>`.
- **2026-09-20 (stage 54): a pin outlived its instance.** `coops-model`
  was destroyed through the gate and `pins.yaml` kept binding it, so with
  `require_released_builds` on, `validate` refused every run, including
  the one that would release the build. `forget instance <name>` drops the
  pin and launch parameters and records the correction; it refuses (exit
  2) while the instance is still declared.
- **2026-09-21: an `sso-session` profile was read as ABSENT for an hour**
  while the CLI was refreshing its token underneath, and `just full-test`
  skipped its live legs. `preflight` now reports such a profile as
  `present; refreshes itself from the refresh token in sso cache <id>
  while the portal session lives (no fixed expiry readable)`. A session
  that lapses mid-run is environmental: `aws sso login --profile <p>`,
  then re-run the legs.
- **2026-09-22: `sft resolve --quiet` exited 126 with no output** when the
  client wanted a browser. `verify login` names the cause in its `resolves`
  check: `the client has no session (as the enrolled client: run sft
  login; as the workload: OPA_TOKEN is missing or was refused)`.
- **2026-09-23 10:15 (stage 61 item 3): a state backup pulled from the
  configuration root instead of the mirror and kept nothing.** The
  callback's load changes directory to the root AND replaces the Typer
  context object, so the `invoked_cwd` recorded before the load was gone
  when `state-migration backup` read it, and the step ran in the root,
  found no initialised terraform root, said "nothing to keep" and let the
  `state rm` run unbacked. The callback now records the invocation
  directory again after the load, `backup` refuses (exit 1) a directory
  that is not an initialised root or a location with no state, and
  `state-migration begin`/`finish` share the fix. Proved live the same
  day (backup serial 36 kept). If a runner step reports `REFUSED: <dir> is
  not an initialised terraform root`, the step was invoked from the wrong
  directory; the runner's `( cd ... && cd "$(materialize ...)" && ... )`
  wrapper is what puts it in the right one.
- **Undated, found live: `run --all` in a fresh process resolved to the
  four built-ins.** The hook plugins that register `release` and
  `retention` loaded only inside the run, after the names were parsed.
  `run` now loads them first. `Unknown lifecycle 'release'` today means
  the hook entry points are not installed in the environment running the
  command.

### Raised by the code, not yet seen

A retired global option is a parser error, not a message of this
package's own: `cs-image-system --force <command>` prints the usage and
`No such option: --force` and exits 2 (stage 63; until 2026-09-25 the
option was accepted and ignored). Drop it; if something should be forced,
use the named override (`run --force-bake`, `gate-plan --allow-destroy`,
`test-mods --force`).

Usage (exit 2), all on standard error:

```text
Unknown lifecycle '<name>'; expected one of [...] or 'all'
No lifecycles selected; pass names or --all (...)
--migrate-state moves state and needs --no-dry-run: a dry run never moves state
--apply-runtime: unknown runtime '<rt>'
--only-runtime: unknown runtime '<rt>'
encrypt: --file needs at least one --field
encrypt: give a value (or '-' for stdin), or --file with --field
decrypt: --file needs at least one --field
release: an image name is required (or --declared)
gate-plan: pass a plan JSON file or --planfile
public-safe: <path> is not inside a git repository
state-migration: the action is begin, finish or backup, not '<x>'
prune-attachments: no group builder named '<name>'
workload describe: no group builder names a workload connection and role
<name>: retired in V2. ...
```

The load (exit 1, `Error reading config file : <e>` then a traceback):
`Failed to read configuration from <root>/cfg` (no tree there);
`--undeclare '<spec>': expected <kind>:<name>` or `unknown kind`;
`Overlay <path> does not exist` / `must be a mapping` / `unknown top-level
key(s)` / `'<key>' must be a list of named entries`; `an encrypted value
is present but CSIS_CONFIG_IDENTITY is not set -- export the age identity
(...)`; `CSIS_CONFIG_IDENTITY=<value>: not an AGE-SECRET-KEY-1 string, an
identity file or a directory`; `no identity in CSIS_CONFIG_IDENTITY can
decrypt this value (N tried; it was encrypted to other recipients)`; `No
runtime providers configured.`; `Working directory <path> does not exist.`;
and every plugin's own load-time refusal (the AWS and GCE networking
checks, the Okta workspace's credential assertions). Look at the line
before the traceback; the message names the file or value.

The run (exit 1, `Run <id> FAILED: <error>` and the summary's `error`):
`--only names unknown image(s): <names>; known: <names>`; `Validation
failed with N error(s)` (each also logged as `validation: <error>`);
`run scope: bake(s) outside the apply scope ...`; `--migrate-state moves
state and needs --no-dry-run` (raised again inside the run, in case a
library caller set it); any generation or apply exception, named by class.
The summary and journal are still written.

The value tools (exit 1): `decrypt: not an ENC[age:...] marker`,
`decrypt: expected a JSON object of string values on stdin`, `decrypt: a
marker is required (or '-' for stdin, or --json)`, `reencrypt: NOTHING
written -- <file>: <reason>`, `materialize: nothing to materialize at
<path>`, `materialize: '<path>' is not in the subpath of '<root>'`,
`mask: <reason>`, `public-safe: REFUSED -- N finding(s) ...` (with every
finding on standard output), `encrypt: <reason>` and `reencrypt: NOTHING
written -- <reason>` when the recipients (or, for `reencrypt`, the
identity) cannot be read: for example `encrypt: <root>/cfg/_config.yml:
no encryption.recipients declared`, or `reencrypt: NOTHING written -- an
encrypted value is present but CSIS_CONFIG_IDENTITY is not set -- export
the age identity (the AGE-SECRET-KEY-1 string, an identity file, or a
directory of *.age-identity files)`. Until 2026-09-25 (stage 63) those
two ended in a traceback rather than a message.

The gates (exit 3): `DETACH NOT UNMOUNTED: <instance>:<storage> has no
successful unmount receipt (unmount storage ..., or unmount storage
--confirm)`; `STALE PLANFILE: ...`; `DESTROY NOT WHITELISTED: <address>`
(one line per address; whitelist it by operation, never by hand);
`apply-check: no cfg/_config.yml found ...`; `apply-check: overlay <path>
is gone; refusing to apply`; `apply_<lifecycle> is false NOW in
<path> ...` (turn the flag on, or pass `--apply-runtime` on the run that
generates the script).

Runner steps that stop the runner (exit 1): `state-migration begin: the
new location <loc> already holds state (lineage <id>) that is not this
workspace's: a collision, refused. The old state is untouched.`;
`state-migration begin: init against <file> failed:` / `state pull
failed:`; `state backup for workspace '<ws>' REFUSED: <dir> is not an
initialised terraform root; nothing is removed from state`; `state backup
for workspace '<ws>' REFUSED: the location holds no state, yet a state rm
is due`; `Identity builder <name>: 'state list' failed in <dir>; nothing
is removed from state`; `Identity builder <name>: 'state rm <addr>'
failed; the runner stops here`. Exit 2 from `state-migration begin` when
`--backend-config` is missing, names a file that does not exist, or
meta-state records no location for the workspace (`there is nothing to
migrate from`), and from `finish` when `begin` did not run.

The identity runner's `identity-attributes --probe --dry-run-apply` step
is emitted without `--root-dir`, so it loads the configuration from the
directory it runs in, the root's mirror, which holds no `cfg/`. In a real
run of a tree that declares group or user attributes the step would fail
its load (`Error reading config file : ...`, exit 1) and with it the
identity lifecycle, after its apply. No tree has declared attributes in a
real run yet. The fix belongs to the identity
plugin's emission (`system_cli_executable_with_config`), not to this
package.

Other commands (exit 1 unless noted): `upgrade: <reason>` (kind, name,
build, runtime); `release refused: <reason>`; `release: no build of
'<image>' recorded in lineage`; `runtime describe: unknown runtime`;
`empty: <reason>` (exit 2), `empty: <kind> still present on <rt>: ...`,
`empty: state query drift: ...`; `restamp: unknown runtime`; `relabel:
could not retag [...]`; `unmount: instance '<name>' is not declared`,
`unmount: ... names runtime '<rt>', which is not configured`, `unmount of
<mount> on <instance> failed (exit N): <tail>`; `verify: instance '<name>'
is not declared`, and the verification record with `ok: false`; `verify
login: <reason>`; `dispose: ...`; `export-gids: <reason>` (`query must name
an identity_type`, `No identity plugin registered for identity type
'<t>'`, `identity plugin '<t>' reported no gid for groups [...]`, `OPA
credentials for team '<t>' not found in the environment (...)`); `FAIL
<image>/<mod>: ...` from `test-mods`; `identity attributes: the provider
reports conflicts; refusing: ...` (exit 3); `writing identity attributes is
disabled ...` (exit 4). `preflight` (exit 2): `preflight: no runtimes
declared under <root> (cfg/runtime-builders.yml)`, `preflight: a session
is absent or has EXPIRED -- the configuration cannot load (aws sso login
--profile <p> / gcloud auth application-default login)`, `preflight: an
environment credential is set but empty (see above)`; (exit 1 with
`--strict`) `preflight: a session expires before the expected run length
(see above); renew it or lower config.preflight.expected_run_minutes`.

Silent behaviour to know about (`mask` is no longer among it: since
stage 63 item 2, 2026-09-24, a file it cannot read for masking -- the
identity missing or wrong, a file that does not parse, a malformed marker
-- ends it with `mask: FAILED` naming each file and exit 1, so a CI step
that cannot mask fails instead of printing nothing);
`run --commit` outside a git repository or over a gitignored `generated/`
logs a warning and reports `meta_state_commit: null`; a plain `run` logs
`preflight session: ...` warnings and `state query: <unavailable>`
warnings and goes on.

## Related

- [The base library](../base/README.md): the runner, the commands every
  subcommand delegates to, meta-state, encryption and the public-safe gate.
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md): the operator's manual,
  every command in use, the exit-code table, the credentials contract and
  CI; [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md): the tree, the
  overlays, the run scoping options and the environment variables;
  [docs/DESIGN.md](../../docs/DESIGN.md): the headless contract;
  [docs/PLUGINS.md](../../docs/PLUGINS.md): the package index.
- The plugins whose steps the runner scripts call through this CLI:
  [okta-opa-plugin](../okta-opa-plugin/README.md) (`export-gids`,
  `prune-attachments`, `identity-attributes`),
  [tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md) and
  [tf-gcp-plugin](../tf-gcp-plugin/README.md) (`verify instance`,
  `unmount storage`), [hashicorp-utils](../hashicorp-utils/README.md)
  (the gated sequence, `state-migration`).
- [The Justfile](../../Justfile): `just cli`, `preflight`,
  `cloud-preflight`, the `cloud-*` recipes and `ci-login-proof`.
