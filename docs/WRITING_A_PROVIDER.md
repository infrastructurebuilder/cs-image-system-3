# Writing a provider

This is the one guide to writing a provider for `cs-image-system`: a
package that adds a place images are baked and machines are run (a
cloud, a container daemon), with the OpenTofu roots that go with it.
Its example throughout is the docker provider,
[packages/docker-plugin](../packages/docker-plugin/README.md), which
is built and tested exactly as described here. An identity plugin, a
state backend or a modification builder follows the same rules; only
what it registers differs.

A provider written this way can be tested with nothing else of this
repository beside it, and can be installed beside any other provider
without changing what the other does.

## What a provider is made of

A provider is one distribution. The docker provider's is
`cs-image-system-docker-plugin`, and its
[pyproject.toml](../packages/docker-plugin/pyproject.toml) declares
everything the system needs to find it:

| It declares | Where | For docker |
| --- | --- | --- |
| The runtime type | an entry point in `cs_image_system.plugins.runtime` | `docker` |
| The roots (instances, storage) | an entry point in `cs_image_system.plugins.instance` | `tofu-docker` and `tf-docker-volume` |
| The Terraform modules its roots call | an entry point in `cs_image_system.modules`, naming a directory of package data | [tfmodules/](../packages/docker-plugin/src/cs_image_system/docker_runtime/tfmodules) |
| Its part of the image-source catalog | `data/image-sources.yml` in the runtime's package | the `docker` blocks |
| A setup section, if it has one | an entry point in `cs_image_system.bootstrap` | the container-host section |
| Commands, if it has any | an entry point in `cs_image_system.commands` | none |

Each entry point in a `cs_image_system.plugins.*` group names an
`initialize` function that returns the plugin's metadata: the model
and builder classes it registers and the `type:` word each answers
to. One distribution may hold several import packages. Docker's holds
two, the runtime (`cs_image_system.docker_runtime`) and the roots
(`cs_image_system.tf_docker_plugin`), and they release together.

