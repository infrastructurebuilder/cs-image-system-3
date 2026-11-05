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
   `helpers/yaml_process.py` if still unreferenced after [§127](STAGE-127.md);
   `bin/manage_ec2.sh`.
3. The devcontainer installs `just` (the single entry point is not
   the entry point there).
4. The release family's bash becomes `scripts/release.py` with unit
   tests behind a three-line recipe; the sibling repository's working
   tree is read through one documented function; the release appends
   `docs/CHANGES.md` (§119's owed item).
5. The lint bar, once [§124](STAGE-124.md) and [§127](STAGE-127.md) have lowered the `Any` count:
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

**Acceptance**: each item its own commit; `just test` green after
each; one squash, branch kept. Records: the squash; this section goes
at "merge 130".
