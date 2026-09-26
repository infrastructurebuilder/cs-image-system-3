# cs-image-system-local-state-plugin

The `local` **state backend** plugin (stage 47): a state file on disk. It
registers one model, `LocalStateBuilderModel`, for entries with `type:
local` under `state_backends:` in `cfg/state-backends*.yml`. It is the type
that needs nothing -- no bucket, no cloud, no credentials -- so a developer
or a test can run a real `tofu init` against it, and it is what lets the
frozen fixture exercise two backend types without a second cloud account.
Like the S3 plugin it emits no files and runs no commands of its own: the
terraform roots that bind to it get an empty `backend "local" {}` block, a
partial configuration file carrying one setting, and consumers reading
their state get a `terraform_remote_state` data source with the same
setting.

## What it registers

```toml
[project.entry-points."cs_image_system.plugins.state"]
local_state_plugin = "cs_image_system.local_state_plugin.main:initialize"
```

| Service name (`type:` of a backend entry) | Model class | Builder class | Classifications (VCT) |
|---|---|---|---|
| `local` | `LocalStateBuilderModel` | `LocalStateBuilder` | `STATE_BACKEND_MODEL`, `STATE_BACKEND` |

`initialize()` in [main.py](src/cs_image_system/local_state_plugin/main.py)
returns a `LocalStateTypes` metadata object (plugin metadata version `1`,
Python `3.13`). `LocalStateBuilder` in
[local_state_builder.py](src/cs_image_system/local_state_plugin/local_state_builder.py)
extends `StateBuilderBase` and implements no hooks: it generates nothing
and defers nothing, and exists so the registry can pair the model with a
builder class.

## The model

| Field | Type | Default | Meaning |
|---|---|---|---|
| common builder fields | | | `name` is what a root's `state_configuration` names; `is_default` marks the backend `default` resolves to |
| `path` | str | `state` | a directory: relative to the configuration root, or absolute; one spelling per directory, so a `.` or `..` segment and a bare `/` are refused at load (stage 63) |
| `executable` | str or null | null | the `cfg/executables.yml` entry the bound roots' tofu comes from; when declared it must exist there and is version-checked, when unset nothing is checked (stage 63; see "Configuration reference") |

## The kind

`LocalBackendKind` in
[local_state_models.py](src/cs_image_system/local_state_plugin/local_state_models.py)
renders the type for the collector (the contract the S3 plugin's README
describes under "Adding a backend type"):

| `location(settings, workspace)` | `backend_settings(...)` | `remote_state_settings(...)` |
|---|---|---|
| `local://<directory>/<super_safe_name(workspace)>.tfstate`, the directory normalised (repeated slashes collapsed, `./` and a trailing slash dropped, an absolute path kept); a `.` or `..` segment never reaches here, the model refuses it at load (stage 63) | `path = "<state path>"` | `path = "<state path>"` |

The state path is the absolute directory as declared, or, for a relative
one, the directory rewritten from the root directory's fixed depth:
`../../../../<directory>/<workspace>.tfstate` (a root sits at
`generated/<lifecycle>/<workspace>/<phase>/`, four below the configuration
root). The emission therefore names no absolute path of the machine that
generated it, and the same file works from a fresh clone.

Two roots on one directory whose names collapse under `super_safe_name`
would share a state file and are refused by the stage-46 collision check;
the same name under `s3` and under `local` are two locations, not a
collision. Because the model refuses a `.` or `..` segment at load (stage
63), the directory the check compares is the directory's one spelling:
`a/../b` can no longer pose as a second location beside `b` (until
2026-09-25 it could, and the check saw two places where the disk had one).

## Emission

The frozen fixture binds its identity roots (`oktagroups`, `okta-tf-users`)
to `local-dev` (`cfg/state-backends-3.yml`, `path: state`), so the golden
carries
[oktagroups-group-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation.tfbackend.hcl):

```hcl
# Backend 'local-dev' (local) partial configuration for workspace oktagroups
path = "../../../../state/oktagroups.tfstate"
```

