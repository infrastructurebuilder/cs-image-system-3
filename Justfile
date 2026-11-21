# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# cs-image-system -- the Justfile is the single entry point for the build
# lifecycle. The five contract targets come first, in lifecycle order (bare
# `just` lists them so): init -> build -> test -> full-test -> release.
# Everything after them is the DEVELOPER's: the bar's parts, the golden, the
# release, and `just cli ...` against the reference configuration for the
# system's own live proofs. The cycle recipes (the cloud cycle, the CI login
# proof, the OPA client) live in a configuration repository's own Justfile,
# which the release ships; a team runs them from its own repository.

# Bare `just` lists the recipes in file order: the contract first
[private]
default:
	@just --list --unsorted

# ------------------------------------------------------------- the contract

# The REFERENCE configuration is its own repository, checked out beside this one by
# default; CSIS_CONFIG_ROOT overrides. The tests never read it -- they own the frozen fixture
# under tests/fixtures/config/ -- so `just test` needs no live configuration at all; every
# recipe that drives one depends on config-guard. It stands alone: its own
# Justfile drives its cycles; the recipes here read it for the system's own proofs.
config_root := env("CSIS_CONFIG_ROOT", justfile_directory() + "/../cs-image-system-testconfig")
# the reference declares the Google Cloud family, which this venv does not hold: it is layered in from the
# index for each command (scripts/with-released-families)
live_cli := "uv run --no-sync python scripts/with-released-families cs-image-system --root-dir " + quote(config_root)
# The branch a release is cut on: ONE branch, named here, never a walk or feature branch. `main`:
# develop is where work is done and main is where releases live. Before a release main takes
# develop by fast-forward; the release commit and the tag land on main; develop takes main back
# by fast-forward. A failed release leaves its evidence on main alone. A maintenance branch
# `release/<major.minor>` is also accepted, for an old version's fix cut while develop is past
# it; the develop-is-an-ancestor check applies to main alone.
release_branch := "main"
# Provider plugin cache: a provider downloaded once is reused by every `tofu init`; with a root's
# kept .terraform.lock.hcl the init needs no network at all. The cache is not safe under concurrent
# `init`, so one tofu process runs at a time by construction: every invocation that may
# EXECUTE tofu passes `--locked`, which holds .tofu-plugin-cache/.lock and refuses a
# second holder with exit 75. Dry runs enumerate and never start tofu; the suite's one real-tofu
# test uses a private cache and never contends.
export TF_PLUGIN_CACHE_DIR := justfile_directory() / ".tofu-plugin-cache"

# One-time setup: the toolchain and every workspace package (idempotent). Every extra but
# `gcloud` and `all`: the Google Cloud family is released from its own repository, and this
# repository's tests pass without it (spec 005)
init:
	@uv sync --all-extras --no-extra gcloud --no-extra all
	@mkdir -p "$TF_PLUGIN_CACHE_DIR"
	@just hooks

# Package every workspace member (sdist + wheel) under dist/; no tests
build:
	@uv build --all-packages

# The fast suite, every check blocking: lint (ruff), type-check (pyright), the
# unit tests (the golden emission included), the core's own suite with no
# provider installed (`test-core`), the two terraform libraries' own suites
# with nothing but themselves (`test-terraform-alone`) and the docker family's
# own suite in an environment that holds only that package
# (`test-docker-alone`). The local acceptance bar; `verify` is its alias.
[doc("The fast suite, all blocking: lint (ruff), type-check (pyright), the unit tests, then the core, the terraform libraries and the docker family each alone; `verify` is its alias")]
test: lint typecheck pytest test-core test-terraform-alone test-docker-alone

# Everything `test` does plus the slow and external legs: the
# modification tests under docker (`test-mods --strict`), and -- only when
# `just preflight` finds every runtime session present -- a headless dry
# `run --all` over a private copy of the fixture followed by
# `state query --strict`. A leg whose prerequisite is absent reports SKIPPED
# loudly with its reason and does not fail the run; a leg that runs and fails
# does. Two legs are never skipped: `test-docker-install` and
# `test-docker-live`, which fail when the container daemon does not answer. Identity credentials (OKTA_API_*, TF_VAR_<team>_*) are not gated: a
# dry run without them warns and skips the identity roots' plan.
[doc("`test` plus the docker-backed modification tests and, when the runtime sessions are present, a headless dry run --all with state query --strict")]
full-test: test
	@just full-test-legs

# Cut a release, run from develop: the probes first -- the branch (develop, from which it
# moves to `release_branch` itself; `release_branch` with develop an ancestor; or a
# maintenance branch), a clean tree, the
# index itself (its upload endpoint and every project page answer, and no project
# holds the version), the index token, the tag, the remote -- then from develop the
# checkout of `release_branch` and its fast-forward to develop, `uv sync --all-extras --no-extra gcloud --no-extra all`,
# the venv's probes, the bar, the index asked AGAIN (the
# bar takes twenty minutes), the bump, the lock, the
# build and the upload, and only then the release's row in docs/CHANGES.md, the commit and
# the tag, so a failed upload leaves
# an uncommitted bump to discard and never a tagged, unpublished version. TARGET is a
# part for bump-my-version (`patch`, `minor` and `major` open the next version as its
# first development release, 0.1.0 -> 0.1.1.dev1; `dev` is the next development release
# of the same version; `stage` finalises it, 0.1.1.dev2 -> 0.1.1) or an explicit version.
# INDEX is `test` (TestPyPI, the default) or `pypi`: a development release to TestPyPI is
# gated on `test`, the bar, and `test-docker-install` (it needs a container daemon); a PyPI
# release on `full-test` (which holds the install check), the modification-test evidence
# in the live configuration and a clean live checkout. A refusal before the bump returns
# the checkout to the branch it started on. After the tag: `git push origin main
# v<version>` (main and its own tag by name, so no other local tag travels: GitHub starts
# no tag run when more than three tags are pushed at once), develop checked out,
# fast-forwarded to main and pushed, and `uv sync --all-extras --no-extra gcloud --no-extra all` again (a maintenance
# branch: that branch and its tag pushed, develop untouched); the pushed tag makes CI
# publish (it uploads nothing the index already holds). A failed step there names itself
# and the commands left. `yes` as the third argument is the dry form:
# the probes, the version, and every move and push it would make; nothing changed.
# The family's logic is scripts/release.py (every step a function, tested with a stubbed
# shell); the recipes here hand it the branch and the live configuration's root.
[doc("From develop, gated on the bar (test) or full-test (pypi): probe, bump, lock, build, publish, commit, tag v<version>, push main and develop; `yes` = dry")]
release target index="test" dry="no":
	@uv run --no-sync --project "{{justfile_directory()}}" python "{{justfile_directory()}}/scripts/release.py" release "{{target}}" "{{index}}" "{{dry}}" \
		--release-branch "{{release_branch}}" --config-root {{quote(config_root)}}

