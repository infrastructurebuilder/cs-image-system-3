# cs-image-system-gcs-state-plugin

The `gcs` **state backend** plugin (stage 47): a Google Cloud Storage bucket
as a terraform state backend. It registers one model,
`GcsStateBuilderModel`, for entries with `type: gcs` under `state_backends:`
in `cfg/state-*.yml`. Like the S3 and local plugins it emits no files and
runs no commands of its own: a root that binds to it gets an empty
`backend "gcs" {}` block, a partial configuration file, and consumers reading
its state get a `terraform_remote_state` data source with the same settings.

Declaring the type binds nothing. The standing decision keeps every live
root -- the GCE roots included -- on the S3 backend; the fixture declares a
`gcs` backend that no root binds to, so the type loads and renders, and the
golden does not move.

## What it registers

```toml
[project.entry-points."cs_image_system.plugins.state"]
gcs_state_plugin = "cs_image_system.gcs_state_plugin.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/gcs_state_plugin/main.py)
returns a `GcsStateTypes` metadata object (plugin metadata version `1`,
Python `3.13`) that pairs the model with its builder. The package depends
on `cs-image-system-system` and `cs-image-system-hashicorp-utils` at its
own version ([pyproject.toml](pyproject.toml)); the collector the kind
renders for lives in the latter.

| Service name (`type:` of a backend entry) | Model class | Builder class | Classifications (VCT) |
|---|---|---|---|
| `gcs` | `GcsStateBuilderModel` | `GcsStateBuilder` | `STATE_BACKEND_MODEL`, `STATE_BACKEND` |

## The model

`GcsStateBuilderModel` in
[gcs_state_models.py](src/cs_image_system/gcs_state_plugin/gcs_state_models.py)
extends `StateBuilderModel`
([state_builder.py](../base/src/cs_image_system/base/models/state_builder.py)),
which adds nothing over `BuilderModel`
([builder_model.py](../base/src/cs_image_system/base/models/builder_model.py))
except the classification. A state backend has no `runtime` field. Every
field, with its type and default, is in the configuration reference below.
`GcsStateBuilder` in
[gcs_state_builder.py](src/cs_image_system/gcs_state_plugin/gcs_state_builder.py)
extends `StateBuilderBase` and implements no hooks: it exists so the
registry can pair the model with a builder class.

## The kind

`GcsBackendKind` in
[gcs_state_models.py](src/cs_image_system/gcs_state_plugin/gcs_state_models.py)
renders the type for the collector (the contract the S3 plugin's README
describes under "Adding a backend type"). OpenTofu's `gcs` backend stores a
root's state as `<prefix>/<terraform workspace>.tfstate`, and the terraform
workspace is `default` for every root this system emits, so the root's own
prefix is the declared prefix with the root's safe name appended -- two
roots never share an object:

| `location(settings, workspace)` | `backend_settings(...)` | `remote_state_settings(...)` |
|---|---|---|
| `gcs://<bucket>/<prefix>/<super_safe_name(workspace)>/default.tfstate` | `bucket`, `prefix = "<prefix>/<root>"`, then `credentials`, `impersonate_service_account`, `encryption_key`, `kms_encryption_key` when set | `bucket`, `prefix`, then `credentials` and `impersonate_service_account` when set |

`super_safe_name` lowercases the root's name and turns `-`, `.`, `:`, `+`,
`/`, `\`, `@` and spaces into `_`, so the root `gcp-pd` under the declared
prefix `statefiles/csia` keeps its state at
`gcs://csis-sandbox-tfstate/statefiles/csia/gcp_pd/default.tfstate`, and
its partial configuration file reads:

```hcl
# Backend 'gcs-east1' (gcs) partial configuration for workspace gcp-pd
bucket = "csis-sandbox-tfstate"
prefix = "statefiles/csia/gcp_pd"
```

The root's prefix is normalised before it is rendered or compared
(repeated slashes collapsed, leading and trailing ones stripped, case
kept), so `//a//b/` and `a/b` are one place. An empty declared prefix puts
every root directly under the bucket (`gcs://<bucket>/<root>/default.tfstate`).

## Example configuration

[`cfg/state-gcm.yml`](../../tests/fixtures/config/cfg/state-gcm.yml) in the
fixture, declared and bound to nothing:

```yaml
---
state_backends:
  - name: gcs-east1
    type: gcs
    bucket: csis-sandbox-tfstate
    prefix: statefiles/csia
```

The live configuration carries the same file with every line commented out:
a placeholder for the day the GCE roots move, which is a decision, not a
declaration. A file of comments loads as no declaration at all
([tests/test_v2_state_locations.py](../../tests/test_v2_state_locations.py)
proves both shapes).

