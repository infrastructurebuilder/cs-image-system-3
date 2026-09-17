# Parity: where the system and its documentation can diverge

*As of 2026-09-16. This is the one document allowed to say "as of": it
describes the gaps between what the code does and what the documents say,
the check that closes each gap today, and what a later change could
automate. Everything else in this repository describes the present without
a date.*

The documents are written by hand from the code. Nothing generates them,
and no test compares them to the code. So every one of them can lag the
code in a specific way, listed here with its check.

## The gaps and their checks

| Where | How it can drift | The check today | What could automate it |
| --- | --- | --- | --- |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md), the field tables | A field added to or removed from a model without a doc change; a default or validator changed. | For a model, compare its dataclass fields with the table: `grep -n 'field\|:' packages/<pkg>/src/**/models*.py`. | A test that walks every registered model's fields and asserts each appears in the reference. |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md), the examples | An example copied from the fixture that the fixture later changes, or that stops validating. | `just cli validate` over the frozen fixture: `uv run cs-image-system --root-dir tests/fixtures/config validate`. | Examples extracted from the fixture at documentation-build time. |
| The package READMEs ([docs/PLUGINS.md](docs/PLUGINS.md)) | A plugin registers a new classification, model or `type:` key, or changes an entry point, and its README does not follow. | `grep -n plugins packages/<pkg>/pyproject.toml` against the README's "What it registers"; the registry's view: `uv run cs-image-system --root-dir tests/fixtures/config validate` logs every registration. | A test that every entry point has a README naming it, and every registered `type:` key appears in the README. |
| [docs/OPERATIONS.md](docs/OPERATIONS.md), the recipe catalogue | A recipe added, renamed or changed in the Justfile. | `just --list` against the catalogue table. | A test that every recipe name in `just --list` appears in the manual. |
| [docs/OPERATIONS.md](docs/OPERATIONS.md), CI | A step, a secret or a trigger changed in the workflow. | `.github/workflows/ci.yml` against the CI section; `tests/test_v2_ci_workflow.py` pins the commands and the secrets list, not the prose. | Extend the workflow test to assert each pinned name appears in the manual. |
| [docs/OPERATIONS.md](docs/OPERATIONS.md), the CLI | A subcommand or option added or changed. | `uv run cs-image-system --help` and `<subcommand> --help` against the text. | The CLI's help is the reference; a test that every subcommand is named in the manual. |
| [docs/DESIGN.md](docs/DESIGN.md) | The design record describes a rule the code no longer keeps, or a mechanism that changed shape. | The golden ([GOLDEN.md](GOLDEN.md)) is the executable description of the emission: what the design says about the emission is checked against `tests/fixtures/v2_golden/`. | None planned; design prose is reviewed by hand. |
| [GOLDEN.md](GOLDEN.md), the file counts | The golden gains or loses files. | `find tests/fixtures/v2_golden -type f \| wc -l` and per lifecycle. | Trivial to assert in `tests/test_v2_golden.py`. |
| [DESCRIPTION.md](DESCRIPTION.md) "Known limits" | A limit is lifted and the list is not updated. | Each limit names its evidence (a file, a record, a command); re-check it when the area changes. | None. |
| [BILLING_REMINDERS.md](BILLING_REMINDERS.md) | Console pages, thresholds or recipients changed in the GCP console. | The monthly reminder re-reads the budget page. | None; the console is not scriptable for budgets. |
| The live configuration's README | It describes a tree this repository does not own. | Read it in the sibling repository when its shape changes. | None. |
| The `docs/history/` tree | Frozen on purpose; it carries dates, stage numbers and commit hashes verbatim. | None: nothing current cites it for a fact. | None. |

## What the code checks that the documents rely on

Some documentation claims are backed by tests, and those are the claims to
trust first:

- The emission: every file under `tests/fixtures/v2_golden/` equals what
  the run emits (`tests/test_v2_golden.py`).
- The runner scripts are self-contained and name no absolute path
  (`tests/test_v2_portable_run_scripts.py`).
- The fixture's people are synthetic and its rosters encrypted
  (`tests/test_fixture_personas.py`, `tests/test_v2_encrypted_values.py`).
- The public-safe gate's rules, exemptions and allowances
  (`tests/test_v2_public_safe.py`); the tree scans clean (`just
  public-safe`, CI).
- The CI workflow's commands, secrets and the read-only `live` job
  (`tests/test_v2_ci_workflow.py`).
- The Justfile contract, the guard on the live root, the config-drift
  recipe, the publish-tree recipe (`tests/test_v2_justfile_contract.py`,
  `tests/test_v2_publish_tree.py`).
- The suite never reads the live configuration
  (`tests/test_fixture_independence.py`).

## Known divergences

- **Cloud identifiers in documents** (account id, project number, image
  ids) are copied from records and can go stale when a resource is
  replaced; the records under the live configuration's `meta-state/` are
  authoritative.
- **The frozen history** under `docs/history/` is inconsistent with the
  present by design.
- **The pre-publication history is not in these repositories at all.**
  Each was published as a single commit; everything before it lives in a
  private, archived `…-archive` repository. A claim in any document that
  cites "the history" for something older than the first public commit
  cannot be checked from a public clone.

## How to keep parity

When a change lands: if it adds or changes a model field, a `type:` key, a
recipe, a CLI option, a CI step or a secret, the matching document changes
in the same commit. The checks above take minutes; run the ones that match
what you touched.