and, in every storage and instance root that reads the identity root's
outputs, a `data "terraform_remote_state" "oktagroups"` with
`backend = "local"` and `config = { path = "../../../../state/oktagroups.tfstate" }`
-- a read across backend types, since those roots keep their own state in
S3. The runner header lists `# state: workspace oktagroups ->
local://state/oktagroups.tfstate`.

## Example configuration

```yaml
---
state_backends:
  - name: local-dev
    type: local
    path: state
```

A root binds with `state_configuration: local-dev`. The live configuration
keeps every root on its S3 backend by the standing decision; this type is
for development, tests and configurations that have no cloud state.

## Prerequisites and integration

**Nothing beyond the core.** No account, no IAM role, no API, no
credential and no network: the package's own test
([test_local_backend.py](tests/test_local_backend.py)) runs a real
`tofu init` and `tofu state pull` against the file the kind renders with an
environment of `PATH`, `HOME` and `TF_IN_AUTOMATION` only, and asserts
that no `AWS_*`, `GOOGLE_*` or `OKTA_*` variable is present. What the
type does depend on is what the core already needs, and it is worth
saying where each piece comes from.

- **The package, installed.** The root
  [pyproject.toml](../../pyproject.toml) lists
  `cs-image-system-local-state-plugin` as a workspace member, so
  `just init` installs it beside the others. The core finds it by the
  entry point above: at every CLI start
  [loader.py](../base/src/cs_image_system/base/loader.py) enumerates the
  `cs_image_system.plugins.state` group and registers every service each
  plugin returns. In an environment without this package no model is
  registered under the type `local`, and a configuration whose entry says
  `type: local` does not load.
- **The gate.** The whole backend mechanism is behind
  `config.use_state_backends` in `cfg/_config.yml`. Off, the entry is
  loaded and registered but no root binds to it: no `backend "local" {}`
  block, no `.tfbackend.hcl`, no remote-state data source, no
  `# state:` header line, and no record in
  `meta-state/state-locations.yaml`.
  Off is itself refused by `validate` when any root would read another's
  outputs through remote state (stage 63 item 19), so it is a shape only
  for a tree where nothing reads anything.
