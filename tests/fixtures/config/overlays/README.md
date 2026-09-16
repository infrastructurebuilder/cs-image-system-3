# Overlays: transient declarations — the tests' copies

Files here are **never read by the configuration loader**; each is applied
only when an invocation names it with the global `--overlay <file>` option
(repeatable). An overlay's `config:` keys override `cfg/_config.yml` for
that invocation, and its `instances:` / `storages:` entries update the
same-named declaration key by key, add a new one, or (`undeclare: true`)
remove the tree's declaration for that invocation. The generated
`apply-check` re-reads the same overlay at execution, so a runner script
generated under an overlay applies only under that overlay; a named overlay
that is missing is a refusal, not a skip.

These are **test devices** in the frozen fixture. The live configuration
carries no overlays, and no Justfile recipe names one: `just
gce-decommission` passes `--undeclare instance:gce-test` instead, the same
undeclare as a flag.

- `gce-cycle-launch.yaml` — declares `gce-test` and allows the GCE instance
  root to apply (the launch leg's shape).
- `gce-cycle-decommission.yaml` — undeclares `gce-test` for one invocation
  and lets the GCE instance root apply: the overlay `undeclare` form that
  `--undeclare` reproduces.
- `gce-cycle-storage-teardown.yaml` — requests `gce_data` / `gce_bucket`
  `destroyed` for one invocation; by rule a cycle never destroys a
  config-declared storage, so no recipe uses it — it is the pattern a test
  uses for a storage the test itself declared.

The overlays that drove the live proofs are frozen under
`docs/history/overlays/` as evidence, not configuration.
