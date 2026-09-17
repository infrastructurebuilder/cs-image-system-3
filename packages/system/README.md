# cs-image-system-system

The command-line host of cs-image-system. It installs one console script,
`cs-image-system`, that loads the plugins, reads a configuration tree and
drives the lifecycle runner, the state tools and the value tools of
`cs-image-system-base`. The package holds no builder logic of its own:
every command delegates to the base library or to a plugin.

Licensed under Apache-2.0. Requires Python 3.13 or later. Declared
dependencies: `typer[all]` and `cs-image-system-base`. The entry point is
`cs_image_system.system.cli:app` (a Typer application); `python -m
cs_image_system.system` runs the same application.

Source: [`src/cs_image_system/system/cli.py`](src/cs_image_system/system/cli.py).

## Contents

- [Invocation and output](#invocation-and-output)
- [Global options](#global-options)
- [What the callback does before a command](#what-the-callback-does-before-a-command)
- [Commands](#commands)
- [Credentials](#credentials)
- [Commands the generated runner scripts call](#commands-the-generated-runner-scripts-call)
- [Exit codes at a glance](#exit-codes-at-a-glance)

## Invocation and output

```text
cs-image-system [GLOBAL OPTIONS] <command> [ARGS]
cs-image-system --help
cs-image-system <command> --help
```

`-h` and `--help` both print help. Logs go to standard error through a
rich handler; standard output is reserved for machine-readable output (the
run summary JSON, the gid shim's JSON, a decrypted value). Inside the
workspace, `just cli <args>` runs the CLI against the live configuration
root.

## Global options

These are options of the top-level callback and come before the command
name.

| Option | Default | Meaning |
| -------- | --------- | --------- |
| `--root-dir PATH` | the current directory | The configuration root: the directory holding `cfg/`, `groups/`, `storages/`, `images/`, `instances/` and `meta-state/`. The process changes into it for the command and returns afterwards. |
| `--verbose / --no-verbose` | off | Log at `DEBUG`. With a configuration load, also writes the string-stage-rendered document to `./YAML_DUMP.yaml`. |
| `--dry-run / --no-dry-run` | `--dry-run` | Dry run: generation is complete and runner scripts are written, but deferred finalization commands (packer builds, tofu init/plan/gate/apply, system CLI steps) are enumerated, not executed. `--no-dry-run` executes them. The same flag governs `dispose image`, `lineage restamp` and `lineage relabel`, which report a plan under a dry run. |
| `--overlay FILE` (repeatable) | none | A transient declaration file merged over the tree for this invocation only. `config:` keys override; named `instances:`/`storages:` (and other item) entries update or add; an entry with `undeclare: true` removes the tree's entry. The tree on disk never changes. |
| `--undeclare KIND:NAME` (repeatable) | none | Treat a declared tree entry as absent for this invocation, for example `instance:gce-test`. `KIND` is an item collection key (`instances`, `storages`, ...); the singular is accepted. |
| `--base-only` | off | Makes `build-all` and `generate` select the base-image lifecycle only. The configuration is still read in full. |
| `--only-providers NAME` (repeatable) | none | Accepted and recorded on the run context; the configuration is still read in full and a warning says so. |
| `--force` | off | Recorded on the run context. |

## What the callback does before a command

The callback decides, per command, how much to load:

| Commands | Before the command runs |
| ---------- | ------------------------- |
| `test`, `cleanup` | Nothing. They are retired names and exit 2. |
| `preflight` | Reads only the raw `cfg/runtime-builders.yml` and `cfg/_config.yml` (and overlays' `config:`). No plugin loads, no configuration loads. |
| `gate-plan`, `apply-check`, `identity export-gids` | No configuration tree loads. `identity export-gids` loads plugins on demand; `apply-check` reads only `cfg/_config.yml` as text. |
| `encrypt`, `decrypt`, `reencrypt`, `public-safe` | Records the configuration root (`--root-dir` or the current directory). No plugin loads, no configuration loads. |
| every other command | Loads plugins. For `run` and `state ...` it first prints the credential session lines read from the raw tree and exits 1 when a session has expired. Then it reads the whole configuration (`read_config_and_transform`): the string stage, structuring, builder construction and item reading, with overlays and undeclarations applied. |

Loading the configuration constructs every runtime builder, and the cloud
runtime plugins validate their networking against the cloud during that
step. See [Credentials](#credentials).

## Commands

### `run [LIFECYCLES...]`

Run one or more lifecycles of the meta-workflow in declared order. The
lifecycle names are `identity`, `storage`, `base-image`, `instance-image`,
the registered `release` and `retention`, or `all`. Aliases: `id`,
`storages`, `base-images`, `base`, `instance-images`, `instances`. Names
resolve in declared order, never in argument order.

| Option | Default | Meaning |
| -------- | --------- | --------- |
| `--all` | off | Every lifecycle, registered ones included. |
| `--apply / --no-apply` | `--apply` | After generation, execute the runner scripts that exist. Under a dry run they are enumerated. |
| `--commit / --no-commit` | `--no-commit` | Make the meta-state commit (read-models, pins, lineage, launch parameters, generated IaC) in the configuration repository after the run. |
| `--state-query / --no-state-query` | `--state-query` | First ask reality (read-only) and write `generated/state-report.json`; validation refuses to run on hard drift. `--no-state-query` keeps the existing report. |
| `--only NAME` (repeatable) | none | Restrict the bake surface to the named image(s), as `<image>` or `<image>@<runtime>`. Sources, build blocks and bake steps exist for nothing else; terraform roots are untouched. Unknown names fail. `--only none` bakes nothing. |
| `--only-runtime NAME` | none | Restrict the bake surface to every image baked on that runtime. Terraform roots of other runtimes are not generated or planned. |
| `--apply-runtime NAME` | none | Let the storage and instance roots of that runtime apply, as if `apply_storage` and `apply_instances` listed it. Implies `--only-runtime NAME` unless `--only` or `--only-runtime` is given. The generated `apply-check` steps carry it. |
| `--force-bake NAME` (repeatable) | none | Bake the named image(s) even when current; `all` forces every image in the run's surface. |
| `--allow-unscoped-bakes` | off | Let a `--no-dry-run` run bake on runtimes outside its apply scope. Without it such a run refuses before any bake. |

The run summary is printed to standard output as JSON. Exit 0 on success.
Exit 1 when the run failed (validation, generation, apply or commit).
Exit 2 for an unknown lifecycle name, no lifecycle selected, or an unknown
`--apply-runtime` / `--only-runtime` runtime.

### `build-all`

Alias: `run` every lifecycle with `--apply` and `--no-commit`; with
`--base-only`, the base-image lifecycle only. Exit codes as for `run`.

### `generate`

Alias: `run` every lifecycle with `--no-apply` and `--no-commit`; with
`--base-only`, the base-image lifecycle only. Exit codes as for `run`.

### `validate`

Run every validation rule (unique names, executables present and
version-compliant, lineage policies, every registered validator) and
generate nothing. Prints each error to standard error. Exit 0 when clean,
exit 1 with errors.

### `upgrade KIND NAME [--to BUILD] [--runtime RT]`

Move exactly one pin. `KIND` is `instance` or `image`; `NAME` is the
instance or the instance image. `--to` names the target build id (default:
the head of the relevant series in lineage). `--runtime` selects which
runtime's pin moves for an image baked on several runtimes. For an
instance the move is understood as a destroy-and-recreate: the next
instance-image run plans a whitelisted replacement. Exit 1 on any error
(unknown name, unknown build, ambiguous runtime).

### `preflight [--strict]`

Report the credential sessions the configuration's runtimes need (AWS SSO
profiles or static keys, GCP application default credentials), read from
the local caches without loading the configuration and without printing a
credential value. Exit 0 when every session is present; exit 2 when no
runtime is declared, or a session is absent or expired; exit 1 with
`--strict` when a session expires within
`config.preflight.expected_run_minutes` (default 30).

### `encrypt [VALUE] [--file FILE ...] [--field NAME ...]`

Encrypt to the tree's `encryption.recipients`. With a `VALUE` (or `-` for
standard input) prints one `ENC[age:...]` marker. With `--file` and at
least one `--field`, encrypts in place every scalar under the named keys
and every element of a block list under them, preserving every other byte,
and reports counts on standard error. Needs no identity. Exit 2 when
`--file` is given without `--field`, or neither a value nor `--file`.

### `decrypt [MARKER] [--json]`

Decrypt one marker (or `-` for standard input) with the identity in
`CSIS_CONFIG_IDENTITY` and print the plaintext without a trailing newline.
With `--json` it speaks the terraform `external` data source protocol:
reads a JSON object of strings on standard input and prints it with every
marker decrypted and every other value passed through. Exit 1 on a bad
marker, a missing identity, or a value none of the identities can open.

### `reencrypt [--dry-run]`

Rotate every marker in every `*.yml` / `*.yaml` under the root (skipping
`.git` and `generated`) to the current `encryption.recipients`: decrypt
with `CSIS_CONFIG_IDENTITY`, re-encrypt, write in place. Nothing is
written unless every value opens. `--dry-run` reports what would change.
Exit 1 when a value cannot be opened.

### `public-safe [--staged] [--tree PATH] [--config FILE]`

Scan a tree (tracked plus untracked non-ignored files; default `--root-dir`
or the current directory) or, with `--staged`, the git index, for material
that must not be public: keys, tokens, PEM bodies, an age identity, a
service-account file, plans and state by name; addresses and long tokens
outside prose and tests. `--config` names the `_config.yml` whose
`public_safe.allow` applies (default: the tree's, or the frozen fixture's
inside the system repository). Prints every finding. Exit 0 when clean;
exit 1 with findings; exit 2 when `--staged` is used outside a git
repository.

### `test-mods [--image NAME ...] [--force] [--strict]`

Run every modification of the instance images against a throwaway local
container, twice (apply, then idempotence), and record the results in
`meta-state/mod-tests.yaml`. `--image` restricts to named images;
`--force` re-tests mods that already passed; `--strict` fails when tests
are skipped (no docker). Results are printed as JSON. Exit 1 on a failed
or non-idempotent mod, or on skips with `--strict`.

### `release [IMAGE] [--build ID] [--model NAME] [--note TEXT] [--runtime RT] [--declared]`

Mark a tested build as released for a model (default `default`). Without
`--build` the series head is used (`--runtime` picks which runtime's
head). Prints the release entry as JSON. With `--declared`, releases every
image's verified head per its declared `release: {model}`; this is the
step the release runner script invokes. Exit 2 when neither an image nor
`--declared` is given; exit 1 when no build is recorded or the release is
refused (no in-bake verification, a failed mod test, no or failed post-bake
tests).

### `gate-plan [PLAN_JSON] [--planfile FILE] [--tofu BIN] [--allow-destroy ADDR ...] [--require-unmounted INSTANCE:STORAGE ...]`

The apply gate. Reads a plan as JSON (the output of `tofu show -json`) or
converts a saved plan file locally with `<tofu> show -json`. Every planned
destroy must match an `--allow-destroy` address exactly or as a prefix
followed by `.` or `[`. Every `--require-unmounted` pair needs a successful
unmount receipt under `./unmount-receipts`. Exit 0 when the plan passes.
Exit 3 on a destroy that is not whitelisted, a stale plan file (older than
the newest `.tf` in its root, or missing), or a missing unmount receipt.
Exit 2 when neither a plan nor `--planfile` is given.

### `apply-check --lifecycle NAME [--config-root PATH] [--root NAME] [--root-alias NAME ...] [--overlay FILE ...] [--apply-runtime RT]`

The execution-time apply guard. Re-reads `config.apply_<lifecycle>` from
`cfg/_config.yml` now (walking up from the working directory to the nearest
directory holding it unless `--config-root` is given), applies the
`config:` keys of every `--overlay`, and honours `--apply-runtime` for the
`storage` and `instances` lifecycles. `--root` and `--root-alias` let a
list-valued flag be checked for one terraform root. Exit 0 when the flag
allows the apply; exit 3 when it does not, when no `cfg/_config.yml` is
found, or when an overlay file is gone.

### `identity export-gids`

The gid shim: a terraform `data "external"` program. Reads the query (a
JSON object of strings: `identity_type`, `groups` as a comma-separated
list, and provider fields such as `org`, `team`, `api_host`) on standard
input, asks the identity plugin registered for that type, and prints
`{group: gid}` as JSON. Credentials come from the environment, never from
the query. Exit 1 on any error, including a group the provider cannot
answer for.

### `runtime describe NAME`

Print configuration-driven facts about a runtime as JSON: project or zone,
ephemerality, retention, the images baked there, the declared storages with
their cloud names, the instances, its `builders` (image, storage and
instance builders bound to it) and its `emission` (the
`<lifecycle>/<builder>` directories under `generated/` that hold its
emission and exist now -- what a run scoped to another runtime leaves
untouched, and what `just runtime-unchanged` compares across records).
Exit 1 for an unknown runtime.

### `empty --runtime NAME`

Assert the runtime holds nothing beyond its declared storages (no
instances, no custom images, no other disks or buckets) and that a strict
state query agrees. Names every leftover. Exit 2 when the runtime cannot
answer; exit 1 on leftovers or real drift; exit 0 when empty.

### `lineage restamp --runtime RT [--series NAME ...] [--commit/--no-commit]`

Record the current input fingerprint on series heads whose recorded one
predates the current fingerprint recipe, keeping the previous value, and
re-tag the cloud image to match. Prints the plan as JSON. Under the global
dry run it only reports. `--commit` makes the meta-state commit. Exit 1 on
error.

### `lineage relabel --runtime RT [--build ID ...]`

Re-tag cloud images whose lineage tags disagree with their record, from
the record. No meta-state change. Prints the plan as JSON. Under the
global dry run it only reports. Exit 1 on error or when an image could not
be retagged.

### `unmount storage --instance NAME --storage NAME --mount-point PATH [--workdir DIR] [--confirm] [--timeout SECONDS]`

Unmount a storage on a launched instance through the runtime's session
mechanism and write the receipt that `gate-plan --require-unmounted`
checks, under `<workdir>/unmount-receipts` (default: the current
directory). `--confirm` runs nothing and records the operator's assertion
instead. `--timeout` defaults to 300. Exit 1 on error.

### `verify instance NAME [--expect-build ID] [--timeout SECONDS] [--record-only]`

Run the runtime's verification of a launched instance (serial console,
booted image, data disks, and the image's `tests.post_bake`) and record the
verdict in `meta-state/verifications.yaml` (and `image-tests.yaml`).
`--expect-build` defaults to the instance's pin or launch record;
`--timeout` defaults to 600. Prints the record as JSON. Exit 1 on failure,
which stops a runner script and leaves an ephemeral instance standing.
With `--record-only` a failed verdict is recorded and the exit is 0, so a
teardown can proceed.

### `verify assert NAME`

Exit 1 when the instance's last recorded verification failed, else 0.

### `dispose image [BUILD_ID ...] [--runtime RT] [--all] [--retention] [--commit/--no-commit]`

Delete recorded images from their runtime and drop their lineage record and
any image pin at them in one operation. `--runtime` restricts to builds
baked there; with `--all`, every one of them. `--retention` applies the
declared retention instead: image `retention.keep`, runtime
`retention_keep`, everything on an ephemeral runtime. Refuses unrecorded
builds and builds an instance is pinned to or launched from. Prints the
plan as JSON. Under the global dry run nothing is deleted. Exit 1 on
error.

### `state query [--strict] [--json]`

Ask every plugin for its provider's view of what the system manages
(images by lineage tags, storages by name, groups by gid), diff it against
meta-state, and write `generated/state-report.json`. Prints the rendered
report, or JSON with `--json`. Touches nothing. Exit 1 on hard drift; with
`--strict`, also on any `missing`, `foreign` or `changed` drift (`stale`
is reported only) and when a credential session expires within the
expected run length.

### `state import [--images/--no-images] [--storages/--no-storages]`

Adopt foreign artifacts (tagged as ours, unrecorded) into meta-state:
images into lineage, storages into storage-state. Writes meta-state only,
never the cloud, the identity provider or terraform state, then rewrites
the state report. Exit 0.

### `identity-attributes [--probe] [--dry-run-apply] [--apply] [--json]`

Show the identity attributes plan written by the identity lifecycle (or
compute it), probe the provider read-only with `--probe`, and preview an
apply with `--dry-run-apply` (one `would set:` line per change). Writing is
disabled: `--apply` exits 4 whenever there is a change to write, and no
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
| The age identity in `CSIS_CONFIG_IDENTITY` only | `decrypt`, `reencrypt`. |
| Identity-provider credentials from the environment, and plugins installed | `identity export-gids`. |
| The age identity when the tree holds encrypted values, and live credentials for every declared cloud runtime | Every command that loads the configuration: `run`, `build-all`, `generate`, `validate`, `upgrade`, `test-mods`, `release`, `runtime describe`, `empty`, `lineage restamp`, `lineage relabel`, `unmount storage`, `verify instance`, `verify assert`, `dispose image`, `state query`, `state import`, `identity-attributes`. Loading constructs every runtime builder, and the cloud plugins validate networking against the cloud in that step. `run` and `state` print the session lines first and exit 1 on an expired session. |

Beyond loading, `test-mods` needs a local `docker`; `verify instance`,
`unmount storage`, `dispose image`, `lineage relabel`, `empty`, `state
query` and `state import` call the cloud or the identity provider; a real
`run` executes packer and tofu with their own credentials.

## Commands the generated runner scripts call

A run writes `generated/<lifecycle>/run-<lifecycle>.sh` per lifecycle
with deferred work and `generated/final_execution.sh`, which runs each
script that exists. The scripts call back into this CLI:

| Command line | Emitted where |
| -------------- | --------------- |
| `cs-image-system gate-plan --planfile tfplan --tofu <tofu> [--allow-destroy ADDR ...] [--require-unmounted PAIR ...]` | After every terraform root's `plan -out=tfplan`, in the identity, storage and instance-image runners. |
| `cs-image-system apply-check --lifecycle <identity\|storage\|instances> [--root NAME --root-alias RT] [--overlay FILE ...] [--apply-runtime RT]` | Just before `tofu apply tfplan`, only when the root is allowed to apply. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] release --declared` | The release runner, when an image declares `release:`. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] dispose image --retention` | The retention runner, when retention or an ephemeral runtime is declared. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run run storage --only none --no-state-query --no-commit [--apply-runtime RT]` | The retention runner, for transient overlay storages on an ephemeral runtime. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] verify instance NAME [--record-only]` | The instance-image runner, after an ephemeral instance's launch applied. |
| `cs-image-system --root-dir "$CSIS_ROOT" --no-dry-run [--overlay ...] unmount storage --instance NAME --storage NAME --mount-point PATH --workdir DIR` | The instance-image runner, before a plan that detaches a storage. |
| `cs-image-system identity-attributes --probe --dry-run-apply` | The identity runner, when users or groups declare attributes. |

Two more are not script lines but programs terraform runs at plan time:
`cs-image-system identity export-gids` is the `data "external"` program in
an identity root that needs gids by query, and `cs-image-system decrypt
--json` is the `data "external" "sensitive"` program in every root that
references an encrypted value. Both read their query on standard input and
answer on standard output, which is why logs go to standard error.

`"$CSIS_ROOT"` is defined at the top of each runner script as the
configuration root relative to the script, so a committed script names no
absolute path.

## Exit codes at a glance

| Code | Meaning |
| ------ | --------- |
| 0 | Success. |
| 1 | The operation failed or was refused: a failed run, validation errors, a refused release, a failed verification, hard drift, a value that cannot be decrypted, a public-safe finding, an expired session before a load. |
| 2 | Usage: unknown lifecycle or runtime, nothing selected, a missing argument, a retired command, `public-safe --staged` outside git, `preflight` with an absent or expired session or no runtimes, `empty` on a runtime that cannot answer. |
| 3 | A gate refused: `gate-plan` (destroy not whitelisted, stale plan file, missing unmount receipt), `apply-check` (flag off, no `_config.yml`, overlay gone), `identity-attributes` validation. |
| 4 | `identity-attributes --apply`: writing attributes is disabled. |

## Tests

[`tests/test_cli_dry_run.py`](tests/test_cli_dry_run.py) pins the dry-run
contract: on by default and toggled by `--dry-run/--no-dry-run`. The CLI is
exercised end to end by the workspace suite against the frozen fixture at
[`tests/fixtures/config`](../../tests/fixtures/config), whose emission is
pinned under [`tests/fixtures/v2_golden`](../../tests/fixtures/v2_golden).
