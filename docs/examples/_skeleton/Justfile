# The Justfile of a cs-image-system CONFIGURATION repository: the single entry point
# for everything a team does to its environment. Every recipe wraps the released
# `cs-image-system` command against THIS tree; nothing here is the system's code.
#
# The command comes from a release. Either of:
#   uv tool install cs-image-system            the CLI on PATH (the default below)
#   a pyproject.toml here depending on it       then: export CSIS="uv run cs-image-system"
# A version pin for CI lives in .csis-version (see .github/workflows/ci.yml).
#
# The five contract targets come first, in lifecycle order; bare `just` lists them.

[private]
default:
	@just --list --unsorted

# ------------------------------------------------------------- the contract

csis := env("CSIS", "cs-image-system")
root := justfile_directory()
cli := csis + " --root-dir " + quote(root)
# A CSIS that names a path (a development checkout's venv) is not on PATH, yet a run's own steps and the
# emitted runner scripts call the command back by its bare name: its directory goes first on PATH for every
# recipe. A release on PATH, or CSIS="uv run cs-image-system" (uv puts its venv on the child's PATH), needs nothing.
export PATH := if csis =~ "/" { parent_directory(csis) + ":" + env("PATH") } else { env("PATH") }

# One tofu process at a time: every recipe that may execute tofu passes `--locked` to the command,
# which holds a lock under this cache directory for the whole run (a second holder is refused with exit 75).
export TF_PLUGIN_CACHE_DIR := justfile_directory() / ".tofu-plugin-cache"

# One-time setup: the command must be reachable, the public-safe hook is installed, the plugin cache exists
init:
	#!/usr/bin/env bash
	set -euo pipefail
	{{csis}} --help >/dev/null 2>&1 || { echo "init: '{{csis}}' is not runnable -- install a release (uv tool install cs-image-system) or export CSIS=\"uv run cs-image-system\" beside a pyproject that depends on it"; exit 2; }
	git config core.hooksPath .githooks && echo "init: core.hooksPath = .githooks (the public-safe gate)"
	mkdir -p "$TF_PLUGIN_CACHE_DIR"
	echo "init: $({{csis}} --version 2>/dev/null || echo cs-image-system) ready against {{root}}"
	echo "init: the run's callbacks find $(command -v cs-image-system || echo 'NOTHING -- put the command on PATH, or point CSIS at it')"

# The emission: a DRY run of every lifecycle writes generated/ and enumerates every apply; nothing executes
build:
	@{{cli}} run --all

# The fast checks: every rule of the configuration, and nothing here that must never be public.
# `validate` loads the tree without reaching a cloud: the runtimes' networks come from the recorded
# meta-state/runtime-facts.yaml, which `cs-image-system validate --online` (with the sessions `just preflight`
# reports) and every real run write; the public-safe scan needs nothing.

# The fast checks: validate (needs the sessions) and public-safe
test:
	@{{cli}} validate
	@{{cli}} public-safe --tree "{{root}}"

# `test` plus the slow legs: a dry run of everything over a private copy, the strict state query against
# both clouds, and every modification twice in a container (docker). A leg whose prerequisite is absent
# reports SKIPPED loudly; a leg that runs and fails, fails.

# `test` plus the slow legs: test-mods under docker, a dry run --all and state query --strict over a private copy
full-test: test
	#!/usr/bin/env bash
	set -uo pipefail
	status=0
	if docker info >/dev/null 2>&1; then
		echo "full-test: modification tests under docker (test-mods --strict)"
		{{cli}} test-mods --strict || { echo "full-test: FAILED test-mods"; status=1; }
	else
		echo "full-test: SKIPPED test-mods -- docker is not available"
	fi
	if {{cli}} preflight; then
		copy=$(mktemp -d "${TMPDIR:-/tmp}/csis-full-test.XXXXXX")
		# never the provider cache: gigabytes, and the copy's inits use this tree's (TF_PLUGIN_CACHE_DIR above)
		(cd "{{root}}" && tar --exclude=./.git --exclude=./generated --exclude=./_private --exclude=./.tofu-plugin-cache -cf - .) | tar -xf - -C "$copy"
		echo "full-test: dry run --all over a private copy ($copy)"
		{{csis}} --root-dir "$copy" run --all || { echo "full-test: FAILED dry run --all"; status=1; }
		echo "full-test: state query --strict over the copy"
		{{csis}} --root-dir "$copy" state query --strict || { echo "full-test: FAILED state query --strict"; status=1; }
		rm -rf "$copy"
	else
		echo "full-test: SKIPPED the credential-gated legs (dry run --all, state query --strict) -- a runtime session is absent or expired"
	fi
	if [ "$status" -eq 0 ]; then echo "full-test: passed"; else echo "full-test: FAILED"; fi
	exit $status

