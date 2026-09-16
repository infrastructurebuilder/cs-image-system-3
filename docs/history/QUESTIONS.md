> **Frozen record.** This document is history, kept verbatim as it was when frozen; nothing in it describes the present. Current documentation starts at [README.md](../../README.md).

# V2 questions

Questions about the V2 work, answered in place. Newest first.

## Aren't we basically only working on V2 now, or is there something else? (asked 2026-09-11)

**Short answer: yes.** Since 2026-08-25 every commit has been V2 work
and there is no other track. "V2" is no longer one effort beside a V1;
it is the system. What is left of V1 is three small remnants, listed
below, none of them work in progress.

### What the two labels mean here

- **V1** is the system as it stood on 2026-08-25: the per-builder
  generation with its own commands (46 commits from the 2026-07-02
  initial commit).
- **V2** is the rewrite against the target goals in [GOALS.md](../GOALS.md),
  planned that same day in the document that became
  [docs/DESIGN.md](DESIGN.md) (revisions 1–3) and executed since
  through gates and numbered stages (145 commits). It landed
  incrementally on `develop`, in place: there was never a separate V2
  branch, package or code path to switch over to.

### What is still V1, and why it is kept

1. ~~The V1 CLI commands `test`, `verify` and `cleanup` remain as
   stubs.~~ **Retired 2026-09-11** (see the second follow-up).
   `validate` still runs "V1 checks plus every V2 rule" — the V1 checks
   (unique names, executables) are simply part of V2's validation now,
   and that is no longer a remnant so much as a description.
2. Gate 1's layout-equivalence test
   ([test_v2_gate1_layout_equivalence.py](../tests/test_v2_gate1_layout_equivalence.py))
   keeps the V1 generated layout as a frozen baseline and proved that
   `run --all` reproduces it line for line through a V1→V2 path map.
   **Demoted to documentation 2026-09-11**: the five baseline tests are
   skipped with a reason, the baseline stays on disk as evidence, and the
   golden fixture pins emission instead.