- **A tofu binary for the root, not for the backend.** The commands that
  touch the state (`init`, `plan`, `apply`, `state pull`) are the ROOT's:
  the identity, storage or instance builder's `executable:` names an
  entry in `cfg/executables.yml`, and that binary is what runs (the
  golden's identity runner calls `/usr/local/bin/tofu`). The backend
  entry's own `executable` field does not pick the binary; since stage 63
  it is a declaration that is CHECKED: when set it must name an entry of
  `cfg/executables.yml` (so the tofu the roots on this backend run is
  declared and version-checked like every other entry), and when unset --
  the default now, where it used to default to `tofu` and be checked by
  nothing until 2026-09-25 -- nothing is checked on the backend's behalf.
  The `local` backend
  is built into OpenTofu and Terraform: it downloads no provider and
  needs no plugin cache entry. This plugin sets no version floor; the
  `version` requirement declared on the root's executable in
  `cfg/executables.yml` is what `validate` and every run check (stage 48).
  OpenTofu 1.12.6 is what the package test and the probes recorded below
  ran against.
- **A directory the operator can write.** `path` names it, relative to
  the configuration root (the directory that holds `cfg/`, `generated/`
  and `meta-state/`) or absolute. It need not exist beforehand: tofu
  creates the directory and the file at the first state write (probed
  2026-09-23 with OpenTofu 1.12.6: `init` against a missing directory
  succeeds, `state pull` answers empty, `apply` creates the directory
  and writes `<workspace>.tfstate`). There is no lock service; tofu's
  local backend locks the file itself for the duration of a command, and
  the system runs one tofu process at a time.
- **The state stays on the machine.** A local state file never travels
  with the configuration repository: the live tree's `.gitignore` ignores
  `*.tfstate`, the run's `--commit` stages only `meta-state/` and
  `generated/` ([meta_state.py](../base/src/cs_image_system/base/meta_state.py),
  `commit_meta_state`), and the public-safe rules refuse a `*.tfstate` at
  any depth under those trees. So a fresh clone, a second machine and CI
  hold NO state for a root bound to this type -- which is why the live
  configuration keeps every root on S3, and why the consequences are
  spelled out under "When it fails".
- **The private mirror.** Since stage 49 a real run materialises a root
  into `_private/<lifecycle>/<workspace>/<phase>/` and runs tofu there.
  `mirror_path` in
  [materialize.py](../base/src/cs_image_system/base/materialize.py) puts
  `_private/` exactly where `generated/` stands, at the same depth, so
  `../../../../<directory>/<workspace>.tfstate` counts up to the same
  configuration root from either tree and one state file serves both. No
  `_private/state/` is ever created.
- **Reads across types.** A consumer root (an S3-bound storage or
  instance root reading the identity root's outputs) gets a
  `terraform_remote_state` data source with `backend = "local"` and the
  same relative `path`. Terraform reads that file on the machine where the
  consumer's plan runs: the producer's state must be present THERE.

## Configuration reference

The entry under `state_backends:` in `cfg/state-backends*.yml`. The model
is a pydantic dataclass with `extra="forbid"`: an unknown key is refused at
load, and a `parameters:` key is refused with a message naming
`variables:` (stage 26). Inherited fields come from `NameTyped` and
`BuilderModel` in
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py);
`StateBuilderModel` adds nothing but the classification, and a state
backend has no `runtime` field.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | The backend's name, normalised at load (lowercased, spaces and `:` to `_`); `/` and `\` are refused. This is the value a root's `state_configuration:` (or a runtime's) names; the collector looks the name up first and then the backends' `aliases` (stage 63). |
| `type` | str | required | `local`. Selects this plugin at load and is the terraform backend type written into the consumers' `backend "local" {}` block and `backend = "local"` data sources. |
| `path` | str | `state` | The directory the state files live in. Whitespace is stripped; empty or blank is refused at load. Relative means relative to the configuration root; absolute is kept as declared. Normalised for the location: repeated slashes collapsed, a leading `./` dropped, a trailing `/` dropped. No `~` or environment-variable expansion. Since stage 63 the normalised form may not contain a `.` or `..` segment (`a/../b`, `./x/./y`, `..`, `../state` are refused at load) and may not be the bare filesystem root `/`: one directory has one spelling. `path: .` (or `./`) alone is still accepted: it is the configuration root itself, one spelling of one directory. Until 2026-09-25 a `..` segment was kept as written (so `a/../b` and `b` were two locations to the collision check), and `path: /` rendered `//<workspace>.tfstate`. Each bound workspace gets `<path>/<super_safe_name(workspace)>.tfstate`. |
| `is_default` | bool | `false` | Marks the backend that `state_configuration: default` (and an omitted field) resolves to. More than one default among the declared backends is refused when a root resolves it. |
| `description` | str or null | null | Accepted, not read. |
| `aliases` | set[str] | `{}` | Other names the backend answers to (stage 63). They travel on the `BackendRegistration`, and the collector's `resolve_backend` tries the backend names first and then every backend's aliases, so a root's (or runtime's) `state_configuration:` may name an alias and `validate` accepts the binding. Until 2026-09-25 aliases were registered and never read, and a binding to one was refused as not declared. The records (`# state:` header, `state-locations.yaml`) still name the backend by its `name`. |
| `executable` | str or null | null | The `cfg/executables.yml` entry the tofu for the roots on this backend comes from (stage 63). Unset (the default): nothing is checked on the backend's behalf. Declared: `validate` and every run refuse a name that is not an entry of `cfg/executables.yml` (`check_state_backend_executables`), and the entry itself is version-checked like every executables entry (stage 48). The plugin still runs nothing under it, and the binary a root runs is still the root builder's own `executable`. Until 2026-09-25 the field defaulted to `tofu` and was checked by nothing. |
| `config` | dict | `{}` | Accepted, not read. |
| `gitignore` | list[str] | `[]` | Accepted, not read. |
| `tags` | dict[str, str] | `{}` | Accepted, not read. |

`path` is the only field the kind renders from: it is the one setting the
registration carries (`settings={"path": ...}`). `aliases` travel beside it
on the registration for the lookup, and `executable` is read by
`validate`, not by the plugin.

Fields outside this file that decide what the entry does:

| Where | Field | Effect |
|---|---|---|
| `cfg/_config.yml` | `config.use_state_backends` | The gate. False: the entry is inert. |
| a root's builder (group, user, storage, instance) | `state_configuration` | Names this backend, or `default`; the root's own value wins, else its runtime's, else the default (stage 46). |
| a runtime builder | `state_configuration` | The second rung: every storage and instance root on that runtime inherits it unless the root names its own. The identity roots have no runtime and skip this rung. |

See [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 10 for
the chain and the collision rule in full.

### Variations

- **Relative vs absolute `path`.** When `path` is relative (`state`,
  `state/dev`), the backend file and every data source carry
  `../../../../<directory>/<workspace>.tfstate`, climbing four directories
  from the phase directory to the configuration root, and the emission
  names nothing of the generating machine. When `path` is absolute
  (`/var/tf/state`), the file carries `/var/tf/state/<workspace>.tfstate`
  verbatim: the emission then names a path that must exist on every
  machine that runs the root, and a fresh clone elsewhere cannot use it
  unchanged. The location record and the `# state:` header show the
  declared directory in both cases (`local://state/...`,
  `local:///var/tf/state/...`).
- **`path: .`** (or `./`): the state files live in the configuration
  root itself, and the backend file carries
  `../../../../<workspace>.tfstate` with no directory segment. This is the
  one place a `.` is accepted: stage 63 refuses a `.` or `..` segment
  inside a longer path, not `.` alone.
- **Named vs alias binding.** A root may name the backend by its `name`
  or by any of its `aliases` (stage 63); both resolve to the same
  registration and the same location, so switching a root from one
  spelling to the other moves nothing.
- **`executable` declared or not.** Unset, nothing about the backend is
  version-checked. Declared (`executable: open-tofu-1`), the name must be
  an entry of `cfg/executables.yml`, and that entry's version requirement
  is checked by `validate` and at the head of every run (stage 63).
- **Settings that were encrypted.** Any value may be an `ENC[age:...]`
  marker. Since stage 63 the partial configuration file writes such a
  setting as the ciphertext it was read from (`render_backend_value` in
  the collector calls `emit`), and the execution's materialise step puts
  the plaintext back in the `_private/` copy tofu runs from; until
  2026-09-25 it was written in clear and only the plaintext guard caught
  it. A `path` is not a secret, so for this type the rule is a
  consistency guarantee rather than a practical option; the data source,
  the `# state:` header and the location record are not part of that
  change.
- **Dry run vs real run.** A dry run (the default) initialises every root
  with `init -backend=false`: providers are installed and the emission is
  validated, but the backend file is not read, the state directory is not
  created and no state file is touched. The frozen fixture's proof runs
  are dry, which is why `tests/fixtures/config/` has no `state/`
  directory. A real run (`--no-dry-run`) initialises with
  `init -input=false -reconfigure -backend-config=<workspace>-<phase>.tfbackend.hcl`,
  at generation time and again in the runner script before every plan,
  and every plan and apply then reads and writes the file on disk.
- **`use_state_backends` on vs off.** On, everything above. Off, the entry
  is loaded and registered but no root is bound: no block, no file, no
  data source, no header line, no location record, and the collision and
  move checks skip (`check_state_locations` returns nothing when backends
  are disabled).
- **Named vs default vs inherited binding.** A root that names this
  backend (`state_configuration: local-dev`) is bound to it whatever its
  runtime says. A root at `default` on a runtime whose
  `state_configuration` names a backend inherits THAT one. Only a root at
  `default` with no runtime rung (the identity roots, or a runtime also
  at `default`) takes the entry marked `is_default: true`.
- **This type vs the object-store types.** The S3 and GCS kinds render a
  bucket, a key or prefix and, for the backend file, encryption, locking
  and identity settings; this kind renders one `path` in both the backend
  file and the data source, and the stage-39 encryption rule
  ([test_v2_state_encryption.py](../../tests/test_v2_state_encryption.py))
  is scoped to `s3` and does not apply to it. A consumer in one type reads
  a producer in another through a data source of the PRODUCER's type: an
  S3-bound root reading a `local`-bound one emits
  `backend = "local"` with a `path`, and the read happens on disk.
- **`--migrate-state <root>` on a root bound to this type.** The move
  operation (stage 46.4) is type-agnostic: `state-migration begin` writes
  the previous location from `meta-state/state-locations.yaml` beside the
  root as `<workspace>.tfbackend.previous.hcl`, initialises against the
  new file and pulls; for a `local` new location that has no file yet
  the pull answers empty and the location counts as empty, so the move
  proceeds (`init -migrate-state -force-copy`, a plan that must be clean,
  `state-migration finish`). A dry run refuses the flag outright.
- **CI.** The CI recording job is dry, so it never initialises against
  the file and never needs the directory; the `perform` job runs the live
  tree, which binds no root to this type.

## What it tests and verifies

- **At load (pydantic, `__post_init__`).** `path` empty or whitespace is
  refused; the value is stripped. The common checks apply: `name` with
  `/` or `\` is refused, a name in the reserved set (`default`, `self`,
  ...) is refused, an unknown key is refused, `parameters` is refused.
  Since stage 63, a `path` whose normalised form has a `.` or `..`
  segment, or is the bare `/`, is refused too (messages under "When it
  fails").
  The verdict is a load error: the command that loaded the configuration
  (`validate`, `run`, anything) stops before any check runs, with the
  pydantic or `ValueError` message on stderr and exit 1.
- **At `finalize()` (configuration load, before any generation phase).**
  The model registers `BackendRegistration(name, "local", {"path": ...},
  LOCAL_KIND, is_default, aliases)` with the run-wide `TerraformCollector`
  (the aliases since stage 63). A
  second registration under the same name with different settings is
  refused (`HclConfigConflictError`); the same settings again are a
  no-op.
- **At `validate`, and at the head of every `run`
  (`check_state_locations` in
  [validate.py](../base/src/cs_image_system/base/commands/validate.py)).**
  From the declarations alone, with nothing generated: every terraform
  root's backend is resolved through the chain (by name, or by alias
  since stage 63) and must be declared;
  more than one `is_default` among the backends is refused; every root's
  location is rendered by this kind (`local://<directory>/<workspace>.tfstate`)
  and no two roots may share one; and a root whose resolved location
  differs from the one `meta-state/state-locations.yaml` recorded is
  refused while the records show live resources in it (a storage not
  destroyed, a group or user the identity read-model attributes to it
  after an executed identity run, an instance pinned to a build). A root
  with nothing deployed moves with one INFO line. Verdicts are entries in
  the validation error list: `validate` prints each and exits 1;
  `run` records them in `generated/run-summary.json` under
  `validation_errors`, generates nothing and exits 1.
- **At `validate` and every run, the executables check
  (`check_state_backend_executables`, stage 63).** A backend entry whose
  `executable` is declared must name an entry of `cfg/executables.yml`;
  that entry is version-checked with the others (stage 48). An unset
  `executable` is skipped. Until 2026-09-25 the backend's `executable`
  was not among the executables checked.
- **At generation.** Each root binds itself with `set_backend`; a second
  binding of one workspace to a different backend is refused
  (`HclConfigConflictError`). Before the terraform block is rendered the
  collector runs `validate_state_locations()` again over the bound
  workspaces. The kind then renders the backend file, the data sources
  and the `# state:` header, and the run records every bound workspace's
  location in `meta-state/state-locations.yaml` as `backend`, `type`,
  `location` and the file's `path` (a migrating root keeps its old record
  until `finish`).
- **At apply.** Nothing of the plugin's. Tofu's own `init` (real-run
  form) validates the backend file and `plan`/`apply` read and write the
  state file; their verdicts are tofu's exit codes in the runner, and
  the run's `apply` status in `run-summary.json` and `meta-state/runs.yaml`.
- **After apply (post-finalize hooks).** Nothing: the builder implements
  no hooks.
- **In the state query.** Nothing: this plugin contributes no provider
  view, and the state file itself is never inspected by the system. The
  only memory the system keeps of where the state is, is the location
  record above.
- **In the suite.** [test_local_backend.py](tests/test_local_backend.py)
  pins the three renderings (relative, absolute, normalised spelling),
  the collision rule across types, and a real `tofu init` plus
  `state pull` with an empty environment (skipped when `tofu` is not on
  the PATH). [tests/test_v2_state_locations.py](../../tests/test_v2_state_locations.py)
  and [tests/test_v2_gate4_identity_storage.py](../../tests/test_v2_gate4_identity_storage.py)
  pin the golden's record, header line and cross-type data source.

## When it fails

### Failures that have happened

- **2026-09-19, the private mirror one level too deep.** Found by probing
  an availability-zone change: `tofu init` in the materialised copy
  could not read its module, because the mirror stood one directory
  deeper than the root it mirrored. Every relative path in an emission counts
  directories up to the configuration root, and this type's
  `../../../../<directory>/<workspace>.tfstate` is one of them: from the
  deeper mirror it would have named a directory that does not exist
  (or, worse, a different `state/` under `_private/`) and a real run
  would have planned against an empty state. The fix in
  [materialize.py](../base/src/cs_image_system/base/materialize.py)
  (`mirror_path`) replaces the generation directory's name with
  `_private` instead of nesting under it, and its docstring names this
  type. What to look for if it recurs: an `init` or `plan` in
  `_private/...` that fails to find a module source or reports an empty
  state while `generated/...` on the same machine has it; compare the
  depth of the two directories.

### Failures the code raises

- `Terraform state backend 'path' cannot be empty for 'local' type.` --
  at load, `path: ""` or `path: "   "`. Give the entry a directory or
  delete the key (the default is `state`).
- ``state backend '<name>': `path: <path>` has a `.` or `..` segment;
  write the directory once, without them`` -- at load (stage 63), a
  `path` such as `a/../b`, `./x/./y`, `..` or `../state` (`.` alone is accepted). Write the
  directory the way it is meant (`b`, `x/y`), or give an absolute path
  for a directory outside the configuration root. Until 2026-09-25 such a
  path was accepted and `a/../b` was a different location from `b` to the
  collision check.
- ``state backend '<name>': `path: /` would put state files in the
  filesystem root; name a directory`` -- at load (stage 63), `path: /` (or
  `//`). Until 2026-09-25 it rendered `//<workspace>.tfstate`. Name a real
  directory.
- `Executable <x> specified for state backend <name> not found in
  executables list.` -- at `validate`/`run` (stage 63), the entry's
  `executable` names nothing in `cfg/executables.yml`. Fix the spelling,
  declare the entry, or remove the key (unset means unchecked).
- `Name '<name>' contains invalid characters: {'/', '\\'}` -- at load, a
  backend name with a slash. Name it without one; the directory belongs
  in `path`.
- A pydantic "extra inputs are not permitted" error naming the key -- at
  load, a key the model does not have (a `bucket:` or `key:` copied from
  an S3 entry, a typo). The only own field is `path`.
- A message saying `parameters` was retired (stage 26) and naming
  `variables:` -- at load; delete the key.
- `State backend '<name>' registered twice with different configurations`
  -- at load (`finalize`), two entries with one name across the
  `state-backends*.yml` files. Rename one.
- `workspace '<ws>' names state backend '<name>', which is not declared`
  -- at `validate`/`run`, a root's (or its runtime's) `state_configuration`
  names something no entry is registered under, by name or by alias.
  Check the spelling against the entry's `name` and `aliases` (an alias
  resolves since stage 63; until 2026-09-25 it was refused here).
