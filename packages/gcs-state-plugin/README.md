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

| Service name (`type:` of a backend entry) | Model class | Builder class | Classifications (VCT) |
|---|---|---|---|
| `gcs` | `GcsStateBuilderModel` | `GcsStateBuilder` | `STATE_BACKEND_MODEL`, `STATE_BACKEND` |

## The model

| Field | Type | Default | Meaning |
|---|---|---|---|
| common builder fields | | | `name` is what a root's `state_configuration` names; `is_default` marks the backend `default` resolves to |
| `bucket` | str | required, non-empty | the state bucket |
| `prefix` | str | `statefiles` | the prefix inside the bucket; each root gets its own beneath it |
| `credentials` | str or null | null | a PATH to a credentials file; never a value |
| `impersonate_service_account` | str or null | null | the service account terraform impersonates |
| `encryption_key` | str or null | null | a customer-supplied encryption key (from the environment in practice) |
| `kms_encryption_key` | str or null | null | a Cloud KMS key name |
| `executable` | str or null | `tofu` | |

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
declaration.

## Related

- [tf-s3-state-plugin](../tf-s3-state-plugin/README.md): the S3 type, and
  the recipe for adding a type.
- [local-state-plugin](../local-state-plugin/README.md): the type that needs
  nothing.
- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 10 and
  [docs/OPERATIONS.md](../../docs/OPERATIONS.md) "Where state lives".
