# Meta-examination: did the last two weeks improve anything, and would spec-kit help?

Date: 2026-11-16. Written for the operator.

## 0. What was asked and what I compared

Three questions:

1. How do the four earlier re-examinations
   (`INPROGRESS/REEXAMINE1.md` to `REEXAMINE4.md`, all dated 2026-11-03 or
   2026-11-04) compare with the one I wrote today (`REEXAMINE.md`)?
2. Was improvement made between them, or were the two weeks wasted?
3. Would spec-kit-based work improve the quality of this codebase compared
   with the way the work is done now?

**What I read.** All four earlier files: the second and fourth whole, the
first whole, and the third by its headings, its lead findings, its table
of contradictions, its scorecard and its suggestions (its body is long and
I did not read every paragraph). They live only in the checkout at
`/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3`, which ignores them.
Paths below are relative to that checkout at `10c3007c` (release 0.1.10).

**What I measured.** Where an earlier review gave a number, I measured
today's counterpart. Their numbers are theirs: I cannot see the tree of 3
November without checking it out, and did not. Where the method of
counting may differ I say so.

**A caveat about my own report.** I opened the earlier files briefly this
morning, before you told me to ignore them, and so I had seen their
overall scores (6, 7.8 and 6.3) before I wrote mine (6). My findings came
from six readers who never saw those files and from my own checks, so the
findings are independent. **My score is not.** Do not read "6 then, 6 now"
as a measurement of no progress. Compare the findings, which is what this
document does.

---

## 1. The answer in brief

**The two weeks were not wasted, and they were not well spent.**

- **Not wasted.** The earlier reviews' digest listed about sixty actions.
  By my count 43 are done, 8 partly done and 9 not done (§3). The
  structural findings that put "separation" at 4 out of 10 are gone, and I
  confirmed that from the code, not from the work list: the GCE and docker
  Terraform roots no longer inherit the AWS one; no cloud's name is left
  in the core's logic; the 1,587-line context object and all four
  singletons are gone; a configuration loads without calling a cloud; a
  run no longer spawns itself as a child process; cross-family plugin
  imports went from nine to none.
- **Not well spent.** The three conclusions every earlier review shared
  were not on the action list as things to do, and none of them moved:
  *subtract rather than add* (the source grew about 16%, the tests about
  31%, the contract's protocols from 31 to 49, the release scripts
  threefold); *the method has become the product* (seven more hygiene
  bundles, and new tests that police the wording of comments and the
  names of test files); and *build the model image* (excluded from scope
  on 4 November).
- **Why today's report resembles the old ones.** Partly because a third
  of today's findings are old findings that were never acted on; partly
  because a third are the *next layer down*, visible only because the
  first layer was fixed; and partly because a third are new, created by
  the fixes themselves or by the churn (§5). Same themes, mostly different
  instances.
- **"The other session did a poor job" is half right.** It executed the
  list it was given with high completion and real care: the row-by-row
  documentation fixes hold up. Its failures were of judgement, not
  diligence: it turned themes into a checklist, certified items as done
  that were not (the contract "surface review"), answered a criticism of
  process with more process, and introduced regressions nobody caught.
  Two of the decisions that most limited the outcome were yours: the
  scope, and keeping twenty-two packages (§5.6).
- **Spec-kit: yes, conditionally.** It would help with the actual root
  cause, which is the *unit of work*: findings and stages instead of
  outcomes a named user can verify. It would hurt if it is added on top
  of the present ledgers instead of replacing them. §7 says how I would
  use it and how to tell within two weeks whether it is working.

---

## 2. Then and now, measured

