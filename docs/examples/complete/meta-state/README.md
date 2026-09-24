# meta-state/

Normally **written by a run** (CONFIGURATION.md section 1.3: the identity
and storage read-models, the storage transitions, lineage, pins, launch
parameters, runs, verifications, image tests, releases, mod tests, state
locations). Two files are hand-written here on purpose:

- [`aliases.txt`](aliases.txt) -- the **alias pool** (stage 59): pre-approved,
  memorable names, one per line, hand-appended in advance. The run that can
  launch a NEW durable machine takes the first free line, records it as that
  machine's alias in its launch parameters, and comments the line out in
  place with what took it and when; a name is spent exactly once. The first
  line shows the spent form. A dry run, a run whose instance roots may not
  apply, and an ephemeral instance draw nothing. `validate` refuses a free
  line that is not a hostname label, repeats another, or is a name the
  configuration already gives an instance.
- [`storage-state.yaml`](storage-state.yaml) -- a **synthetic storage-state
  record** that makes the tree's `state: archived` and `state: destroyed`
  requests legal: the state machine refuses any requested state but `active`
  for a storage that was never applied, so a record saying `mnt_archive` and
  `old-bucket` stand `active` is what lets the declarations in
  [`../storages/storages-aws.yaml`](../storages/storages-aws.yaml) validate.
  In a live tree this file is the run's own record; never hand-edit it there.