# A release of this environment is a PERFORMING run on one runtime (what CI does on main): the bakes that
# are due, the declared releases and the declared retention, gated on a green full-test, records committed

# The performing run on one runtime, gated on full-test: due bakes, declared releases, retention; records committed
release runtime: full-test
	@{{cli}} --locked --no-dry-run run base-image instance-image release retention --only-runtime {{runtime}} --commit

# Take a release (hygiene XXI): the whole walk of moving this tree onto VERSION, in one box. The
# first act is the catch-up guard (fetch, `merge --ff-only origin/main`, `merge-base
# --is-ancestor`); then the release is installed (unless CSIS names another command), the files the
# release owns are listed against the previous release (`init-config --changes-since`) and the
# recipe STOPS if any changed, because refreshing them stays BY HAND: run
# `cs-image-system init-config . --force`, read `git diff`, then `just take VERSION patched`. With
# nothing to patch (or `patched`) it writes .csis-version, runs `just init` and `just validate`,
# commits "Take VERSION" and pushes `develop`; if `just init` or `just validate` fails the pin is put back, so
# the same command can be run again. Pushing `develop` to `main` is its own act: `main` performs.
[doc("Take a release in one box: guard, install, list what the release changed, init, validate, commit, push develop; `patched` after refreshing by hand")]
take version patched="no":
	#!/usr/bin/env bash
	set -euo pipefail
	version="{{version}}"
	[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.dev[0-9]+)?$ ]] || { echo "take: '$version' is not a release version (for example 0.1.6 or 0.1.6.dev2)"; exit 2; }
	[ "{{patched}}" = "no" ] || [ "{{patched}}" = "patched" ] || { echo "take: the second argument is 'patched' (you refreshed the release-owned files by hand) or nothing"; exit 2; }
	branch=$(git rev-parse --abbrev-ref HEAD)
	[ "$branch" = develop ] || { echo "take: this checkout is on '$branch'; a release is taken on develop -- nothing was changed"; exit 1; }
	if [ "{{patched}}" = "no" ]; then
		[ -z "$(git status --porcelain)" ] || { echo "take: the tree must be clean first (commit or discard; after refreshing the release-owned files by hand, say 'patched'):"; git status --short; exit 1; }
	fi
	# the catch-up guard of develop from origin/main, its own first act (missed twice before it was a recipe)
	git fetch -q origin
	if git rev-parse -q --verify origin/main >/dev/null; then
		git merge --ff-only origin/main >/dev/null || { echo "take: develop cannot fast-forward to origin/main -- reconcile them first; nothing was changed"; exit 1; }
		git merge-base --is-ancestor origin/main HEAD || { echo "take: origin/main is not an ancestor of develop -- nothing was changed"; exit 1; }
	fi
	old=$(git show HEAD:.csis-version 2>/dev/null | head -1 || true)
	# a development release is on TestPyPI only, with PyPI as the extra index (stage 99)
	test_index=(--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --index-strategy unsafe-first-match)
	index=(); [[ "$version" == *.dev* ]] && index=("${test_index[@]}")
	oldindex=(); [[ "$old" == *.dev* ]] && oldindex=("${test_index[@]}")
	# the umbrella with the extras this tree's `type:` words need (`just extras`): a bare install carries no runtime
	extras=$(just extras)
	if [ -z "${CSIS:-}" ]; then
		uv tool install --force ${index[@]+"${index[@]}"} "cs-image-system${extras:+[$extras]}==$version" >/dev/null 2>&1 || { echo "take: cs-image-system${extras:+[$extras]}==$version could not be installed from the index (a development release is on TestPyPI, a final one on PyPI) -- nothing was changed"; exit 1; }
	fi
	have=$({{csis}} --version 2>/dev/null | awk '{print $NF}')
	if [ "$have" != "$version" ]; then
		# hygiene XXII item 1: a CSIS in a checkout's venv answers with the version the venv was last synced to
		case "${CSIS:-}" in
			*/.venv/bin/*) echo "take: '$CSIS' reports '$have', not $version -- it lies in the venv of ${CSIS%%/.venv/bin/*}, which has not been synced to that release: run \`just init\` THERE, then run this again; nothing was changed" ;;
			*) echo "take: '{{csis}}' reports '$have', not $version -- point CSIS at that release, or install it; nothing was changed" ;;
		esac
		exit 1
	fi
	if [ "{{patched}}" = "no" ] && [ -n "$old" ] && [ "$old" != "$version" ]; then
		prev=$(uvx ${oldindex[@]+"${oldindex[@]}"} --from "cs-image-system==$old" python -c 'from cs_image_system.system import starters; print(starters.starters_root())' 2>/dev/null) \
			|| { echo "take: the previous release $old could not be fetched to compare with -- nothing was changed"; exit 1; }
		if ! {{csis}} init-config . --changes-since "$prev"; then
			echo "take: STOP -- the release changed files it owns (above). Refresh them by hand: \`cs-image-system init-config . --force\` (it keeps your values where the release has REPLACE-ME), read \`git diff\`, then \`just take $version patched\`. Nothing was committed"
			exit 1
		fi
	fi
	# hygiene XXII item 2: a failure after the pin is written puts the pin back, so the same command runs again
	had=no; prior=
	if [ -f .csis-version ]; then had=yes; prior=$(cat .csis-version); fi
	printf '%s\n' "$version" > .csis-version
	for step in init validate; do
		just "$step" || {
			if [ "$had" = yes ]; then printf '%s\n' "$prior" > .csis-version; else rm -f .csis-version; fi
			echo "take: \`just $step\` failed (above); .csis-version is back at ${prior:-nothing}, so run the same command again: just take $version{{ if patched == "patched" { " patched" } else { "" } }}"
			exit 1
		}
	done
	git add -A
	git diff --cached --quiet && { echo "take: nothing changed -- $version is already what this tree pins"; exit 0; }
	git commit -q -m "Take $version"
	git push origin develop
	echo "take: $version is taken and develop is pushed. Pushing develop to main is its own act (main performs): git push origin develop:main"

# The extras of the umbrella this tree needs, comma-separated in the order aws,gcloud,docker,okta
# (empty when it needs none): `uv tool install cs-image-system` carries no runtime, and each provider
# is an extra -- `cs-image-system[aws,okta]`. Read from the `type:` words under cfg/ (every file but
# executables.yml, which names tools, not plugins): a runtime's word, its terraform roots' instance
# and storage words, its state backend's word and the Okta identity words map to their extra. The
# table is the umbrella's own, cs_image_system.extras.WORDS; a test holds the two to be one.
# `take` and the workflows install with it: "cs-image-system${extras:+[$extras]}==$version".
[private]
extras:
	#!/usr/bin/env bash
	set -euo pipefail
	aws=; gcloud=; docker=; okta=
	words=$(for f in "{{root}}"/cfg/*.yml; do
		[ -f "$f" ] || continue
		case "$f" in */executables.yml) continue ;; esac
		sed -n 's/^[[:space:]]*type:[[:space:]]*\([^#[:space:]]*\).*/\1/p' "$f"
	done | tr -d "'\"" | sort -u)
	for word in $words; do
		case "$word" in
			aws|s3|tf-aws|tf-aws-ebs|tf-aws-efs|tf-aws-s3|tofu) aws=aws ;;
			gcloud|gcs|tf-gcp|tf-gcp-filestore|tf-gcp-gcs|tf-gcp-pd|tofu-gce) gcloud=gcloud ;;
			docker|tf-docker-volume|tofu-docker) docker=docker ;;
			okta-tf|okta-tf-ro) okta=okta ;;
			*) ;;
		esac
	done
	out=""
	for extra in $aws $gcloud $docker $okta; do out="${out:+$out,}$extra"; done
	printf '%s\n' "$out"