| Measure | 3 November (as the earlier reviews reported) | 16 November (measured) | Direction |
| --- | --- | --- | --- |
| Commits on the public history | 290 | 336; 49 since 3 November, 68,800 lines inserted and 56,230 deleted | |
| Final releases | 0.1.6 | 0.1.10 (four more) | |
| Hygiene bundles | XXIII | XXX (seven more) | worse |
| Workspace packages | 22, and "too many" in all three reviews | 23 | worse |
| Source lines, core (contract, base and engine, CLI, the Terraform libraries) | 30,791 | 37,401 | +21% |
| Source lines, plugins | 16,136 | 16,937 | +5% |
| Source lines, total | 46,927 | 54,338 | **+16%** |
| Test functions | 1,464 | 1,921 | +31% |
| Markdown, current plus frozen | 47,400 | about 50,300 | +6% |
| Protocols in the contract | 31 | 49 | worse |
| Members of the runtime builder's protocol | 49, called "a base class, not a contract" | 53 of its own, 83 with inherited | worse |
| Classifications; lifecycle phases | 40; 36 | 40; 36 (nine phases used) | unchanged |
| Process singletons | 4 | 0 | **fixed** |
| The context "god object" | 1,587 lines, a 331-line function | gone; the largest function anywhere in the core is 198 lines | **fixed** |
| Largest module | `global_context.py`, 1,587 | `cli.py`, 1,969 (was 1,734) | moved |
| `os.chdir` sites in the core | 16 | 3 | better |
| `getattr`/`hasattr` in base (now kit plus engine) | 356 | 384 | slightly worse |
| `type: ignore`; `except Exception` (same scope) | 71; 63 | 65; 55 | slightly better |
| Cross-plugin import sites; crossing a provider family | 21; 9 | 5; 0 | **fixed** |
| Places the core names a cloud | "three places" and more | none in logic (tool names remain, and are now in the contract) | **fixed**, with residue |
| Live cloud calls while loading a configuration | yes | no | **fixed** |
| A run spawning the CLI as a child process | yes | no (one code path that can still build that command remains in the kit) | **fixed**, with residue |
| Test files named after stages or bundles | 49 | 0 | fixed |
| Stage, date and finding tokens in source and tests | 690 and 389 | 0 and 0, held by a 432-line test | fixed |
| Golden files; runtimes the golden covers | 122; two | 148; three | better |
| Lint and type bar | two ruff families; pyright `basic` | five ruff families with a complexity ceiling; pyright `standard` | better |
| Justfile | 679 lines | 586 lines | better |
| Release scripts | 754 to 850 lines | 2,493 lines, plus about 3,800 lines of tests for them | **worse** |
| Documentation claims found correct when checked | 6 of 30 | about two thirds of about 60 (a different sample) | **better** |
| A quickstart; a plugin author's guide; a diagram | none | none | unchanged |
| The model image | not built | not built | unchanged |

Read down the right-hand column and the shape of the fortnight is plain.
The specific defects with a file and a line were fixed. Everything that
measures mass went up.

---

## 3. The earlier action list, item by item

The fourth earlier file is a digest of the other three: eleven common
themes and about sixty actions. This is its action list against today's
tree. "Done" means I found it true in the code or the documents, not that
the work list says so.

### Before the kit and engine split

| Action | Now |
| --- | --- |
| Hoist a provider-neutral Terraform root | **Done** (`tofu-roots`; an install test proves it) |
| Rename the AWS subclass to tf-aws | Not done: still `tf-ebs-instance-plugin`, and the bare word `tofu` still means AWS |
| Drop the AWS pins from the GCE and docker roots | **Done** |
| Test that those roots import without AWS | **Done** |
| Register the tofu version checker neutrally | **Done** (a second, AWS-only checker remains) |
| One `packer` key with runtime hooks | **Done**, with residue: the older keys were to load "for one release" and are still there four releases on; every runtime's file is still named `…-ebs-ansible-setup.pkr.hcl` |
| Preflight's provider detection behind a hook | **Done** |
| Device and mount logic onto the storage protocol | **Done** |
| The vendor image catalogue into the runtime plugins | **Done** |
| Okta fields, workload token and `sft` paths into okta-opa | **Done** |
| Package-manager branching into default-os | **Done** |
| Each module family inside its owning plugin | **Done**, with residue: the modules sit in the *runtime* package while the code that calls them is in the *root* package, and module names are one flat namespace |
| hashicorp-utils a leaf on the contract | **Done** |
| Split the global context | **Done** |
| Pass the context; retire the singleton | **Done** |
| Recompute the closure before the split | **Done** |
| No re-export shims from base into engine | **Done** in the letter; base's manifest now declares an entry point that resolves into the engine, which is the same coupling in another form |

### Decomposition and packaging

| Action | Now |
| --- | --- |
| One wheel per provider bundle, not twenty-two | **Rejected**: "shape (b), the twenty-two projects kept"; now twenty-three |
| Test doubles out of the umbrella | **Done** |
| The contract gets its own version | **Done** (and a release failed once because it was not bumped) |
| Review the contract's surface | **Recorded as done, not achieved**: the work list says 64 members left the protocols; the runtime protocol has more members than before and there are 18 more protocols |
| Service protocols instead of context members | **Done** (thirteen; 45 of their 52 methods forward to kit functions the plugin already has) |
| The "what may a plugin import" test first | **Done** |
| Runtimes as extras | **Done** |
| Prove the external runtime with docker | Not done (planned, stage 116) |
| Each moved package gets its own fixture, golden and tests | Not done. This is now the main blocker |
| Hold the Azure and Google repositories | Held, but the stale scaffolding is still on disk |
| Name the Google repository to match the plan | Partly: the plan now defers to the name that exists |
| Never copy the root `pyproject.toml` into a runtime repository | Not done: both placeholders still hold that copy |
| Archive starter-tree | Not done |
| Decide packaging before the release-walk stage | Decided, as "keep" |
| Close the shim bracket | **Done** |