3. One retired V1 field, `groups` on the instance model, is kept only
   so that a V1-era `groups:` entry raises a specific error instead of
   being silently dropped
   ([instance.py:160](../packages/base/src/cs_image_system/base/models/instance.py#L160);
   see the follow-ups below — **its condition lapsed on 2026-09-12**,
   third follow-up),
   and the lifecycle phase names were kept "unchanged from V1 so every
   builder hook keys on exactly what it did before"
   ([lifecycles.py:62](../packages/base/src/cs_image_system/base/lifecycles.py#L62)).

Everything else — the lifecycles, meta-state, gates, the plugins'
builders — is V2 code with no V1 twin.

### Is anything else being worked on?

No. The side documents are V2 stages or their housekeeping:
[GCP-READINESS.md](history/GCP-READINESS.md) (2026-09-02, the GCE increment of
the plan), [BILLING_REMINDERS.md](../BILLING_REMINDERS.md) (2026-09-05, GCP
housekeeping from the same stage), [EXPLORE.md](../EXPLORE.md)
(exploration inside the V2 work before acceptance). [TODO.md](../TODO.md)
has no stage in progress; ~~§17 and §18 are planned V2 stages held by
your instruction~~ (as of 2026-09-14: §17 landed 2026-09-12; §18 and §19
are held by your instruction, and §30, the plugin contract package, is
planned). `docs/Implementation.md` is out of bounds by your
2026-09-02 directive and is not being worked on.

### About the "littered" references

Counted in `packages/` and `tests/` (`.py` files) **before the rename of
2026-09-11**; the third column says where each resolves now:

| Reference form            | Count | Resolves where today                                  |
|---------------------------|------:|-------------------------------------------------------|
| `TODO §N` (a stage)       |   203 | now written `stage N`; resolves in TODO.md while in flight, PLAN.md's worksheet archive once landed |
| `V2_DESIGN §…`            |    71 | now `DESIGN §…` — [docs/DESIGN.md](DESIGN.md), numbering unchanged |
| `V2_EXPLORE`              |    60 | now `EXPLORE` — [EXPLORE.md](../EXPLORE.md)              |
| `N1`–`N26`, `Q1`–`Q7`     | 139, 35 | the stakeholder notes and questions in DESIGN       |
| `finding N` / `ledger N`  | 54, 28 | [docs/LEDGER.md](LEDGER.md)                     |
| `gate N`                  |    11 | DESIGN §4                                             |
| `V2.md`                   |     6 | now `GOALS.md` — [GOALS.md](../GOALS.md)                 |
| `V2_PLAN`                 |     5 | all in the gate-1 test's normalizer, which maps the frozen baseline's literal `V2_PLAN` to `DESIGN` — it must keep the old spelling because the baseline is frozen |
| bare `V2`                 |    82 | the label itself                                      |
| bare `V1`                 |    25 | the three remnants above (5 files)                    |

These are not "V2 as opposed to something else" markers. They are
provenance: each names the decision (Q/N), the design section (§3x),
the stage (TODO §N) or the finding (ledger N) that explains why a piece
of code is the way it is. They still resolve: the
[PLAN.md](../PLAN.md) records where each kind moved, so an old
"V2_PLAN §3F5" reads as "DESIGN §3F5", "ledger 68" is in
[docs/LEDGER.md](LEDGER.md), and an old "TODO §10.14" resolves as
stage 10.14 in PLAN.md's archive. The
`TODO §N` form is the largest group and the one whose home moves when
a stage lands; that has been so since stage 1, and the archive keeps
every stage's section under its number.

### What was decided (2026-09-11)

Of the three options originally listed here, the operator chose the
second and third. Both were carried out on 2026-09-11.

- **Keep the pointers as they are** — *not chosen.* It had been the
  recommendation: the pointers are cheap provenance and they resolved.
- **A one-time rename pass** — **done** (`feature/reference-rename`).
  `TODO §N` became `stage N` (303 citations, including three chains
  where the following `, §N` was converted too). The `V2` prefix left
  the document names: `V2.md` → [GOALS.md](../GOALS.md), `V2_EXPLORE.md` →
  [EXPLORE.md](../EXPLORE.md), `V2_QUESTIONS.md` → this file (moved to `docs/` on 2026-09-15),
  `docs/V2_DESIGN.md` → [docs/DESIGN.md](DESIGN.md),
  `docs/V2_OPERATIONS.md` → [docs/OPERATIONS.md](OPERATIONS.md) —
  263 references rewritten across 144 files, a pointer stub left at each
  old name. Those stubs were removed the same day, and the former
  `V2_PLAN.md` — already only a pointer — was folded into
  [PLAN.md](../PLAN.md). The gate-1 normalizer now maps
  the frozen baseline's `V2_PLAN` to `DESIGN`, and the golden fixture was
  regenerated for the emitted comments that carry these names.
  Bare `§N` citations were left alone: some name a stage and some name a
  design section, and only the explicit `TODO §N` form was unambiguous.
  The known cost stands — commit messages, branch histories and memory
  notes written before today still name the old files; nothing in the
  tree does.
- **Retire the V1 remnants** — **done** (`feature/retire-v1-remnants`);
  see the second follow-up below.

### Follow-up: don't the stubs do code management, and what is the retired field? (asked 2026-09-11)

**The stubs do nothing.** Each is four lines: print a yellow
"`<name>`: no-op (lifecycle `<name>` phase is not implemented)" and
return with exit 0. They were V1's placeholders for lifecycle phases
V1 planned and never built; V2 built verification differently
(`verify instance` over the runtime's session, post-bake image tests,
the Justfile's `test`). Their docstring's word "alias" is misleading —
they alias nothing. Two facts sharpen this:

- `verify` is dead code. The `verify` command group (`verify instance`,
  `verify assert`, [cli.py:581](../packages/system/src/cs_image_system/system/cli.py#L581))
  is registered under the same name and wins the resolution, so the
  stub can never run. (*The stub was deleted the same day; the retired
  names now live in the `_RETIRED` table at
  [cli.py:784](../packages/system/src/cs_image_system/system/cli.py#L784).*)
- `test` and `cleanup` are reachable and succeed. An old script calling
  `cs-image-system test` gets a yellow line and a green exit, which is
  the opposite of failing loudly (my earlier line above was wrong on
  that point). If they are kept at all they should exit non-zero and
  name the replacement (`test-mods`, `verify instance`, the retention
  lifecycle).

**The retired field is a guard, not a leftover.** In V1 an instance
declared its own `groups:` list (with an `ALL` magic value meaning every
group). V2 moved ownership to the instance image: an image belongs to
one group and an instance inherits it (DESIGN Q4). The `groups` field
survives on the instance model solely so that `__post_init__` can raise
"Instance 'x' declares 'groups'; V2 removed per-instance groups … the
owning group lives on the instance image" when a V1-era file is loaded.
The reason it has to be a field: ~~the configuration converter does
not forbid unknown keys, so without the field a stale `groups:` would be
dropped silently~~ — **no longer true since 2026-09-12**: stage 21 made
every model refuse unknown keys (`extra="forbid"` in
`CSIS_MODEL_CONFIG`), and stage 23 replaced the converter with
[`PydanticConverter`](../packages/base/src/cs_image_system/base/orchestrator.py#L452).
~~That same converter setting is a wider hazard: any misspelt key in any
configuration file (`ephemral: true`) is silently ignored today.~~ A
misspelt key is refused at load now.

TRIAL-001 (2026-09-11) measured this. Forbidding unknown keys and
removing the `groups` field, then loading the external configuration at
`../cs-image-system-testconfig`, inventoried **sixteen** unknown keys —
at least eleven of them genuinely dead, including `jethro: bodine` and a
`dask_version` whose value is a joke. None had ever been reported to
anyone. It also found the limit of the fix: keys nested inside a field
typed as a plain mapping are not checked, ~~so a typo in
`credentials.profile_name` would stay silent either way~~ (credentials
became a typed object in stage 17, 2026-09-12, so that example is now
checked; the limit itself stands for the 23 plain-mapping fields on the
base models, `config:` and `tags:` among them). And it
confirmed that retiring the `groups` field removes a real check —
the test asserting the migration message fails with a bare `TypeError`
in its place. So refusing unknown keys is worth having and would cover
most such cases, but it is a small stage rather than a one-line change:
the dead keys have to go first, because the configuration does not load
until they do. (*Done: stage 22 removed the dead keys and stage 21
turned the refusal on, both 2026-09-12.*)

### Second follow-up: retiring the V1 remnants (done 2026-09-11)

Carried out on `feature/retire-v1-remnants`, stacked on the rename branch.

- **`verify` deleted.** It was unreachable: the `verify` command group
  (`verify instance`, `verify assert`) is registered under the same name
  and wins, so the stub could never run. Removing it changes no behaviour,
  which is the point — it was dead code.
- **`test` and `cleanup` now fail loudly.** Each prints what replaced it
  and exits 2, instead of printing a warning and succeeding. `test` names
  `test-mods`, `verify instance` and `just test`; `cleanup` names the
  retention lifecycle and `dispose image`. Both are handled before the
  configuration loads, so an old invocation gets the message immediately
  rather than after a full load that might fail on credentials first.
- **The `groups` guard was kept**, as the condition in the original
  option said: the converter still does not refuse unknown keys, so the
  field is still the only thing standing between a V1-era `groups:` and a
  silent drop. TRIAL-001 measured exactly what removing it costs.
  *That condition lapsed the next day — see the third follow-up.*
- **Gate 1 demoted.** Its five V1-equivalence tests carry a skip marker
  naming the date and the reason; the frozen baseline is kept as evidence
  and can be re-enforced by deleting one marker. The sixth test in that
  module is unrelated — it pins the generated `.gitignore` ordering fixed
  earlier the same day — and still runs.

What is left of V1 after this: the `groups` guard, the lifecycle phase
names kept so builder hooks key on what they always did, `validate`'s
inherited checks, and the frozen baseline as evidence. No V1 code path
executes.

### Third follow-up: the `groups` guard's condition lapsed (noted 2026-09-14)

The guard was kept on one condition: that the converter did not refuse
unknown keys. Stage 21 (2026-09-12) removed that condition — every model
now refuses an unknown key at load — so a V1-era `groups:` on an instance
would be refused without the field. What the field still buys is the
specific message ("V2 removed per-instance groups … the owning group
lives on the instance image") in place of the generic unknown-key
refusal; the test at
[test_v2_gate4_identity_storage.py:365](../tests/test_v2_gate4_identity_storage.py#L365)
asserts that message. **Decided and done 2026-09-14**
(`feature/retire-groups-field`, ledger 83): the middle way stage 26 set
the precedent for — a `model_validator(mode="before")` on the instance
model that raises the same message when a `groups:` key is present, with
no field at all. The test's assertion is unchanged; the last V1 field is
gone.

What is left of V1 after 2026-09-14, then: the lifecycle phase names,
`validate`'s inherited checks, and the frozen gate-1 baseline as evidence.
No V1 field, code path or command remains.
