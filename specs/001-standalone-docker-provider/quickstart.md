# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Commands**: [contracts/commands.md](contracts/commands.md)

This is the run guide for accepting the feature once it is built. Each
step is a command that passes or fails. Nothing here applies anything:
every run is stubbed or a dry run.

Every box is run on your local machine, in a shell at the repository
root, on the branch `feature/001-standalone-docker-provider`. Times
are estimates.

## Before you start

- `just init` has been run on this branch.
- For steps 6 and 7: a container daemon is running, and `docker`,
  `packer`, `ansible-playbook`, `bash` and `tofu` are on the path.
- For step 7: the reference configuration is checked out beside this
  repository as `cs-image-system-testconfig`, and the cloud sessions
  its dry run needs are live.
- For step 7: the reference's "before" result exists. Task T003 makes
  it before any change and records it in
  [tasks.md](tasks.md). The starter's "before" emission is made on the
  day of the comparison, in step 7 itself.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | The docker family alone, in place, from a copy, at both ends of its SDK ranges | Story 1; FR-001 to FR-003, FR-012 to FR-014; SC-001, SC-003, SC-004, SC-005 |
| 2 | The docker family's golden agrees with the shared golden | FR-015, FR-025; SC-003 |
| 3 | The core alone | Story 2; FR-005, FR-006; SC-002, SC-009 |
| 4 | The shared Terraform libraries alone | FR-026; SC-011 |
| 5 | The local bar: every suite, the surface rule, the interference cases | Stories 3 and 4; FR-007 to FR-011, FR-016 to FR-020; SC-006 |
| 6 | The usual install delivers docker | FR-021; SC-010 |
| 7 | Nothing moved for the reference or the starter | FR-022; SC-007 |
| 8 | The guide, and the statements corrected | Story 5; FR-023; SC-008 |
| 9 | The release bar | all |

## Step 1: the docker family alone

About 3 minutes.

```sh
# step 1 -- box 1 of 1 -- v1
just test-docker-alone
```

Expect three runs (high end in place, high end from a copy, low end),
each ending in a count with `0 skipped`, and before each run one line
per SDK library saying where it came from: `from the index` or
`from this repository's build (development install)`. Before the first
release that publishes the SDK at 0.2.0, every line says the second.

Fails if any run collected no tests, skipped one, or failed one.

## Step 2: the two goldens agree on docker

The docker family's golden and the shared golden pin the same docker
emission. Under 10 seconds.

```sh
# step 2 -- box 1 of 1 -- v1
for d in base-image/pckr-docker instance-image/pckr-docker \
         instance-image/tofu-docker storage/docker-volume; do
  diff -r "packages/docker-plugin/tests/golden/generated/$d" \
          "tests/fixtures/golden/generated/$d" || echo "DIFFERENT: $d"
done; echo "compared"
```

Expect `DIFFERENT: instance-image/tofu-docker` and then `compared`,
and no other `DIFFERENT` line. The one difference is recorded under
T022 in [tasks.md](tasks.md): in the shared golden the docker instance
root also carries remote-state blocks for the AWS storage builders
(`aws_efs`, `aws_ebs`, `aws_s3`), because the shared fixture declares
them and the family's fixture does not. (The Google Cloud ones it also
carried left the shared fixture with spec 005.) Every other docker file is byte-identical.

The other half of "beside every other provider" is step 5: the same
family suite, against the same golden, passes in the workspace
environment where every provider is installed.

## Step 3: the core alone

About 3 minutes.

```sh
# step 3 -- box 1 of 1 -- v1
just test-core
```

Expect the list of installed distributions to hold no docker, AWS,
Google Cloud or Okta plugin, and the count to end in `0 skipped`.

## Step 4: the shared Terraform libraries alone

About 2 minutes.

```sh
# step 4 -- box 1 of 1 -- v1
just test-terraform-alone
```

Expect three runs (the roots library and the collectors library at the
high end of the kit range that `tofu-roots` declares, and the roots
library again at the low end), each listing as installed only the two
libraries, the kit, the contract and third-party packages, and each
ending in a count with `0 skipped`.

The other half of FR-026, that no module of the contract, the kit, the
engine or the command line imports either library, is a test that
step 5 runs.

## Step 5: the local bar

About 35 minutes.

```sh
# step 5 -- box 1 of 1 -- v1
just test
```

Expect lint clean, the type check at zero errors, and every test
passing. This run includes, by name of what each proves:

