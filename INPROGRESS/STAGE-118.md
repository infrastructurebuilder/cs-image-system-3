# 118. The summary layer comes current

**Status: OPEN 2026-11-04. Waits for "do 118". Documentation only;
changes no code.**

REEXAMINE1 §4.2 checked thirty claims against the tree and found six
fully right; REEXAMINE3 §2.3 tabulates twelve contradictions. The
pattern is the same in both: the detailed pages (CONFIGURATION, the
plugin READMEs, OPERATIONS §1) stay current because a test or a daily
use touches them; the summary pages (README, DESCRIPTION, DESIGN §1)
and the cross-references do not, and they are what a newcomer reads
first. A morning's work, and the precondition for every stage below
being documented against a true baseline.

1. [README.md](../README.md): the runtimes are AWS, GCE and docker; the
   plugin list is whole (seventeen); the starters are five; the
   reading order gains the glossary ([§119](STAGE-119.md)) when it exists.
2. [DESCRIPTION.md](../docs/DESCRIPTION.md): releases publish to an index;
   CI's `perform` bakes, releases and applies retention on `main`
   under the write role; the state backends are s3, gcs and local; an
   ansible item with only `config:` is refused at load; `base_images/`
   is not a collection. "Known limits" stays as honest as it is.
3. [docs/DESIGN.md](../docs/DESIGN.md) §1 and §3F6 lose `base_images:`;
   §3P's Reversibility paragraph keeps the rule and loses the
   operational state (the tags, the undo recipe, the reminder go to
   REMINDERS.md).
4. Every row of REEXAMINE1 §4.2 and REEXAMINE3 §2.3 is fixed or shown
   wrong, in the squash message row by row. The list, by page:
   OPERATIONS (the starter count, the workflow count, the project
   count, line 18's `module_source_base`, the GCP zone claim near
   line 2675, "docs-only changes skip the bar", the CI recipe
   catalogue, the "Other CLI commands" table); CONFIGURATION (`jq`,
   `availability_zone` on instances and storages); GOLDEN (122
   files); DAILY_DRIVER (the helper scripts, F44 lives in REMINDERS,
   no bundle is open); hashicorp-utils README's dependencies; the
   seven plugin READMEs that name `system` as a dependency; packer
   README's AWS dependency; tf-s3-state README's self-contradiction;
   okta-opa README's example without `posix:`; docker-runtime
   README's "next branch" note and its missing image-query table;
   base/README's "one in-place change" row and its plugin count;
   system/README's retired option rows and its plugin count.
5. The starters' READMEs under [docs/examples/](../docs/examples):
   standard-aws-posix's `--from`; complete's counts (four runtimes,
   the posix builders, seven storage builders, four packer builders,
   ten storages, five base images, nine instance images). They are
   published at the next tag; `test_docs_examples` reads them.
6. **USER**, the reference repository on its `develop` (catch up
   first): README's "What stands" becomes a pointer to `state query
   --strict` and the records it duplicates; the stale `# stage 22.3
   REMOVED` comments in `cfg/os-builders.yml` and the duplicated
   "SHUT DOWN" block above the live `coops-model` declaration go.
   Comments are not read; the emission does not move.
7. [GOALS.md](../GOALS.md). **YOUR DECISION:** a preface mapping each
   requirement to implemented or deferred (the default; the table in
   REEXAMINE1 §6.1 is the draft, and the body stays verbatim as the
   founding document), or a rewrite in the current voice.
8. `QA_QUESTIONS.md` and `QA_ANSWERS.md` go (empty templates).
9. [PARITY.md](../docs/PARITY.md)'s proposed-tests column points at [§128](STAGE-128.md),
   which writes them.

**Out of scope**: the narration ([§119](STAGE-119.md)); any test ([§128](STAGE-128.md)); code.

**Acceptance**: the docs tests green (`test_docs_contract`,
`test_docs_examples`, `test_docs_image_sources`, `test_v2_ci_runner`);
the two tables re-checked row by row and each row named in the squash
as fixed or refuted; one squash, branch kept. Records: the squash
message; this section goes at "merge 118".