# ------------------------------------------------------------ every day

# Every rule, nothing generated; the first thing after any edit
validate:
	@{{cli}} validate

# A dry run of the lifecycles named (default: all): generated/ and the runner scripts, nothing executed
dry *LIFECYCLES:
	@{{cli}} run {{ if LIFECYCLES == "" { "--all" } else { LIFECYCLES } }}

# A REAL run of the lifecycles named, gated, its records committed here (you push)
run +LIFECYCLES:
	@{{cli}} --locked --no-dry-run run {{LIFECYCLES}} --commit

# The record: a dry run of EVERY lifecycle, unscoped, its emission and meta-state committed here (you push);
# what CI's perform job makes first and last, so a record exists whatever happens in between
record:
	@{{cli}} run --all --commit

# The credential sessions the runtimes need, read from the caches over the loaded tree (no cloud call)
preflight:
	@{{cli}} preflight

# Reality against the records, read-only; --strict (any drift class but stale) before a cycle step
state-query *ARGS:
	@{{cli}} state query {{ARGS}}

# Reality must match the records exactly before a cycle step
cloud-preflight:
	@{{cli}} state query --strict

# The configuration's facts about a runtime (project or account, zone, images, storages, instances) as JSON
cloud-describe runtime:
	@{{cli}} runtime describe {{runtime}}

