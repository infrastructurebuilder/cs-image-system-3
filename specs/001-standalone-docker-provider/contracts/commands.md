# Contract: recipes, CI jobs and the messages they print

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R6, R11 to R13, R17, R18

These are the commands a person or a CI job runs, what each needs, and
exactly when each passes. They serve FR-004, FR-007, FR-008, FR-013,
FR-016, FR-017, FR-021 and FR-026.

## Recipes

### `just test-core`

Builds the wheels, installs a plain `cs-image-system` (no extras) with
the test kit's extra into an empty environment, and runs the core
suite there.

- **Needs**: nothing beyond what `just init` needs. No daemon.
- **Passes when**: at least one test was collected, none was skipped,
  none failed.
- **Prints**: the installed distributions, then the counts.

### `just test-docker-alone`

Builds the wheels and runs the docker family's suite three times, each
in its own empty environment:

| Run | Environment | Tests |
| --- | --- | --- |
| High end, in place | The family and its declared dependencies, SDK at the highest version of the family's range | The whole suite and the import check |
| High end, copy | The same, with the family's directory copied outside the workspace and installed from the copy | The whole suite |
| Low end | The family, SDK at the lowest version of its range | The unit tests and the import check |

The fourth setting the spec names, beside every other provider, is not
run here: `just pytest` runs the family's suite in the workspace
environment, against the same golden.

- **Needs**: no daemon. The index, to learn whether an SDK version is
  published and to fetch it if so.
- **Passes when**: every run collected at least one test, skipped
  none and failed none.
- **Prints**, for each run, one line per SDK library:

```text
<library> <version> from the index
<library> <version> from this repository's build (development install)
```

When the lowest and highest versions are the same, it says so and
still runs the low-end tests.

### `just test-terraform-alone`

Builds the wheels and runs the tests of the two shared Terraform
libraries in empty environments that hold only the two libraries and
the dependencies they declare (FR-026):

| Run | Environment | Tests |
| --- | --- | --- |
| High end | Both libraries, the kit at the highest version of `tofu-roots`' range | Both packages' whole suites and the import check |
| Low end | Both libraries, the kit at the lowest version of that range | Their unit tests and the import check |

- **Needs**: no daemon. The index, as for `test-docker-alone`.
- **Passes when**: every run collected at least one test, skipped
  none and failed none.
- **Prints**: where the kit came from, in the same two forms as above.

### `just test-docker-install`

Builds the wheels, installs `cs-image-system[docker]` from them into
an empty environment that holds nothing else, renders the
`standard-docker` starter with the installed command, then runs
`validate` and a dry `run --all` on it.

- **Needs**: `docker`, `packer`, `ansible-playbook`, `bash` and `tofu`
  at the starter's declared versions; a container daemon that answers;
  the registry.
- **Passes when**: the install, the validation and the dry run each
  ran and each succeeded. A step that could not start is a failure.
- **Option**: `keep=<directory>` leaves the emitted tree there, for
  the before-and-after comparison of FR-022.

### `just sdk-bump <kit|terraform> <last|middle>`

Moves one version line: the kit's, or the two Terraform libraries'
together, and every exact pin on the members of that line. Does not
touch the other line, the workspace version, the contract, or any
range. After `middle`, the ranges that name that line are the
person's to move, and `just surface-record` must be run.

### `just surface-record`

Rewrites each SDK library's baseline from its code. Refuses when the
MIDDLE number is the same as the baseline's and an entry would be
removed or changed.

### Changes to existing recipes

| Recipe | Change |
| --- | --- |
| `just test` | Runs `test-core`, `test-docker-alone` and `test-terraform-alone` after the unit tests. |
| `just full-test` | Gains `test-docker-install` as a leg that fails, not skips, without a daemon. |
| `just golden-regen` | Takes which golden to regenerate: the shared one (the default, as today), the core's, or docker's. |

## CI jobs

Added to the main workflow, on every push and pull request, in the
same runner image as the existing jobs:

| Job | Runs |
| --- | --- |
| `core-alone` | `just test-core` |
| `docker-alone` | `just test-docker-alone` |
| `terraform-alone` | `just test-terraform-alone` |
| `docker-install` | `just test-docker-install` |

None has a condition that lets it report success without running its
recipe.

## Messages

### A plugin that cannot be used

Logged once, at ERROR, while plugins load. The command continues.

```text
Plugin <name> (<distribution>) is skipped: failed to import: <error>
Plugin <name> (<distribution>) is skipped: refused: <reason>
Plugins <a> (<distribution>) and <b> (<distribution>) are both skipped: both register <kind> '<name>'
```

What both register is one of: a registry key (written
`<classification> <namespace>/<name>`), `command '<path>/<name>'`,
`bootstrap section '<name>'`, `entry point '<name>' (<group>)`,
`enrollment kind '<name>'`, `field kind '<name>'`, or
`image-source block '<runtime type>'`.

A plugin that claims something the system itself already holds (a
built-in command, the system's own bootstrap section, one of its field
kinds) is skipped alone, in one line that names the plugin and what it
claimed.

A plugin's commands and its bootstrap section are read apart from its
classes, each through an entry point of its own. One that cannot be
used is skipped the same way, and the line says which part failed
(`its commands`, `its bootstrap section`). The command line still
starts, and `--help` still answers.

Two bootstrap sections that declare one Terraform provider differently
refuse the generated root, in one line that names the provider and
both sections. The answers already given are kept.

### A configuration that needs such a plugin

Printed by `validate` as a configuration error, exit status 1:

```text
 - <kind> type '<word>' is registered by <plugin>, which is installed but could not be used: <cause>
```

The existing message for a word no installed plugin registers
("install the extra: ...") is unchanged and is used only when the
plugin really is absent.

A plugin whose module did not import registered nothing, so the words
it would have registered are not known. A configuration that names a
word nothing usable registers therefore gets the unknown word's own
line, followed by one line for each such plugin:

```text
   (installed but could not be used: <plugin> (<distribution>): failed to import: <error>)
```

### Two plugins claim one bare word

Unchanged: validation names the word, both qualified forms, and asks
for one of them to be written.

### Terraform provider disagreement

Raised when a root is emitted, and only for a provider that root
declares. The message is the collector's own, unchanged, and names the
provider and every root in the disagreement:

```text
Irreconcilable version constraints for '<name>': '<constraint>' requested by <a>; '<constraint>' requested by <b>
Provider '<name>' requested with different sources: [<sources>] (requested by [<a>, <b>])
```

A root that does not declare the provider is emitted as if the
disagreement were not there. The run-wide form of the check
(`validate_all()`, every provider) is unchanged for a caller that
wants it; emission uses the per-root form (`validate_for(<root>)`).

### The stand-in

Printed by the modification tests:

```text
stand-in: <runtime type> (the only one installed)
stand-in: <runtime type> (named with --stand-in)
```

Failures, exit status 1:

```text
stand-in: <a>, <b> can both serve; name one with --stand-in
stand-in: no installed plugin can serve; the modification tests did not run
stand-in: <runtime type> did not answer (<cause>); the modification tests did not run
```

The last two become a recorded exclusion, exit status 0, only when the
caller passed the explicit exclusion option.