A root would bind with `state_configuration: gcs-east1` on the builder
(or on its runtime, so that everything on that runtime keeps its state
there); no fixture or live root does.

## Prerequisites and integration

Everything below is what a root BOUND to a `gcs` backend needs; a declared
and unbound backend (the fixture, the live tree) needs nothing beyond the
core, and a dry run never reaches the bucket.

- **The core, and the gate.** `cs-image-system-system` and
  `cs-image-system-hashicorp-utils` at the same version (the package's
  dependencies). The whole state-backend mechanism is gated by
  `config.use_state_backends` in `cfg/_config.yml`: when it is false or
  absent, nothing this plugin registers is rendered, recorded or checked
  (the collector answers "no backend" for every workspace), and none of
  what follows applies.
  Off is itself refused by `validate` when any root would read another's
  outputs through remote state (stage 63 item 19), so it is a shape only
  for a tree where nothing reads anything.
- **A bucket that exists.** The system creates no state bucket: the
  `bucket` field names one the operator made beforehand, in a project the
  identity below can write to. Nothing in the system checks that it
  exists; the first real `tofu init -backend-config=...` against it does,
  and refuses with tofu's own message when it does not.
- **A Google identity for tofu.** This plugin reads no environment
  variable and no credential file. It passes three declarations through
  to tofu, in the root's `.tfbackend.hcl` and in every consumer's
  `terraform_remote_state` data source: `credentials` (a PATH to a
  credentials file -- the emission is committed, so never a value),
  `impersonate_service_account` (the service account tofu impersonates),
  or neither, in which case OpenTofu's `gcs` backend finds its identity
  the way OpenTofu documents (Application Default Credentials, or its own
  `GOOGLE_*` backend variables in the environment of whoever runs
  `init`/`plan`/`apply`). The live convention for GCE is ADC obtained by
  `gcloud auth application-default login --impersonate-service-account=csis-runner@<project>.iam.gserviceaccount.com`
  ([docs/OPERATIONS.md](../../docs/OPERATIONS.md), "Credentials
  contract"). `preflight`, `state query` and every run report whether ADC
  exist (`GOOGLE_APPLICATION_CREDENTIALS`, else
  `~/.config/gcloud/application_default_credentials.json`) as one
  `session:` line -- for the GCE runtimes that declare them; the line
  knows nothing about a state backend, and no session check is made on a
  backend's behalf.
- **Encryption keys, when declared.** `encryption_key` (a customer-supplied
  key) and `kms_encryption_key` (a Cloud KMS key name) are written verbatim
  into the root's `.tfbackend.hcl` when set. That file is part of the
  committed emission, so a raw encryption key does not belong in the
  field: leave it unset and supply it through tofu's environment, or name
  a KMS key (a name, not a secret).
- **The tofu binary.** The consumer root's, not this plugin's: a root's
  `executable` names an entry of `cfg/executables.yml` (the fixture's
  `open-tofu-1`, type `tofu`, `>1,<2`), and that entry is what `validate`
  and every run check. The model's own `executable` field (default
  `tofu`) is accepted and read by nothing; see the reference below.
- **Network.** Whoever runs a real `init`, `plan` or `apply` must reach
  Google Cloud Storage. A dry run initialises with `init -backend=false`
  and never touches the bucket, so CI's dry records, an operator's preview
  and `validate` need no reachability at all.
- **An AWS session, today.** Not for this plugin -- but because every
  live root, the GCE roots included, keeps its state on the S3 backend,
  any GCE lifecycle still needs a live AWS session until the move is
  decided.

## Configuration reference

