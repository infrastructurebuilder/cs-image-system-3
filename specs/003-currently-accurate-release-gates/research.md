# Research: Release gates that cannot report a pass they did not earn

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each decision is marked with what it rests on: **read** (seen in the
code on 2026-11-21, at `develop` `35446e3f`), **decided** (the
operator's answer in the spec's Clarifications) or **chosen** (this
plan's choice, with the alternatives). The spec has no Clarifications
section, so nothing here is **decided**; every choice the operator
should make is listed in the plan under "Decisions for the operator"
with a recommended default, and is marked here as **chosen, pending the
operator**.

## R1. Every way a gate passes today without checking

**Read.** Eleven places where a check that did not run is reported as
a pass, or is not reported at all:

| # | Where | What happens |
| --- | --- | --- |
| 1 | [Justfile:212-231](../../Justfile#L212) | without `docker info`, eight legs (`test-mods`, `test-posix-accounts`, `test-bake-steps`, `runner-image`, `test-docker-bake`, `test-docker-cycle`, `test-podman-cycle`, `test-podman-desktop-cycle`) print one `SKIPPED` line and the run goes on to `full-test: passed` |
| 2 | [Justfile:232-233](../../Justfile#L232) | without the reference configuration beside the checkout, the dry run `--all` and `state query --strict` print `SKIPPED` and pass |
| 3 | [Justfile:234, 246-247](../../Justfile#L234) | with a session absent or expired (`just preflight` exit 2), the same two legs print `SKIPPED` and pass |
| 4 | [Justfile:494-500](../../Justfile#L494), [514-526](../../Justfile#L514) | `test-podman-cycle` without `CSIS_PODMAN_HOST`, and `test-podman-desktop-cycle` without a running Podman machine, print `SKIPPED` and exit 0 even when docker answers |
| 5 | `just test` (its `pytest` step) | 23 tests are skipped on every run: the five container files `tests/test_posix_containers.py` (14), `tests/test_bake_steps_containers.py` (6), `tests/test_docker_bake_live.py`, `tests/test_docker_cycle_live.py` and `tests/test_docker_starter_live.py` (1 each), each gated by an environment variable its leg sets (`CSIS_CONTAINER_TESTS`, `CSIS_DOCKER_BAKE`, `CSIS_DOCKER_CYCLE`; [Justfile:440, 449, 462, 474](../../Justfile#L440)). Counted with `pytest --collect-only` over those files: 23 |
| 6 | the same five files, inside their legs | with the leg's variable set, a missing `packer`, `ansible-playbook` or `tofu` skips the test ([test_docker_cycle_live.py:54-60](../../tests/test_docker_cycle_live.py#L54)), and a daemon already holding the leg's names skips it ([test_docker_starter_live.py:62-64](../../tests/test_docker_starter_live.py#L62)); pytest exits 0 when every test skipped, so the leg passes |
| 7 | the dry run `--all` leg | the Okta workspace, without `OKTA_API_*` in the environment, logs a warning and skips `plan` for the user root ([okta_tf_workspace.py:20-22, 221-228](../../packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_tf_workspace.py#L20)); the leg passes having planned less than the tree. The Justfile says so as a feature ([Justfile:73-74](../../Justfile#L73)) |
| 8 | [Justfile:722-727](../../Justfile#L722) (`fixture-live`, CI's `live` job) | without docker, `test-mods` prints `SKIPPED` and the recipe passes |
| 9 | [ci.yml:191-217](../../.github/workflows/ci.yml#L191), [ci-from-scratch.yml:73-101](../../.github/workflows/ci-from-scratch.yml#L73) | the `live` job with none of its four secrets says `SKIPPED` in its summary and ends green |
| 10 | [ci.yml:297-331](../../.github/workflows/ci.yml#L297) | the `publish` job with no index token ends green; a final tag without `STARTER_PUSH_TOKEN` publishes no template repository and ends green |
| 11 | [release.py:643-651](../../scripts/release.py#L643) | when `session-minutes-left` cannot answer, the probe says "every runtime session of the live configuration is present" (the line `just preflight` earned, said again over a question nobody answered) |

The release's PyPI probes ([release.py:625-660](../../scripts/release.py#L625))
exist because of items 1 to 3: they ask for docker and the sessions
before the gate, since the gate would skip without them. They are asked
once, about an hour before the legs that need the sessions run.

**Read, and already honest.** The isolated runs (`test-core`,
`test-terraform-alone`, `test-docker-alone`) and the install check fail
on a skip or a step that did not run
([isolated-run:252-260](../../scripts/isolated-run#L252), reading
[strict.py:23-33](../../packages/system/src/cs_image_system/system/testing/strict.py#L23));
`test-docker-install` and `test-docker-live` fail without a daemon
([Justfile:205-211](../../Justfile#L205)); `own-versions-current`,
`with-released-families --check` and `publish-target-ready` refuse when
they cannot ask ([release.py:547-593](../../scripts/release.py#L547),
`UNASKED`, `ELSEWHERE_UNASKED`, exit 2); `test-mods --strict` exits 1 on
any skipped modification test, and without a stand-in fails unless
excluded (spec 001, research R17).

## R2. The leg runner moves into the release script

**Chosen.** `full-test-legs` stops being 57 lines of bash in the
Justfile and becomes a command of [scripts/release.py](../../scripts/release.py)
(`release.py full-test-legs [without=...] [list]`), with the legs as one
table of data (name, prerequisites, command) and the run, the
exclusions and the summary as functions over the script's existing
`run` callable. The recipe becomes a one-line wrapper, as `release`,
`release-finish` and `publish` already are.

Why there: the release's PyPI gate is this run; with the legs in the
same script the gate calls them in-process and has the summary for the
release record (R9) without a file passed between processes; and the
script's stubbed shell, which its 1,235 lines of tests already use,
makes every verdict testable without a daemon, a session or a cloud.

**Alternatives considered**:
- *Keep the bash and add the counts to it.* Rejected: its only tests
  read its text ([test_justfile_contract.py:99](../../tests/test_justfile_contract.py#L99),
  [test_ci_runner.py:162](../../tests/test_ci_runner.py#L162),
  [test_podman_machine_host.py:123](../../tests/test_podman_machine_host.py#L123)),
  which Principle IX forbids, and the legs themselves cannot be run in
  a test.
- *A new script `scripts/full-test`.* Rejected by FR-016: no new release
  script.

## R3. How an exclusion is asked for

**Chosen.** By words on the command line, each `without=<name>[,<name>...]`:

```text
just full-test without=docker
just full-test without=reference,test-cloud-starters
```

A name is a leg's name or a prerequisite's name, which stands for every
leg that needs it. The prerequisites are two: `docker` (a container
daemon that answers `docker info`, and the tools the docker legs call:
`packer`, `ansible-playbook`, `tofu`) and `reference` (the reference
configuration at `config_root`, `just preflight` exit 0, and the
identity credentials of R8). A name that is neither refuses the run
before any leg starts (exit 2), so a misspelling never excludes
anything. No environment variable, file or absent tool excludes a leg
(FR-003): `CSIS_CONTAINER_TESTS`, `CSIS_DOCKER_BAKE` and
`CSIS_DOCKER_CYCLE` are removed (R6). `just full-test-legs list` prints
the table (each leg and its prerequisites) and runs nothing, so the
documents link to it rather than list the legs by hand (Principle VIII).

**Alternatives considered**:
- *An environment variable (`CSIS_FULL_TEST_EXCLUDE`).* Rejected: an
  exported variable is an exclusion a developer did not ask for in this
  run (FR-003, the edge case "impossible to get by accident").
- *A second recipe (`full-test-quick`).* Rejected: it hides which
  checks were left out, and the spec asks that they be named.
- *Leg names only.* Rejected: a developer without a daemon would type
  nine names; the prerequisite names keep the exclusion short without
  making it implicit.

## R4. The summary and the exit status

**Chosen.** Every run ends with the three counts and one of three
results, the last line of the run (the contract:
[contracts/full-test-verdict.md](contracts/full-test-verdict.md)):

```text
full-test: passed -- 12 run, 0 excluded, 0 failed
full-test: passed WITH EXCLUSIONS -- 4 run, 8 excluded on request (docker: test-mods, ...), 0 failed
full-test: FAILED -- 3 run, 0 excluded, 9 failed (did not run: test-mods, ... -- docker is not available; say without=docker to leave them out)
```

A leg that could not run because a prerequisite is missing, and was not
excluded, is counted as failed and named as "did not run" with its
cause. Exit 0 for both kinds of pass, 1 for a failure, 2 for a refused
word. Exit 0 for a pass with exclusions because the developer asked for
it by name and every check they required passed; the result line, not
the exit status, distinguishes the two, and the release cannot reach
the second (R9).

**Alternatives considered**: *a distinct non-zero exit for a pass with
exclusions.* Rejected: `just` and every shell treat any non-zero exit
as a failure, so the developer's own request would read as a failed
run, and the release needs no such code because it accepts no
exclusions at all.

## R5. The legs that need a session run first

**Chosen.** The table orders the `reference` legs (the dry run `--all`,
`state query --strict`, `test-mods`) first, immediately after
`just preflight`, and the slow docker legs after them. Today they run
last ([Justfile:232-248](../../Justfile#L232)), after the docker legs,
which take most of the run.

**Read.** A login lasts one hour and a PyPI release takes nearly all of
it ([release.py:641-658](../../scripts/release.py#L641)); `full-test`
runs after `just test` (about twenty minutes). Running the session legs
first shortens the window in which a session can lapse before they run.
A session that lapses while a leg runs fails that leg (its cloud call
is refused), which is a failure, not a skip (the spec's edge case).

## R6. The 23 tests `just test` skips

**Chosen.** The five container files move to `tests/containers/`, which
joins `norecursedirs` in [pyproject.toml](../../pyproject.toml) as
`tests/cloud_starters` already does, so the default run no longer
collects them. Their `skipif` markers on the leg's variable and on the
daemon are removed; the legs run them by path. Inside a leg a missing
tool or a daemon already holding the leg's names fails the test
(`pytest.fail`, with today's reason) instead of skipping it. The legs
run them under the strict session (`-p cs_image_system.system.testing.strict`).

The workspace's own pytest settings take the strict session in
`addopts`, so `just test` and every `just test-one` fail on any skip.
The remaining skip markers in the default run are guards on tools the
acceptance tests already require (`just`, `tofu`, `git`, `uv`: 19
markers, listed by `git grep -n "skipif\|pytest.skip" tests packages/*/tests`);
they are removed, so an absent tool fails by its own error, as the
isolated runs already require ([ci-from-scratch.yml:37-44](../../.github/workflows/ci-from-scratch.yml#L37)
installs `tofu` for that reason).

**Alternatives considered**:
- *A `conftest.py` `collect_ignore`.* Equivalent, but hidden in a file
  nobody reads for collection rules; `norecursedirs` already holds the
  one other exclusion.
- *Keep the files in place and leave the skips.* Rejected: a run that
  reports 23 skipped as part of a pass is the fault FR-001 names, and
  it is the TestPyPI gate's first step.

## R7. The Podman legs

**Chosen, pending the operator (D1).** The two Podman legs leave
`full-test` for a recipe of their own, `just test-podman` (both legs,
strict: no Podman service or machine fails it), which no gate requires.

**Read.** Today the legs run only when a Podman service is named or a
machine is running ([Justfile:494-526](../../Justfile#L494)), and pass
otherwise; so no release has ever required them. The spec keeps "which
checks a development release requires and which a final release
requires" as they are today; under FR-002, keeping them in `full-test`
would make every final release require a running Podman machine, whose
power state is the operator's.

**Alternatives considered**: *keep them as required legs* (every final
release then needs a Podman machine started by the operator: a change
to what a release requires, which the spec rules out unless the
operator chooses it); *keep them as legs a release may exclude*
(rejected by FR-006: a release has no optional checks).

## R8. The identity roots in the dry run

**Chosen, pending the operator (D2).** The `reference` prerequisite
includes the identity credentials the reference configuration's
identity roots read. The leg checks that each variable the Okta
workspace reads (`OKTA_API_CLIENT_ID`, `OKTA_API_SCOPES` and
`OKTA_API_PRIVATE_KEY`, or `OKTA_API_TOKEN`) is set and not empty,
before the dry run starts; absent, the leg did not run and fails.

**Read.** The warning and the skipped `plan` are the Okta plugin's
([okta_tf_workspace.py:221-228](../../packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_tf_workspace.py#L221));
`just preflight` reads only the runtimes' and state backends' sessions
([preflight.py:1-30](../../packages/engine/src/cs_image_system/engine/commands/preflight.py#L1));
the TestPyPI gate does not run the dry run. Spec 008 moves the plugin
to its own repository.

**Alternatives considered**: *make the plugin refuse to skip `plan`*
(the cure where the skip is made, but a change to the plugin's
behaviour that spec 008 is about to carry away; better done in that
repository, under its own tests); *give identity providers a
`session_status` hook so `preflight` reads them* (a contract protocol
member, budgeted at 0 here); *accept a dry run that plans less*
(rejected by FR-001).

## R9. The release's gate, its words and its record

**Chosen.**
- `release.py` refuses any word it does not know before anything else
  (exit 2): today a third word other than `yes` runs a real release
  ([release.py:792, 806](../../scripts/release.py#L792); `main` passes
  `ns.args[:3]`), so `just release patch pypi without=docker` would cut
  a release and ignore the exclusion. The refusal says a release has no
  optional checks (FR-006, US1 scenario 4).
- The PyPI gate calls the leg runner in-process with no exclusions; the
  TestPyPI gate runs `just test` and `test-docker-install` as today.
- **The record** (FR-008) is the body of the release commit
  `release <version>`: one line per required check of that gate, with
  "ran and passed" (the `test` step, then each leg). The commit is the
  record that travels with the tag; `git show v<version>` reads it.

**Alternatives considered**: *the tag's annotation* (equal, but the
commit body is what `git log` shows on `develop`); *the release's row in
`docs/CHANGES.md`* (a one-line table row; twelve checks do not fit it,
and that row is a history table, not a log).

## R10. What a release confirms again after the gate

**Read.** After the gate the release asks the index again
([release.py:781-782](../../scripts/release.py#L781)); the remote was
fetched and compared before the gate only ([release.py:803](../../scripts/release.py#L803)).

**Chosen.** After the gate and the index, before the bump: the fetch
probe again (`fetched_or_refuse`, the same function, so a remote that
moved is refused with the same words and the checkout returns to its
starting branch through `go_back`); and, for `release-take` alone, whose
remaining step (the take) needs the reference's sessions, `just
preflight` in the reference again. The plain `release` needs no cloud
session after its gate: its remaining steps need the index token (set,
not expiring) and `git push`. The tags line is not asked again: it
refuses nothing.

## R11. The probes before the gate stay

**Chosen.** The probes stay as an early refusal: they cost seconds, and
without them a missing daemon is found twenty minutes in. Their
reason changes from "the live legs would be skipped" to "the gate would
fail at them". Item 11 of R1 is corrected: when `session-minutes-left`
cannot answer, the line says the minutes could not be read, and refuses
nothing (`just preflight` has already passed).

## R12. The watcher reports a missing run in minutes

**Read.** A run not found is waited on to the timeout (sixty minutes;
[release-watch:354-379](../../scripts/release-watch#L354)) and then
said `NEVER STARTED` ([release-watch:426-429](../../scripts/release-watch#L426)).
A run started by hand is already accepted: `poll` takes the push runs
of the workflow on the branch, or any run when there is none
([release-watch:348-352](../../scripts/release-watch#L348)), so a
`workflow_dispatch` run on the same ref is found (FR-011). No test
holds that.

**Chosen.** Each expected run gains its workflow's file name
(`ci.yml`, `ci-from-scratch.yml`). Once any expected run of the same
repository and commit has been found, an expected run still not found
five minutes later is settled as never started, and its line ends with
the command that starts it:
`GH_PAGER=cat gh workflow run <file> --ref <branch> -R <owner/repo>`.
Before any sibling is found (the watcher started before the release
pushed anything) the full timeout still applies. A test adds the
dispatched run for FR-011. The 0.1.10 remedy in
[docs/DAILY_DRIVER.md:1259](../../docs/DAILY_DRIVER.md) is the same
command.

**Alternatives considered**: *a fixed five-minute timeout for every run*
(rejected: the runs take twenty to thirty minutes); *asking GitHub for
the push event's deliveries* (needs the webhook API and an admin token).

## R13. Publishing the starters again finishes what is missing

**Read.** `publish-starters` checks every repository before pushing any
and refuses all of them when one already holds the tag
([Justfile:622-631](../../Justfile#L622)).

**Chosen.** A repository that already holds `v<version>` is reported
as done and left alone; the rest are built, gated and pushed as today.
The repositories' base URL becomes a Justfile variable,
`starter_remote := env("CSIS_STARTER_REMOTE", "https://github.com")`, so
a rehearsal points it at local bare repositories (R18). It names where
to push, not what to check, so it is not an exclusion.

**Alternatives considered**: *compare the held tag's tree with the
built tree and refuse a difference* (stronger, but a template takes
the release's tree once and is never re-cut, as a version is not; the
watcher already reads that each holds the tag).

## R14. One command finishes a release after the upload

**Read.** `release-finish` starts only from an uncommitted bump
([release.py:826-836](../../scripts/release.py#L826)). After a refused
push the commit and tag exist, and the release prints the rest as
commands to type ([release.py:165-166, 481-491](../../scripts/release.py#L165)).

**Chosen.** `release-finish` accepts a second starting state: HEAD is
the commit `release <version>`, tagged `v<version>`, the tree clean,
every project holding the version. From there it runs the ending
(`run_ending`), whose steps are safe to repeat (a push of refs origin
already holds, a fast-forward already made). `ENDING_FAILED` then names
`just release-finish <index>` instead of the list of commands. After a
`release-take`, the finish prints the take's line, as `TAKE_STOPPED`
already does; it does not run it.

## R15. What must stay fixed

**Read.**
- **The tag by name** (FR-014): the ending pushes the cut branch and
  `v<version>` and nothing else ([release.py:452-460](../../scripts/release.py#L452));
  held by [test_release_script.py:689-703](../../tests/test_release_script.py#L689)
  (no `--follow-tags`, no `--tags`).
- **The index asked afresh** (FR-015): the take runs with `UV_REFRESH=1`
  ([release.py:175-177, 890-891](../../scripts/release.py#L175)); held by
  [test_release_script.py:1067-1069](../../tests/test_release_script.py#L1067).

Both stay; R14's finish reuses the same `ending`, so it cannot push
another tag.

## R16. A CI job that did not perform its steps is not green

**Chosen.** The gate steps lose their "none configured" branch: any
missing or empty secret of the job fails it, naming each one. That
removes a case rather than adding one. The `publish` job fails on a
final tag without `STARTER_PUSH_TOKEN`. `fixture-live` fails without
docker, as the `full-test` legs do. A pull request keeps the job-level
condition `if: github.event_name != 'pull_request'`
([ci.yml:166](../../.github/workflows/ci.yml#L166)), which GitHub shows
as skipped: not run, neither success nor failure, and not blocking
(FR-005). A push to a fork with no secrets fails its `live` job; the
fork's owner sees what is missing.

**Alternatives considered**: *a "neutral" conclusion through the
check-runs API* (needs a GitHub App token in the job; not available to
a workflow's own token for its own job); *`continue-on-error`* (shows
the job green with a warning: the fault itself).

## R17. The starters' own gates

**Chosen, pending the operator (D3).** Out of this feature. The
starters' workflows and `_skeleton/Justfile` keep their SKIPPED rule
([docs/examples/_skeleton/Justfile:57-80](../../docs/examples/_skeleton/Justfile#L57),
[CI_SETUP.md:713-731](../../docs/examples/_skeleton/CI_SETUP.md#L713)).

**Read.** A repository made with "Use this template" pushes its first
commit before any secret exists, and its CI_SETUP walks the reader
through a green, SKIPPED `live` job as step 1 of its proofs. Changing
that changes what an adopting team sees on its first push, which is
spec 002's concern (its reader has no secret). The release gates of
this feature do not depend on the starters' jobs.

## R18. The rehearsal

**Chosen.** No new release mode. A rehearsal is three things, each
publishing nothing:

1. **The release family under its stubbed shell** (the `Family(run=...)`
   the tests already build): the gate failing after the probes passed
   (a session lapsing during the gate), the remote moving during the
   gate, the push refused after the upload, `release-finish` from each
   state. Each asserts that no upload command was sent.
2. **The real commands with a prerequisite taken away from them**:
   `DOCKER_HOST=unix:///nonexistent` makes `docker info` fail without
   touching the daemon's power state; `CSIS_CONFIG_ROOT=<empty dir>`
   takes the reference away. The real `just full-test-legs` and the dry
   form of `just release` then show the refusal.
3. **Scratch repositories for the starters**: local bare repositories
   named as `scripts/starter-tree --list` names them, some holding the
   tag, reached through `CSIS_STARTER_REMOTE=file://...` and the dry
   form of `just publish-starters`.

**Alternatives considered**: *a `rehearse` word on `release` that runs
every step against a fake index and scratch remotes.* Rejected under
FR-016: it adds a mode to every step of the release, and the scenarios
the spec names all stop before an upload, where the stubbed shell and
the dry form already reach.

## R19. Interactions with other specifications

**Read.**
- **Spec 001** ([research.md R17](../001-standalone-docker-provider/research.md)):
  assigned the daemon-gated legs of `full-test` to this feature; R1 to
  R6 take them.
- **Spec 005**: the Google Cloud family's repository has its own
  `scripts/full-test-legs` and `scripts/release`, with no `SKIPPED`
  path found (`grep SKIP` there, 2026-11-21). Unchanged by this feature.
  The `test-cloud-starters` leg layers the Google Cloud family in from the index and
  needs the network, not a prerequisite word: without the network it
  fails.
- **Spec 007** (the AWS family leaves): after its phase 3 the dry run
  `--all` leg layers the AWS family in from the index through
  `scripts/with-released-families`, as it layers the Google Cloud family
  today; the `reference` prerequisite does not change. Its phase 1
  moves the AWS stubs into `cs_image_system.aws_runtime.testing`; the
  container files of R6 import from `harness`, which 007 edits:
  whichever lands second rebases the imports.
- **Spec 008** (the Okta plugin leaves): R8's prerequisite names the
  Okta plugin's variables in this repository's leg runner, which is
  about the reference configuration, not the core (Principle VI holds:
  no core code names a provider). The cure at the source (the plugin
  refusing to skip `plan`) belongs to the plugin's own repository.
- **Spec 002** (the first dry run): its CI job that runs the quickstart
  page must not end green when it did not run (FR-005 here).
- **Sequencing (D5)**: specs 007 and 008 each cut releases in their
  phases 1 and 3. Landing this feature first makes those releases the
  first to pass the honest gate; landing it after means three more
  releases through a gate that can skip. Both edit `ci.yml`'s `live`
  job and the Justfile.

## R20. How the budget is measured

**Read**, by the method of spec 004's T002: source lines are the lines
of `*.py` under `packages/*/src` and `src`; test lines are the tracked
`*.py` under `tests` and `packages/*/tests`, fixtures left out; tests
are the `def test_` functions in those files. On 2026-11-21 at
`35446e3f`: 19 workspace packages, 54,249 source lines, 46,069 test
lines in 272 files, 2,007 tests.

The method does not count `scripts/`, the Justfile or the workflows,
where this feature works, so the plan also measures **the release
tooling** for SC-007: the eleven scripts the release runs
(`release.py`, `release-watch`, `isolated-run`, `publish-target-ready`,
`own-versions-current`, `with-released-families`, `publish-dist`,
`session-minutes-left`, `index-knows`, `dev-pin-resolves`,
`starter-tree`: 3,263 lines), the Justfile (773 lines) and the two
workflows (`ci.yml` 365, `ci-from-scratch.yml` 170); and **its tests**,
the sixteen files that hold them (`test_release_script`,
`test_release_watch`, `test_release_probes`, `test_isolated_run`,
`test_publish_dist`, `test_publish_target`,
`test_own_version_builds_match_the_index`, `test_with_released_families`,
`test_starter_tree`, `test_dev_pin_install`, `test_release_on_main`,
`test_release_version`, `test_justfile_contract`, `test_ci_workflow`,
`test_preflight_sessions`, and `packages/system/tests/test_strict_session`):
4,078 lines, 183 tests.

## R21. The release that carries this feature

**Chosen, pending the operator (D6).** The next final release (0.1.13
to PyPI), cut with `just release-take` and followed by `just
release-watch`, is SC-008's proof: it is the only release whose gate is
`full-test`, whose tag run publishes the starters, and whose watch reads
the templates. A development release to TestPyPI before it is allowed
and proves the TestPyPI gate's zero skips; it does not stand for
SC-008.