- `Multiple default state backends registered: [...]` -- at
  `validate`/`run` when a root resolves `default` and more than one entry
  says `is_default: true`. Leave one.
- `state location collision: workspaces <a>, <b> would share the state
  object local://<directory>/<name>.tfstate` -- at `validate`/`run`: two
  roots on one directory whose names collapse under `super_safe_name`
  (`ws-local` and `ws_local`), or two backend entries that normalise to
  one directory (`state` and `./state//`). Rename a root or separate the
  directories. The check compares the normalised directory; since stage
  63 a `.` or `..` segment is refused at load, so `a/../b` can no longer
  slip past as a second spelling of `b` (it could until 2026-09-25). An
  absolute path is still never matched against the relative spelling of
  the same directory.
- `Workspace '<ws>' is bound to state backend '<x>' and cannot be rebound
  to '<y>'` -- at generation, a builder trying to bind one workspace to
  two backends; not reachable from configuration alone.
- `workspace '<ws>' would move its state from local://... to <new> while
  <what stands> stand(s) in it: the new location is empty, so the next
  plan would create everything again and strand the old state. To MOVE
  the state: `run --no-dry-run ... --migrate-state <ws>` ...` -- at
  `validate`/`run`, after a root bound to this type is rebound (to S3, or
  to another directory) while its records show live resources. Either
  run the migration, or correct the records if the resources are gone;
  never edit the record to get past it.