# Bake only what changed on the runtime; the storage and instance roots plan and gate only
cloud-bake runtime dry="no": cloud-preflight
	@{{cli}} --locked {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} run base-image instance-image --only-runtime {{runtime}} --commit

# The performing run of a runtime (what CI does on main): due bakes, declared releases, declared retention
cloud-perform runtime: cloud-preflight
	@{{cli}} --locked --no-dry-run run base-image instance-image release retention --only-runtime {{runtime}} --commit

# The whole cycle as ONE run, scoped and applied to a runtime whose instances are all ephemeral; then the emptiness assertion
cloud-cycle runtime dry="no": cloud-preflight
	@{{cli}} --locked {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} run --all --only-runtime {{runtime}} --apply-runtime {{runtime}} --commit
	@{{ if dry == "yes" { "echo 'dry run: empty assertion skipped'" } else { "just cloud-empty " + runtime } }}

# The same cycle for a runtime that carries STANDING instances: no emptiness assertion afterwards
cloud-stand runtime dry="no": cloud-preflight
	@{{cli}} --locked {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} run --all --only-runtime {{runtime}} --apply-runtime {{runtime}} --commit

# Gated launch of the runtime's instances alone (nothing re-bakes); an ephemeral instance launches, verifies and tears down
cloud-launch runtime dry="no": cloud-preflight
	@{{cli}} --locked {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} run instance-image --only none --apply-runtime {{runtime}} --commit

# Gated destroy of ONE instance of the runtime: INSTANCE is undeclared for this invocation alone (the tree is
# untouched), so a leftover standing machine is destroyed through the gate instead of re-verified; a dry
# run keeps the record. `cloud-dispose-images` afterwards is the runtime's full teardown.
cloud-decommission runtime instance dry="no": cloud-preflight
	@{{cli}} --locked {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} --undeclare instance:{{instance}} run instance-image --only none --apply-runtime {{runtime}} --commit

# Verify a standing instance through the system; `sft` adds the login proof through the managed policy
cloud-verify runtime instance leg="serial":
	#!/usr/bin/env bash
	set -euo pipefail
	{{cli}} verify instance {{instance}} --timeout 600
	if [ "{{leg}}" = "sft" ]; then
		just ci-login-proof {{instance}} && echo "cloud-verify: login through the managed policy confirmed"
	fi

# A durable instance takes its image's next build as ONE gated sequence: the pin moves (`to` = a build id;
# default the series head), the replace launches through the gate, the proof runs on the new machine, the
# release records the build, one more launch gives the machine its names. require_released_builds stays true.
cloud-upgrade runtime instance to="": cloud-preflight
	#!/usr/bin/env bash
	set -euo pipefail
	{{cli}} upgrade instance {{instance}} {{ if to != "" { "--to " + to } else { "" } }}
	just cloud-launch {{runtime}}
	just cloud-verify {{runtime}} {{instance}}
	{{cli}} --locked --no-dry-run run release --only-runtime {{runtime}} --commit
	just cloud-launch {{runtime}}
	# hygiene XIII item 1: the last run regenerates the instance lifecycle alone, so the release
	# read-model the release run moved reaches the committed emission only with a full record
	# (until 2026-10-15 `live` on main failed on config-drift until one was made by hand)
	just record
	echo "cloud-upgrade: {{instance}} stands on its released build, recorded; run 'just ci-login-proof {{instance}}' to log in by name"

# End-of-cycle assertion: the runtime holds nothing beyond its declared storages, and the strict state query agrees
cloud-empty runtime:
	@{{cli}} empty --runtime {{runtime}}

# Dispose of every recorded image on the runtime through the recorded path
cloud-dispose-images runtime dry="no":
	@{{cli}} {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} dispose image --runtime {{runtime}} --all --commit

