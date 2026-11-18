# Contract: the test kit

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R2 to R6, R16

This is what a provider's tests may rely on in place of the
workspace's shared harness. It serves FR-001, FR-002, FR-005, FR-006
and FR-020.

## Where it is

`cs_image_system.system.testing`, shipped in `cs-image-system-system`.
It needs `pytest`; install it with the `testing` extra. A provider
declares the core and `pytest` as test dependencies and nothing else
of this repository.

The names below are the shape of the interface. Exact signatures are
settled in implementation and then recorded in the guide.

## The stubbed run

| Operation | Does |
| --- | --- |
| Copy a fixture | Copies a fixture configuration into a temporary directory and returns its root. Takes the fixture's path; it knows no fixture of its own. |
| Run | Loads the copied configuration and runs the lifecycles as a dry run, with every external command recorded instead of executed, a fixed clock, a fixed user, the fixture's own test identity, and executable version checks answered. Takes a list of stub functions. Returns the emitted tree and the recorded commands. |
| Read a tree | Returns a directory's files as a mapping of relative path to bytes. |

A **stub function** takes the test's `monkeypatch` and replaces one
provider's calls to the outside world. The test kit applies each one
it is given. It names no provider and imports none.

A provider ships its stub function in its own package (for docker,
`cs_image_system.docker_runtime.testing`), so both the provider's own
suite and the every-provider suite can use it.

Two more operations serve a provider's own tests. **Encrypt a value**
returns a marker that the fixture's test identity opens, for a test
that declares a secret value. **Run the modification tests** runs them
on the stand-in an installed runtime offers, as the `test-mods` command
does; it reaches a real target, so a provider calls it only from a test
it runs on purpose.

## Golden

| Operation | Does |
| --- | --- |
| Compare | Compares an emitted tree with a golden directory, byte for byte, ignoring the three per-run files the shared golden already ignores. On a difference it fails with a unified diff per file and the lists of missing and unexpected files. |
| Regenerate | Deletes a golden directory and rewrites it from an emitted tree. Used only by a recipe a person runs on purpose. |

Both take the fixture and golden paths as arguments.

## The test-double runtime

A runtime type that exists only inside a test run. A fixture that
names it needs no provider. It is registered by the test kit for the
duration of a run and is never an installed entry point, so it never
appears among the `type:` words of a real installation.

It bakes through Packer's `null` source and offers no instance, no
storage and no stand-in.

## The isolation assertion

A context manager a test wraps around a load and a run. On exit it
fails, naming what changed, if any of these differ from their state on
entry:

- the process environment;
- the working directory;
- `sys.path`;
- the root logger's level and handlers.

It also fails if the kit's opened-secret store lost an entry. That
store is shared by every run in the process by decision and may only
grow.

It is `cs_image_system.system.testing.isolation.process_unchanged()`.
An environment variable that changed is named and its value is never
shown. The load makes the configuration's root the working directory,
which is the core's own doing and is put back by the command line when
a command ends; a test stands in the root before it starts, as a
command run from the root does.

## A broken neighbour

`broken_neighbour(monkeypatch)` installs, for the length of one test,
a plugin that fails to import, in the entry-point group the test
names (a runtime by default), and reads the installed plugins again
with it among them. It returns what could not be used. A provider's
suite calls it before making its run, then asserts that its fixture
still validates (`validation_errors(ctx)` is empty) and that the run
still emits its golden.

## What the test kit promises not to do

- It does not import a provider.
- It does not read [tests/](../../../tests) or anything else outside
  the installed distributions and the paths it is given.
- It does not skip. A test that cannot run fails.

## Stability

The test kit is versioned with the workspace, not with the SDK. A
provider inside this repository is tested against the test kit of the
same commit. What a provider outside this repository may rely on
across versions is a question for the specification that moves one
out.