### Execution and loading

| Action | Now |
| --- | --- |
| No live cloud calls during load | **Done** |
| No child CLI processes that reload the configuration | **Done** |
| Parse each YAML file once | **Done**; the templating that follows is still three stages with retry loops |
| Foreign-key resolution as an explicit pass | Partly |
| All meta-state files listed; atomic writes | **Done** |
| Delete the dead modules and the skipped tests | **Done**; new dead code has appeared (about 180 lines in the template utilities, about 95 commented-out in the Packer builder) |

### Documentation

| Action | Now |
| --- | --- |
| README, DESCRIPTION and DESIGN §1 current | **Done**. I spot-checked the old tables of wrong claims and the rows I checked are fixed |
| Fix every tabulated contradiction | **Done** for each of the five rows I spot-checked (the reference's stale comments and README line, the deleted orphan files, the skipped tests and their fixture, `hashicorp-utils`'s dependency statement) |
| Write the stage index | **Done** (`docs/CHANGES.md`) |
| Strip the stage parentheticals from current pages | **Done** by pattern; the habit of explaining the present as a change from the past survives in prose |
| Strip stage numbers from source, Justfile and fixtures | **Done**, and a test now enforces it |
| One owning page per reference table | Partly |
| Incident logs into one page | **Done**, then abandoned: nothing after 1 November, and two later release failures are recorded only in the work list |
| A glossary | **Done**, then damaged: six entries were deleted in the kit-and-engine commit, including "the gate", which the README still advertises |
| Mark the walk frozen; fix the frozen pages' links | **Done**, and done well |
| Reframe GOALS | Partly: a good status table over a body that still reads as present tense |
| Make PARITY's proposed tests real | **Done**; PARITY's own banner is now false |
| Delete the orphaned root files | **Done** |
| Starters from one skeleton | **Done** |
| The reference's "What stands" becomes a pointer | **Done**; the rest of that README is stale |
| One external-plugin author's guide | Not done |

### Tests and tooling

| Action | Now |
| --- | --- |
| Behaviour names for test files; drop `v2_` | **Done**, and a test now enforces it |
| Stop pinning prose | Partly: the suite's own measure fell sharply; some pins moved to where the measure does not look |
| Docker in the frozen fixture | **Done** |
| Release logic into a tested script | **Done**, at three times the size |
| Raise the lint and type bar | **Done** |
| Install `just` in the devcontainer | **Done** |

### Then

| Action | Now |
| --- | --- |
| Build the model image | Not done; out of scope by decision |

**Tally: 43 done, 8 partly, 9 not done, of 60.** Completion of the list
is about seven in ten outright and more than four fifths counting partials.
As execution of a checklist that is a good result.

---

## 4. What genuinely improved

Said plainly, because the next section is critical and this should not be
lost.

1. **Layering by imports is now real and enforced.** On 3 November the
   GCE and docker roots were subclasses of the AWS root and installing
   either installed boto3. Today that is impossible and a test that
   performs a real install proves it.
2. **The core no longer knows a cloud.** A fourth cloud runtime would not
   edit the core for its sessions, its images, its devices or its
   packages.
3. **Run state is per run.** No singleton, no current context, a registry
   per load. Two runs can share a process.
4. **Loading is cheap and offline.** `validate` went from about twenty
   seconds to under six, by the work list's own measure, and needs no
   session.
5. **The summary documents are true again.** The earlier reviews found 6
   of 30 claims correct. The pages they named were fixed row by row and
   the fixes held.
6. **The golden covers all three runtimes.**
7. **History is fenced.** `docs/history/` is properly marked; the
   mechanical markers are out of the current pages.

These are the things the earlier reviews called the precondition for any
split. They were right to, and the precondition is now met.

---

## 5. Why the report cards still look alike

### 5.1 The list was the wrong unit

