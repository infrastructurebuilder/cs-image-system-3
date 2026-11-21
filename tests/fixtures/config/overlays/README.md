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
carries no overlays, and no Justfile recipe names one; a decommission
recipe passes `--undeclare instance:<name>` instead, the same undeclare as a
flag.

- `aws-cycle-decommission.yaml` — undeclares `test2` for one invocation and
  lets the AWS instance root apply: the overlay `undeclare` form that
  `--undeclare` reproduces.

The overlays that drove the live proofs are frozen under
`ATTIC/history/overlays/` as evidence, not configuration.
