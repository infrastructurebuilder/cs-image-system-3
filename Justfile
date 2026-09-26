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
# which the release ships (stage 64); a team runs them from its own repository.

# Bare `just` lists the recipes in file order: the contract first
[private]
default:
	@just --list --unsorted

# ------------------------------------------------------------- the contract

# The REFERENCE configuration (stage 28) is its own repository, checked out beside this one by
# default; CSIS_CONFIG_ROOT overrides. The tests never read it -- they own the frozen fixture
# under tests/fixtures/config/ -- so `just test` needs no live configuration at all; every
# recipe that drives one depends on config-guard. Since stage 64 it stands alone: its own
# Justfile drives its cycles; the recipes here read it for the system's own proofs.
config_root := env("CSIS_CONFIG_ROOT", justfile_directory() + "/../cs-image-system-testconfig")
live_cli := "uv run cs-image-system --root-dir " + quote(config_root)
# Provider plugin cache: a provider downloaded once is reused by every `tofu init`; with a root's
# kept .terraform.lock.hcl the init needs no network at all. The cache is not safe under concurrent
# `init`, so one tofu process runs at a time by construction (stage 43): every invocation that may
# EXECUTE tofu passes `--locked` (stage 64), which holds .tofu-plugin-cache/.lock and refuses a
# second holder with exit 75. Dry runs enumerate and never start tofu; the suite's one real-tofu
# test uses a private cache and never contends.
export TF_PLUGIN_CACHE_DIR := justfile_directory() / ".tofu-plugin-cache"

# One-time setup: the toolchain and every workspace package (idempotent)
init:
	@uv sync --all-extras
	@just hooks

# Package every workspace member (sdist + wheel) under dist/; no tests
build:
	@uv build --all-packages

# The fast suite, every check blocking: lint (ruff), type-check (pyright), the
# unit tests (the golden emission included). The local acceptance bar;
# `verify` is its alias.
[doc("The fast suite, all blocking: lint (ruff), type-check (pyright), the unit tests; `verify` is its alias")]
test: lint typecheck pytest

# Everything `test` does plus the slow and external legs (stage 16): the
# modification tests under docker (`test-mods --strict`), and -- only when
# `just preflight` finds every runtime session present -- a headless dry
# `run --all` over a private copy of the fixture followed by
# `state query --strict`. A leg whose prerequisite is absent reports SKIPPED
# loudly with its reason and does not fail the run; a leg that runs and fails
# does. Identity credentials (OKTA_API_*, TF_VAR_<team>_*) are not gated: a
# dry run without them warns and skips the identity roots' plan.
[doc("`test` plus the docker-backed modification tests and, when the runtime sessions are present, a headless dry run --all with state query --strict")]
full-test: test
	@just full-test-legs

