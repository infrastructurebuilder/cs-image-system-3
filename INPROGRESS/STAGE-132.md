# 132. Hygiene bundle XXV

**Status: EXECUTED 2026-11-12 on feature/hygiene-xxv; waits for
"merge 132". Items 1 to 6 landed (item 5 by decision, with its
reminder); item 7 lists the cuts' findings for the next bundle. The
bar and the full-test legs are green.**

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
   a per-run handle. 0.1.7 was released on 2026-11-12, so nothing
   holds this but its "do 132".
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
   cut (found by §130). The operator, 2026-11-12: all six in this
   bundle, each its own commit.
5. **YOUR DECISION:** nine fields carry `# pyright:
   ignore[reportIncompatibleVariableOverride]` where a subclass
   narrows a pydantic field on purpose (`credentials` on the AWS
   runtime model; `variables` on the storage models of tf-docker,
   tf-ebs and tf-gcp; `description` on the OS builder's runtime
   config): the narrowed type is what refuses an unknown key, and
   pyright's invariance rule cannot say "narrowed only". The default is
   no change (the ignores stand, as the mod builders' method-override
   ignore does); the alternative makes the base models generic over the
   field's type, a refactor (found by §130). The operator,
   2026-11-12: the ignores stand, with a reminder in
   [REMINDERS.md](../REMINDERS.md) to revisit them before 1.0.
6. A recording made by a CLI that is not the tree's pinned release
   commits an emission that CI's drift check then calls BEHIND. The
   reference's `.envrc` points `CSIS` at a development checkout (the
   documented arrangement for a checkout beside the tree), so `just
   record` there ran unreleased code against a `.csis-version` of
   0.1.7.dev2; the push failed CI's `live` job at `config-drift` (six
   files, the emission moves of §130; 2026-11-11, cured by a record
   with `CSIS` set to the pinned release). A committing run
   (`--commit`) reads the tree's `.csis-version` and says, before it
   generates, when the version running is not the pin. **YOUR
   DECISION:** it refuses unless told to go on (a flag), the default,
   or it warns and goes on. Either way the boxes for a reference
   record name the CLI they mean (found 2026-11-11, the record of
   §130's item 14). The operator, 2026-11-12: it refuses unless
   told. The check also refuses a development install whose version
   equals the pin, which is what the two were on 2026-11-11 (both said
   0.1.7.dev2); the flag is `--allow-unpinned`, or `CSIS_ALLOW_UNPINNED`
   in the environment.
   Asked while it was built (the operator, 2026-11-12): `lineage
   restamp --commit` is held to the pin as well, because a restamp by
   unreleased code records fingerprints the pinned release may not
   agree with; `dispose image --commit` is not, a disposal recording
   what was removed whatever the code's version.
7. Found by item 4's cuts and left alone, because a cut changes no
   behaviour; each is a finding for the next bundle, which takes this
   list at "merge 132". The one that may matter most is (h).
   a. `read_config_and_transform`: `if not root_dir` is checked only
      after the plugins load and the catalog exists; the `else` that
      would read the configuration's `working_directory` is dead (a
      `Path` is always truthy) while an assert still requires it.
   b. The loader's second "no runtime builders" check can never run.
   c. The loader's `isinstance(config_data, list)` after structuring is
      dead, and comes after an assert that reads the structured value.
   d. `verbose` writes `./YAML_DUMP.yaml` into the invoking directory,
      before the loader changes into the root.
   e. The builder families are built in one order and listed in
      another (`_build_builders` says which).
   f. `reg.get_default_for(vct) != None`, and the same lookup again
      inside the warning.
   g. `resolve_all` compiles the replace template once for nothing
      before it renders it; a syntax error there raises outside the
      `try`.
   h. A plain mapping in the resolver's map renders with
      `template.render`, not `render_inheriting`
      (`TemplateResolver._resolve_mapping`), so a value derived there
      from a decrypted one does not inherit its encryption; every
      other render site inherits. Check whether such a mapping can
      reach the emission, and make it inherit.
   i. The resolver stops after five passes without a word, even with
      templates left; an `UndefinedError` in a replace template also
      skips that field's foreign-key keep for the pass.
   j. `upgrade_deferred_list_generated`'s "can't happen" branch happens
      when the registry's default name is an empty string.
   k. Its last fallback looks up the default item's type under the
      BUILDER classification where the item classification looks
      meant, and its debug line names a builder it then does not use.
   l. Its `if deferred_item_vct:` is always true after the assert.
   m. Its `model_id` warning says the item will not be added to the
      flattened map; it is added.
   n. It computes metadata and subitem overrides for every field of
      every model before asking whether the field is deferred.
   o. `run_lifecycles`: an `--only` refusal returns a summary with
      `requested=[]` that is never written, recorded or handed to the
      on-summary hooks, after the hook plugins have loaded and the
      generated lifecycles were reset.
   p. `{...} or None if force_bake else None` is right only by operator
      precedence.
   q. `register_provider_aliases` writes aliases for a machine that has
      no registry record of its own yet.
   r. On a non-zero return code its `out.strip()` sits outside the
      `try`, so a runtime answering with no output would raise out of
      the after-apply hook.
   s. `(recorded.get(name) or {})` is evaluated three times.

**Acceptance**: each item its own commit; `just test` green after
each batch and at the end, then `just full-test-legs` once (the
operator, 2026-11-12); one squash, branch kept. Records: the squash; this section goes
at "merge 132".
