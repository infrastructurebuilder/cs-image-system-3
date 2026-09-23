# Overlays: transient declarations

Nothing here is read unless an invocation names it with the global
`--overlay <file>` option (repeatable, before the command). An overlay's
`config:` keys override `cfg/_config.yml` for that invocation and its
collection entries update, add or (`undeclare: true`) remove declarations
for that invocation; the tree on disk never changes. Reference:
[CONFIGURATION.md section 12](../../../CONFIGURATION.md#12-overlays).

- `launch.yaml` -- lets the AWS instance root apply for one run, the shape of
  "launch the node now" without editing `cfg/_config.yml`.