# Cut a release (stage 41): the probes first -- the index token, the index, the version
# it would carry (free on the index, untagged) -- then the bar, the bump, the lock, the
# build and the upload, and only then the commit and the tag, so a failed upload leaves
# an uncommitted bump to discard and never a tagged, unpublished version. TARGET is a
# part for bump-my-version (`patch`, `minor` and `major` open the next version as its
# first development release, 0.1.0 -> 0.1.1.dev1; `dev` is the next development release
# of the same version; `stage` finalises it, 0.1.1.dev2 -> 0.1.1) or an explicit version.
# INDEX is `test` (TestPyPI, the default) or `pypi`: a development release to TestPyPI is
# gated on `test`, the bar; a PyPI release on `full-test`, the modification-test evidence
# in the live configuration and a clean live checkout. `yes` as the third argument is the
# dry form: the probes and the version, nothing changed. Nothing is pushed: `git push
# --follow-tags` is the operator's act, and the pushed tag makes CI publish (it uploads
# nothing the index already holds).
[doc("Gated on the bar (test) or full-test (pypi): probe, bump, lock, build, publish, commit, tag v<version>; `yes` = dry")]
release target index="test" dry="no":
	#!/usr/bin/env bash
	set -euo pipefail
	case "{{index}}" in
		test) name=testpypi; simple=https://test.pypi.org/simple ;;
		pypi) name=pypi; simple=https://pypi.org/simple ;;
		*) echo "release: the index is test (TestPyPI, the default) or pypi, not '{{index}}'"; exit 2 ;;
	esac
	shape='^[0-9]+\.[0-9]+\.[0-9]+(\.dev[0-9]+)?$'
	current=$(uv run --no-sync bump-my-version show current_version)
	if [[ "{{target}}" =~ $shape ]]; then
		new="{{target}}"; bump=(bump --new-version "$new")
	else
		new=$(uv run --no-sync bump-my-version show --increment "{{target}}" new_version 2>/dev/null) || { echo "release: '{{target}}' is neither a version part (patch, minor, major, dev, stage) nor a version"; exit 2; }
		bump=(bump "{{target}}")
	fi
	[[ "$new" =~ $shape ]] || { echo "release: $current is a final version and '{{target}}' would make it $new -- open the next version with patch, minor or major (its first development release), then dev for each further one"; exit 2; }
	# the probes, before anything changes. The token: UV_PUBLISH_TOKEN, else the index's own
	# name (TEST_PYPI_TOKEN or PYPI_TOKEN, the repository secrets' names, so one .envrc line
	# serves the shell and CI alike)
	token_var=TEST_PYPI_TOKEN; [ "$name" = pypi ] && token_var=PYPI_TOKEN
	export UV_PUBLISH_TOKEN="${UV_PUBLISH_TOKEN:-${!token_var:-}}"
	[ -n "$UV_PUBLISH_TOKEN" ] || { echo "release: neither UV_PUBLISH_TOKEN nor $token_var is set -- the API token for $name; a release publishes, so it refuses up front rather than leave a tagged, unpublished version"; exit 2; }
	set +e; uv run --no-sync python scripts/index-knows "$simple" cs-image-system "$new"; known=$?; set -e
	case $known in
		0) echo "release: $name already knows cs-image-system $new -- a version is never re-cut; take the next one"; exit 1 ;;
		1) ;;
		*) echo "release: could not read $simple (the probe exited $known)"; exit 2 ;;
	esac
	[ -z "$(git tag -l "v$new")" ] || { echo "release: v$new is already tagged here -- a version is never re-cut, even after its files were deleted from the index"; exit 1; }
	gate=test; [ "$name" = pypi ] && gate=full-test
	if [ "{{dry}}" = "yes" ]; then
		echo "release: dry -- $current would become $new: free on $name, untagged, token present. The real form: just $gate, bump-my-version ${bump[*]}, uv lock, just publish {{index}}, commit 'release $new', tag v$new"
		exit 0
	fi
	dirty=$(git status --porcelain)
	[ -z "$dirty" ] || { echo "release: the working tree must be clean:"; echo "$dirty"; exit 1; }
	if [ "$name" = pypi ]; then
		# full-test's docker leg writes meta-state/mod-tests.yaml in the LIVE configuration (the evidence
		# that the released modifications passed, stage 14): release commits it THERE
		just full-test
		[ -f "{{config_root}}/meta-state/mod-tests.yaml" ] || { echo "release: no modification-test evidence at {{config_root}}/meta-state/mod-tests.yaml (run full-test with docker)"; exit 1; }
		cdirty=$(git -C "{{config_root}}" status --porcelain | grep -v ' meta-state/mod-tests.yaml$' || true)
		[ -z "$cdirty" ] || { echo "release: the live configuration must be clean apart from its mod-test evidence:"; echo "$cdirty"; exit 1; }
	else
		just test
	fi
	uv run --no-sync bump-my-version "${bump[@]}"
	uv lock
	# the upload comes BEFORE the commit and the tag: a failed upload leaves an uncommitted bump
	just publish {{index}} || { echo "release: the upload to $name failed; the bump to $new is uncommitted -- discard it with: git checkout -- pyproject.toml packages/*/pyproject.toml uv.lock"; exit 1; }
	if [ "$name" = pypi ]; then
		git -C "{{config_root}}" add meta-state/mod-tests.yaml
		git -C "{{config_root}}" diff --cached --quiet || git -C "{{config_root}}" commit -q -m "release $new: modification-test evidence"
	fi
	git add pyproject.toml packages/*/pyproject.toml uv.lock
	git commit -q -m "release $new"
	git tag -a "v$new" -m "release $new"
	echo "release: $new is on $name, committed and tagged v$new; push with: git push --follow-tags (CI then checks the tag against the index and uploads nothing already there)"

# Build and upload the version in the tree (stage 41.6): `dist/` cleaned, every package
# built, every file uploaded to INDEX -- `test` (TestPyPI, the default) or `pypi` -- with
# the files the index already holds with the same content skipped (the index's url is
# the check url), so a
# re-run after a partial failure, or CI after a local publish, uploads what is missing and
# nothing twice. The token is UV_PUBLISH_TOKEN, else TEST_PYPI_TOKEN / PYPI_TOKEN (the
# repository secrets' names), from the environment and never here; the endpoints are the
# `[[tool.uv.index]]` entries in pyproject.toml. A deleted version can
# never be uploaded again, on either index: the next upload is a new version.
[doc("Build and upload the version in the tree to TestPyPI (`test`, the default) or PyPI (`pypi`); UV_PUBLISH_TOKEN from the environment")]
publish index="test":
	#!/usr/bin/env bash
	set -euo pipefail
	case "{{index}}" in
		test) name=testpypi ;;
		pypi) name=pypi ;;
		*) echo "publish: the index is test (TestPyPI, the default) or pypi, not '{{index}}'"; exit 2 ;;
	esac
	# the token: UV_PUBLISH_TOKEN, else the index's own name (TEST_PYPI_TOKEN or PYPI_TOKEN)
	token_var=TEST_PYPI_TOKEN; [ "$name" = pypi ] && token_var=PYPI_TOKEN
	export UV_PUBLISH_TOKEN="${UV_PUBLISH_TOKEN:-${!token_var:-}}"
	[ -n "$UV_PUBLISH_TOKEN" ] || { echo "publish: neither UV_PUBLISH_TOKEN nor $token_var is set -- the API token for $name, from the environment; never in this file"; exit 2; }
	version=$(uv run --no-sync bump-my-version show current_version)
	rm -rf dist
	just build
	n=$(ls dist | wc -l | tr -d ' ')
	# --index alone: uv takes the index's url as the check url and refuses an explicit one beside it
	uv publish --index "$name" dist/*
	echo "publish: cs-image-system $version is on $name ($n files: the system and its sixteen packages, sdist and wheel each; files already there with the same content were skipped)"

# ------------------------------------------------------------ development

# So a session that lapsed after the bar costs the legs again, not the bar (hygiene V item 2); the
# session is checked once up front, and a leg that finds it gone mid-way still fails loudly.
# The live legs of full-test alone: test-mods under docker, a dry run --all and a state query --strict over a private copy of the live configuration
full-test-legs:
	#!/usr/bin/env bash
	set -uo pipefail
	status=0
	if docker info >/dev/null 2>&1; then
		echo "full-test: modification tests under docker (test-mods --strict)"
		just test-mods --strict || { echo "full-test: FAILED test-mods"; status=1; }
	else
		echo "full-test: SKIPPED test-mods -- docker is not available"
	fi
	if [ ! -f "{{config_root}}/cfg/_config.yml" ]; then
		echo "full-test: SKIPPED the live-configuration legs (dry run --all, state query --strict) -- no live configuration at {{config_root}} (see: just config-guard)"
	elif just preflight; then
		copy=$(mktemp -d "${TMPDIR:-/tmp}/csis-full-test.XXXXXX")
		# The reference configuration carries its own tfmodules (stage 64), so the copy needs nothing beside
		# it. Never carry its .git (a copy must not commit into the live repo), its generated trees or its mirror.
		mkdir -p "$copy/cs-image-system-testconfig"
		(cd "{{config_root}}" && tar --exclude=./.git --exclude=./generated --exclude=./_private -cf - .) | tar -xf - -C "$copy/cs-image-system-testconfig"
		echo "full-test: headless dry run --all over a private copy of the reference configuration ($copy)"
		uv run cs-image-system --root-dir "$copy/cs-image-system-testconfig" run --all || { echo "full-test: FAILED dry run --all"; status=1; }
		echo "full-test: state query --strict over the copy"
		uv run cs-image-system --root-dir "$copy/cs-image-system-testconfig" state query --strict || { echo "full-test: FAILED state query --strict"; status=1; }
		rm -rf "$copy"
	else
		echo "full-test: SKIPPED the credential-gated legs (dry run --all, state query --strict) -- a runtime session is absent or expired (see above)"
	fi
	if [ "$status" -eq 0 ]; then echo "full-test: passed"; else echo "full-test: FAILED"; fi
	exit $status

# Format code with ruff
format:
	@uv run ruff format packages tests

# Run linter (blocking) -- same command CI runs; then the licensing check: every file carries
# copyright and licence information (an SPDX header, or a REUSE.toml declaration)
lint:
	@uv run ruff check packages tests
	@uv run reuse lint

# Licence headers (REUSE): the SPDX two-liner, holder and licence, on every source file that lacks one.
# Never the fixtures (hashed modification content, the golden) nor prose: those are declared in
# REUSE.toml. Idempotent (--skip-existing); ends with the lint.
headers:
	#!/usr/bin/env bash
	set -euo pipefail
	H="Mykel Alvis <mykelalvis@infrastructurebuilder.org>"; Y=$(date +%Y)
	find packages -name '*.py' -not -path '*/.venv/*' -print0 | xargs -0 uv run reuse annotate --copyright "$H" --license Apache-2.0 --year "$Y" --skip-existing
	find tfmodules -name '*.tf' -print0 | xargs -0 uv run reuse annotate --copyright "$H" --license Apache-2.0 --year "$Y" --skip-existing
	uv run reuse annotate --copyright "$H" --license Apache-2.0 --year "$Y" --skip-existing tests/*.py bin/*.sh .github/workflows/*.yml pyproject.toml packages/*/pyproject.toml
	uv run reuse annotate --copyright "$H" --license Apache-2.0 --year "$Y" --skip-existing --style python Justfile .githooks/pre-commit
	uv run reuse lint

