# Claude Code Instructions

## Python Execution

Always use `uv run python` instead of `python3` for running Python scripts or commands in this project.


## Ignore /ATTIC

The directory `/ATTIC` holds the retired work list, the frozen history and past reviews. Do not read it for guidance, do not cite it, and do not edit or tidy it, unless the operator asks for something in it by name. Nothing there describes the present.

## How Work Is Specified

Work is specified with Spec Kit under `specs/`, governed by `.specify/memory/constitution.md`. Read the constitution before planning or changing anything. Plans live in `specs/<number>-<name>/plan.md`, not in the root `PLAN.md`.

## Outside Configuration For Testing

For all live testing purposes, the repo cs-image-system-testconfig should be used as the source of configuration files.  For fast or local testing, the fixtures should be used.