# Re-tag cloud images whose lineage tags disagree with their record, from the record, and give the
# configuration's id (csis_config) to standing storages and machines that lack it (stage 93). Dry by default.
cloud-relabel runtime dry="yes":
	@{{cli}} {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} lineage relabel --runtime {{runtime}}

# Log into every standing instance (or the ARGS named) through the managed CI policy: as the workload in a
# GitHub Actions job (`workload token` mints the OPA token from this run's OIDC token, the names from the
# configuration), as YOU (the enrolled client, `sft login` first) anywhere else
ci-login-proof *ARGS:
	#!/usr/bin/env bash
	set -euo pipefail
	if [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
		named=$({{cli}} workload describe)
		if [ "$named" != "[]" ]; then
			OPA_TOKEN=$({{cli}} workload token)
			export OPA_TOKEN
		else
			# stage 75: no group builder names an OPA workload connection (a posix-only tree):
			# no token to mint; a posix group's proof logs in with CSIS_PROOF_SSH_KEY
			echo "ci-login-proof: no workload connection is named -- no OPA token to mint" >&2
		fi
	else
		echo "ci-login-proof: not a GitHub Actions job -- logging in as the enrolled client, not the workload" >&2
	fi
	{{cli}} verify login {{ARGS}}

# Present this Actions run's OIDC token to the team's workload connection and say two things: the
# connection accepted it and issued one, and whether that token carries the ROLE (`role: granted` from
# the pinned branch alone, judged by resolving a standing machine of a managed group). The names from the
# environment: OPA_WORKLOAD_CONNECTION, OPA_WORKLOAD_ROLE, SFT_TEAM, OPA_ADDR; needs `id-token: write`
opa-workload-probe:
	@{{cli}} workload probe

# The OPA client, from Okta's apt repository (a no-op where `sft` is already on PATH)
sft-install:
	#!/usr/bin/env bash
	set -euo pipefail
	if command -v sft >/dev/null 2>&1; then echo "sft-install: $(sft --version 2>/dev/null | head -1) already on PATH"; exit 0; fi
	command -v apt-get >/dev/null 2>&1 || { echo "sft-install: not an apt system; install the client by hand: https://help.okta.com/oie/en-us/content/topics/privileged-access/tool-setup/pam-sft-ubuntu.htm" >&2; exit 2; }
	. /etc/os-release
	curl -fsSL https://dist.scaleft.com/GPG-KEY-OktaPAM-2023 | gpg --dearmor | sudo tee /usr/share/keyrings/oktapam-2023-archive-keyring.gpg >/dev/null
	echo "deb [signed-by=/usr/share/keyrings/oktapam-2023-archive-keyring.gpg] https://dist.scaleft.com/repos/deb ${VERSION_CODENAME} okta" | sudo tee /etc/apt/sources.list.d/oktapam-stable.list >/dev/null
	sudo apt-get update -qq && sudo apt-get install -y -qq scaleft-client-tools
	echo "sft-install: $(sft --version | head -1)"

# Every modification twice in a throwaway container (apply, then idempotence); needs docker
test-mods *ARGS:
	@{{cli}} test-mods {{ARGS}}

# Nothing here may be material that must never be public; the pre-commit hook runs the staged form
public-safe *ARGS:
	@{{cli}} public-safe --tree "{{root}}" {{ARGS}}

# The one-time initialisation as terraform, from an interview (stage 70): the answers go to bootstrap.yaml at the
# root of the tree, generated/bootstrap/ is written from them (and rewritten by every run); applying it is yours
bootstrap *ARGS:
	@{{cli}} bootstrap {{ARGS}}

# Is the committed emission current? A dry run over a private copy against generated/ at HEAD (0 / 1 behind / 2 failed)
config-drift:
	@{{cli}} config-drift

# Has RUNTIME's emission changed since REF (default HEAD)? Exit 1 with the diff when a declaration of it changed
runtime-unchanged runtime ref="HEAD":
	@{{cli}} runtime-unchanged {{runtime}} --ref {{ref}}

# Remove the private mirror: the materialised copy an execution ran from (plaintext); never committed
mirror-clean:
	@rm -rf "{{root}}/_private" && echo "removed {{root}}/_private"

# Install the public-safe pre-commit hook (init does this)
hooks:
	@git config core.hooksPath .githooks && echo "hooks: core.hooksPath = .githooks"

# Any command of the CLI against this tree, e.g. `just cli state query`
cli *ARGS:
	@{{cli}} {{ARGS}}