# The licensing check over the live configuration (its REUSE.toml declares every file; no headers there)
reuse-live: config-guard
	@cd "{{config_root}}" && "{{justfile_directory()}}/.venv/bin/reuse" lint

# Fix linting issues automatically (safe fixes)
lint-fix:
	@uv run ruff check --fix packages tests

lint-unsafe-fix:
	@uv run ruff check --fix --unsafe-fixes packages tests

# Type check with pyright (basic mode; see [tool.pyright] in pyproject.toml)
typecheck:
	@uv run pyright

# The unit tests alone (`test` runs them after lint and typecheck)
pytest:
	@uv run pytest

# One file, or any pytest expression, for iterating on a single change.
# NOT the acceptance bar -- `just test` is, and a change is not done until
# that passes. This exists so proving one file does not cost a full suite.
test-one *ARGS:
	@uv run pytest {{ARGS}}

# V2 gate tests only (tests/test_v2_*): the executable evidence for each
# DESIGN §4 gate. Cloud-free: every test runs over a private copy of
# the frozen fixture with AWS/Okta/tool execution stubbed (see GOLDEN.md).
v2-test:
	@uv run pytest tests/test_v2_*.py -q

# Run every modification twice in a throwaway local container (apply +
# idempotence); needs docker. Results: <config_root>/meta-state/mod-tests.yaml
test-mods *ARGS: config-guard
	@{{live_cli}} test-mods {{ARGS}}