# Finish a release whose upload `release` could not complete: after it
# stopped part-way and `just publish INDEX` was run again until every project held the version
# -- a first PyPI release of many projects takes days. On `release_branch`, with the bump
# uncommitted and nothing else changed, and only when the index holds the version for every
# project: the modification-test evidence (on PyPI), the docs/CHANGES.md row, the commit, the
# tag; then the release's own ending: `git push origin main v<version>`, develop's
# fast-forward to main and its push, and `uv sync --all-extras --no-extra gcloud --no-extra all`.
[doc("After a release's upload was completed by `just publish`: check every project holds the version, then commit, tag and push it")]
release-finish index="test":
	@uv run --no-sync --project "{{justfile_directory()}}" python "{{justfile_directory()}}/scripts/release.py" release-finish "{{index}}" \
		--release-branch "{{release_branch}}" --config-root {{quote(config_root)}}

# The release walk's two repositories in one command: the live configuration (`config_root`) is
# asked first (configured, a git checkout, with a `take` recipe); then the release, as `release`
# runs it; then `just take <version>` there, the version read back from what the release cut, with
# `main` passed through when given (the take then pushes develop to main: main performs). A release
# that refuses or fails runs no take; a take that stops says so, with the command that finishes it
# there. WORDS: `main`, `yes` (the dry form: the release's, then the take it would run), both, or neither.
[doc("The release (as `release` runs it), then `just take <version>` in the live configuration; `main`: the take pushes main too; `yes` = dry")]
release-take target index *words:
	@uv run --no-sync --project "{{justfile_directory()}}" python "{{justfile_directory()}}/scripts/release.py" release-take "{{target}}" "{{index}}" {{words}} \
		--release-branch "{{release_branch}}" --config-root {{quote(config_root)}}

# Wait on the runs a release walk started and say one verdict line each, found by commit: here the
# tag's run of CI, main's, develop's and develop's "CI from scratch"; in the live configuration the
# take's develop and, when main was pushed, main. A green job is not proof its steps ran: for the
# tag's run the index (TestPyPI for a development version, PyPI for a final one) must list the
# version and every template repository must hold its tag; for the configuration's main the perform
# job's guard verdict is read, and what it baked. Exit 0 only when every verdict is good; sixty
# minutes at most (scripts/release-watch --timeout). The logic is scripts/release-watch.
[doc("Wait on the runs a release walk started (here and in the live configuration) and say one verdict each; exit 0 only when all are good")]
release-watch version:
	@uv run --no-sync --project "{{justfile_directory()}}" python "{{justfile_directory()}}/scripts/release-watch" "{{version}}" \
		--root "{{justfile_directory()}}" --config-root {{quote(config_root)}}

# What a release needs and `full-test` only finds out twenty minutes in, asked
# first and in one line each, before anything changes. For every index: the venv is in step with
# the lock (`uv sync --all-extras --no-extra gcloud --no-extra all --check`), because every recipe runs `uv run --no-sync` and a venv
# behind the checkout answers with stale metadata. Then, for a release, every package whose version the
# release does not move (the bump's `glob_exclude`: the contract) is either not on the index or held
# there as this tree's build, file for file (scripts/own-versions-current), because an index never takes a
# second build under one version and would refuse the upload after the gate. For a PyPI release also: docker answers (the
# modification-test, posix, bake-step and runner-image legs run in it) and every runtime session of
# the live configuration is present (`just preflight`, the gate full-test itself uses: without it the
# live legs would be SKIPPED, which a release cannot accept) and how many minutes the soonest-expiring session has left
# (scripts/session-minutes-left; refused only when a token has already lapsed, otherwise said). The dry form of `release` prints the
# same verdicts. `release-finish` asks the venv alone: it runs no bar and builds nothing.
[private]
_release-probes index who="release":
	@uv run --no-sync --project "{{justfile_directory()}}" python "{{justfile_directory()}}/scripts/release.py" probes "{{index}}" "{{who}}" \
		--config-root {{quote(config_root)}}

# Build and upload the version in the tree: `dist/` cleaned, every package
# built, every file uploaded to INDEX -- `test` (TestPyPI, the default) or `pypi` -- by
# scripts/publish-dist, one project at a time, with the files the index
# already holds with the same content skipped (the index's url is the check url), so a
# re-run after a partial failure, or CI after a local publish, uploads what is missing and
# nothing twice; when nothing was missing, one file is sent again to prove the token.
# Exit 75 is PyPI's limit on new projects: run it again in a day. The token is UV_PUBLISH_TOKEN, else TEST_PYPI_TOKEN / PYPI_TOKEN (the
# repository secrets' names), from the environment and never here; the endpoints are the
# `[[tool.uv.index]]` entries in pyproject.toml. A deleted version can
# never be uploaded again, on either index: the next upload is a new version.
# Can the index take an upload now? One line per endpoint (the upload endpoint and every
# project's page); exit 0 ready, 75 not ready. `wait` probes every minute until it is, two hours at most.
[doc("Can INDEX (test or pypi) take an upload now? exit 0 ready, 75 not; `wait` probes every minute, two hours at most")]
index-ready index="test" wait="no":
	@uv run --no-sync python scripts/publish-target-ready {{index}} {{ if wait == "wait" { "--wait 7200" } else { "" } }}

# The index asked first (a partial upload of this version is what a re-run completes, so a
# project that already holds it is reported, not refused), then `dist/` cleaned, `just build`,
# and scripts/publish-dist: one project at a time, sdist and wheel together, dependencies first
# and cs-image-system last; the two workspace-only plugins (`Private :: Do Not Upload`) are built
# and never uploaded; a 429 is exit 75 with what is left; a failure shows its cause lines.
[doc("Build and upload the version in the tree to TestPyPI (`test`, the default) or PyPI (`pypi`); UV_PUBLISH_TOKEN from the environment")]
publish index="test":
	@uv run --no-sync --project "{{justfile_directory()}}" python "{{justfile_directory()}}/scripts/release.py" publish "{{index}}"

# ------------------------------------------------------------ development

