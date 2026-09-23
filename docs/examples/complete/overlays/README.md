# Overlays: transient declarations

Nothing here is read unless an invocation names it with the global
`--overlay <file>` option (repeatable, before the command). An overlay is a
mapping whose keys are `config` and/or a collection key (`users`, `groups`,
`storages`, `images`, `instances`, `base_images`); `config:` keys override
`cfg/_config.yml` for the invocation, a same-named entry is updated key by
key, a new name is added for the invocation, and `undeclare: true` removes
the tree's declaration for the invocation. The generated runner scripts
carry the overlays they were generated under and `apply-check` re-reads
them at execution. `--undeclare <kind>:<name>` is the undeclare form as a
flag. Reference: [CONFIGURATION.md section 12](../../../CONFIGURATION.md#12-overlays).

- `apply-identity-and-storage.yaml` -- `config:` only: let two lifecycles apply for one run.
- `gce-cycle-launch.yaml` -- a NEW transient instance plus the GCE instance root allowed to apply.
- `gce-cycle-decommission.yaml` -- the `undeclare` form: the tree's `gce-node` is undeclared for one run.
- `gce-cycle-storage-teardown.yaml` -- same-named storages updated key by key (`state: destroyed`).
- `archive-volume.yaml` -- one storage's requested state changed for one run.