The digest had two parts: "Common themes" and "Actions". The themes
included "the next phase should be subtraction, not addition" and "the
platform goals are met; the purpose is not". The actions were sixty moves:
hoist this, rename that, strip the other. No action said *end the
fortnight with fewer lines, fewer packages, fewer protocols, less release
machinery*, and the purpose appeared once, last, under the heading "Then".

A checklist of moves can be completed while every theme gets worse, and
that is what happened. Each move was a relocation plus a guard: the code
went to a new place, and a test was added to keep it there. Nothing in the
plan was a deletion with a budget.

### 5.2 A criticism of process was answered with process

The earlier reviews said the stage ledger had "colonised the code, the
tests and the documents" and that tests were pinning prose. The response
was two stages that removed the vocabulary, and two new rule tests that
ban it: one of 432 lines over twelve areas of the tree, one that refuses
words in test file names. Six tests of this kind were added in the
fortnight. Then three further hygiene bundles in one day (136 to 138)
each spent part of their effort removing the word "V2", down to
regenerating the golden for one line. The symptom was treated thoroughly.
The cause, which is that the work is organised around its own ledger, was
strengthened: there is now machinery that fails the build when the ledger
shows through.

The reviews also said the release ceremony was too heavy for twenty-two
lock-stepped packages. The response kept the packages and automated the
ceremony, which tripled the scripts. Today's first live run of that
automation needed two interventions by hand (`REEXAMINE.md` §7).

### 5.3 The frontier moved down a layer