# So a session that lapsed after the bar costs the legs again, not the bar; the
# session is checked once up front, and a leg that finds it gone mid-way still fails loudly.
# The live legs of full-test alone: test-mods under docker, a dry run --all and a state query --strict over a private copy of the live configuration
full-test-legs:
	#!/usr/bin/env bash
	set -uo pipefail
	status=0
	# the starters' own install line resolves the newest development tag -- ours from
	# TestPyPI, nothing else from it (read-only; needs the network, not a session)
	echo "full-test: a development pin resolves with the starters' install line (dev-pin-resolves)"
	uv run --no-sync python scripts/dev-pin-resolves || { echo "full-test: FAILED dev-pin-resolves"; status=1; }
	# the starters that declare the Google Cloud family, with it layered in from the index (needs the network)
	echo "full-test: the starters that need every provider, the Google Cloud family from the index (test-cloud-starters)"
	just test-cloud-starters || { echo "full-test: FAILED test-cloud-starters"; status=1; }
	# not gated on the daemon: the usual install must deliver a docker provider that runs, so a daemon
	# that does not answer FAILS this leg (it and test-docker-live, below, are the legs here that never report SKIPPED)
	echo "full-test: cs-image-system[docker] installed alone validates and dry-runs the docker starter (test-docker-install)"
	just test-docker-install || { echo "full-test: FAILED test-docker-install"; status=1; }
	# the same rule: the docker family's own live tests fail, and never skip, without a daemon
	echo "full-test: the docker family's live tests, its stand-in on the local daemon (test-docker-live)"
	just test-docker-live -q || { echo "full-test: FAILED test-docker-live"; status=1; }
	if docker info >/dev/null 2>&1; then
		echo "full-test: modification tests under docker (test-mods --strict)"
		just test-mods --strict || { echo "full-test: FAILED test-mods"; status=1; }
		echo "full-test: the posix accounts script under docker (test-posix-accounts)"
		just test-posix-accounts -q || { echo "full-test: FAILED test-posix-accounts"; status=1; }
		echo "full-test: a bake's step runner against a held package database, under docker (test-bake-steps)"
		just test-bake-steps -q || { echo "full-test: FAILED test-bake-steps"; status=1; }
		echo "full-test: the CI runner image builds and every tool in it answers (runner-image)"
		just runner-image || { echo "full-test: FAILED runner-image"; status=1; }
		echo "full-test: the docker runtime bakes a base image and an instance image on the local daemon, from nothing to nothing (test-docker-bake)"
		just test-docker-bake -q || { echo "full-test: FAILED test-docker-bake"; status=1; }
		echo "full-test: the docker runtime's change cycle on the local daemon, from nothing to nothing (test-docker-cycle)"
		just test-docker-cycle -q || { echo "full-test: FAILED test-docker-cycle"; status=1; }
		echo "full-test: the same cycle against Podman's API service, when one is named (test-podman-cycle)"
		just test-podman-cycle -q || { echo "full-test: FAILED test-podman-cycle"; status=1; }
		echo "full-test: the same cycle against Podman Desktop's machine, when one is running (test-podman-desktop-cycle)"
		just test-podman-desktop-cycle -q || { echo "full-test: FAILED test-podman-desktop-cycle"; status=1; }
	else
		echo "full-test: SKIPPED test-mods, test-posix-accounts, test-bake-steps, runner-image, test-docker-bake, test-docker-cycle, test-podman-cycle and test-podman-desktop-cycle -- docker is not available"
	fi
	if [ ! -f "{{config_root}}/cfg/_config.yml" ]; then
		echo "full-test: SKIPPED the live-configuration legs (dry run --all, state query --strict) -- no live configuration at {{config_root}} (see: just config-guard)"
	elif just preflight; then
		copy=$(mktemp -d "${TMPDIR:-/tmp}/csis-full-test.XXXXXX")
		# The reference configuration carries its own tfmodules, so the copy needs nothing beside
		# it. Never carry its .git (a copy must not commit into the live repo), its generated trees, its mirror
		# or its provider cache (gigabytes, and the copy's inits use this Justfile's own).
		mkdir -p "$copy/cs-image-system-testconfig"
		(cd "{{config_root}}" && tar --exclude=./.git --exclude=./generated --exclude=./_private --exclude=./.tofu-plugin-cache -cf - .) | tar -xf - -C "$copy/cs-image-system-testconfig"
		echo "full-test: headless dry run --all over a private copy of the reference configuration ($copy)"
		uv run --no-sync python scripts/with-released-families cs-image-system --root-dir "$copy/cs-image-system-testconfig" run --all || { echo "full-test: FAILED dry run --all"; status=1; }
		echo "full-test: state query --strict over the copy"
		uv run --no-sync python scripts/with-released-families cs-image-system --root-dir "$copy/cs-image-system-testconfig" state query --strict || { echo "full-test: FAILED state query --strict"; status=1; }
		rm -rf "$copy"
	else
		echo "full-test: SKIPPED the credential-gated legs (dry run --all, state query --strict) -- a runtime session is absent or expired (see above)"
	fi
	if [ "$status" -eq 0 ]; then echo "full-test: passed"; else echo "full-test: FAILED"; fi
	exit $status

# Format code with ruff
format:
	@uv run ruff format src packages tests

# Run linter (blocking) -- same command CI runs; then the licensing check: every file carries
# copyright and licence information (an SPDX header, or a REUSE.toml declaration)
[doc("The linter (ruff, blocking, as CI runs it), then the licensing check: an SPDX header or a REUSE.toml declaration on every file")]
lint:
	@uv run ruff check src packages tests scripts
	@uv run reuse lint

# Licence headers (REUSE): the SPDX two-liner, holder and licence, on every source file that lacks one.
# Never the fixtures (hashed modification content, the golden) nor prose: those are declared in
# REUSE.toml. Idempotent (--skip-existing); ends with the lint.
[doc("Add the SPDX header to every source file that lacks one (never the fixtures or prose: REUSE.toml declares those); then the lint")]
headers:
	#!/usr/bin/env bash
	set -euo pipefail
	H="Mykel Alvis <mykelalvis@infrastructurebuilder.org>"; Y=$(date +%Y)
	find src packages -name '*.py' -not -path '*/.venv/*' -not -path '*/tests/fixture/*' -not -path '*/tests/golden/*' -print0 | xargs -0 uv run reuse annotate --copyright "$H" --license Apache-2.0 --year "$Y" --skip-existing
	find packages -name '*.tf' -not -path '*/.venv/*' -not -path '*/tests/fixture/*' -not -path '*/tests/golden/*' -print0 | xargs -0 uv run reuse annotate --copyright "$H" --license Apache-2.0 --year "$Y" --skip-existing
	uv run reuse annotate --copyright "$H" --license Apache-2.0 --year "$Y" --skip-existing tests/*.py bin/*.sh .github/workflows/*.yml pyproject.toml packages/*/pyproject.toml
	uv run reuse annotate --copyright "$H" --license Apache-2.0 --year "$Y" --skip-existing --style python Justfile .githooks/pre-commit
	uv run reuse lint

# The licensing check over the live configuration (its REUSE.toml declares every file; no headers there)
reuse-live: config-guard
	@cd "{{config_root}}" && "{{justfile_directory()}}/.venv/bin/reuse" lint

# Fix linting issues automatically (safe fixes)
lint-fix:
	@uv run ruff check --fix src packages tests scripts