- `--migrate-state moves state and needs --no-dry-run: a dry run never
  moves state` -- on stderr, exit 2, before the configuration loads.
- `state-migration begin: the new location local://... already holds
  state (lineage ...) that is not this workspace's: a collision, refused.
  The old state is untouched.` -- in the runner of a migrating root, when
  a file already exists at the new path from another lineage. Move or
  remove that file by hand after checking whose it is.
- `State backend '<name>' (type 'local') was registered without a kind`
  -- cannot occur through this model, which always supplies `LOCAL_KIND`;
  it is the collector's guard for a hand-built registration.

### Failures tofu raises that this type invites

The system never inspects the state file, so these surface from tofu in
the runner (a non-zero exit stops the runner at that root; the run
records the lifecycle's apply as `failed`).

- **A plan that creates everything again, on a machine that has no state
  file.** The state stays on the machine that applied (see
  "Prerequisites"), so a real run of a `local`-bound root from a fresh
  clone, another machine or CI finds an empty location and the plan
  proposes every resource anew. Nothing in the system refuses this: the
  location record matches (same `local://...`), so the move guard is
  silent; only the plan's size and the `gate-plan` step (which refuses
  destroys, not creates) stand between the operator and a duplicate
  deployment. Where to look: `<workspace>.tfstate` under the declared
  directory on the machine that last applied; the `# state:` header of
  the runner script names the directory. What to do: copy the file, or
  bind the root to an S3 backend and migrate. This is the reason the
  live configuration keeps every root on S3.
- `Error: Unable to find remote state` / `No stored state was found for
  the given workspace in the given backend.` -- from `plan` in a CONSUMER
  root (an S3-bound storage or instance root reading a `local`-bound
  producer through its `terraform_remote_state` data source) when the
  producer's file is absent on the machine running the plan (probed
  2026-09-23 with OpenTofu 1.12.6). The producer root has never been
  applied here, or was applied elsewhere. Apply the producer first, on
  this machine, or bring its state file.
- `Backend configuration changed` -- would follow from a changed `path`
  on a root initialised against the old one, but every init the system
  emits carries `-reconfigure`, so it does not occur under the system's
  own commands; a hand-run `tofu init` without the flag can hit it.
- A permission error from `apply` or `state push` writing under `path` --
  the directory (or a parent tofu must create) is not writable by the
  operator. Fix the directory; nothing in the system pre-checks it.

## Related

- [tf-s3-state-plugin](../tf-s3-state-plugin/README.md): the S3 type, and
  the recipe for adding a type.
- [hashicorp-utils](../hashicorp-utils/README.md): the collector and the
  `BackendRegistration` / `StateLocation` contract.
- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 10 and
  [docs/OPERATIONS.md](../../docs/OPERATIONS.md) "Where state lives".