This part is progress that looks like repetition. With the import graph
clean, the next layer of coupling is visible, and it is what my report
found: exact version pins on a kit with no declared surface; one test
harness, one fixture and one golden that bind every provider together;
shared run-time channels; a release welded to a sibling checkout. The
earlier reviews mentioned the test problem in a single table row ("the
root suite crosses every package"). It is now the main obstacle. A review
of a layered problem will keep producing "separation is incomplete" until
the last layer is done; that is not evidence the earlier layers were not.

### 5.4 The fixes created some of today's findings

- Module names became one flat namespace across plugins when modules
  moved into wheels.
- A bare `type:` word is now withdrawn when two plugins claim it, since
  registrations became namespaced: installing a second plugin can break a
  tree written for the first.
- Plugin command mounts load unguarded at CLI start, since commands moved
  into plugins.
- The starters still say `uv tool install cs-image-system`, which
  installs no runtime since the extras arrived.
- The starters still say a load needs a live session, which stopped
  being true when loading went offline.
- The package counts in four documents were right until the engine split
  added a package.

Every one of these is a seam that a fix opened and nobody walked back
along. A plan made of moves does not ask "what did this move make false?"

### 5.5 Regressions nobody caught

The glossary lost six entries inside a refactor commit. GOLDEN's own table
stopped adding up. The design record still states the contract's version
as `0.1.0`. The incidents page stopped being kept the week it was created.
None was caught by a suite that had just gained tests for the wording of
comments. That is the clearest single piece of evidence about where the
attention went.

### 5.6 Two limiting decisions were yours

I say this because the question was whether the other session did a poor
job, and the honest answer has to separate what it could decide from what
it could not.

- **Scope.** On 4 November the work was scoped to "separation of layers,
  consolidation of the base classes, and the documentation", with the
  model image out of scope and "hygiene before purpose" standing. Every
  review had named the missing purpose as the largest gap. No session
  could have closed it inside that scope.
- **Package shape.** All three reviews recommended fewer packages. Stage
  126 landed "under shape (b), the twenty-two projects kept". Much of the
  release machinery, and its growth, follows from that.

### 5.7 And one caution about reviews as a measure

Ask a capable reviewer the same five questions about a 54,000-line system
built this way and the answer will have these headings and a score near
six. The prompt fixes the shape, and (in my case) seeing the old scores
fixed the number. A fresh review is a good way to *find* things and a poor
way to *measure* progress. If you want to know whether the next fortnight
worked, decide the measures beforehand (§7.5) instead of commissioning a
sixth review.

---

## 6. So: improvement, or a wasted fortnight?

**Improvement, at a poor rate of exchange.**

What you bought: the first layer of separation, made real and enforced;
true summary documents; a cleaner run model. These were necessary, and
stage 116 would have proved nothing without them.

What it cost: 49 commits, about 69,000 lines inserted against 56,000
deleted, four releases, seven hygiene bundles, and a codebase that is 16%
larger with 31% more tests and three times the release tooling.

What it did not buy: any movement on the purpose; any reduction in mass;
any change to the method the reviews criticised; a codebase a stranger
can enter.

My estimate, and it is a judgement, not a measurement: something like half
of the fortnight's effort went into work that changed the form of things
(stripping narration and policing it, renaming tests and policing that,
removing "V2" across three bundles, automating the release walk) against
half that changed their substance (the Terraform root, the core's
neutrality, the context, offline loading, the documents' facts). The
substantive half was worth doing. The formal half was the review's
criticism being absorbed by the thing it criticised.

Assigning that fairly:

| Cause | Whose |
| --- | --- |
| Turning themes into a checklist of moves, with no budget and no outcome | The plan's author (the same model that then executed it) |
| Completing about seven in ten of that checklist carefully | To the session's credit |
| Marking the contract review done while the surface grew | The session |
| Answering "too much process" with rule tests | The session, within a method it was given |
| Regressions in the documents | The session |
| Excluding the purpose; keeping twenty-two packages | The operator |
| Using fresh reviews as the measure of progress | The arrangement as a whole |

---

## 7. Would spec-kit-based work improve the quality of this codebase?

### 7.1 What spec-kit is today

I read the project's README today; I could not open its guide for existing
projects (the address a search returned answered 404), so what follows
about adopting it in an existing codebase is my reasoning, not its
documentation. My memory of its file layout is from earlier versions and
may be out of date.

Spec Kit is GitHub's open-source toolkit for spec-driven development with
coding agents. Its core process is a sequence of agent commands:
`/speckit-constitution` (the project's standing principles),
`/speckit-specify` (what to build and why, without the how),
`/speckit-plan` (the technical approach), `/speckit-tasks`,
`/speckit-implement`, and `/speckit-converge`, repeated with implement
until it reports convergence. It installs with `uv tool install
specify-cli` and keeps its state under `.specify/` in the repository. Two
bundled extensions matter here: **bug** (assess, fix, test, with a verdict
of verified, partial or failed) and **assess** (intake, research, define,
shape, decide, with a decision of *go*, *needs-clarification* or *kill*).
It also has presets and project-local overrides for adapting its
templates.

### 7.2 What it would fix here

The root cause in §5.1 is the unit of work. Spec-kit changes the unit, and
that is the whole case for it.

1. **Work starts from an outcome a named user can verify.** A
   specification says who wants what and how they will know they have it.
   "Hoist the Terraform root" cannot be written that way; "a plugin author
   builds, tests and releases a runtime without this repository" can. The
   second form would have put the shared test harness on the table on day
   one, because the acceptance test cannot pass without it.
2. **It forces the question this project keeps avoiding: who is the
   user?** My report's first open question was who the second reader is.
   A specification cannot be written without answering it.
3. **Intent becomes durable.** Today a stage's plan is deleted when it
   lands and "the squash commit is the record". The only lasting
   statement of what the system should do is 34,000 lines of narrative.
   A kept specification per capability is a far better thing to check
   documents and code against than a narrative is.
4. **A constitution is the right home for the rules that are now
   scattered** through "standing decisions", the glossary and rule tests,
   and it is consulted when a plan is made rather than discovered when a
   test fails.
5. **Convergence is checked against the specification, not against a
   fresh review.** That replaces the loop of §5.7.
6. **The assess extension has a "kill" decision.** The present method has
   no way to decide that a finding is not worth acting on: a finding goes
   into a bundle, and a bundle lands. Thirty bundles is what the absence
   of "no" looks like.

### 7.3 What it would not fix, and how it could make things worse

1. **It does not choose what to work on.** If the first specifications
   are "hygiene bundle XXXI" in new clothes, nothing changes. The scope
   decision stays yours.
2. **This project's failure mode is surplus artefacts, and spec-kit
   produces artefacts.** A specification, a plan and a task list per
   feature, written in this project's habits and laid on top of the work
   list, the stage files, CHANGES, INCIDENTS and REMINDERS, would be a
   fifth ledger. Adopted as an addition, it will make the repository
   worse.
3. **It is strongest for features and weaker for restructuring.** Much of
   what remains (splitting the tests, versioning the kit) is structural.
   It can be framed as a user outcome, as in 7.2 item 1, and the framing
   is clarifying; but it takes discipline not to write an implementation
   plan and call it a specification.
4. **It will not, by itself, subtract.** Nothing in the process rewards
   deletion. That has to come from the constitution.
5. **The same diligence will be applied to it.** The session that
   completed seven in ten of a sixty-item list will complete a task list
   just as faithfully. That is the reason to give it a better list, and
   also the reason a bad specification is dangerous.

### 7.4 My recommendation: adopt it as a replacement, narrowly, starting with the purpose

**Replace, do not add.**

- Specifications replace the stage files. The constitution replaces the
  "standing decisions". The bug extension replaces hygiene bundles, with
  the rule that a defect which does not block a named user waits until
  its code is touched for another reason.
- `INPROGRESS/TODO.md` shrinks to a list of open specifications.
  CHANGES stays as the index and is generated. No new ledger is created.
- Do **not** write specifications for the existing system. Specify only
  what changes. The golden and the existing tests are the specification
  of what exists.

**A short constitution.** Seven articles are enough; these are the ones
this history argues for.

1. *Purpose first.* Every specification names the user it serves: a
   modeller, a team adopting a starter, a plugin author, or the operator.
   Work that serves none of them needs a stated reason.
2. *Acceptance is executable.* Each specification ends in a command that
   passes or fails. A review is not acceptance.
3. *A budget.* Each plan states its effect on source lines, packages,
   protocol members and test count. Growth needs a reason in the plan.
4. *Each fact has one source.* Counts, recipe lists and field tables in
   documents are generated or absent.
5. *Tests guard behaviour or architecture.* No test of wording, naming
   or ordering.
6. *A skipped gate fails.*
7. *What a change makes false is part of the change.* Every plan lists
   the statements elsewhere that stop being true.

**The first three specifications**, in this order:

1. **A real model image.** "A CO-OPS modeller logs into an instance of a
   released image and runs the model to a known result." Acceptance: the
   model's own check passes on a machine launched from the released
   build. This is the purpose, and it is the only work that will tell you
   which of the platform's parts are right.
2. **A runtime outside the repository.** "A plugin author installs the
   kit, writes or moves a runtime, and its tests pass with only its
   declared dependencies installed." Acceptance: a CI job that does
   exactly that for docker. This is stage 116 restated as an outcome, and
   it pulls in the test kit, the per-family fixture and the versioned kit
   surface as tasks rather than as afterthoughts.
3. **Fifteen minutes to a dry run.** "A newcomer with nothing installed
   reaches a successful dry run by following one page." Acceptance: that
   page's commands run in CI on a clean image.

Run the first one through the **assess** extension as well. If its
decision is anything but *go*, you will have learned something more
valuable than another hygiene bundle.

**What to stop**, whether or not you adopt spec-kit: opening hygiene
bundles as a standing activity; adding rule tests about form; and
commissioning fresh reviews to see whether things improved.

### 7.5 How to tell in two weeks whether it is working

Decide these now and check them on 30 November. No review needed.

| Measure | Today | Working if |
| --- | --- | --- |
| A model's own check passes on a released image | no | yes, or a written reason why not |
| Source lines | 54,338 | lower |
| Workspace packages | 23 | lower |
| Protocols in the contract | 49 | not higher |
| Rule tests about form added | 6 in the last fortnight | 0 |
| Hygiene bundles opened | 7 in the last fortnight | 0 |
| A provider family's tests pass with only its own dependencies installed | no | yes for one family |
| Release-script lines | 2,493 | lower |
| Specifications open at once | n/a | 3 or fewer |

If the first row is still "no" and the second is higher, the tool has
changed and the method has not.

### 7.6 The short version

Spec-kit will not make this codebase better. A better choice of what to
build will, and spec-kit is a reasonable way to make that choice
explicit, durable and checkable, **provided it replaces the stage ledger
instead of joining it and the first specification is the model image.**
The last fortnight shows the capacity is there: sixty items, seven in ten
landed, carefully. It was pointed at a list of moves. Point it at three
outcomes.

---

## 8. Limits of this document

- The numbers for 3 November are the earlier reviews' own; I did not
  check out that tree.
- Some counts are not like-for-like (how "Any" or prose pins were
  counted); I have marked or omitted those.
- The item-by-item statuses in §3 rest on this morning's reading. Where
  that reading was a delegated one I re-checked the items this document
  leans on, but not all sixty.
- The share of effort I call "formal" in §6 is a judgement.
- What I say about spec-kit beyond its README is my reasoning and may not
  match its current guidance for existing projects.
- My overall score in `REEXAMINE.md` was not blind to the earlier scores.

Sources for §7.1: the [Spec Kit repository](https://github.com/github/spec-kit)
(read today). A search also returned an
[existing-projects guide](https://github.github.com/spec-kit/guides/existing-projects.html),
which I could not open.