An entry under `state_backends:` in any `cfg/state-*.yml` (the fixture's
is `cfg/state-gcm.yml`) with `type: gcs`. Unknown keys are refused at load
by pydantic (naming the key); a `parameters:` key is refused with a message
naming `variables:`. Field names are exact: `type` in YAML is the model's
`type_`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | what a root's or runtime's `state_configuration` names; normalised (lowercase, spaces to `_`); `/` and `\` are refused, and so are `default`, `self` and the empty name |
| `type` | str | required | `gcs`; also the terraform backend type written into consumers' `backend "gcs" {}` block |
| `description` | str or null | null | free text; not read |
| `aliases` | set[str] | `{}` | extra names the registry resolves to this backend |
| `is_default` | bool | `false` | the backend `default` resolves to (a root that names none, whose runtime names none); more than one default across all backend types is refused when anything resolves it |
| `bucket` | str | required, non-empty | the state bucket; whitespace is trimmed |
| `prefix` | str | `statefiles` | the prefix inside the bucket; leading and trailing `/` and whitespace are trimmed; each root gets `<prefix>/<root safe name>` beneath it; may be empty, must be a string (`null` is refused) |
| `credentials` | str or null | null | a PATH to a credentials file, never a value; written as-is into the backend file and every consumer's data source when set |
| `impersonate_service_account` | str or null | null | the service account tofu impersonates; written into the backend file and every consumer's data source when set |
| `encryption_key` | str or null | null | a customer-supplied encryption key; written into the backend file only, in clear, when set |
| `kms_encryption_key` | str or null | null | a Cloud KMS key name; written into the backend file only, when set |
| `executable` | str or null | `tofu` | **accepted, not read.** Present for shape parity with the other tofu builders; this plugin runs no commands, and `validate`'s executable check covers runtime, storage, OS, mod, image and instance builders, not state backends (the default `tofu` names no entry in `cfg/executables.yml`, and nothing notices) |
| `required_plugins` | list[`TFTofuPluginModel`] | `[]` | **accepted, not read** |
| `config` | mapping | `{}` | **accepted, not read** |
| `gitignore` | list[str] | `[]` | **accepted, not read** |
| `tags` | mapping[str, str] | `{}` | **accepted, not read** |

What reaches the emission is exactly what `to_backend_registration()`
registers: `bucket`, `prefix`, `credentials`, `impersonate_service_account`,
`encryption_key`, `kms_encryption_key`, plus `name`, `type` and
`is_default` on the registration itself. Two other declarations, owned by
other plugins, decide whether any of it is used:

| Declared where | Field | Effect on this plugin |
|---|---|---|
| `cfg/_config.yml` | `config.use_state_backends` (bool, default false) | off: no backend block, no `.tfbackend.hcl`, no remote-state data source, no location record, no location check -- the declaration is validated at load and then ignored |
| an instance, storage or identity builder; a runtime builder | `state_configuration` (default `default`) | the binding: the root's own value when it names a backend, else its runtime's, else the single `is_default` backend; `gcs-east1` binds a root here |

### Variations

- **Bound or unbound.** When a root's `state_configuration` (or its
  runtime's, or the default) resolves to a `gcs` entry, the root gets the
  empty `backend "gcs" {}` block, the `.tfbackend.hcl` above, an
  `init -reconfigure -backend-config=<file>` on real runs, a
  `# state: workspace <root> -> gcs://...` line in its lifecycle's runner
  header, and a record in `meta-state/state-locations.yaml`; every consumer
  that reads the root's outputs gets a `data "terraform_remote_state"` with
  `backend = "gcs"` and the `remote_state_settings` above. When no root
  resolves to it (the fixture, the live tree) the entry is loaded,
  validated and registered, and nothing else happens: the golden carries
  no `gcs` file.
- **`use_state_backends` on or off.** Off, the plugin's registration is
  inert: `validate` skips the location rules, no file or record names the
  bucket, and `init` runs bare.
- **Dry run or real run.** A dry run's generation-time init is
  `init -backend=false`: providers are installed and the emission is
  validated, and the bucket is never contacted (there is no state to read,
  and nothing after it needs one). A real run's generation-time init and
  the committed runner script's own init are
  `init -input=false -reconfigure -backend-config=<root>-<phase>.tfbackend.hcl`
  (the bare file name; tofu runs inside the phase directory). Both forms
  record the root's location in meta-state; the record is not a claim of
  reality, only of resolution.
- **Identity declared or not.** With `credentials` and/or
  `impersonate_service_account` set, both the backend file and every
  consumer's data source carry them, so a consumer reads the producer's
  state with the same identity the producer wrote it with. With neither,
  the files carry `bucket` and `prefix` alone and tofu resolves the
  identity from its own environment.
- **Encryption keys declared or not.** `encryption_key` and
  `kms_encryption_key` go into the backend file only; a remote-state data
  source never carries them (the test
  [tests/test_gcs_backend.py](tests/test_gcs_backend.py) pins this). Set
  neither and the objects are stored with the bucket's own settings.
- **Declared prefix empty or set.** Empty (`prefix: ""`), a root's object is
  `gcs://<bucket>/<root>/default.tfstate`; set, it is
  `<prefix>/<root>/default.tfstate`. Either way no two roots share an
  object, because the root's own safe name is always a segment.
