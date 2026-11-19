# Specifications

Work on this system is specified here with Spec Kit, under the
[constitution](../.specify/memory/constitution.md). A specification says
what changes and why, for a named user, and ends in an acceptance that a
command or a CI job can pass or fail. The existing system is not
specified here; its golden and its tests describe it.

## Written

| Specification | Serves | Ends in | State |
| --- | --- | --- | --- |
| [001 A provider that stands alone (docker first)](001-standalone-docker-provider/spec.md) | a plugin author; operators | the docker family's tests passing with only its declared dependencies installed | merged into `develop` 2026-11-18; branch kept ([tasks](001-standalone-docker-provider/tasks.md)) |
| [002 Fifteen minutes to a first dry run](002-first-dry-run/spec.md) | an adopting team | CI running the quickstart page's own commands on a clean machine | written |
| [003 Release gates that cannot report a pass they did not earn](003-currently-accurate-release-gates/spec.md) | operators; those who install a release | a rehearsed release stopping when a required check did not run | written |
| [004 Kinds a plugin declares, not kinds it registers on import](004-kinds-in-metadata/spec.md) | a plugin author; operators | every discovery order giving the same accepted plugins and registered kinds | merged into `develop` 2026-11-18; branch kept ([tasks](004-kinds-in-metadata/tasks.md)) |
| [005 The Google Cloud provider in a repository of its own](005-relocate-gcp-provider/spec.md) | a plugin author; operators; an adopting team | the family's own repository passing its acceptance tests from a fresh clone, and this one passing without it | in progress: phase 1 merged ([tasks](005-relocate-gcp-provider/tasks.md)) |

The numbers are the order of writing, not of priority. None of 001 to
003 depends on another; 004 follows 001, whose code it simplifies. 003 is
the smallest.

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
