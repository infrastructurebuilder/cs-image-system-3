# Contract: the SDK surface, its check and its version rule

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R7 to R11

This is what a plugin author may rely on. It serves FR-009 to FR-014,
FR-019 and FR-026.

## What the SDK is

Three distributions on two version lines:

| Distribution | Import package | Version line |
| --- | --- | --- |
| `cs-image-system-base` (the kit) | `cs_image_system.base` | the kit's |
| `cs-image-system-hashicorp-utils` | `cs_image_system.hashicorp_utils` | the Terraform libraries' |
| `cs-image-system-tofu-roots` | `cs_image_system.tofu_roots` | the Terraform libraries' |

The two Terraform libraries are themselves written against the kit's
surface, as a provider is: `tofu-roots` pins the kit by a range and
passes the import check below.

The contract (`cs-image-system-contract`) sits underneath, with its
own version and its own rule, unchanged by this feature. Everything
public in the contract may be imported.

## The declaration

Each SDK library has a module named `surface` that holds its
declaration. A plugin may:

- import a name the declaration lists, from the module it lists it
  under;
- subclass a listed class;
- override or call an underscore-prefixed member of a listed class
  only if the declaration lists that member as a hook.

Everything else in the three libraries is private, including public-
looking names that are not listed.

## The version rule

Each version line is `0.MIDDLE.LAST`, starting at 0.2.0. The two
lines move independently; the table applies to each.

| Change | Number that must rise |
| --- | --- |
| A listed name or hook is removed | MIDDLE |
| A listed name or hook changes: parameters, defaults, annotations, a model's fields, a constant's value | MIDDLE |
| A name or hook is added to the declaration | LAST |
| Any other change to the bytes of an SDK distribution | LAST |

A provider declares each SDK library it uses as a range covering one
MIDDLE number of that library's line, for example `>=0.2,<0.3`, and
may raise the floor within it (`>=0.2.3,<0.3`) when it starts to use
something added later. `tofu-roots` declares the kit the same way.

## The import check

```text
python -m cs_image_system.base.surface check <source directory>
python -m cs_image_system.base.surface check --tests <tests directory>
```

It reads source files and does not import them. It reads the surface
from the SDK that is installed.

Exit status 0 when nothing is found. Exit status 1 otherwise, with one
line per finding:

```text
<file>:<line>: <import or member> — <reason>
```

Reasons, on a source directory:

| Finding | Reason printed |
| --- | --- |
| An SDK name that the installed library does not list | `not on the surface of <library> <version>` |
| An override of, or access to, an SDK underscore member that is not a listed hook | `private to <library>` |
| Anything of `cs_image_system.engine` or `cs_image_system.system` | `a plugin may not import the engine` |
| Any other `cs_image_system` package that is not the plugin's own | `another plugin` |

With `--tests`, two more things are allowed: the test kit
(`cs_image_system.system.testing`) and the plugin's own `testing`
module.

The same check is callable from a test, returning the findings as a
list.

Guarantee: run against the lowest SDK version in a provider's range,
the check names every name the provider uses that that version lacks.

## The baseline check

Each SDK library has a committed baseline: its surface entries as of
the first release of the current MIDDLE number. A test in the
library's own suite regenerates the entries from the code and fails
when:

| Situation | Message names |
| --- | --- |
| A baseline entry is missing from the code, MIDDLE unchanged | the entry, and that MIDDLE must rise |
| A baseline entry differs from the code, MIDDLE unchanged | the entry, both forms, and that MIDDLE must rise |
| MIDDLE is higher than the baseline's | that the baseline must be re-recorded (`just surface-record`) |

An entry the code has and the baseline lacks is an addition. It keeps the rule, and it fails this check until
it is recorded (`just surface-record`, which may add under the same MIDDLE): an addition left out of the
baseline could later be removed or altered with nothing to notice it.

## What refuses a release

A release is refused, before anything is built or uploaded, when
either holds:

1. The built bytes of an SDK distribution differ from what the index
   holds under the same version. (The existing probe, extended to the
   three.)
2. The baseline check fails.

The refusal names the distribution and, for the second case, the
entry.
