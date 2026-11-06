# 127. Loading once, without the cloud

**Status: OPEN 2026-11-04; RE-EVALUATED 2026-11-05 after §125. Waits
for "do 127"; §124 has landed, so nothing blocks it.**

**Re-evaluated 2026-11-05.** Every finding below still holds, read
against the tree after §124 and §125: the loader is
`base/config_loader.py` (the seven passes, `cycle_yaml` and
`cycle_named_key` in `template_utils.py`, the dead
`original_yaml_strings*` at config_loader.py:477-499); the runtime
model's `finalize()` still queries the cloud at load
(`aws_runtime_models.update_networking`), so item 1 stands and the
session hooks §121 added are its online check; the child-process
runs are `_execute_in_process` in `commands/run_lifecycles.py` and
the deferred queue is the `Finalizer` (§124), the one place item 3
changes. Two things §125 fixed in place: the context handed to a
builder is `RunContextProtocol`, so item 3's in-process call passes
the loaded context without a fetch, and the system CLI is a service
(`ctx.services.cli.system_cli_executable_with_config` returns an
`ExecutableProtocol` whose binary is the CLI): item 3 keeps that
shape and makes the runner resolve such an executable in-process,
the operator's hand-run lines unchanged. Item 4's measure should be
taken now, before the stage, on the fixture and the reference.

Loading a configuration is seven passes (REEXAMINE3 §1.1): the merged
tree is dumped back to a YAML string, re-parsed and re-dumped once per
plugin type with up to ten Jinja cycles each, dict fields are rendered
as JSON strings through Jinja and parsed back, foreign keys are
resolved by mutation inside context building with the errors in a
module global, two dictionaries of per-item YAML strings are built and
never read, and the runtime builders' `finalize()` queries EC2, STS
and Compute during load, so `validate` needs a live session and the
raw pre-reader in `preflight.py` exists to look before loading. During
a run, `_execute_in_process` spawns `cs-image-system` child processes
for materialize, gate-plan, apply-check, state-migration,
prune-attachments, verify and unmount, each re-running the loader;
two materialisation mechanisms coexist (REEXAMINE3 §1.3).

1. No network at load: the runtime's `finalize()` is pure and a
   separate discovery hook fetches the network facts, called by `run`
   and `verify` (cached under `_private/` or the runtime-facts
   record), never by `validate` or a dry generation; `validate
   --online` runs it on request. The raw pre-reader goes; §121's
   session hooks are the online check.
2. One parse: each file is parsed once; interpolation and scoping
   walk the parsed tree; the dump/load round-trips in `cycle_yaml`
   and `cycle_named_key` go; the dead `original_yaml_strings*` go;
   `resolve_all` renders dict values in place; foreign-key resolution
   is an explicit pass before rendering and returns its errors.
3. No child CLI: an `ExecutableModel` whose binary is `cs-image-system`
   calls the function with the loaded context; the runner scripts
   keep their CLI lines for the operator's hand runs. One
   materialisation mechanism remains (**YOUR DECISION:** the
   `materialize` step in the executable list, the default, or the
   context manager).
4. Measured: load time of the fixture and the reference before and
   after, in the squash; the golden proves the output did not move.

**Out of scope**: the 36 lifecycle phases and the 40 classifications;
a change there is its own stage.

**Acceptance**: emission byte-identical; `validate` on the reference
passes with no AWS session and no GCP credentials; `just test`; one
squash, branch kept. Records: the squash; this section goes at
"merge 127".