[doc("Fix linting issues automatically, unsafe fixes included; review the diff")]
lint-unsafe-fix:
	@uv run ruff check --fix --unsafe-fixes src packages tests scripts

# Type check with pyright (standard mode; see [tool.pyright] in pyproject.toml)
typecheck:
	@uv run pyright

# The unit tests alone (`test` runs them after lint and typecheck)
pytest:
	@uv run pytest

# Move one of the SDK's two version lines: LINE is `kit` (cs-image-system-base) or `terraform`
# (cs-image-system-hashicorp-utils and cs-image-system-tofu-roots together); PART is `last` (any change that
# removes or alters nothing on a declared surface) or `middle` (a declared name or hook removed or altered).
# The member's own version and every exact pin on it move; the workspace's version, the contract, the other
# line and every range do not. After `middle`: move the ranges that name the line by hand, and run
# `just surface-record`.
[doc("Move one SDK version line: `kit` or `terraform`, by `last` or `middle`; ranges are yours to move after `middle`")]
sdk-bump line part:
	#!/usr/bin/env bash
	set -euo pipefail
	case "{{line}}" in kit|terraform) ;; *) echo "sdk-bump: '{{line}}' is not a version line; say kit or terraform" >&2; exit 2 ;; esac
	case "{{part}}" in last|middle) ;; *) echo "sdk-bump: '{{part}}' is not a part; say last or middle" >&2; exit 2 ;; esac
	uv run --no-sync bump-my-version bump --config-file ".bumpversion-{{line}}.toml" "{{part}}"
	uv lock
	echo "sdk-bump: the {{line}} line is now $(uv run --no-sync bump-my-version show --config-file ".bumpversion-{{line}}.toml" current_version)"
	if [ "{{part}}" = middle ]; then echo "sdk-bump: move every range that names this line, then run: just surface-record"; fi

# Does each SDK library keep its version rule? Its surface as a plugin sees it (every declared name, member,
# field and hook, with its shape) is compared with the baseline committed beside it
# (packages/<library>/surface-baseline.txt). An entry removed or changed while the middle number of the
# library's version is unchanged fails, naming the entry; so does a baseline of an earlier line, and an
# entry added and not yet recorded (`just surface-record` records it under the same middle). Silent when
# every library keeps to its baseline. The same comparison is a test in each library's own suite, and the
# release's probes run this recipe before anything is built.
[doc("Compare each SDK library's surface with its committed baseline; fails naming an entry removed or changed without a new middle number, or one added and not yet recorded")]
surface-check:
	#!/usr/bin/env bash
	set -uo pipefail
	status=0
	uv run --no-sync python -m cs_image_system.base.surface baseline cs_image_system.base packages/base/surface-baseline.txt || status=1
	uv run --no-sync python -m cs_image_system.base.surface baseline cs_image_system.hashicorp_utils packages/hashicorp-utils/surface-baseline.txt || status=1
	uv run --no-sync python -m cs_image_system.base.surface baseline cs_image_system.tofu_roots packages/tofu-roots/surface-baseline.txt || status=1
	exit $status

# Write each SDK library's baseline from its code: in the change that raises its middle number (`just
# sdk-bump <line> middle`), and in any change that adds to its surface, which keeps the middle number.
# Refused for a library whose middle number is still its baseline's while an entry would be removed or
# changed: that change needs the new middle number first. Read the diff.
[doc("Rewrite each SDK library's surface baseline (after `just sdk-bump <line> middle`, or after an addition); refused when an entry would change under the same middle number")]
surface-record:
	#!/usr/bin/env bash
	set -uo pipefail
	status=0
	uv run --no-sync python -m cs_image_system.base.surface record cs_image_system.base packages/base/surface-baseline.txt || status=1
	uv run --no-sync python -m cs_image_system.base.surface record cs_image_system.hashicorp_utils packages/hashicorp-utils/surface-baseline.txt || status=1
	uv run --no-sync python -m cs_image_system.base.surface record cs_image_system.tofu_roots packages/tofu-roots/surface-baseline.txt || status=1
	exit $status

# The core's own suite where no provider can help it: the workspace's wheels
# are built, an empty environment outside the workspace gets a plain
# `cs-image-system` (no extras: no docker, AWS, Google Cloud or Okta plugin),
# each distribution from its wheel, and the tests of the core's packages run
# there under the system package's pytest settings. The core is the contract,
# the kit, the engine, the command line and the always-installed plugins; its
# fixture and golden are packages/system/tests/fixture and golden. A run fails
# when no test was collected, any was skipped, or any failed.
[doc("The core's own tests in an empty environment holding a plain install with no extras (no provider); a skipped test fails")]
test-core:
	@uv run --no-sync python scripts/isolated-run --subject core --require "cs-image-system" --root packages --pytest-config packages/system/pyproject.toml --tests contract/tests base/tests engine/tests system/tests ansible-plugin/tests bash-mod-plugin/tests default-os-plugin/tests packer-plugin/tests local-state-plugin/tests posix-identity-plugin/tests

# The two shared terraform libraries (the HCL and collector library, the OpenTofu roots) where nothing else of
# this repository can help them: the workspace's wheels are built, and an empty environment outside the
# workspace gets the roots library and only what it declares -- its sibling library, the kit and the contract --
# each from its wheel. Each library's own tests run there from its own directory, with its own pytest settings.
# Three runs: both libraries at the HIGH end of the kit range the roots library declares, and the roots library
# again at the LOW end. Each run says whether the kit came from the index or from this repository's build. A
# run fails when no test was collected, any was skipped, or any failed. It is what shows the two libraries can
# be taken out of this repository.
[doc("The two terraform libraries' own tests in an empty environment holding only them and what they declare, at both ends of the kit range; a skipped test fails")]
test-terraform-alone:
	@uv run --no-sync python scripts/isolated-run --subject "terraform libraries: the roots, high end" --require "cs-image-system-tofu-roots" --root packages/tofu-roots --sdk-end high
	@uv run --no-sync python scripts/isolated-run --subject "terraform libraries: the collectors, high end" --require "cs-image-system-tofu-roots" --root packages/hashicorp-utils --sdk-end high
	@uv run --no-sync python scripts/isolated-run --subject "terraform libraries: the roots, low end" --require "cs-image-system-tofu-roots" --root packages/tofu-roots --sdk-end low