# The credential sessions the reference configuration's runtimes need, read from the caches without
# loading the configuration (exit 0: every one present; 2: one absent or expired) -- full-test's gate
preflight: config-guard
	@{{live_cli}} preflight

# Regenerate tests/fixtures/v2_golden (the pinned V2 emission) after an
# INTENTIONAL emission change; review the resulting diff before committing.
golden-regen:
	@uv run python tests/golden.py

# Public-safe by construction (stage 35): scan what a commit could publish -- tracked files and
# untracked files that are not ignored -- for material that must never be public (keys, tokens,
# PEM bodies, an age identity, plans and state by name; addresses and long tokens outside prose
# and tests). The allow list is the frozen fixture's cfg/_config.yml public_safe.allow. CI runs it.
public-safe *ARGS:
	@uv run cs-image-system public-safe --tree . --config tests/fixtures/config/cfg/_config.yml {{ARGS}}

# Build a publishable tree (stage 40): the TRACKED files of ROOT at HEAD (nothing ignored can enter),
# a USER exclusion list (PUBLISH_EXCLUDE="path/one path/two", default none), the public-safe gate over
# the result with the root's own allow list, the ignore policy checked line by line, then ONE commit on
# main (PUBLISH_MESSAGE, default "Initial public release"). Refuses a dirty root, a finding, a missing
# ignore line or an existing DEST. Never pushes: the remote is the operator's act (TODO §40.4).
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
	# publication push was refused for exactly that (stage 43)
	name=$(git -C "$root" config user.name || true); email=$(git -C "$root" config user.email || true)
	[ -z "$name" ] || git -C "$dest" config user.name "$name"
	[ -z "$email" ] || git -C "$dest" config user.email "$email"
	git -C "$dest" add -A
	git -C "$dest" commit -q -m "${PUBLISH_MESSAGE:-Initial public release}"
	echo "publish-tree: $(git -C "$dest" ls-files | wc -l | tr -d ' ') files, one commit on main at $dest"