- **Encrypted or clear values.** Any value in the tree may be an
  `ENC[age:...]` marker and decrypts at load, but this plugin's kind treats
  every setting as a plain string and registers nothing as sensitive: a
  decrypted `bucket`, `prefix`, path or key would be written in CLEAR into
  the `.tfbackend.hcl`, the data sources, the runner header and
  `state-locations.yaml`. The system's plaintext guard then refuses the
  meta-state write and the commit, naming the file and line -- so
  encrypting a backend field is not supported; keep these values public
  (the bucket name is public by decision) or out of the tree (a key in
  tofu's environment). `name` and `type` may not be markers at all.
- **`--migrate-state <root>`.** A root moving onto or off a `gcs` backend
  goes through the migration operation like any other: the record of the
  previous location (`backend`, `type`, `location` and the settings above)
  is what `state-migration begin` writes back as
  `<root>.tfbackend.previous.hcl`; the kind renders it, the operation is
  type-agnostic. No such move has been made.
- **Fixture or live tree.** The fixture declares `gcs-east1` (so the type
  is loaded, registered and rendered in every test run); the live tree
  carries the same file entirely commented out, which loads as nothing. CI
  therefore never sees a `gcs` registration.

## What it tests and verifies

- **At load (pydantic, then `__post_init__`).** `bucket` present and
  non-empty after trimming; `prefix` a string (trimmed of `/` and
  whitespace); unknown keys and `parameters:` refused; `name` free of `/`
  and `\` and not `default`, `self` or empty. A failure is a
  `ValidationError` naming the field, raised while the configuration
  loads, so `validate` and every run stop with exit 1 before anything is
  generated. Then `finalize()` -- called once per model at load, after
  every plugin key has been structured -- registers a `BackendRegistration`
  with the collector; the same name registered twice with different
  settings is an `HclConfigConflictError` (`State backend '<name>'
  registered twice with different configurations`).
- **At `validate`, and again at the start of every run** (gated by
  `use_state_backends`; `check_state_locations` in
  [validate.py](../base/src/cs_image_system/base/commands/validate.py)):
  every terraform root's backend is resolved through the chain from the
  declarations alone; a root naming an undeclared backend, a prefix whose
  rendered key carries a `.` or `..` segment, more than one `is_default`,
  two roots that would share one object (same bucket and normalised
  prefix under two names, or two root names that collapse under
  `super_safe_name`), and a root whose resolved location differs from the
  one recorded in `meta-state/state-locations.yaml` while the records show
  live resources in it, are each one line in the validation errors; exit
  1, nothing generated. A root with nothing deployed moves with one INFO
  line. Note the timing of the `..` rule: the model accepts `prefix:
  a/../b` at load, and the refusal comes when a location is asked for.
- **At generation.** The collector's `validate_all()` (provider
  constraints plus the collision rule) runs before every terraform block,
  provider block, variable block and remote-state data source is rendered;
  a conflict is an `HclConfigConflictError` and the run fails. Each bound
  root's location is written to `meta-state/state-locations.yaml`
  (`backend`, `type`, `location`, the backend-file settings, `run`) and
  named in the runner header. The GCS type's tests here are the four in
  [tests/test_gcs_backend.py](tests/test_gcs_backend.py) (the per-root
  prefix and its normalisation, identity as a path or an impersonation
  never a value, the model's trimming and registration, and a `gcs`
  location as a third kind of place beside `s3` and `local` in the
  collision rule) and the fixture-level test in
  [tests/test_v2_state_locations.py](../../tests/test_v2_state_locations.py)
  (declared, bound to nothing, moves nothing in the golden; its commented
  twin loads as nothing). [tests/test_v2_state_encryption.py](../../tests/test_v2_state_encryption.py)
  requires every declared and emitted `s3` backend to encrypt and counts
  `s3` and `local` files; it asks nothing of `gcs`, and no `gcs` file is
  emitted.
- **At apply.** Nothing of its own. The plugin runs no command; whether
  the bucket exists, is reachable and is writable by the identity is
  established by tofu's `init` against the backend file, and its verdict
  is tofu's output in the run log (and a non-zero exit for the lifecycle).
- **After apply (post-finalize hooks) and in the state query.** Nothing.
  The state query asks runtimes and identity providers, never a state
  backend; the location record is the only memory of where a root's state
  was resolved to, and it is compared, not verified against the bucket.
- **Executable versions.** Nothing: the stage-48 version checks cover the
  declared `executables` and the six builder classes that run tools; a
  state backend's `executable` is not among them.

## When it fails

No failure involving this plugin has happened live: since it landed on
2026-09-17 (stage 47.4) no root has been bound to a `gcs` backend, in the
fixture or in the live tree, so nothing below carries a date. What follows
is what the code raises, in the order an operator would meet it.

- `1 validation error for GcsStateBuilderModel / bucket / Field required`
  or `Terraform state backend 'bucket' cannot be empty for 'gcs' type.` --
  the entry lacks a bucket, or it is blank. Raised at load (the log names
  the file's plugin key and the item that failed to structure); exit 1.
  Add the bucket.
- `prefix / Input should be a valid string` -- `prefix: null` or a
  non-string. The field is a string; omit it for the default `statefiles`
  or write `""` for none.
- `<key> / Unexpected keyword argument` (or pydantic's extra-input
  refusal naming the key) -- a field this model does not have, a typo
  (`impersonate_service_acount`), or an S3 field (`key`, `region`,
  `profile`) on a `gcs` entry. Remove or rename it; the table above is
  the whole set.
- `<name>: `parameters` was retired (stage 26) ...` -- delete the key.
- `Name '<name>' contains invalid characters` / `Name cannot be in
  '['default', None, '', 'self']'` -- rename the backend.
- `Unrecognized type/alias 'gcs' for VCT.STATE_BACKEND_MODEL` (a
  `KeyError` at load) -- the plugin is not installed in the environment
  that loaded the tree (it is a workspace member here, so this means a
  foreign or partial install). Install `cs-image-system-gcs-state-plugin`
  at the system's version.
- `State backend '<name>' registered twice with different
  configurations` -- two files declare the same name with different
  settings (an uncommented live `state-gcm.yml` beside a second copy, for
  instance). Keep one.
- `workspace '<root>' names state backend '<name>', which is not declared`
  -- a root's or runtime's `state_configuration` names a backend no file
  declares; the live tree's `gcs-east1` is commented out, so binding a
  live root to it today fails exactly here. Declare it, or change the
  binding. Exit 1 from `validate` or the run.
- `workspace '<root>': state key '<prefix>/<root>' carries a '..' segment`
  -- the declared prefix contains `.` or `..`. Write a plain prefix.
- `Multiple default state backends registered: [...]` -- two backends,
  of any types, carry `is_default: true`. Keep one.
- `state location collision: workspaces <a>, <b> would share the state
  object gcs://<bucket>/<prefix>/<name>/default.tfstate` -- two root names
  that collapse under `super_safe_name` (`Gcp-PD` and `gcp_pd`) on one
  `gcs` backend, or two `gcs` backends naming the same bucket and prefix
  bound to same-named roots. The same bucket name under `s3` and under
  `gcs` is two places, not a collision. Rename a root or separate the
  prefixes.
- `workspace '<root>' would move its state from <old> to
  gcs://... while <resources> stand(s) in it: the new location is empty,
  so the next plan would create everything again and strand the old
  state. To MOVE the state: run --no-dry-run ... --migrate-state <root>
  ...` -- the guard that makes moving the GCE roots onto a `gcs` backend an
  operation. The record is `meta-state/state-locations.yaml`; the way
  through is the migration operation ([docs/OPERATIONS.md](../../docs/OPERATIONS.md),
  "Where state lives"), never a rebinding. A root with nothing deployed
  logs `moves its state from ... nothing is deployed from it` and
  proceeds.
- `State backend '<name>' (type 'gcs') was registered without a kind` --
  cannot happen through this model (it always registers `GCS_KIND`); it
  would mean a hand-built `BackendRegistration` in a test.
- **tofu refuses at `init`** -- the bucket does not exist, the identity
  cannot read or write it, `credentials` names a file that is not there
  where tofu runs (the real run's commands execute in the `_private/`
  mirror beside `generated/`, so give an absolute path), or the network
  is not there. The message is tofu's, in the run log under the root's
  init, and the lifecycle exits non-zero; the plugin makes no claim of its
  own. Only a real run gets here; a dry run's init is `-backend=false`.
- **`meta-state/<file>: <line>` from the plaintext guard, or a refused
  commit** -- a backend field was declared as an `ENC[age:...]` value and
  its plaintext now stands in a record or in the emission. Encrypting a
  backend field is not supported (see Variations); write it in clear or
  move it out of the tree.

## Related

- [tf-s3-state-plugin](../tf-s3-state-plugin/README.md): the S3 type, and
  the recipe for adding a type.
- [local-state-plugin](../local-state-plugin/README.md): the type that needs
  nothing.
- [hashicorp-utils collector.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py):
  `TerraformCollector`, `BackendRegistration`, `StateLocation` and the
  `BackendKind` protocol this plugin's kind implements.
- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 10 and
  [docs/OPERATIONS.md](../../docs/OPERATIONS.md) "Where state lives".
