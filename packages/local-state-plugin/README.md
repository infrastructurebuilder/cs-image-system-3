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

## The model

| Field | Type | Default | Meaning |
|---|---|---|---|
| common builder fields | | | `name` is what a root's `state_configuration` names; `is_default` marks the backend `default` resolves to |
| `path` | str | `state` | a directory: relative to the configuration root, or absolute |
| `executable` | str or null | `tofu` | |

## The kind

`LocalBackendKind` in
[local_state_models.py](src/cs_image_system/local_state_plugin/local_state_models.py)
renders the type for the collector (the contract the S3 plugin's README
describes under "Adding a backend type"):

| `location(settings, workspace)` | `backend_settings(...)` | `remote_state_settings(...)` |
|---|---|---|
| `local://<directory>/<super_safe_name(workspace)>.tfstate`, the directory normalised (repeated slashes collapsed, `./` and a trailing slash dropped, an absolute path kept) | `path = "<state path>"` | `path = "<state path>"` |

The state path is the absolute directory as declared, or, for a relative
one, the directory rewritten from the root directory's fixed depth:
`../../../../<directory>/<workspace>.tfstate` (a root sits at
`generated/<lifecycle>/<workspace>/<phase>/`, four below the configuration
root). The emission therefore names no absolute path of the machine that
generated it, and the same file works from a fresh clone.

Two roots on one directory whose names collapse under `super_safe_name`
would share a state file and are refused by the stage-46 collision check;
the same name under `s3` and under `local` are two locations, not a
collision.

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

## Related

- [tf-s3-state-plugin](../tf-s3-state-plugin/README.md): the S3 type, and
  the recipe for adding a type.
- [hashicorp-utils](../hashicorp-utils/README.md): the collector and the
  `BackendRegistration` / `StateLocation` contract.
- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 10 and
  [docs/OPERATIONS.md](../../docs/OPERATIONS.md) "Where state lives".
