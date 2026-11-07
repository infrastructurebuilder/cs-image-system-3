# 132. Hygiene bundle XXV

**Status: OPEN 2026-11-07. The open bundle; takes items as they are
found. Waits for "do 132".**

The small findings carried out of [§130](../docs/CHANGES.md#s130)
(hygiene bundle XXIV) and the ones it found, none blocking, each its
own commit on the bundle's branch.

1. The one-release shims of §124 retire in the release after 0.1.7
   (carried from §130 item 19, the operator's choice at "do 130"): the
   `GlobalTypeContext` name and `global_context.py`, the no-argument
   fetch (`run_context.current_context`, `registry.current_registry`,
   the fallback in `BuilderBase._get_context()`), and the `RunContext`
   delegations to the finalizer. The model methods that reach the
   current context or registry (`models/image.py`, `base_image.py`,
   `mixins.py`, `builder_model.py`, the okta and docker
   provider-specific image models, `os_types`, `public_safe`,
   `image_sources`, the two state builders' `session_status`) take
   what they need instead; `version_checker_for(exe)` and the
   `TemplateResolver` (whose `flattened_map` is still process-wide) get
   a per-run handle. Waits for the final 0.1.7.
2. The transient-storage teardown (`retention.
   transient_storage_teardown_command`: `run storage --only none` under
   a different overlay set) is the one deferred system step still run
   as a child process (`run_in_process` in the system's `cli.py`
   declines a nested `run`), because it needs a context loaded under
   other overlays; loading that second context in-process retires the
   last spawn (carried from §130 item 27, the operator, 2026-11-07 at
   "merge 130"). After item 1: a second context loaded in the same
   process today rebinds the process-wide state item 1 retires (the
   no-argument fetch, the current image-source catalog, the template
   resolver's map), so the outer run would read the inner one's.
3. `just lint` (and `lint-fix`, `lint-unsafe-fix`) check `src packages
   tests` and not `scripts/`; `scripts/release.py` passes the rules
   today, nothing holds it there. The recipes name `scripts` too
   (found by §130).
4. The complexity ceiling (`[tool.ruff.lint.mccabe] max-complexity`
   in `pyproject.toml`) is the measured maximum, 49. The six functions
   above 20 named in its comment are the next cuts, highest first
   (`read_config_and_transform` at 49); the ceiling falls after each
   cut (found by §130).
5. **YOUR DECISION:** nine fields carry `# pyright:
   ignore[reportIncompatibleVariableOverride]` where a subclass
   narrows a pydantic field on purpose (`credentials` on the AWS
   runtime model; `variables` on the storage models of tf-docker,
   tf-ebs and tf-gcp; `description` on the OS builder's runtime
   config): the narrowed type is what refuses an unknown key, and
   pyright's invariance rule cannot say "narrowed only". The default is
   no change (the ignores stand, as the mod builders' method-override
   ignore does); the alternative makes the base models generic over the
   field's type, a refactor (found by §130).

**Acceptance**: each item its own commit; `just test` green after
each; one squash, branch kept. Records: the squash; this section goes
at "merge 132".