# The docker family's own suite (packages/docker-plugin/tests) where nothing
# else of this repository can help it: the workspace's wheels are built, an
# empty environment outside the workspace gets the docker package and only what
# it declares (its dependencies and its `test` extra), each from its wheel, and
# the suite runs there with the package's own pytest settings. Three runs, at
# the two ends of the SDK range the package declares (the kit and the two
# terraform libraries, each `>=0.2,<0.3`): at the HIGH end the whole suite, in
# place and again from a copy of the package's directory outside the
# workspace; at the LOW end the unit tests and the surface check, with the
# package and the SDK alone (no command line, no test kit: the engine pins
# the kit exactly, so a whole run belongs to the high end). Each run says, for
# each SDK library, whether it came from the index or from this repository's
# build. A run fails when no test was collected, any was skipped, or any
# failed. No container daemon is needed: the suite's runs are stubbed. The
# index is asked which SDK versions it holds.
[doc("The docker family's own tests in an empty environment holding only that package and what it declares, at both ends of its SDK range: in place, from a copy outside the workspace, and the unit tests at the low end; a skipped test fails")]
test-docker-alone:
	@uv run --no-sync python scripts/isolated-run --subject "docker, high end" --require "cs-image-system-docker-plugin[test]" --root packages/docker-plugin --sdk-end high
	@uv run --no-sync python scripts/isolated-run --subject "docker, high end, copy outside the workspace" --require "cs-image-system-docker-plugin[test]" --root packages/docker-plugin --sdk-end high --copy-outside
	@uv run --no-sync python scripts/isolated-run --subject "docker, low end" --require "cs-image-system-docker-plugin" --root packages/docker-plugin --sdk-end low --tests tests/unit

# What a person who installs the docker extra gets: the workspace's wheels are
# built, an empty environment outside the workspace gets `cs-image-system[docker]`
# from them and nothing else, the INSTALLED command renders the standard-docker
# starter (`init-config <dir> --from standard-docker`), and the installed
# `validate` and a dry `run --all` run on it. Three steps are reported, each as
# ran and succeeded, ran and failed, or did not run, and the recipe passes only
# when all three ran and succeeded. It needs what the starter needs: docker,
# packer, ansible-playbook, bash and tofu, a container daemon that answers, and
# the registry (a dry run resolves the base image with a pull). `keep=<directory>`
# (or the directory alone) leaves the emitted `generated` tree there.
[doc("`cs-image-system[docker]` installed alone from the built wheels, the standard-docker starter rendered with the installed command, then `validate` and a dry `run --all` on it; all three must run and succeed (needs a container daemon)")]
test-docker-install keep="":
	@uv run --no-sync python scripts/isolated-run --install-check --subject "docker install" --require "cs-image-system[docker]" --starter standard-docker {{ if keep != "" { "--keep " + quote(trim_start_match(keep, "keep=")) } else { "" } }}

# The docker family's tests that need the real thing: the modification tests
# of the family's fixture on the docker runtime's own stand-in, a throwaway
# container on the local daemon (packages/docker-plugin/tests/live). In no
# default path and no isolated run. Without a daemon that answers it FAILS,
# it never skips: where it is required (a leg of `full-test`), a missing
# daemon is a failure.
[doc("The docker family's tests that need a container daemon (packages/docker-plugin/tests/live): the modification tests on its own stand-in; fails, never skips, without a daemon")]
[positional-arguments]
test-docker-live *ARGS:
	@uv run pytest packages/docker-plugin/tests/live -p no:cacheprovider "$@"

# One file, or any pytest expression, for iterating on a single change.
# NOT the acceptance bar -- `just test` is, and a change is not done until
# that passes. This exists so proving one file does not cost a full suite.
# Each word reaches pytest whole ("$@"), so `-k "a or b"` is one expression.
[doc("One file, or any pytest expression, for iterating on one change; NOT the acceptance bar (`just test` is)")]
[positional-arguments]
test-one *ARGS:
	@uv run pytest "$@"

# Run every modification twice in a throwaway local container (apply +
# idempotence); needs docker. Results: <config_root>/meta-state/mod-tests.yaml
[doc("Run every modification twice in a throwaway container (apply + idempotence); needs docker; results in <config_root>/meta-state/mod-tests.yaml")]
[positional-arguments]
test-mods *ARGS: config-guard
	@{{live_cli}} test-mods "$@"

# The posix accounts script on AlmaLinux 10 and Debian 12, under
# docker -- run twice, against an equal and a differing pre-existing group, a
# member with no account yet, sudo through visudo. A leg of `full-test`; under
# `just test` the same file is skipped.
[doc("The posix accounts script on AlmaLinux 10 and Debian 12 under docker, run twice, with pre-existing groups and sudo; a leg of full-test")]
[positional-arguments]
test-posix-accounts *ARGS:
	@CSIS_CONTAINER_TESTS=1 uv run pytest tests/test_posix_containers.py "$@"

# A bake's settle step and step runner on AlmaLinux 10 and Debian 12,
# under docker, with the package database REALLY held by another process (rpm's
# transaction lock, dpkg's frontend lock). A leg of `full-test`; under `just
# test` the same file is skipped.
[doc("A bake's settle step and step runner on AlmaLinux 10 and Debian 12 under docker, the package database held by another process; a leg of full-test")]
[positional-arguments]
test-bake-steps *ARGS:
	@CSIS_CONTAINER_TESTS=1 uv run pytest tests/test_bake_steps_containers.py "$@"

# The docker runtime's cycle on the local daemon -- a tree of nothing
# but a docker runtime is written from the frozen fixture's pieces, its AlmaLinux
# 10 and Debian 12 base images and a posix-owned instance image are BAKED
# (packer's docker plugin, ansible through the daemon), the lineage and the
# tags are checked, and the images are disposed. Needs docker, packer with the
# docker and ansible plugins, and ansible-playbook; several minutes (pulls,
# two package updates, the mods). A leg of `full-test`; under `just test` the
# same file is skipped.
[doc("The docker runtime bakes two base images and an instance image on the local daemon, from nothing to nothing; needs docker, packer and ansible; a leg of full-test")]
[positional-arguments]
test-docker-bake *ARGS:
	@DOCKER_HOST="$(just docker-host)" CSIS_DOCKER_KEEP_HOST=1 CSIS_DOCKER_BAKE=1 uv run pytest tests/test_docker_bake_live.py "$@"

# The docker runtime's CHANGE CYCLE on the local daemon, from
# nothing to nothing -- the bake above, then two containers launched on one
# volume through tofu (kreuzwerker/docker), verified, their accounts reconciled;
# one stopped and left stopped by the next apply, then started; one upgraded to
# a new build (a new generation); both decommissioned, the volume destroyed, the
# images disposed. Needs what test-docker-bake needs plus tofu; several minutes
# more. A leg of `full-test`; under `just test` the same file is skipped.
[doc("The docker runtime's change cycle on the local daemon: the bake, two containers launched through tofu, stopped, upgraded, decommissioned; a leg of full-test")]
[positional-arguments]
test-docker-cycle *ARGS:
	@DOCKER_HOST="$(just docker-host)" CSIS_DOCKER_KEEP_HOST=1 CSIS_DOCKER_CYCLE=1 uv run pytest tests/test_docker_cycle_live.py tests/test_docker_starter_live.py "$@"

