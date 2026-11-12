# 133. Hygiene bundle XXVI

**Status: IN PROGRESS since "do 133", 2026-11-12 (opened the same
day; the decisions are under each item).**

The findings carried out of [§132](../docs/CHANGES.md#s132)
(hygiene bundle XXV), none blocking, each its own commit on the
bundle's branch. Items 1 to 19 are what §132's six complexity cuts met
and left alone, because a cut changes no behaviour; the one that may
matter most is item 8.

1. `read_config_and_transform` (`config_loader.py`): `if not root_dir`
   is checked only after the plugins load and the catalog exists; the
   `else` that would read the configuration's `working_directory` is
   dead (a `Path` is always truthy) while an assert still requires it.
2. The loader's second "no runtime builders" check can never run.
3. The loader's `isinstance(config_data, list)` after structuring is
   dead, and comes after an assert that reads the structured value.
4. `verbose` writes `./YAML_DUMP.yaml` into the invoking directory,
   before the loader changes into the root. The operator, 2026-11-12:
   it goes under the root's `_private/`.
5. The builder families are built in one order and listed in another
   (`_build_builders` says which).
6. `reg.get_default_for(vct) != None`, and the same lookup again
   inside the warning.
7. `resolve_all` (`orchestrator.py`) compiles the replace template once
   for nothing before it renders it; a syntax error there raises
   outside the `try`.
8. A plain mapping in the resolver's map renders with
   `template.render`, not `render_inheriting`
   (`TemplateResolver._resolve_mapping`), so a value derived there from
   a decrypted one does not inherit its encryption; every other render
   site inherits. Find whether such a mapping can reach the emission,
   and make it inherit either way, with a test that a derived leaf
   stays an `ENC[...]` marker.
9. The resolver stops after five passes without a word, even with
   templates left; an `UndefinedError` in a replace template also skips
   that field's foreign-key keep for the pass. The operator,
   2026-11-12: the limit stays and a warning names every field still
   holding a template after the last pass.
10. `upgrade_deferred_list_generated`'s "can't happen" branch happens
    when the registry's default name is an empty string.
11. Its last fallback looks up the default item's type under the
    BUILDER classification where the item classification looks meant,
    and its debug line names a builder it then does not use.
12. Its `if deferred_item_vct:` is always true after the assert.
13. Its `model_id` warning says the item will not be added to the
    flattened map; it is added.
14. It computes metadata and subitem overrides for every field of every
    model before asking whether the field is deferred.
15. `run_lifecycles`: an `--only` refusal returns a summary with
    `requested=[]` that is never written, recorded or handed to the
    on-summary hooks, after the hook plugins have loaded and the
    generated lifecycles were reset. The operator, 2026-11-12: the check
   comes first, so the refusal changes nothing and records nothing.
16. `{...} or None if force_bake else None` is right only by operator
    precedence.
17. `register_provider_aliases` writes aliases for a machine that has
    no registry record of its own yet. The operator, 2026-11-12: such a
    machine is passed over and said, as a machine that is off is.
18. On a non-zero return code its `out.strip()` sits outside the `try`,
    so a runtime answering with no output would raise out of the
    after-apply hook.
19. `(recorded.get(name) or {})` is evaluated three times.
20. A commented-out block in `models/builder_model.py` (about line 220)
    still calls the `Orchestrator()` that §132 deleted; dead text goes.
21. Since §132 two runs can share one process (the nested teardown run
    executes in process). What a plugin caches for the whole process
    (`functools.cache` functions, SDK clients, the scan's runtime secret
    rules) is now shared by both: list every such cache in base and the
    plugins and say, per cache, why sharing it is safe or make it per
    run (found by §132 item 2).
22. [§113](STAGE-113.md)'s plan names modules §132 retired
    (`global_context`, `singleton`, the `GlobalTypeContext` imports of
    seven plugin modules); its import counts were taken before them.
    Re-measure before "do 113" and correct the plan (checked against
    the re-examination, as every plan is).
23. `SCC_ALL_MAX` in `tests/test_import_closure.py` is 45, above the
    measured 27: the ceiling falls to the measurement (found by item
    22).
24. `docs/DESIGN.md` still says the plugin-import rule has "an
    exception list of four"; the list is empty (found by item 22).
25. The contract's module docstrings still say the core re-exports
    names that were removed with the shims (`constants.py`, `hcl.py`,
    `names.py`, `fields.py`, `field_kinds.py`, `assets.py`,
    `lifecycles.py`): they say where the names live now (found by
    item 22).
26. This repository's own `.gitignore` names no `_private/`, so a run
    over a configuration tree inside it (a copy of the frozen fixture
    under `tests/`) could leave its materialised plaintexts committable;
    only the verbose dump was covered, by its file name. It ignores
    `_private/` at any depth (found by item 4).
27. The narration rule (`tests/test_sources_do_not_narrate.py`) reads a
    docstring and a comment one line at a time, so a token split across
    a line break escapes it: fifteen do today ("stage" at the end of
    one line, the number at the start of the next, in ten source files
    and five tests). The rule also reads each docstring whole and each
    run of comment lines joined, and the fifteen become the behaviour's
    name (found while doing item 25).
28. The narration rule does not read the repository's hook
    (`.githooks/pre-commit`), its `.gitignore`, or the starter trees
    under `docs/examples/` (their Justfiles, workflows, `.gitignore`s,
    hooks, `cfg/` and other YAML comments), which every template
    repository publishes: about a hundred stage, bundle and date tokens
    sit there. The rule gains those areas and they are cleaned, except
    the starters' modification files (`playbooks/`, the scripts a mod
    runs), whose content is hashed into an image's fingerprint and so
    stays as it is. A starter file is release-owned, so the reference
    refreshes these at its next take (found while doing item 27).
29. `base/helpers/config.py` is a dead module (a star import of the
    contract's constants that nothing imports), and `base/utils.py`
    calls its `SYSTEM_CLI` import "re-exported for every caller" while
    every caller imports it from the contract: the module goes, the
    comment says the import is the module's own, and the contract's
    `constants.py` docstring stops naming either (found by item 25).
30. Every run spends four of the resolver's five passes on nothing: an
    image builder subconfig's `machine_type` renders to `default`, the
    templated kind's context step turns it back into its template, and
    each pass reports a change. The output is right; the passes are
    wasted, and the pass-limit warning of item 9 could fire on a tree
    with one more level of templates. Make a field that rendered to its
    own default stay rendered (found by item 9).

**Acceptance**: each item its own commit; a fix that moves the golden
regenerates it in that commit and names every moved line (the
operator, 2026-11-12); `just test` green after each batch and at the
end, then `just full-test-legs` once; one squash, branch kept. Records: the
squash; this section goes at "merge 133".