# Install the plain pre-commit hook (.githooks/pre-commit) for this checkout; `init` does this.
hooks:
	@git config core.hooksPath .githooks && echo "hooks: core.hooksPath = .githooks"

# Alias of `test` (the contract's name for the blocking fast suite); kept
# because notes and habits say `just verify`.
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

# The system's live proof over the FROZEN FIXTURE (stage 64: what this repository's CI `live` job runs; the
# reference configuration's own CI proves the live tree). With real sessions -- the fixture names the real
# account's networks and project -- and the fixture's committed TEST identity: validate, then a headless dry
# run --all over a private copy (tfmodules beside it, as the fixture's module_source_base expects) with the
# state query off (the fixture's declarations are synthetic; reality would read as drift), then the
# modification tests under docker over the copy. Exit 0 when every leg passed.
fixture-live:
	#!/usr/bin/env bash
	set -uo pipefail
	export CSIS_CONFIG_IDENTITY="{{justfile_directory()}}/tests/fixtures/config/.age-identity"
	status=0
	echo "fixture-live: validate the frozen fixture"
	uv run cs-image-system --root-dir tests/fixtures/config validate || { echo "fixture-live: FAILED validate"; status=1; }
	copy=$(mktemp -d "${TMPDIR:-/tmp}/csis-fixture-live.XXXXXX")
	mkdir -p "$copy/x"
	cp -R tests/fixtures/config "$copy/x/config"
	cp -R tfmodules "$copy/x/tfmodules"
	echo "fixture-live: headless dry run --all over a private copy ($copy), state query off"
	uv run cs-image-system --root-dir "$copy/x/config" run --all --no-state-query || { echo "fixture-live: FAILED dry run --all"; status=1; }
	if docker info >/dev/null 2>&1; then
		echo "fixture-live: modification tests under docker over the copy (test-mods --strict)"
		uv run cs-image-system --root-dir "$copy/x/config" test-mods --strict || { echo "fixture-live: FAILED test-mods"; status=1; }
	else
		echo "fixture-live: SKIPPED test-mods -- docker is not available"
	fi
	rm -rf "$copy"
	if [ "$status" -eq 0 ]; then echo "fixture-live: passed"; else echo "fixture-live: FAILED"; fi
	exit $status

# Run the CLI against the reference configuration, e.g. `just cli validate`, `just cli config-drift`,
# `just cli state query --strict`: the system's own live proofs. Its cycles run from ITS Justfile.
cli *ARGS: config-guard
	@{{live_cli}} {{ARGS}}

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
