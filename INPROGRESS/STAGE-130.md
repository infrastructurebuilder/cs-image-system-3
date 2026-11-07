# 130. Hygiene bundle XXIV

**Status: OPEN 2026-11-04. The open bundle; takes items as they are
found. Waits for "do 130".**

The small findings of the three reviews, none blocking, each its own
commit on the bundle's branch.

1. `meta_state.ALL_FILES` lists all fifteen meta-state files (seven
   are missing: image-tests, state-locations, instance-state,
   login-proofs, releases, mod-tests, aliases); `_dump` writes through
   a temporary file and `os.replace`; a test for each (REEXAMINE3
   §1.4).
2. Dead material: `helpers/async_utils.py` and
   `helpers/yaml_process.py` if still unreferenced after §127;
   `bin/manage_ec2.sh`.
3. The devcontainer installs `just` (the single entry point is not
   the entry point there).
4. The release family's bash becomes `scripts/release.py` with unit
   tests behind a three-line recipe; the sibling repository's working
   tree is read through one documented function; the release appends
   `docs/CHANGES.md` (§119's owed item).
5. The lint bar, once §124 and §127 have lowered the `Any` count:
   ruff gains `B`, `I`, `C90` (a complexity ceiling measured first)
   and stops ignoring `F841`; pyright `standard` for contract,
   hashicorp-utils and the plugins, `basic` for base and system until
   each is small enough for `strict`; each step its own commit with
   the fix count.
6. A plugin whose entry point fails to import is reported and skipped
   as a hook plugin is, not a traceback on every command (`loader.py`).
7. The sixteen `os.chdir` sites become one context manager.
8. The entry-point groups mean something (`storage`, `user`, `other`
   are declared and used by nobody; storage and user builders register
   under `instance` and `group`): the unused groups go or the loader
   checks the group against the classifier.
9. **YOUR DECISION:** merged feature branches older than a quarter
   move to an `archive/` namespace (names kept, the listing shorter);
   the default is no change, the kept-branch rule being the
   operator's.
10. The starter count in code strings (found by §118, which
    changes no code): the Justfile's `publish-starters` comment and
    `[doc]` say four template repositories; `packages/system/
    pyproject.toml` says three. Five exist. Since §121 the one list is
    the `docs/examples/` directory itself (every tree with a `cfg/`,
    beside the `DEFAULT` marker), read by `hatch_build.py` and by
    `starters.py` at run time; the strings say "every starter tree"
    or read the directory.
11. `tests/test_docs_image_sources.py` parametrises the aws and gcloud
    query tables only; docker-runtime's README now carries the same
    table (§118) and `_runtimes()` gains it.
12. `ansible_models.py`'s refusal of an item with only `config:` says the
    playbooks are "files the config keys feed as variables"; the builder
    passes only connection variables in `--extra-vars` and CONFIGURATION
    says `config` is not passed to ansible. The message says what is.
13. `just --list` prints a comment fragment for every recipe without a
    `[doc]` attribute (`fixture-live`, `lint`, `test-bake-steps`,
    `verify` read as the last line of a paragraph); each gets a `[doc]`.
14. After §121 lands and a release carries it: the reference's and
    the starters' image builders move from `packer-ebs`, `packer-gce`
    and `packer-docker` to the one `packer` key (the operator,
    2026-11-04: the reference keeps the old keys at the take; the
    move is this item, its own commit on the reference's develop,
    re-recorded if anything moves). The fixture keeps the old keys
    as the standing proof that the aliases resolve.
15. Rename `sft_enrollment_token` (the launch credential's terraform
    variable, a core constant whose value names OPA's client) to a
    neutral name (`enrollment_token`): every instance root and
    launch script template moves, so the golden is regenerated and
    the reference re-records at its next take; the one excused line
    in `tests/test_core_names_no_runtime.py` goes with it (the
    operator, 2026-11-05, at §122).
16. The ansible plugin's Python-prep line for a bake (`ansible_builder.py`,
    the `dnf` install of the interpreter) is dnf-only and breaks a
    debian bake; route it through the OS type's
    `ansible_python_install_command` (three golden lines move; found
    by §122).
17. The instance roots (tf-ebs-instance, tf-gcp, tf-docker) still
    assemble their `templatefile` maps by storage kind in
    `_launch_args`; the storage builders' `launch_variables()` names
    what each kind reads, so the roots can build the map from the
    hooks (output unchanged; found by §122).
18. `packages/tf-ebs-instance-plugin/tests/test_instance_module_calls.py::
    test_pre_finalize_writes_tfvars_for_resolved_psis` fails when it is
    the first test in a process (`utils.root_in_runtime_scope` asks
    the context before anything built it) and passes after any test
    that loads one; under the bar it passes by order. The test builds
    its own context or the helper tolerates none (found by §122).

19. The one-release shims of §124 retire in the release after
    0.1.7: the `GlobalTypeContext` name and `global_context.py`, the
    no-argument fetch (`run_context.current_context`,
    `registry.current_registry`, the fallback in
    `BuilderBase._get_context()`), and the `RunContext` delegations to
    the finalizer. The model methods that reach the current context
    or registry (`models/image.py`, `base_image.py`, `mixins.py`,
    `builder_model.py`, the okta and docker provider-specific image
    models, `os_types`, `public_safe`, `image_sources`, the two state
    builders' `session_status`) take what they need instead;
    `version_checker_for(exe)` and the `TemplateResolver` (whose
    `flattened_map` is still process-wide) get a per-run handle (found
    by §124).
20. Eleven function-local imports left beside §124's registry edits
    are cycle-free and hoist to the top level (`commands/load_failures`,
    `commands/preflight`, `image_sources`, `public_safe`: the
    `load_plugins` + `current_registry` pairs; the two state builders'
    `current_registry`; `loader.py`'s `Orchestrator`), after which
    `LAZY_EDGES_CORE_MAX` in `tests/test_import_closure.py` falls from
    13 to 3 (found by §124).
21. `ImageSourceCatalog` (`image_sources.py`) is the last `@singleton`
    a run reads; it goes per-run like the registry, reached through
    the context (found by §124).

22. `LaunchServiceProtocol` still lists `hostname_problems` and
    `register_enrollment_kind`, both pure contract functions since
    §125 (`contract.launch_vocabulary`, `contract.enrollment`); no
    plugin reaches them through the service, so the two members go
    and the adapter with them (found by §125).
23. CLOSED by §129 (2026-11-07): the ceiling test it asked for landed
    as `tests/test_sources_do_not_narrate.py`, which holds zero over
    the sources, the tests, the modules, the Justfile, pyproject.toml
    and the fixture's comments; nothing is left to do here.
24. The bootstrap root (`base/bootstrap/generate.py`) renders its
    module calls from `module_source_base` alone: a `config:
    module_sources` entry for `bootstrap_aws`, `bootstrap_gcp` or
    `bootstrap_github` is honoured by every generated root through
    `utils.module_source` and not by the bootstrap's, which should
    resolve each section's module the same way (found by §126).
25. The module stamps never reach a commit: the skeleton's
    `.gitignore` ignores every dotfile (`.*`) and names no exception for
    `.csis-module`, so a tree's fourteen stamps stay untracked and a
    fresh checkout (CI, another machine) holds unstamped copies. Today
    they are adopted as identical; the release after a module changes
    would REFUSE every one of them, and the edited-copy protection the
    docs promise (DAILY_DRIVER, CONFIGURATION 2.x, OPERATIONS) does not
    hold across clones. Add `!**/.csis-module` to the skeleton's
    `.gitignore`; the reference takes it at the next refresh, which
    then commits the stamps (found 2026-11-06, the 0.1.7.dev2 take:
    "5 files in the index").
26. The loader sorts every free-form mapping's keys
    (`template_utils.sort_mappings`, one call in `read_config_and_transform`)
    only to keep the emission where the old dump-and-reparse left it (the
    YAML dumper sorted keys, so an image's `tags` block came out sorted).
    Dropping the call moves the golden by one key-order hunk and lets a
    file's own order win; a deliberate emission change, with a golden
    regeneration (found by §127).
27. The transient-storage teardown (`retention.
    transient_storage_teardown_command`: `run storage --only none` under
    a different overlay set) is the one deferred system step still run
    as a child process, because it needs a context loaded under other
    overlays; loading that second context in-process (the loader is
    offline now) would retire the last spawn (found by §127).
28. Narration the §129 rule does not reach: `.github/workflows/*.yml`
    and `scripts/*` (36 stage, bundle and date tokens between them, not
    in §129's list); "ledger NN" references (21 in the sources and
    tests, a numbering the rule's pattern does not name); the fixture
    value `instances.yaml: description: ... (stage 128; ...)`, a value
    the golden holds; and the comments of the fixture's four
    modification files (`setup_dask.yml` and its kin), which the
    emission copies and hashes, so cleaning them is a golden
    regeneration. Extend the rule's areas and pattern, regenerate the
    golden once (found by §129).

**Acceptance**: each item its own commit; `just test` green after
each; one squash, branch kept. Records: the squash; this section goes
at "merge 130".