# The daemon the docker legs run against: DOCKER_HOST when the shell sets it, else the endpoint of
# the docker command's ACTIVE CONTEXT (`docker context inspect`), so packer, the tofu provider and
# the system all reach the daemon `docker` itself uses. The tofu docker provider and packer read
# DOCKER_HOST and otherwise take /var/run/docker.sock, which on a host with several engines
# (OrbStack, Docker Desktop, a Podman machine) may point at one that is not running; the context
# is the operator's choice (`docker context use orbstack`) and this recipe follows it.
[private]
docker-host:
	@if [ -n "${DOCKER_HOST:-}" ]; then printf '%s\n' "$DOCKER_HOST"; else docker context inspect --format '{{{{.Endpoints.docker.Host}}' 2>/dev/null || true; fi

# The cycle above against PODMAN'S API SERVICE instead of the
# environment's docker daemon. CSIS_PODMAN_HOST is the DOCKER_HOST URL of a running
# service (`podman system service`, a `podman machine`, or an ssh:// URL to a host
# that has one); unset, the leg is SKIPPED, said so, and exits 0. The leg refuses to
# pass on a daemon that does not say it is Podman. What differs from docker is what
# it fails on, and is recorded in docs/OPERATIONS.md, "Container hosts".
[doc("test-docker-cycle against Podman's API service at CSIS_PODMAN_HOST; unset, SKIPPED with exit 0; refuses a daemon that is not Podman")]
[positional-arguments]
test-podman-cycle *ARGS:
	#!/usr/bin/env bash
	set -euo pipefail
	if [ -z "${CSIS_PODMAN_HOST:-}" ]; then
		echo "test-podman-cycle: SKIPPED -- CSIS_PODMAN_HOST is not set (the DOCKER_HOST URL of a Podman API service, e.g. unix://\$XDG_RUNTIME_DIR/podman/podman.sock)"
		exit 0
	fi
	DOCKER_HOST="$CSIS_PODMAN_HOST" CSIS_DOCKER_KEEP_HOST=1 CSIS_PODMAN_CYCLE=1 CSIS_DOCKER_CYCLE=1 \
		uv run pytest tests/test_docker_cycle_live.py tests/test_docker_starter_live.py "$@"

# test-podman-cycle against PODMAN DESKTOP's machine on macOS. The address is
# not typed: scripts/podman-machine-host reads it from `podman machine` (the one machine,
# or the default of several; CSIS_PODMAN_MACHINE names one) and CSIS_PODMAN_HOST is set
# to it for the run. The leg never creates, starts or stops the machine (the power state
# is the operator's): with no podman, no machine, a stopped or an ambiguous one it is
# SKIPPED, said so with the reason, and exits 0. A bare `docker` keeps answering from
# whatever else is running (OrbStack): only the leg's own calls are aimed at Podman.
# Podman 6 dropped Intel Macs: this leg proves Podman 5.8 there until June 2027.
[doc("test-podman-cycle against Podman Desktop's machine on macOS (its address read from `podman machine`); no machine, or a stopped one, is SKIPPED")]
[positional-arguments]
test-podman-desktop-cycle *ARGS:
	#!/usr/bin/env bash
	set -uo pipefail
	why=$(mktemp "${TMPDIR:-/tmp}/csis-podman-host.XXXXXX")
	if host=$(uv run python scripts/podman-machine-host 2>"$why"); then
		rm -f "$why"
		echo "test-podman-desktop-cycle: Podman Desktop's machine at $host"
		CSIS_PODMAN_HOST="$host" just test-podman-cycle "$@"
	else
		echo "test-podman-desktop-cycle: SKIPPED -- $(cat "$why")"
		rm -f "$why"
	fi

# Build the CI runner image (ci/runner-image: AlmaLinux 10, every tool pinned) for
# amd64 and run its probe, which asks every tool its version from where cfg/executables.yml
# pins it. A leg of `full-test`; the Runner image workflow builds and publishes the same.
[doc("Build the CI runner image (ci/runner-image) for amd64 and run its probe: every pinned tool answers its version; a leg of full-test")]
runner-image tag="csis-ci:alma10-local":
	@docker build --platform linux/amd64 -t {{tag}} ci/runner-image
	@docker run --rm --platform linux/amd64 {{tag}} csis-ci-probe

# The credential sessions the reference configuration's runtimes need, read from the caches over the
# loaded configuration -- a load reaches no cloud, so no session is needed to ask (exit 0: every one
# present; 2: one absent or expired) -- full-test's gate
[doc("The runtime sessions the reference configuration needs, read from the credential caches (exit 0 all present, 2 one absent or expired); full-test's gate")]
preflight: config-guard
	@{{live_cli}} preflight

# Regenerate a golden (a pinned emission) after an INTENTIONAL emission
# change; read the rewritten files one by one before committing. SUITE is
# `shared` (tests/fixtures/golden, every provider's emission; the default),
# `core` (packages/system/tests/golden, what the core emits with no provider)
# or `docker` (packages/docker-plugin/tests/golden, the docker family's own).
[doc("Regenerate a golden after an INTENTIONAL emission change: `shared` (tests/fixtures/golden, the default), `core` (the core's own) or `docker` (the docker family's own); read the diff before committing")]
golden-regen suite="shared":
	#!/usr/bin/env bash
	set -euo pipefail
	case "{{suite}}" in
		shared) uv run python tests/golden.py ;;
		core) uv run python packages/system/tests/regen_core_golden.py ;;
		docker) uv run python packages/docker-plugin/tests/regen_golden.py ;;
		*) echo "golden-regen: '{{suite}}' is not a golden; say shared, core or docker" >&2; exit 2 ;;
	esac

# Public-safe by construction: scan what a commit could publish -- tracked files and
# untracked files that are not ignored -- for material that must never be public (keys, tokens,
# PEM bodies, an age identity, plans and state by name; addresses and long tokens outside prose
# and tests). The allow list is the frozen fixture's cfg/_config.yml public_safe.allow. CI runs it.
[doc("Scan what a commit could publish (tracked and unignored files) for material that must never be public, under the fixture's allow list; CI runs it")]
[positional-arguments]
public-safe *ARGS:
	@uv run cs-image-system public-safe --tree . --config tests/fixtures/config/cfg/_config.yml "$@"