**Kinds.** A plugin that brings an enrollment kind (what a machine
does at first boot to enroll with an identity agent) or a field kind
(a late-binding behaviour for configuration fields) declares it in its
metadata, beside its classes: `enrollment_kinds`, a sequence of the
contract's `EnrollmentKind`, and `field_kinds`, a mapping from a kind's
name to its `FieldKindHandler`. On the kit's metadata base class these
are two properties a subclass overrides; both are empty by default. The
system registers the declared kinds once, after the plugins are
discovered, and only for a plugin it accepts, so a plugin that is
skipped leaves no kind behind. A plugin cannot register a kind by a
call, and the four field kinds of the system's own (`fk`, `templated`,
`deferred_list`, `deferred_list_fk`) are no plugin's to declare. The
example is the Okta plugin's `OktaTypes`, which declares the
`sftd-token` enrollment kind; the plugin is no longer in this
repository but in its own,
[cs-image-system-okta](https://github.com/infrastructurebuilder/cs-image-system-okta),
and the class is in its
[`main.py`](https://github.com/infrastructurebuilder/cs-image-system-okta/blob/develop/packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/main.py).

Everything a provider needs at run time ships in its own
distribution, the Terraform modules included. A provider never relies
on a file that lives in another package.

**The namespace.** What a plugin registers carries a namespace: the
one its metadata names, or else the distribution's name with
`cs-image-system-` and `-plugin` dropped. Docker's two halves each name
their own (`docker-runtime` and `tf-docker`), as they were when they
were two distributions, so a configuration that wrote a qualified word
still loads. A configuration may write a `type:` word bare (`docker`)
while only one installed plugin registers it, and qualified
(`docker-runtime/docker`) always.

## What it may import

A provider's sources import three things and nothing else of this
system:

1. **The contract**, `cs_image_system.contract`: everything public in
   it.
2. **The SDK's declared surface.** The SDK is three libraries: the
   kit (`cs_image_system.base`) and the two Terraform libraries
   (`cs_image_system.hashicorp_utils`, the HCL builder and the
   collectors; `cs_image_system.tofu_roots`, the base classes for
   roots). Each ships a declaration of what a plugin may use, in its
   `surface` module: the names it may import, and the
   underscore-prefixed members of the library's classes it may
   override or call (the hooks).
3. **Its own packages**, and those of a plugin it declares as a
   dependency.

It never imports the engine (`cs_image_system.engine`), the command
line (`cs_image_system.system`) or another provider.

A provider's tests may import one thing more, the test kit
(`cs_image_system.system.testing`).

### Checking it

The kit carries the check. It reads source files and never imports
them, and it reads each library's declaration from the library that is
installed:

```sh
python -m cs_image_system.base.surface check src
python -m cs_image_system.base.surface check --tests tests --source src
```

Each finding is one line: the file, the line, what was reached and
why it is not allowed. Docker runs the same check as two tests, so it
runs wherever the suite runs:
[tests/unit/test_keeps_to_the_surface.py](../packages/docker-plugin/tests/unit/test_keeps_to_the_surface.py).

If a provider needs something the surface does not list, the answer
is to add it to the library's declaration in a change to that
library, which is an addition and raises the last number of its
version. Reaching past the surface is not an answer: nothing promises
that what is found there will still be there.

## How it depends on the SDK

A provider declares the contract and each SDK library it uses **by a
range** covering one middle number, never by an exact version. The form,
with `M` the middle number it is written against and `M+1` the next:

```toml
dependencies = [
    "cs-image-system-contract>=0.M,<0.M+1",
    "cs-image-system-base>=0.M,<0.M+1",
    "cs-image-system-hashicorp-utils>=0.M,<0.M+1",
    "cs-image-system-tofu-roots>=0.M,<0.M+1",
]
```

The docker provider's own lines, with the values in force today, are in
its [pyproject.toml](../packages/docker-plugin/pyproject.toml); each
library's current version is in its own manifest.

The range means something because the SDK's libraries keep one rule
about their versions:

- **Removing or altering anything on a declared surface raises the
  middle number** (`0.M.x` to `0.M+1.0`).
- **Anything else raises the last number** (`0.M.x` to `0.M.x+1`): an
  addition to a surface, a fix, a change behind it.

So a provider that passes its tests against the first release of a
middle number works with every later release of it, and a range of
`>=0.M,<0.M+1` says exactly that. The kit is on
one version line; the two Terraform libraries share another. Neither
follows the version of the system as a whole.

Each library keeps a baseline of its surface as it stood when its
middle number began, and a test in the library compares the two, so
the rule is held by a check and not by care. Inside this repository
`just surface-check` runs it for all three, and a release is refused
while it fails.

A provider tests itself at **both ends** of its range: the lowest
version it claims to work with and the highest. The low end is where
a provider learns that it has begun to use something a later release
added, and must raise the bottom of its range.

## Where its tests live

Everything a provider's tests need lives in the provider's own
directory. Docker's:

| Path | Holds |
| --- | --- |
| [tests/unit/](../packages/docker-plugin/tests/unit) | Tests that need the contract, the SDK and the package, and nothing else. They are what runs at the low end of the range, so nothing they need may sit in a `conftest.py` above them. |
| [tests/pipeline/](../packages/docker-plugin/tests/pipeline) | Tests that drive a whole run through the test kit. |
| [tests/live/](../packages/docker-plugin/tests/live) | Tests that need the real thing (here, a container daemon). They are in no default path and no isolated run; a recipe of their own runs them (`just test-docker-live`), as a leg of `full-test`, and they fail without it. |
| [tests/fixture/](../packages/docker-plugin/tests/fixture) | A configuration that declares this provider and no other. |
| [tests/golden/](../packages/docker-plugin/tests/golden) | What a run over the fixture emits, pinned byte for byte. |
| [tests/regen_golden.py](../packages/docker-plugin/tests/regen_golden.py) | Rewrites the golden, on purpose (`just golden-regen docker`). |
| [docker_runtime/testing.py](../packages/docker-plugin/src/cs_image_system/docker_runtime/testing.py) | The provider's stub: what answers in place of its calls to the outside world. |

**The stub ships in the package**, not in its tests. It is a function
that takes a test's `monkeypatch` and replaces the provider's own
calls to a daemon or a cloud. Shipping it means the provider's own
suite and any suite that runs it beside other providers use the same
answers.

**The fixture declares only this provider**, plus the core plugins
whose `type:` words it needs (an image builder, an OS family, a state
backend, an identity). The package's `test` extra names those plugins
and the command line with its test kit:

```toml
[project.optional-dependencies]
test = [
    "cs-image-system-system[testing]==<version>",
    "cs-image-system-packer-plugin==<version>",
    # ... one line per core plugin the fixture declares
]
```

It does not name the top-level `cs-image-system` package, which lists
the provider in an extra of its own: a dependency in both directions
is a cycle no release can order.

**The golden is the provider's own.** When an intended change moves
the emission, regenerate it and read the rewritten files one by one;
a golden regenerated to make a test pass is how a defect becomes the
expected output.

**What stays outside.** A provider's suite tests the provider. What the
core or another plugin does with it beside other providers (an identity
plugin's objection to a container runtime, the preflight's line for each
session) needs more than the provider installed, and is tested in the
repository's own `tests/`, where every provider is.

## What the test kit gives it

`cs_image_system.system.testing` drives a whole run over a fixture
with nothing outside the process touched. It names no provider and
imports none.

| It offers | For |
| --- | --- |
| `Run(tmp_path, monkeypatch, fixture=..., stubs=(...))` | A private copy of the fixture, loaded, with every external command recorded instead of executed, a fixed clock and the fixture's own test identity. `run("all")` drives the lifecycles. |
| `copy_fixture`, `stub_core`, `load_context`, `drive_lifecycles` | The same in separate steps, for a test that needs to stand between them. |
| `emitted(generated, meta_state)`, `assert_matches(golden, emitted, ...)` | Comparing what a run emitted with a golden, with a unified diff per file on a difference. |
| `validation_errors(ctx)` | What `validate` would print for a loaded configuration; empty when it is valid. |
| `encrypted(config_root, plaintext)` | A value as an `ENC[age:...]` marker the fixture's test identity opens, for a test that declares a secret. |
| `run_mod_tests(ctx, images=...)` | The modification tests on the stand-in an installed runtime offers, as `test-mods` runs them. It reaches a real target, so it belongs in a provider's `tests/live`. |
| `broken_neighbour(monkeypatch)` | A plugin that fails to import, installed beside the one under test for the length of one test. |
| `isolation.process_unchanged()` | A context manager that fails, naming what changed, if a block leaves the environment, the working directory, `sys.path` or the root logger other than it found them. |
| `isolation.root_logger_restored` | A fixture's body that puts the root logger back after each test; a suite applies it in its `conftest.py`. |
| `double` (a module of the kit) | A runtime type that exists only inside a test run, for a fixture that should declare no provider at all. |

A pipeline test is short. This is the whole of docker's golden test:

```python
def test_the_emission_matches_the_family_golden(family_run, golden_dir):
    run = family_run()
    summary = run.run("all", apply=True)
    assert summary.ok, summary.error
    kit.assert_matches(golden_dir, kit.emitted(run.generated, run.meta_state),
                       regenerate_with="just golden-regen docker")
```

`family_run` is the suite's own fixture, in
[tests/pipeline/conftest.py](../packages/docker-plugin/tests/pipeline/conftest.py):
it makes a `Run` over the provider's fixture with the provider's
stubs.

Two more tests are worth having in every provider, and docker has
both. [test_broken_neighbour.py](../packages/docker-plugin/tests/pipeline/test_broken_neighbour.py)
shows that a broken plugin installed beside the provider changes
nothing: the fixture validates and the run emits the golden.
[test_leaves_the_process_alone.py](../packages/docker-plugin/tests/pipeline/test_leaves_the_process_alone.py)
shows that loading and running the provider changes nothing
process-wide that another plugin could observe.

The test kit never skips. A test that cannot run fails.

## Running its tests alone

The workspace's own environment cannot show that a provider stands
alone, because every package is installed in it. The proof is a run
in an environment that holds only the provider and what it declares:

```sh
just test-docker-alone
```

It builds the wheels and runs docker's suite three times, each in an
empty environment of its own:

| Run | Holds | Runs |
| --- | --- | --- |
| High end, in place | The package, its dependencies and its `test` extra, the SDK at the highest version of its range | The whole suite |
| High end, from a copy | The same, with the package's directory copied outside the workspace and built there | The whole suite |
| Low end | The package, the contract and the SDK at the lowest version of its range | The unit tests, the surface check among them |

A run fails when no test was collected, when any test was skipped, or
when any failed. For each SDK library it says where the version came
from, in one of two forms:

```text
cs-image-system-base <version> from the index
cs-image-system-base <version> from this repository's build (development install)
```

The second form is a development install, and is never to be read as
proof against a release. No container daemon is needed: the suite's
runs are stubbed.

The same suite also runs in the workspace's environment, beside every
other provider, as part of `just pytest`, against the same golden.
Passing in both places is what shows that installing other providers
beside this one does not change what it emits.

One more check covers what a person who installs the provider gets:

```sh
just test-docker-install
```

It installs `cs-image-system[docker]` from the built wheels into an
empty environment, renders the
[standard-docker](examples/standard-docker) starter with the
installed command, and runs `validate` and a dry `run --all` on it.
This one needs a container daemon that answers, and it fails without
one.

The recipes and what each needs are listed in the recipe table of
[OPERATIONS.md](OPERATIONS.md).

## How a plugin that cannot be used shows itself

An installed plugin that cannot be used is treated as absent, never
as a reason for the system to stop. The command continues, one line
at ERROR names the plugin and the cause, and every command on a
configuration that does not use the plugin works as if it were not
installed.

```text
Plugin <name> (<distribution>) is skipped: failed to import: <error>
Plugin <name> (<distribution>) is skipped: refused: <reason>
Plugins <a> (<distribution>) and <b> (<distribution>) are both skipped: both register <what>
```

A plugin is skipped when:

- its entry point does not import, or its `initialize` raises;
- it is **refused**: a class it registers does not satisfy the
  contract's protocol for its kind, it sits in an entry-point group
  whose kind it does not register, it has no namespace, it declares a
  field kind of the system's own, or it declares one kind twice;
- it **collides** with another plugin. Two plugins that claim one
  thing are both skipped, so the outcome never depends on which was
  found first. The things that can collide are a registered class
  under one namespace and name, an entry-point name within a group, a
  command, a setup section, an enrollment kind or a field kind that
  two plugins declare differently (one declared alike by both is one
  registration, and both load), and an image-source block for a
  runtime type another plugin registers.

A configuration that needs a skipped plugin fails validation, and the
message says the plugin is installed and why it could not be used. It
does not suggest installing it:

```text
 - <kind> type '<word>' is registered by <plugin>, which is installed but could not be used: <cause>
```

Two cases are refusals of the thing asked for, not skips. Two
distributions that ship a Terraform module directory of one name are
refused when modules are read, naming both. Two plugins that register
one bare `type:` word under different namespaces both load, and a
configuration that writes the bare word is asked to write one of the
qualified forms.

For a provider's author this means three things. Choose names that
are yours: the namespace comes from the distribution, so module
directories, commands and section names are where a clash can happen.
Keep per-run state on the run, through
`ctx.plugin_state("<namespace>/<name>", factory)`, never in a module
variable. And change nothing process-wide: not the environment, not
the working directory, not the logging.

## Where the rest is

- The protocols a model and a builder satisfy, and the phases a hook
  keys on: the [contract's README](../packages/contract/README.md).
- The base classes and what the run context offers: the
  [kit's README](../packages/base/README.md).
- The collectors and the HCL builder: the
  [hashicorp-utils README](../packages/hashicorp-utils/README.md).
  The base classes for roots: the
  [tofu-roots README](../packages/tofu-roots/README.md).
- The smallest plugin there is, written against the contract and
  nothing else: the
  [contract example plugin](../packages/contract-example-plugin/README.md).
- Every package, with what it registers: [PLUGINS.md](PLUGINS.md).