- the shared golden, unmoved;
- the docker family's suite beside every other provider;
- every workspace plugin, and both Terraform libraries, passing the
  surface check;
- each SDK library's baseline check;
- no core module importing a Terraform library;
- a plugin that fails to import, one that is refused, and one whose
  commands entry point is broken, each skipped and named while a
  configuration that does not use it still works;
- each collision (type, command, bootstrap section, entry-point name,
  enrollment kind, field kind, image-source block) reported with both
  plugins named and neither winning;
- a provider disagreement failing only the roots that declare that
  provider;
- the stand-in with one, with two and with none installed;
- a docker-only configuration that validates and completes a dry run
  with a deliberately broken extra plugin installed.

## Step 6: the usual install

About 4 minutes. Needs the container daemon.

```sh
# step 6 -- box 1 of 1 -- v1
just test-docker-install keep="$TMPDIR/after-standard-docker"
```

Expect three results in order, each saying it ran and succeeded: the
install of `cs-image-system[docker]` from the built wheels, the
validation, the dry run.

To see that the check bites, the suite holds the cases in which a step
does not succeed (`tests/test_isolated_run.py`): a failed install
reports the validation and the dry run as not run, a failed validation
reports the dry run as not run, and each fails the check.

## Step 7: nothing moved

The reference configuration. About 5 minutes.

```sh
# step 7 -- box 1 of 3 -- v1
just cli config-drift; echo "exit=$?"
```

Expect `exit=0`, the same as the result task T003 recorded.

The `standard-docker` starter. Its "before" emission comes from the
commit this branch started from, `be648dbb` (task T003's record),
checked out beside the repository for the purpose. Since the branch
merged, a merge-base with `develop` is `develop` itself, so the box names
that commit. A difference that spec 004 or spec 005 made on purpose is
read against their records, not counted against this specification. Both emissions must be made on the same day, because
the starter's emission holds the resolved digest of a vendor image.
About 6 minutes.

```sh
# step 7 -- box 2 of 3 -- v2
base=be648dbb
git worktree add --detach "$TMPDIR/csis-001-before" "$base"
( cd "$TMPDIR/csis-001-before" && just init \
  && uv run cs-image-system init-config "$TMPDIR/before-tree" --from standard-docker \
  && uv run cs-image-system --root-dir "$TMPDIR/before-tree" run --all )
ls "$TMPDIR/before-tree/generated" | head -5
```

Expect a listing of lifecycle directories. If the dry run asks for the
starter's test identity, export it as the starter's own `README` says
and run the box again.

Under 10 seconds, after step 6. A dry run's emission carries the run's
own id and its time stamp in image names, and the "before" tree holds
what `tofu init` left behind, so the two trees are compared as
`config-drift` compares an emission: after the system's own
normalisation of exactly those things.

```sh
# step 7 -- box 3 of 3 -- v2
uv run python - "$TMPDIR/before-tree/generated" "$TMPDIR/after-standard-docker/generated" <<'PY'
import shutil, sys, tempfile
from pathlib import Path
from cs_image_system.engine.commands.emission import diff_trees, normalise_emission
with tempfile.TemporaryDirectory() as td:
    sides = []
    for name, src in zip(("before", "after"), sys.argv[1:3]):
        dst = Path(td) / name
        shutil.copytree(src, dst, symlinks=True)
        normalise_emission(dst)
        sides.append(dst)
    print("\n".join(diff_trees(*sides)) or "identical")
PY
```

Expect `identical`. Afterwards the temporary checkout can be removed
with `git worktree remove "$TMPDIR/csis-001-before"`.

## Step 8: the guide

```sh
# step 8 -- box 1 of 1 -- v1
grep -rn "contract alone" --include='*.md' --include='*.toml' --include='*.py' \
  . 2>/dev/null | grep -v -e '^./ATTIC/' -e '^./specs/' -e '^./.venv/' \
  -e 'contract-example-plugin'; echo "searched"
```

Expect the single line `searched`.

Then the reading test of Story 5: a person who did not write the
docker family opens `docs/WRITING_A_PROVIDER.md`, follows it, and
arrives at step 1's command passing. The guide is written by this
feature, so the path is not a link yet.

## Step 9: the release bar

About an hour. Needs the container daemon and the live sessions.

```sh
# step 9 -- box 1 of 1 -- v1
just full-test
```

Expect `full-test: passed`, with the docker install leg listed as run.