# Build a publishable tree: the TRACKED files of ROOT at HEAD (nothing ignored can enter),
# a USER exclusion list (PUBLISH_EXCLUDE="path/one path/two", default none), the public-safe gate over
# the result with the root's own allow list, the ignore policy checked line by line, then ONE commit on
# main (PUBLISH_MESSAGE, default "Initial public release"). Refuses a dirty root, a finding, a missing
# ignore line or an existing DEST. Never pushes: the remote is the operator's act.
[doc("Build a publishable tree of ROOT's tracked files at HEAD, gate it public-safe, and make ONE commit on main at DEST; never pushes")]
publish-tree root dest:
	#!/usr/bin/env bash
	set -euo pipefail
	root=$(cd "{{root}}" && pwd -P); dest="{{dest}}"
	[ ! -e "$dest" ] || { echo "publish-tree: $dest exists"; exit 1; }
	[ -z "$(git -C "$root" status --porcelain)" ] || { echo "publish-tree: $root is not clean -- commit or discard first"; exit 1; }
	mkdir -p "$dest"
	git -C "$root" archive --format=tar HEAD | tar -xf - -C "$dest"
	for p in ${PUBLISH_EXCLUDE:-}; do rm -rf "$dest/$p"; done
	cfg="$root/cfg/_config.yml"; [ -f "$cfg" ] || cfg="$root/tests/fixtures/config/cfg/_config.yml"
	uv run cs-image-system public-safe --tree "$dest" --config "$cfg"
	for p in .envrc .private_key.pem .private_key.json .public_key.json '*.pem' tfplan '*.tfstate' '*.tfstate.backup'; do
		grep -qxF -- "$p" "$dest/.gitignore" || { echo "publish-tree: .gitignore lacks $p"; exit 1; }
	done
	git -C "$dest" init -q -b main
	# the one commit carries the SOURCE repository's identity (git config reads its local values,
	# then the global ones): a fresh `git init` knows only the global identity, and the first
	# publication push was refused for exactly that
	name=$(git -C "$root" config user.name || true); email=$(git -C "$root" config user.email || true)
	[ -z "$name" ] || git -C "$dest" config user.name "$name"
	[ -z "$email" ] || git -C "$dest" config user.email "$email"
	git -C "$dest" add -A
	git -C "$dest" commit -q -m "${PUBLISH_MESSAGE:-Initial public release}"
	echo "publish-tree: $(git -C "$dest" ls-files | wc -l | tr -d ' ') files, one commit on main at $dest"

# Publish the template repositories: for each starter, its repository
# (`scripts/starter-tree --list`) takes the starter's tree at this release -- its committed files,
# `.csis-version`, the generated README header, links out of the tree pointed at the tag -- as ONE
# commit `cs-image-system <version>` on main and the tag `v<version>`, after the public-safe gate with
# the starter's own allow list. A final version only (a template names a version teams install from
# PyPI), from a clean checkout of its tag, never twice. `yes` is the dry form: it builds every tree
# and shows what would change, and pushes nothing. The starters are every tree of docs/examples/
# with a cfg/ (the one list, read by `scripts/starter-tree --list`); the push needs STARTER_PUSH_TOKEN
# (Contents and Workflows read/write on every template repository); CI's publish job runs it after PyPI.
[doc("Publish every starter tree of docs/examples as its template repository at a final release's tag; `yes` = dry")]
publish-starters dry="no":
	#!/usr/bin/env bash
	set -euo pipefail
	version=$(uv run --no-sync bump-my-version show current_version)
	case "$version" in *.dev*) echo "publish-starters: $version is a development version -- a template names a version teams install from PyPI; nothing was published"; exit 1 ;; esac
	[ -z "$(git status --porcelain)" ] || { echo "publish-starters: the tree is not clean -- nothing was published"; exit 1; }
	if [ "{{dry}}" != "yes" ]; then
		git tag --points-at HEAD | grep -qx "v$version" || { echo "publish-starters: HEAD is not the tag v$version -- a template is published from its release's tag (its links point there); nothing was published"; exit 1; }
		[ -n "${STARTER_PUSH_TOKEN:-}" ] || { echo "publish-starters: STARTER_PUSH_TOKEN is not set -- the token that may push to the template repositories; nothing was published"; exit 2; }
	fi
	work=$(mktemp -d "${TMPDIR:-/tmp}/csis-starters.XXXXXX")
	# a template carries the modules of the plugins installed where it is written: the Google Cloud
	# family is not in this workspace's venv (spec 005), so it is layered in from the index for the
	# writing alone (`gcloud-with`)
	read -r -a with <<< "$(just gcloud-with)"
	# every repository is checked before any is pushed: one that holds the version refuses them all
	while read -r name repo; do
		if ! git clone -q --depth 1 "https://github.com/$repo.git" "$work/$name.git" 2>/dev/null; then
			[ "{{dry}}" = "yes" ] || { echo "publish-starters: $repo cannot be read -- does it exist, public? nothing was published"; exit 1; }
			echo "publish-starters: dry -- $repo cannot be read yet (it does not exist, or is not public); showing its first commit"
			git init -q "$work/$name.git"
		elif [ -n "$(git -C "$work/$name.git" ls-remote --tags origin "refs/tags/v$version")" ]; then
			echo "publish-starters: $repo already holds v$version -- a version is published once; nothing was published"; exit 1
		fi
		uv run --no-sync "${with[@]}" python scripts/starter-tree "$name" "$version" "$work/$name.tree"
		uv run --no-sync cs-image-system public-safe --tree "$work/$name.tree" --config "$work/$name.tree/cfg/_config.yml"
	done < <(uv run --no-sync python scripts/starter-tree --list)
	# the commit's identity: this checkout's (the operator's), or GitHub Actions' bot in CI
	name_id=$(git config user.name || true); email_id=$(git config user.email || true)
	if [ -n "${GITHUB_ACTIONS:-}" ] && [ -z "$email_id" ]; then
		name_id="github-actions[bot]"; email_id="41898282+github-actions[bot]@users.noreply.github.com"
	fi
	while read -r name repo; do
		clone="$work/$name.git"
		find "$clone" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
		cp -a "$work/$name.tree/." "$clone/"
		git -C "$clone" checkout -q -B main
		git -C "$clone" add -A
		if [ "{{dry}}" = "yes" ]; then
			echo "publish-starters: dry -- $repo would take v$version: $(git -C "$clone" diff --cached --shortstat HEAD 2>/dev/null || echo "$(git -C "$clone" ls-files | wc -l | tr -d ' ') files, its first commit")"
			continue
		fi
		git -C "$clone" -c user.name="$name_id" -c user.email="$email_id" commit -q -m "cs-image-system $version" -m "Generated from docs/examples/$name of infrastructurebuilder/cs-image-system-3 at v$version; this repository takes no pull requests."
		git -C "$clone" -c user.name="$name_id" -c user.email="$email_id" tag -a "v$version" -m "cs-image-system $version"
		auth=$(printf 'x-access-token:%s' "$STARTER_PUSH_TOKEN" | base64 | tr -d '\n')
		git -C "$clone" -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $auth" push -q origin main "refs/tags/v$version"
		echo "publish-starters: $repo holds cs-image-system $version (main and v$version)"
	done < <(uv run --no-sync python scripts/starter-tree --list)
	rm -rf "$work"

