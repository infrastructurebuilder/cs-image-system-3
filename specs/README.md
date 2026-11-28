# Specifications

Work on this system is specified here with Spec Kit, under the
[constitution](../.specify/memory/constitution.md). A specification says
what changes and why, for a named user, and ends in an acceptance that a
command or a CI job can pass or fail. The existing system is not
specified here; its golden and its tests describe it.

Each specification is one directory: `spec.md` says what and why,
`plan.md` how, and `tasks.md` the steps, each ticked when it is done and
recorded with its evidence. A specification is **complete** only when
the constitution's definition of done holds (Development Workflow: every
task checked and recorded, `/speckit-converge` run after the last
implementation, its quickstart walked, its branch squash-merged, its
release published with every run it started green and taken by the
reference configuration, and its status line saying so); until then a
merged one is **merged**.

**Converged** is ✅ when the last `/speckit-converge` run on the
specification appended no task, and ❌ when it appended tasks or has
never been run. **Last converge check** is the date of that run, or
`never`. A ❌ whose appended tasks are all done still meets the
definition of done; the mark says only what the last run found.

| # | Spec | Converged | Serves | Ends in | State | Needs first | Branch | Tasks | Released in | Last converge check |
| ---: | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| 1 | [001 A provider that stands alone (docker first)](001-standalone-docker-provider/spec.md) | ❌ | a plugin author; operators | the docker family's tests passing with only its declared dependencies installed | complete 2026-11-21: merged 2026-11-18, released in 0.1.11; its last converge appended T144 to T150, all done ([tasks](001-standalone-docker-provider/tasks.md)) | nothing | `feature/001-standalone-docker-provider` | 150 | 0.1.11 | 2026-11-21 |
| 2 | [004 Kinds a plugin declares, not kinds it registers on import](004-kinds-in-metadata/spec.md) | ❌ | a plugin author; operators | every discovery order giving the same accepted plugins and registered kinds | complete 2026-11-21: merged 2026-11-18, released in 0.1.11; its last converge appended T038 to T043, all done ([tasks](004-kinds-in-metadata/tasks.md)) | 001 | `feature/004-kinds-in-metadata` | 43 | 0.1.11 | 2026-11-21 |
| 3 | [005 The Google Cloud provider in a repository of its own](005-relocate-gcp-provider/spec.md) | ✅ | a plugin author; operators; an adopting team | the family's own repository passing its acceptance tests from a fresh clone, and this one passing without it | complete 2026-11-21: merged, released in 0.1.12, the family at 0.2.0 from its own repository; converged on the second run ([tasks](005-relocate-gcp-provider/tasks.md)) | nothing | `feature/005-prepare`, `feature/005-relocate-gcp-provider` | 82 | 0.1.12 | 2026-11-21 |
| 4 | [010 Every machine and every id recorded once, by an identity the system ships](010-posix-server-registry/spec.md) | ❌ | operators; an adopting team; a plugin author | a colliding id refused at validation across every identity, an undeclared id pooled and never drifting, and the core's registry tests passing with the Okta plugin absent | merged 2026-11-23 (`6bd23ee7`), carried by 0.1.13.dev1 (not yet recorded under its T046); open: T003 (a look at an enrolled machine) and T047 (the reference's applying run), the operator's ([tasks](010-posix-server-registry/tasks.md)) | nothing | `feature/010-posix-server-registry` | 64 | 0.1.13.dev1 | 2026-11-23 |
| 5 | [008 The Okta identity plugin in a repository of its own](008-relocate-okta-plugin/spec.md) | ❌ | a plugin author; operators | the Okta plugin's own repository passing its acceptance tests from a fresh clone, and this one passing without it | merged 2026-11-23 (phases 1 to 3 inside 010's squash, 4 to 6 `770ef2d8`), carried by 0.1.13.dev1; open: T057 to T059 (the release, the reference's take, the quickstart) ([tasks](008-relocate-okta-plugin/tasks.md)) | 010 | `feature/008-relocate-okta-plugin` | 60 | 0.1.13.dev1 | never |
| 6 | [013 Releases go to TestPyPI until 1.0](013-testpypi-until-1-0/spec.md) | ❌ | operators; an adopting team; a plugin author | a release proven in full and published to TestPyPI only, every consumer taking the system's packages from there and nothing else | merged 2026-11-24 (`509b8571`; the families' halves in their own repositories), released in 0.1.13.dev1 and taken by the reference; its third converge (2026-11-26, after specification 002 changed the release's gate and the Publish workflow) appended T041 to T045, all done and merged 2026-11-26 (`0f34b70b`); its fourth converge (2026-11-26, with an independent review of its documents against the three repositories) appended T046 to T053; the operator dropped T052 and T053 the same day, and T046 to T051 were done the same day; its fifth converge (2026-11-26, with a second independent review) found every requirement met in code and nine statements in comments and documents still false, appended as T054 to T062 and done the same day; both merged 2026-11-26 from `feature/converge-013-fourth`; its sixth converge (2026-11-26, with a third independent review) found one defect, the families' overlay unable to take a pin only TestPyPI holds, which a release's tag will meet once a family releases there alone, and seven more false statements, appended as T063 to T070 and done the same day (branch `feature/converge-013-sixth`), T066 dropped by the operator, merged 2026-11-27; its seventh converge (2026-11-27, with a fourth independent review and the suite run on a scratch clone in a release commit's state) found three tests that fail at a release's tag, so the next tag's CI would be red, and five more false statements, appended as T071 to T076 and done the same day (branch `feature/converge-013-seventh`), T076 dropped by the operator, merged 2026-11-27; its eighth converge (2026-11-27, with a fifth independent review and the release's own steps rehearsed in a scratch clone: `just test`, the quickstart page and the cloud starters pass at the rehearsed tag) found the three tests still failing at a tag that pins a family at a version their stubs do not list, and three groups of false statements, appended as T077 to T080 and done the same day (branch `feature/converge-013-eighth`), merged 2026-11-27; its ninth converge (2026-11-27, with a sixth independent review, of the corrections themselves and of four events walked in order) found two gaps in the release's step after its tag and five of the corrections wrong or overstated, appended as T081 to T087 and done the same day (branch `feature/converge-013-ninth`), merged 2026-11-27; its tenth converge (2026-11-27, with a seventh independent review and a third rehearsal, green at the tag) found the new probe for a tree left pinned not reading the `all` extra, and four small disagreements in the release script's own descriptions, appended as T088 to T092 and done the same day (branch `feature/converge-013-tenth`; 92 of 92 tasks closed); not complete until converge finds nothing and a release's runs all pass ([tasks](013-testpypi-until-1-0/tasks.md)) | nothing | `feature/013-testpypi-until-1-0` | 92 | 0.1.13.dev1 | 2026-11-27 |
| 7 | [002 Fifteen minutes to a first dry run](002-first-dry-run/spec.md) | ✅ | an adopting team; operators new to the system | CI running the quickstart page's own commands on a clean machine, and a newcomer reaching a dry run in fifteen minutes | merged 2026-11-26 (`e6226c44`), the full proof passed, converged; 32 of 35 tasks done, open: the release, the reference's take and SC-002's walk ([tasks](002-first-dry-run/tasks.md)) | 013 | `feature/002-first-dry-run` | 35 | | 2026-11-25 |
| 8 | [003 Release gates that cannot report a pass they did not earn](003-currently-accurate-release-gates/spec.md) | ❌ | operators; those who install a release | a rehearsed release stopping when a required check did not run | planned 2026-11-21 ([plan](003-currently-accurate-release-gates/plan.md)) | nothing | none yet | | | never |
| 9 | [006 A runtime written by its qualified word works as its bare word does](006-qualified-runtime-type/spec.md) | ❌ | operators; an adopting team | a configuration written with qualified runtime words validating with no image-source refusal the bare words do not also give | planned 2026-11-21 ([plan](006-qualified-runtime-type/plan.md)) | nothing | none yet | | | never |
| 10 | [007 The AWS provider family in a repository of its own](007-relocate-aws-provider/spec.md) | ❌ | a plugin author; operators; an adopting team | the AWS family's own repository passing its acceptance tests from a fresh clone, and this one passing without it | planned 2026-11-21 ([plan](007-relocate-aws-provider/plan.md)) | 005; 008 | none yet | | | never |
| 11 | [009 Every builder written by its qualified word works as its bare word does](009-qualified-builder-words/spec.md) | ❌ | operators; an adopting team; a plugin author | the shared fixture with every builder word qualified emitting all of its files identical to the bare form's, and every root initialising | planned 2026-11-21 ([plan](009-qualified-builder-words/plan.md)) | 006 | none yet | | | never |
| 12 | [011 The engine declares its own plugin and modules, not the kit](011-engine-owns-its-entry-points/spec.md) | ❌ | a plugin author; operators; an adopting team | the kit installed alone declaring nothing outside itself, and every tree's take refreshing its bootstrap module with no hand edit | clarified 2026-11-22 ([spec](011-engine-owns-its-entry-points/spec.md)) | nothing | none yet | | | never |
| 13 | [012 A provider narrows its own fields with no type-check exception](012-narrowed-fields-without-ignores/spec.md) | ❌ | a plugin author; maintainers | zero variable-override exceptions with the type check at zero errors, and a plugin built against the published kit passing unchanged | planned 2026-11-24 ([plan](012-narrowed-fields-without-ignores/plan.md)) | nothing | none yet | | | never |

## The order, and what stands beside the specifications

The first seven rows are in the order they were built and merged. The
operator's order of 2026-11-21 for what was then unbuilt was 008 first,
then 003, then 007, with 006 and 002 between them; 002 was built first
among those left once 013 had settled how a release is installed, and
the rest follow that order. 009 waits for 006,
whose word handling it extends; 011 and 012 have no place in that order
yet. The numbers are the order of writing, not of building.

Two families are released from repositories of their own and carry
their halves of 005, 008 and 013 there:
[cs-image-system-google-cloud](https://github.com/infrastructurebuilder/cs-image-system-google-cloud)
and
[cs-image-system-okta](https://github.com/infrastructurebuilder/cs-image-system-okta).
The reference configuration,
[cs-image-system-testconfig](https://github.com/infrastructurebuilder/cs-image-system-testconfig),
takes each release; a specification whose plan names a release is not
complete until it has. Work before Spec Kit was done in numbered stages,
recorded in [docs/CHANGES.md](../docs/CHANGES.md).

## Next to add: the model proof

The purpose of the system is an image that is correct for a given HPC
model and formally released (Constitution, Principle I). The first
specification for it is the next one to write. It was held back on
2026-11-16 because two things are not decided:

1. **What it runs on.** The chosen model is SECOFS, run through the
   Cloud-Sandbox workflow, and the intended proof was on one machine.
   Cloud-Sandbox's own instructions for SECOFS give two large nodes as
   the minimum for a cold start, because of memory at initialisation.
   The choices are: one very large high-memory machine; a small cluster,
   which the system cannot launch today; a first model that fits one
   machine, with SECOFS second; or the SECOFS build with a reduced run.
2. **What passing means.** Cloud-Sandbox ships public inputs for a
   SECOFS test case and no reference output to compare with. The choices
   are: the run completes and a modeller's sanity bounds hold; the output
   matches a reference a modeller supplies; or the run completes.

Already decided for it: the owning group is `secofs`; the acceptance is
automated first (CI's workload identity logs in and runs the check) and
then confirmed once by a modeller from the group; it serves modellers and
the operators who support them.

## Working on a specification

`/speckit-clarify` to settle open points, `/speckit-plan`,
`/speckit-tasks`, `/speckit-implement`, then `/speckit-converge`. One
feature branch per specification, `feature/<name>` from `develop`.
