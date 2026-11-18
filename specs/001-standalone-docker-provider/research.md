# Research: A provider that stands alone (docker first)

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Date**: 2026-11-16

This file records what the code does today, where that matters to the
plan, and the decisions the plan rests on. Each decision gives what was
chosen, why, and what else was considered. Line numbers are those of
commit `be648dbb` on `develop`.

Two kinds of fact appear below. Facts marked **read** were read in the
code during planning. Facts marked **to confirm** are inferences; the
first task of the phase that depends on one confirms it before building
on it.

## What the code does today

### The docker family

- Two distributions:
  [packages/docker-runtime-plugin](../../packages/docker-runtime-plugin)
  (the runtime, the bootstrap section, the two Terraform modules, about
  1,300 source lines) and
  [packages/tf-docker-plugin](../../packages/tf-docker-plugin) (the
  instance and storage roots, about 470 source lines). **read**
- `tf-docker-plugin` depends on `docker-runtime-plugin`. It imports one
  name from it (`docker_names.tag_name`), calls its private `_docker`
  through `getattr`
  ([tf_docker_storage_builder.py:101](../../packages/tf-docker-plugin/src/cs_image_system/tf_docker_plugin/tf_docker_storage_builder.py#L101)),
  and ships no Terraform modules of its own: its roots call the
  `docker_container` and `docker_volume` modules that the runtime
  package ships. **read**
- From the kit the family imports eleven names in nine modules, all
  under `base.basic` and `base.models`. From the contract it imports
  about thirty names. From `tofu_roots` it imports five names and
  overrides or calls about fifteen underscore-prefixed hooks. From
  `hashicorp_utils` it imports one name. It imports nothing from the
  engine. **read**
- Both packages already have small tests that use no shared helper (22
  tests). Every other docker test lives in [tests/](../../tests) and
  goes through the shared harness. **read**

### The shared test harness

- [tests/harness.py](../../tests/harness.py) `stub_environment` imports
  the AWS, Google Cloud, Okta and docker plugins unconditionally (lines
  240 to 313). Every `FixtureRun`, the golden test and 108 of the 168
  files in `tests/` therefore need every provider installed. **read**
- Package tests reach that harness through the root
  [pyproject.toml](../../pyproject.toml) `pythonpath`, which also puts
  every package's `src` on the path. A provider's modules are therefore
  importable in the workspace even when its distribution is not
  installed. **read**
- A configuration with no runtime is refused
  ([config_loader.py:539](../../packages/engine/src/cs_image_system/engine/config_loader.py#L539)),
  and only provider plugins register a runtime. **read**

### The kit

- [packages/base](../../packages/base) is 12,605 source lines in 72
  modules. It has no `__all__` and no surface declaration. The rule
  that stands in for one is a test,
  [tests/test_plugin_imports.py](../../tests/test_plugin_imports.py):
  a plugin may import `base.basic.*`, `base.models.*` and two metadata
  classes. **read**
- Every package pins the kit at `==` the workspace version, and
  [tests/test_package_metadata.py](../../tests/test_package_metadata.py)
  holds them to it. **read**
- The contract is the only package with a version of its own. Its
  machinery: it is listed under `glob_exclude` in the bump
  configuration; `scripts/own-versions-current` rebuilds every package
  so listed and refuses a release when the built bytes differ from what
  the index holds under the same version. There is no check of *which*
  number must change: the contract's MINOR-versus-PATCH rule is prose
  only. **read**

### Run-time channels between plugins

| Channel | Today |
| --- | --- |
| Entry point fails to import or `initialize` raises | One ERROR line names the plugin; it is skipped; the command continues ([loader.py:213](../../packages/engine/src/cs_image_system/engine/loader.py#L213)) |
| Plugin loads but is refused (namespace, conformance, group) | Every command that loads plugins dies with a traceback |
| A broken `cs_image_system.commands` entry point | Every invocation dies at import, `--help` included |
| A configuration uses a plugin that is installed but failed | The message says "install the extra", which is wrong advice |
| Two entry points with one name in one group | The second is silently never loaded |
| Same registry key, different class | `ValueError`, not classified, printed as a config read error |
| Same command name | `ValueError` at import |
| Same bootstrap section name | The later one silently replaces the earlier |
| Same Terraform module directory name | Raises naming both distributions (already correct) |
| Same bare `type:` word from two plugins | `AmbiguousTypeError` naming the qualified forms (already correct) |
| Image-source catalog block for another runtime's key | WARNING; the first runtime by name wins |
| Enrollment kinds and field kinds | Silently replaced |
| Provider agreement across Terraform roots | Every root's emission fails if any two roots anywhere in the run disagree ([collector.py:428](../../packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py#L428)) |
| Local stand-in for the modification tests | The installed runtime classes are asked in name order and the first that answers is used |

All rows **read**.

## Decisions

### R1. The docker family becomes one distribution

**Decision**: merge the two packages into one distribution,
`cs-image-system-docker-plugin`, in `packages/docker-plugin/`. The two
import packages keep their names (`cs_image_system.docker_runtime`,
`cs_image_system.tf_docker_plugin`), the entry-point names keep theirs,
and each plugin metadata record names its present namespace
(`docker-runtime`, `tf-docker`) through the existing
`PluginMetadata.namespace` override, so every qualified `type:` word a
configuration may have written still resolves.

**Rationale**:

- FR-001 and FR-003 speak of the family's tests, fixture and golden
  "kept with the family" and of copying "the family's directory". One
  distribution has one directory. Two do not.
- The one private reach between the two packages becomes a call inside
  one package, and the cross-plugin import edge disappears.
- The family ships its own Terraform modules as one unit (FR-019).
- The later specification that moves the family to its own repository
  moves one thing.
- It removes a package (Constitution VII).

**Alternatives considered**:

- *Keep two packages.* No rename and no new project on the index. But
  the family then has no single home; its family-level tests would sit
  in whichever package is "on top"; and the private reach has to become
  a public method across a distribution boundary. Rejected, though it
  remains the fallback if the merge shows a cost not seen here.
- *Keep two packages under a new `families/docker/` directory.* Changes
  the workspace layout that the bump configuration, the release scripts
  and many tests assume (`packages/*`). Rejected as the most churn for
  the least gain.

**Cost and how it is contained**:

- A new project name on the index; the two old names stop at 0.1.10.
  New projects are routine here.
- An environment upgraded in place could hold the old two plugins and
  the new one. R13 makes that a reported collision that names both,
  not a silent loss.
- **Confirmed on 2026-11-16 (task T019)**: nothing in the emission is
  derived from a distribution's name; the shared golden stayed
  byte-identical through the merge. One value outside the emission
  is: the namespace a shipped Terraform module is listed and stamped
  under comes from its distribution's name, by the contract's stated
  rule, so docker's two modules are now `docker`'s, not
  `docker-runtime`'s. Stamps are compared by content hash, not by
  that label, and a stamp is rewritten only when its module's copy
  is.

### R2. The test kit lives in the system package

**Decision**: the published test kit is
`cs_image_system.system.testing`, inside the existing
`cs-image-system-system` distribution. It holds the provider-neutral
part of today's harness (copy a fixture, load a context, run the
lifecycles with the external commands stubbed, read the emitted tree,
compare against a golden), a test-double runtime (R5) and the isolation
assertions (R16). It needs `pytest`, declared as an extra
(`cs-image-system-system[testing]`).

**Rationale**: the harness drives a whole run, so it needs the engine
and the command line. The kit may not import the engine (Constitution
VI), so the test kit cannot live in the kit. The system package is the
lowest package that sees everything the harness needs. The contract
already sets the precedent of shipping its test helpers in the package
(`cs_image_system.contract.testing`).

**Alternatives considered**:

- *A new `cs-image-system-testkit` package.* Allowed by FR-024, but it
  adds a package, a project on the index and a second thing to version,
  for about 400 lines. Rejected under Constitution VII.
- *Inside the kit.* Breaks the layer rule. Rejected.

**Consequence**: a provider's tests declare the core as a test
dependency. That is honest: a provider cannot produce an emission
without the core.

### R3. A provider ships its own stubs

**Decision**: the stubs that stand in for a provider's external calls
ship in that provider's package. For docker:
`cs_image_system.docker_runtime.testing`, holding what
`stub_environment` does for docker today (lines 277 to 280 and 305 to
308 of the harness). The test kit's run takes a list of stub functions.

**Rationale**: the family's own suite and the every-provider suite both
need docker's stubs. If they lived in the family's `tests/` directory,
the every-provider suite would import a test helper from outside
itself, and would lose it when the family leaves the repository.

**Alternatives considered**: *stubs in the test kit* (the test kit
would then name providers, which is the coupling being removed);
*stubs in the family's tests directory* (see above). Both rejected.

AWS, Google Cloud and Okta stubs stay where they are, in
[tests/harness.py](../../tests/harness.py), until those providers get
specifications of their own.

### R4. Three suites, and what goes in each

**Decision**:

| Suite | Where | Runs with |
| --- | --- | --- |
| Core | the `tests/` directory of each core package, plus the core fixture, golden and pipeline tests under `packages/system/tests/` | a plain install, no extras |
| Docker family | `packages/docker-plugin/tests/` (`unit/`, `pipeline/`, `fixture/`, `golden/`) | the family, its declared dependencies and its declared test dependencies |
| Every-provider | [tests/](../../tests), unmoved | every provider installed (the workspace environment) |

Rules that decide where a test lives:

1. A package's `tests/` directory holds only tests that pass with that
   package's declared dependencies. A file there that imports the root
   harness is ported to the test kit or moved to `tests/`.
2. A docker test moves to the family when its subject is docker. The
   four docker files in `tests/` (47 tests) move.
3. A test bound to the shared fixture stays in the every-provider
   suite unless it ports to another fixture without changing what it
   asserts. This feature does not rewrite assertions to move a test.
4. [tests/harness.py](../../tests/harness.py) becomes a composition:
   the test kit, plus the docker package's stubs, plus the AWS, Google
   Cloud and Okta stubs it keeps.

**Rationale**: FR-025 keeps the shared fixture, the shared golden and
their tests whole. FR-005 lets a test that needs a provider stay in the
every-provider suite until that provider has a suite. Thirty-two files
that are core in meaning assert on AWS emission paths today; rewriting
them is a different piece of work from isolating docker and would more
than double this feature.

**Alternatives considered**: *port every core-meaning test to the core
fixture now* (rejected: size, and Constitution VII); *select suites by
pytest marker in one environment* (rejected: the workspace environment
makes every provider importable, so a marker proves nothing about
isolation).

**Consequence stated plainly**: after this feature the core suite is
real but not large. Most behaviour tests of the core still run in the
every-provider suite. They migrate as their code is touched.

### R5. The core fixture uses a test-double runtime

**Decision**: the test kit ships a minimal runtime, a subclass of the
kit's `RuntimeBuilderBase` with its model, registered only inside a
test run and never as an installed entry point. The core fixture
declares one runtime of that type, the local state backend, POSIX
groups, one OS builder, and images baked through the core's own image
builder with Packer's `null` source. It declares no instance and no
storage, because only providers register builders for those.

**Rationale**: a configuration with no runtime is refused, and no core
package registers a runtime. `RuntimeBuilderBase` supplies defaults for
nearly every method, so the double is small.

**Alternatives considered**: *allow a configuration with no runtime*
(changes product behaviour for a test's convenience; rejected); *give
the dummy plugin a runtime* (the dummy plugin is not part of a plain
install, so the core suite would need something beyond the core;
rejected).

**To confirm**: that the core's image builder emits with a runtime
whose Packer source is `null`. If it does not, the core fixture
declares no image and the core golden is smaller.

### R6. Isolated runs are clean environments built from wheels

**Decision**: each isolated run builds the workspace's wheels, creates
an empty virtual environment outside the workspace's own, installs the
named distribution from the built wheels (third-party packages come
from the index), and runs `pytest` with the root configuration's
`pythonpath` and `testpaths` switched off. Each run fails if zero tests
were collected or any test was skipped.

**Rationale**: the workspace environment cannot prove isolation, since
every package's source is on the path. FR-003 asks for dependencies
"installed from built packages". One mechanism serves the core run,
the docker run, the copy-outside run and the install check.

**Alternatives considered**: *`uv sync --package`* (installs from the
lock and the workspace sources, and the root `pythonpath` still
applies; this is what
[tests/test_neutral_tofu_root.py](../../tests/test_neutral_tofu_root.py)
does today and it does not prove what FR-002 asks); *a container per
run* (heavier, and no more isolated for Python imports).

### R7. The SDK is three distributions on two version lines

**Decision**: the kit, `hashicorp-utils` and `tofu-roots` together are
the SDK: what a provider is written against. They are versioned on two
lines, both separate from the workspace version, both starting at
0.2.0, both under the rule of FR-010:

| Line | Members | Depends on |
| --- | --- | --- |
| The kit | `cs-image-system-base` | the contract |
| The Terraform libraries | `cs-image-system-hashicorp-utils`, `cs-image-system-tofu-roots` | the contract; `tofu-roots` also on the kit, by a range, and on `hashicorp-utils` exactly |

Each of the three declares a surface. A provider pins the kit by one
range and each Terraform library it uses by another. Every other
workspace package keeps exact pins on them, now at each line's own
version. `just sdk-bump <kit|terraform> <last|middle>` moves one line.

**Rationale**: FR-026, added on 2026-11-16, requires the Terraform
libraries to carry a version separate from the kit's, so that a later
specification can move them out. The two libraries share one line
between them because `tofu-roots` is built on `hashicorp-utils` and
the two would leave together; the spec leaves that to planning.

**Alternatives considered**: *one version for all three* (this plan's
first decision, before FR-026; it ties the libraries to the kit's
release rhythm and makes them impossible to move alone); *three lines*
(a third rule and a third range for two libraries that move together;
rejected); *fold the two libraries into the kit* (`hashicorp-utils` is
deliberately a leaf that depends on the contract alone; rejected).

**Consequence**: any change to the bytes of a member needs at least a
last-number bump of its line before a release, because the existing
probe compares built bytes with the index. The kit changes often, so
its version will rise at most releases; the Terraform libraries change
less often and now rise only when they do. A range absorbs last-number
bumps.

### R8. The surface is a list of names, hooks included

**Decision**: each SDK library declares its surface in one module
(`cs_image_system.base.surface`, and the same in the other two): the
names a plugin may import, module by module, and the underscore-prefixed
subclass hooks a plugin may override or call, class by class. The
first declaration is generated from what the workspace's plugins use
today and then read and committed; from then on it is edited by hand.

**Rationale**:

- FR-009 asks for one place that says what a plugin may import.
- FR-019 forbids reaching into private members, and FR-009 defines
  private as "everything else". The roots library's extension points
  are underscore-prefixed methods that every provider's roots override.
  Naming them on the surface makes them public by declaration without
  renaming them in the AWS and Google Cloud plugins, which the spec
  says to leave alone.
- A list of names is narrower than "everything public in 48 modules",
  so fewer changes count as altering the surface.

**Alternatives considered**: *a facade module that re-exports the
surface* (every plugin's imports change, AWS and Google Cloud
included; rejected); *rename the hooks to drop the underscore*
(touches every provider's roots for no change in behaviour; rejected);
*module-level surface* (too broad; nearly every kit change would count
as an alteration).

### R9. One import check, shipped in the kit

**Decision**: the kit ships the check FR-014 asks for, runnable as
`python -m cs_image_system.base.surface check <source dir>` and
callable from a test. It reads source with `ast`, so it needs nothing
but the SDK installed. It fails, naming the file, line and import,
when the source imports: a kit, `hashicorp_utils` or `tofu_roots` name
that is not on the installed library's declared surface; anything of
the engine or the command line; or any `cs_image_system` package that
is neither the contract, an SDK library, nor the plugin's own. It also
fails on an override of, or access to, an SDK underscore member that
is not a declared hook. A `--tests` mode additionally allows the test
kit and the plugin's own testing module.

**Rationale**: it replaces
[tests/test_plugin_imports.py](../../tests/test_plugin_imports.py),
which is tied to this repository's layout, with something a plugin
outside the repository can run. Because it reads the surface from the
*installed* SDK, running it against the lowest SDK in a provider's
range names exactly what that version lacks (the spec's edge case).

**Alternatives considered**: *in `contract.testing`* (any contract
change needs a contract version bump, and the contract does not know
the kit; rejected).

### R10. A release is refused in two ways

**Decision**:

1. The existing byte probe extends to the three SDK distributions by
   listing them under `glob_exclude`: a release is refused when their
   built bytes differ from the index's under the same version.
2. A new baseline check: each SDK library keeps a committed record of
   its surface (every declared name with its kind and signature, model
   fields included) as of the first release of the current middle
   number. The check fails when a recorded entry is missing or
   different while the middle number is unchanged, and says which
   entry. Raising the middle number requires re-recording the baseline
   in the same change (`just surface-record`).

The baseline check is a test in each library's own suite, so `just
test` blocks on it, and the release script names it in its refusal.

**Rationale**: FR-011 needs the *right* number to change, which the
byte probe alone cannot tell. The byte probe covers "adding raises the
last number"; the baseline covers "removing or altering raises the
middle number". Neither needs the network during `just test`.

**Alternatives considered**: *compare against the published wheel's
surface at release time only* (the mistake would surface an hour into
a release walk instead of in the change that made it; rejected).

### R11. What runs at each end of the range

**Decision**: on every change the docker run tests two environments.

- **High end**: the highest version of each SDK line in the family's
  ranges, which is the workspace's. The family's whole suite runs:
  unit tests, pipeline tests, the golden, the import check. A library
  whose version is published comes from the index, otherwise from this
  repository's build, and the run prints which for each.
- **Low end**: the lowest version of each SDK line in the ranges. The
  family's unit tests and the import check run. The pipeline tests and
  the golden do not.

**Rationale for the limit at the low end**: the pipeline tests need the
engine, and the engine pins the kit exactly because it uses the kit's
internals. An environment holding the lowest kit therefore holds an
older engine or none. An older engine's emission is not this change's
emission, so the golden cannot be the judge there. What the low end
*can* prove is the thing a range promises: the family's code imports
and works against the oldest SDK it claims.

This narrows FR-013 as written ("tested"), and is recorded in the
plan's Complexity Tracking so the operator can reject it.

**Alternatives considered**: *install the older published core that
carried the lowest kit and run everything* (fails for reasons outside
the family whenever the core's part of the emission changed; a red
check nobody can fix; rejected); *make the engine depend on a range of
the kit* (the engine would have to be held to the surface; a larger
change than this feature; rejected).

With two version lines (R7) there are still two environments, not
four: the low end takes the lowest version of each line in the
family's ranges, the high end the highest of each.

At delivery both ends are 0.2.0 on both lines, so the two environments
differ only after the first last-number bump.

### R12. The local bar and the CI jobs

**Decision**:

- Three recipes: `just test-core`, `just test-docker-alone`,
  `just test-docker-install`.
- `just test` gains `test-core` and `test-docker-alone`. Neither needs
  a container daemon.
- `just test-docker-install` needs a daemon and the registry, so it
  joins `just full-test` and fails, rather than skips, without one.
- CI gets three jobs, each calling one recipe on every change.

**Rationale**: the constitution makes `just test` the local acceptance
bar; if CI ran checks the local bar did not, a local pass would not
predict CI. Story 1's fourth scenario asks for the isolated docker run
to be a job of its own.

**Cost**: in CI the core and docker runs happen twice, once inside
`just verify` and once as named jobs. Estimated three to five minutes
per push. **Alternative considered**: leave them out of `just test`
(rejected for the reason above).

### R13. One policy for a plugin that cannot be used

**Decision**: every way a plugin can be unusable gets the same
treatment. The plugin is skipped, one ERROR line names it and the
cause, every command on a configuration that does not use it works,
and a configuration that does use it fails validation with a message
that says the plugin is installed and why it could not be used. This
covers: import or `initialize` failure (already so); refusal for
namespace, conformance or group; a broken commands, hooks or bootstrap
entry point.

A collision is the same case with two plugins: both are skipped, one
line names both and the thing they both claim, and neither wins. This
covers: a registry key, a command name, a bootstrap section name, an
entry-point name within a group, an enrollment kind, a field kind, and
an image-source catalog block for a runtime type another plugin
registers. Terraform module names and bare `type:` words already
behave correctly and are held by a test each.

**Rationale**: FR-016 and FR-017, and the operator's stated rule that
the system fail the same way every time. "Skip both" is the only
outcome that does not depend on load order.

**Alternatives considered**: *first one wins, with a warning* (order
dependent; and it is what FR-017 forbids); *refuse every command when
any collision exists* (contradicts FR-016).

**Kinds a plugin registers by a call of its own** (enrollment kinds,
field kinds), added in convergence (T128, T137, T138). Two questions are
answered apart. *Who collides* over a kind is whoever's load added it,
whatever defines its code, so a collision always names both plugins.
*What a skipped plugin loses* is only the kinds whose code is defined in
its own package (the package its entry point names); a kind a library
registered when the plugin imported it stays, because a library's
module runs once per process and another plugin that imports it relies
on what it registered without registering it again.

**A stated limit.** Code is judged by the module that defines it (the
function a `functools.partial` wraps is followed). A kind a plugin
builds from a library's code, such as a renderer a library's factory
returns or an instance of a library's handler class, therefore reads as
the library's and is kept when the plugin is skipped. Telling the two
apart would need knowing which plugin a library's registration was meant
for, which a module that runs once cannot say. Keeping it is the side
that cannot break a usable plugin. No plugin in this repository builds a
kind that way.

**Where this spec stops, by the operator's decision of 2026-11-18.** A
plugin registers these kinds as a side effect of being imported, into
registries every run in the process shares, and the loader can only
infer afterwards who registered what and undo it. Five rounds of
convergence found that inference wrong in a new order-dependent case
each time. Four cases are left as they are, all latent (in this
repository only the Okta plugin registers a kind, from its own module):

1. A plugin that fails while loading may leave behind a kind a library
   registered for it; a usable plugin that registers the same kind is
   then skipped as colliding with the system, in one discovery order
   and not the other (T140).
2. The second plugin of a kind collision never becomes a candidate, so
   a third plugin that collides with the first on another key is
   skipped in some orders and loads in others (T141).
3. A kind has one recorded owner; when two plugins depend on the code
   that registers it and the one found first is skipped, the other
   loses the kind (T142).
4. When two plugins share a library that registers a kind and a third
   plugin claims it, which of the two is named and skipped depends on
   order, and the other loses the kind (T143).

The cure is not more inference but no side effect: a plugin declares
its kinds in its metadata and the loader registers them, so a skipped
plugin's kinds are never registered at all. That changes the contract
and is specified on its own, as `specs/004-kinds-in-metadata`.

*Superseded by [spec 004](../004-kinds-in-metadata/spec.md):* kinds
are now declared in a plugin's metadata and registered by the system
for the plugins it accepts; the inference above is removed, and the
four cases are tested there as declared kinds, each in every order.

### R14. A provider disagreement fails only the roots that share it

**Decision**: the collector's agreement check runs per provider name:
when emitting a root, it checks only the providers that root declares,
against the other roots that declare the same ones. The failure names
the provider and every root in the disagreement.

**Rationale**: FR-018. The run-wide form exists to "catch config drift
early", by its own docstring; nothing shared between roots depends on
it. So narrowing it to the providers a root declares loses no
protection that root needs. **read**

### R15. The core asks what is declared, not what is installed

**Decision**: where the core today asks every *installed* class a
question, it asks the classes the configuration *declares*. Known
places: failure classification, credential prefixes for preflight, and
the image-source catalog. Stand-in selection (R17) and plugin
discovery itself are the stated exceptions.

**Rationale**: FR-015 and Story 4. Installing a provider beside docker
must not change a docker-only run, and each of these is a way it can.

### R16. Process-wide state

**Decision**: the docker family itself mutates nothing process-wide
(**read**). One core item changes: `plugin_state` keys carry the
plugin's namespace, so two plugins cannot meet on one key. The test
kit ships an assertion that a load and a dry run leave the
environment, the working directory, `sys.path` and the root logger as
they were; the family runs it.

**One stated exception**: the kit's opened-secret store
([encryption.py](../../packages/base/src/cs_image_system/base/encryption.py),
`_OPENED`) stays shared by every run in the process. The docker
family adds to it when a configuration gives it an encrypted host. It
is shared by a recorded decision: what another run opened can only
make a run hide one value more, never one fewer, and a store per run
would put every reader into the safety path for no guard gained
(**read**, from the comment beside it). FR-020 as written does not
allow it, so the exception is recorded in the plan's Complexity
Tracking. The isolation assertion checks that this store only grows.

**Rationale**: FR-020, and Constitution V, whose safety path the
shared store is part of.

### R17. The local stand-in

**Decision**: a runtime class that returns a factory from the existing
`local_test_target()` has declared itself a stand-in. No new contract
member. With one such class installed, the modification tests use it
and print which. With two or more, the command requires
`--stand-in <type>` and fails until given. With none, or with the
daemon unreachable, the result is a failure unless the caller passed
an explicit exclusion.

**Rationale**: FR-007 and FR-008. The capability already exists in the
contract
([runtime.py:231](../../packages/contract/src/cs_image_system/contract/runtime.py#L231));
only the choosing changes.

**Boundary with specification 003**: 003 covers gates that report a
pass they did not earn. This plan changes only the modification
tests' stand-in path. The container-gated legs of `just full-test`
are 003's.

### R18. The install check

**Decision**: `just test-docker-install` builds the wheels, installs
`cs-image-system[docker]` from them into an empty environment, renders
the `standard-docker` starter with the installed command
(`init-config --from standard-docker`), then runs `validate` and a dry
`run --all` on it.

**What it needs on the machine**: `docker`, `packer`,
`ansible-playbook`, `bash` and `tofu` at the starter's declared
versions; a reachable container daemon; and the registry, because a
dry run resolves the base image with a pull. The CI image carries all
of the tools and the jobs mount the daemon's socket. **read**

**Rationale**: FR-021. Using the starter means the check also covers
the starter shipped in the wheel.

### R19. Proving that nothing moved

**Decision**: FR-022 is proved by comparison before and after, on the
same day:

- the reference configuration: `just cli config-drift` exits 0 on
  `develop` before the work and on the feature branch after it;
- the `standard-docker` starter: the emission that
  `just test-docker-install` leaves when told to keep it, compared
  with the same from `develop`.

No starter golden is added.

**Rationale**: a starter's real emission holds a resolved image
digest, which changes when the vendor moves the image; a committed
golden of it would fail for reasons unrelated to any change here.

### R20. The guide, and the counts

**Decision**: one new document, `docs/WRITING_A_PROVIDER.md`, with the
docker family as its example. The four places that explain how to
write a plugin today (the contract's README, `docs/OPERATIONS.md`,
`docs/PLUGINS.md`, the dummy plugin's README) keep what is specific to
them and link to it. Each hand-kept count that this feature makes
false is deleted, not updated (Constitution VIII).

### R21. Sequencing with releases

**Decision**: nothing in this feature is released by it. The first
release after it publishes both SDK lines at 0.2.0 and the new docker
project for the first time. The contract does not change, so its
version does not.

### R22. The Terraform libraries are separable, and stay

**What is true today** (**read**):

- Nothing in the contract, the kit, the engine or the command line
  imports either library. The direction is already right.
- `hashicorp-utils` depends on the contract alone, and a test holds it
  to that.
- `tofu-roots` imports nine kit modules, all under `base.basic` and
  `base.models`, pins the kit exactly, and calls the kit's
  underscore-prefixed `_get_context` in 28 places.
- Three of the five test files in the two packages use the shared
  harness (`test_packer_collector.py`, `test_terraform_collector.py`,
  `test_roots.py`), so they need every provider installed today.
- Ten packages depend on one or both: the three runtimes, the three
  roots plugins, the packer plugin, the Okta plugin, `tofu-roots`
  itself, and the top-level package.

**Decision**: FR-026 is met by five things, none of which moves a
file out of the repository.

1. Each library declares its surface (R8). For `tofu-roots` that
   includes the hooks providers override.
2. The two share a version line of their own (R7).
3. `tofu-roots` pins the kit by a range and passes the import check
   (R9) as a provider does. The kit members it uses, `_get_context`
   among them, go on the kit's surface as named hooks or it stops
   using them.
4. One test holds the reverse direction: no module of the contract,
   the kit, the engine or the command line imports either library.
5. `just test-terraform-alone` runs the two packages' tests in an
   empty environment that holds only them and their declared
   dependencies, at both ends of `tofu-roots`' range on the kit. The
   three files that use the shared harness are ported to the test kit
   where they keep what they assert, and otherwise move to the
   every-provider suite (rule 1 of R4).

**Rationale**: the libraries are already a leaf in the import graph;
what they lack is a boundary anyone can check. These five give them
the same boundary the docker family gets, so the later specification
that moves them has nothing to untangle.

**Alternatives considered**: *treat them as part of the core and
skip the isolated run* (they would stay provable only inside the
repository, which is what FR-026 exists to end; rejected); *move them
now* (FR-026 says this feature does not).

**A consequence for item 5**: `tofu-roots`' tests that need a whole
run need the core, as a provider's do. Its unit tests need only the
kit and `hashicorp-utils`. The same limit as R11 applies at the low
end of its range.