# Install the plain pre-commit hook (.githooks/pre-commit) for this checkout; `init` does this.
hooks:
	@git config core.hooksPath .githooks && echo "hooks: core.hooksPath = .githooks"

# Alias of `test` (the contract's name for the blocking fast suite); kept
# because notes and habits say `just verify`.
[doc("Alias of `test`, the blocking fast suite; kept because notes and habits say `just verify`")]
verify: test

# Clean build artifacts and temporary files
clean:
	@rm -rf build/
	@rm -rf dist/
	@rm -rf *.egg-info/
	@rm -rf .pytest_cache/
	@rm -rf .mypy_cache/
	@rm -rf .ruff_cache/
	@rm -rf htmlcov/
	@rm -rf .coverage
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete

# Remove virtual environment
clean-venv:
	@rm -rf .venv/
	@find . -name __pycache__ -exec rm -rf {} \;

# Clean everything
clean-all: clean clean-venv
	@rm -f uv.lock

# The system's live proof over the FROZEN FIXTURE (what this repository's CI `live` job runs; the
# reference configuration's own CI proves the live tree). With real sessions -- the fixture names the real
# account's networks -- and the fixture's committed TEST identity: `validate --online` (the one
# check that asks the clouds: each runtime's networking against its account, recorded in the fixture's
# meta-state/runtime-facts.yaml for this run and removed again afterwards, since the frozen fixture carries
# no meta-state), then a headless dry run --all over a private copy (the record copied along; the installed
# modules written beside it, as the fixture's module_source_base expects) with the state query off (the
# fixture's declarations are synthetic; reality would read as drift), then the modification tests under
# docker over the copy. Exit 0 when every leg passed.
[doc("The live proof over the frozen fixture (CI's live job): validate --online, a headless dry run --all over a copy, the modification tests under docker")]
fixture-live:
	#!/usr/bin/env bash
	set -uo pipefail
	export CSIS_CONFIG_IDENTITY="{{justfile_directory()}}/tests/fixtures/config/.age-identity"
	status=0
	had_meta_state=0; [ -d tests/fixtures/config/meta-state ] && had_meta_state=1
	echo "fixture-live: validate the frozen fixture against the clouds (validate --online records its network facts)"
	uv run cs-image-system --root-dir tests/fixtures/config validate --online || { echo "fixture-live: FAILED validate"; status=1; }
	copy=$(mktemp -d "${TMPDIR:-/tmp}/csis-fixture-live.XXXXXX")
	mkdir -p "$copy/x"
	cp -R tests/fixtures/config "$copy/x/config"
	uv run cs-image-system modules --write "$copy/x/tfmodules" || { echo "fixture-live: FAILED modules --write"; status=1; }
	# the fixture's docker runtime names a context that exists on no machine (csis-fixture-daemon); for the
	# dry run it is bound to THIS machine's daemon, the one the modification tests use, and removed again after
	made_context=0
	if docker info >/dev/null 2>&1 && ! docker context inspect csis-fixture-daemon >/dev/null 2>&1; then
		host="${DOCKER_HOST:-$(docker context inspect --format '{{{{.Endpoints.docker.Host}}' 2>/dev/null)}"
		docker context create csis-fixture-daemon --docker "host=$host" >/dev/null \
			&& { made_context=1; echo "fixture-live: docker context csis-fixture-daemon -> $host (for this run)"; } \
			|| echo "fixture-live: could not create the docker context csis-fixture-daemon; the docker roots will fail"
	fi
	echo "fixture-live: headless dry run --all over a private copy ($copy), state query off"
	uv run cs-image-system --root-dir "$copy/x/config" run --all --no-state-query || { echo "fixture-live: FAILED dry run --all"; status=1; }
	if docker info >/dev/null 2>&1; then
		echo "fixture-live: modification tests under docker over the copy (test-mods --strict)"
		uv run cs-image-system --root-dir "$copy/x/config" test-mods --strict || { echo "fixture-live: FAILED test-mods"; status=1; }
	else
		echo "fixture-live: SKIPPED test-mods -- docker is not available"
	fi
	[ "$made_context" -eq 1 ] && docker context rm -f csis-fixture-daemon >/dev/null
	rm -rf "$copy"
	# the frozen fixture carries no meta-state: the record validate --online wrote goes again
	[ "$had_meta_state" -eq 0 ] && rm -rf tests/fixtures/config/meta-state
	if [ "$status" -eq 0 ]; then echo "fixture-live: passed"; else echo "fixture-live: FAILED"; fi
	exit $status

# The `uv run` options that layer the families released from their own repositories (the Google
# Cloud family) in from the index for one command (scripts/with-released-families --print)
[private]
gcloud-with:
	@uv run --no-sync python scripts/with-released-families --print

# The starters that need every provider, the Google Cloud family's among them (tests/cloud_starters,
# left out of the default collection; a `full-test` leg and a step of CI's `live` job, never `test`, whose
# runs hold no Google Cloud package): the family is released from its own repository
# and this workspace's venv does not hold it, so it is layered in from the index for this run alone
# (scripts/with-released-families), under the strict session, so a family that is absent fails instead
# of skipping (spec 005, research R11). The index (or uv's cache); no cloud session: the starters'
# clouds are stubbed, as every starter test's are. A starter's runtimes name placeholder accounts,
# so an installed command could not validate one without a real account's `validate --online`.
[doc("The starters that need every provider (tests/cloud_starters), with the Google Cloud family from the index, strict; a full-test leg and CI live")]
test-cloud-starters:
	#!/usr/bin/env bash
	set -euo pipefail
	read -r -a with <<< "$(just gcloud-with)"
	uv run --no-sync "${with[@]}" pytest tests/cloud_starters -p cs_image_system.system.testing.strict -q

# Run the CLI against the reference configuration, e.g. `just cli validate`, `just cli config-drift`,
# `just cli state query --strict`: the system's own live proofs. Its cycles run from ITS Justfile.
[doc("Run the CLI against the reference configuration (`just cli validate`, `just cli state query --strict`): the system's own live proofs")]
[positional-arguments]
cli *ARGS: config-guard
	@{{live_cli}} "$@"

# The reference configuration must be present for the recipes that read it -- never for `just test`
[private]
config-guard:
	#!/usr/bin/env bash
	if [ ! -f "{{config_root}}/cfg/_config.yml" ]; then
		echo "config-guard: no reference configuration at {{config_root}} (cfg/_config.yml is missing)." >&2
		echo "  clone it beside this repository: git clone git@github.com:infrastructurebuilder/cs-image-system-testconfig.git" >&2
		echo "  or point CSIS_CONFIG_ROOT at a checkout." >&2
		echo "  'just test' does not need it: the tests use the frozen fixture under tests/fixtures/config/." >&2
		exit 2
	fi
