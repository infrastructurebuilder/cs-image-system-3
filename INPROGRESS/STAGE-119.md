# 119. The stage index and the end of narration

**Status: OPEN 2026-11-04. Waits for "do 119". Documentation only;
changes no code. After §118.**

About 400 tokens of the form "stage N", "§N", "hygiene N", "FNN" and
ISO dates sit in the current documents (REEXAMINE1 §3.4, §4.3;
REEXAMINE3 §2.2), and the index they point at is deleted on landing:
a TODO section goes at merge, [docs/history/PLAN.md](../docs/history/PLAN.md)
stops at §18, and "stage 75" resolves only through `git log --grep`.
Three numbering schemes (system stages, walk steps, findings) share a
page without a key. The six big pages and the plugin READMEs restate
each other by thirty to forty percent, and no table has an owning
copy (REEXAMINE1 §4.4). The terms the house style uses ("the bar",
"the walk", "the take") are defined nowhere a newcomer looks first.

1. `docs/CHANGES.md`, the stage index: one entry per landed stage
   (stage, release, date, the squash's subject line), written once
   from `git log --grep '^Stage' --grep '^release'` with the command
   recorded at the file's head. Keeping it appended by the release is
   [§130](STAGE-130.md)'s item; until then the rolling documentation stage owes it.
2. The narration goes. In OPERATIONS, CONFIGURATION, DAILY_DRIVER,
   DESIGN, REMINDERS, base/README, system/README and the seventeen
   plugin READMEs, every "(stage N …)", "(hygiene X item Y)", "(FNN)",
   "until DATE" and "before stage N" becomes the present rule alone,
   or the present rule and a link to the CHANGES entry where the
   history matters. Deleted-code tombstones ("…was deleted") go. The
   walk's step numbers in DAILY_DRIVER and REMINDERS become section
   references or go.
3. One incidents page. DAILY_DRIVER §6, base/README's and
   system/README's dated logs (one newest-first, one oldest-first,
   duplicating each other) and the seven READMEs' copies of the
   t2.micro SSM incident move to `docs/INCIDENTS.md` (symptom, cause,
   fix, date, one entry each). "When it fails" keeps symptom, meaning,
   action.
4. One owner per table: CONFIGURATION owns every model field table
   and the `_config.yml` key table; the meta-state file table, the
   exit codes, the encryption rules and the gated apply sequence each
   get one home; every other page links. The README contract's four
   sections stay; the "Models" and "Builders" passes inside a README
   stop repeating the field tables and link instead.
5. `docs/GLOSSARY.md`: about thirty terms (the bar, the walk, the
   take, the record, the reference, runtime, emission, generation,
   box, stage, bundle, finding, perform, live, verify, kit, engine,
   contract, guard, pin, lineage, release, retention, materialise,
   mirror, public-safe, golden, fixture, starter, workload), one
   paragraph each, linked from README's reading order.
6. The frozen history is marked whole:
   [WALK-2026-10.md](../docs/history/WALK-2026-10.md) gets the frozen
   blockquote and one H1; frozen pages' relative links that land on
   live files are rewritten to say so or removed; the eleven current
   citations of `docs/history/` for a fact (tf-gcp, bash-mod and
   dummy READMEs, OPERATIONS line 10 among them) become the fact or a
   CHANGES entry.
7. [REMINDERS.md](../REMINDERS.md) becomes one document under one H1:
   the review worksheet, and the GCP cost reference as a section or
   its own page.
8. OPERATIONS §5's Podman proof narrative moves to INCIDENTS;
   OPERATIONS gains a table of contents (74 `###` under 6 `##`).
9. A style pass, not a rewrite: a sentence holding three rules
   becomes three; a 400-word run gets a heading. **YOUR DECISION:**
   in this stage page by page (the default), or a standing item of
   the rolling documentation stage.

**Out of scope**: the sources, the Justfile, the pyproject and the
fixture comments ([§129](STAGE-129.md)); the test file names ([§128](STAGE-128.md)); code.

**Acceptance**: a grep for the token forms over the current pages
reads zero outside CHANGES.md, INCIDENTS.md and `docs/history/`; the
docs tests green; the squash message carries the before and after
counts per page. **YOUR DECISION:** one squash (the default) or one
per page group; branch kept either way. Records: the squash; this
section goes at "merge 119".
