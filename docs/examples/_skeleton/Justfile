# The Justfile of a cs-image-system CONFIGURATION repository: the single entry point
# for everything a team does to its environment. Every recipe wraps the released
# `cs-image-system` command against THIS tree; nothing here is the system's code.
#
# The command comes from a release. Either of:
#   uv tool install cs-image-system            the CLI on PATH (the default below)
#   a pyproject.toml here depending on it       then: export CSIS="uv run cs-image-system"
# The version pin lives in .csis-version: CI installs it (see .github/workflows/ci.yml), and a committing run
# or restamp is refused when the command is not that release from an index (CSIS_ALLOW_UNPINNED=1 goes on).
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

# Take a release: the whole walk of moving this tree onto VERSION, in one box, in this order:
# 1. the guard: on develop, the tree clean (unless `patched`), develop fast-forwarded from origin/main;
#    a take that already finished (HEAD pins VERSION, develop level with origin/develop) says so and
#    exits 0 here, having changed nothing;
# 2. a FINAL version only: the tag v<VERSION>-before on HEAD, pushed (one already on HEAD is passed);
# 3. the release installed as the uv tool with this tree's extras (`just extras`); every later step
#    runs by THAT binary, whatever CSIS names for the other recipes;
# 4. the runtimes' sessions (`just preflight`): one absent or lapsed refuses, naming its login;
# 5. what the release changed against the previous release (`init-config --changes-since --porcelain`,
#    a module judged by its stamp): anything `edited` in this tree STOPS the take, naming it alone
#    (refresh it by hand, read `git diff`, then `just take VERSION patched`); otherwise
#    `init-config . --force` refreshes what was listed, and nothing else;
# 6. .csis-version, `just init`, `just validate`, and the commit "Take VERSION", whose body names what
#    was refreshed and added, one line per class;
# 7. the record (`just record`, by the same binary), its own commit when the emission moved;
# 8. ONE `git push origin develop` with both; with `main`, then `git push origin develop:main` (`main`
#    performs: it bakes and applies), and without it `main` is never pushed.
# Up to the commit a failure puts the tree back as HEAD has it (with `patched`, the pin alone), so the
# same command runs again; each refusal says what, if anything, was changed (the tag). A failed record
# leaves the commit unpushed and says how to finish: record, then push.
[doc("Take a release in one box: guard, before-tag, install, sessions, refresh what is safe, init, validate, commit, record, push develop. `patched`: you refreshed the release-owned files by hand; `main`: push develop to main too (main performs)")]
[positional-arguments]
take version *words:
	#!/usr/bin/env bash
	set -euo pipefail
	version="$1"; shift
	[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.dev[0-9]+)?$ ]] || { echo "take: '$version' is not a release version (for example 0.1.6 or 0.1.6.dev2)"; exit 2; }
	patched=no; main=no
	for word in "$@"; do
		case "$word" in
			patched) patched=patched ;;
			main) main=main ;;
			*) echo "take: '$word' is not an argument of take: 'patched' (you refreshed the release-owned files by hand), 'main' (push develop to main at the end), both, or neither"; exit 2 ;;
		esac
	done
	again="just take $version"; [ "$patched" = no ] || again="$again patched"; [ "$main" = no ] || again="$again main"
	after_patch="just take $version patched"; [ "$main" = no ] || after_patch="$after_patch main"
	branch=$(git rev-parse --abbrev-ref HEAD)
	[ "$branch" = develop ] || { echo "take: this checkout is on '$branch'; a release is taken on develop -- nothing was changed"; exit 1; }
	if [ "$patched" = no ]; then
		[ -z "$(git status --porcelain)" ] || { echo "take: the tree must be clean first (commit or discard; after refreshing the release-owned files by hand, say 'patched'):"; git status --short; exit 1; }
	fi
	# the catch-up guard of develop from origin/main, its own first act (missed twice before it was a recipe)
	git fetch -q origin
	# a take that already finished: HEAD pins VERSION, the tree is clean and develop is level with
	# origin/develop, so running it again says so and changes nothing (the before-tag below marks the
	# commit before that take, and would refuse)
	pinned=$(git show HEAD:.csis-version 2>/dev/null | head -1 || true)
	if [ "$pinned" = "$version" ] && [ -z "$(git status --porcelain)" ] \
		&& [ "$(git rev-parse HEAD)" = "$(git rev-parse -q --verify origin/develop || true)" ]; then
		if [ "$main" = main ] && ! git merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
			echo "take: $version is already taken and develop is pushed, but origin/main does not hold it -- nothing was changed; to push it: git push origin develop:main"
			exit 1
		fi
		echo "take: $version is already taken: HEAD pins it and develop is level with origin/develop -- nothing was changed"
		exit 0
	fi
	if git rev-parse -q --verify origin/main >/dev/null; then
		git merge --ff-only origin/main >/dev/null || { echo "take: develop cannot fast-forward to origin/main -- reconcile them first; nothing was changed"; exit 1; }
		git merge-base --is-ancestor origin/main HEAD || { echo "take: origin/main is not an ancestor of develop -- nothing was changed"; exit 1; }
	fi
	# a FINAL version marks the tree as it stood before it: the tag v<version>-before on HEAD, pushed
	# (a development version gets none); a run again finds it on HEAD and goes on
	unchanged="nothing was changed"
	if [[ "$version" != *.dev* ]]; then
		tag="v$version-before"
		if at=$(git rev-parse -q --verify "refs/tags/$tag^{commit}"); then
			[ "$at" = "$(git rev-parse HEAD)" ] || { echo "take: the tag $tag exists and marks $at, not HEAD ($(git rev-parse HEAD)) -- a tree is tagged once, before its take; nothing was changed"; exit 1; }
			echo "take: the tag $tag already marks HEAD"
		else
			git tag -a "$tag" -m "The tree before it took $version"
		fi
		git push -q origin "refs/tags/$tag" || { echo "take: the tag $tag could not be pushed (above); it marks HEAD here, and running again pushes it"; exit 1; }
		unchanged="nothing was changed but the tag $tag on HEAD, pushed (running again finds it)"
	fi
	old=$(git show HEAD:.csis-version 2>/dev/null | head -1 || true)
	# a development release is on TestPyPI only, with PyPI as the extra index
	test_index=(--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --index-strategy unsafe-first-match)
	index=(); [[ "$version" == *.dev* ]] && index=("${test_index[@]}")
	oldindex=(); [[ "$old" == *.dev* ]] && oldindex=("${test_index[@]}")
	# the umbrella with the extras this tree's `type:` words need (`just extras`): a bare install carries no runtime
	extras=$(just extras)
	# always the release from the index, as the uv tool: a committing run is held to exactly that, and
	# every step of the take runs by this binary, whatever CSIS names for the tree's other recipes
	uv tool install --force ${index[@]+"${index[@]}"} "cs-image-system${extras:+[$extras]}==$version" >/dev/null 2>&1 || { echo "take: cs-image-system${extras:+[$extras]}==$version could not be installed from the index (a development release is on TestPyPI, a final one on PyPI) -- $unchanged"; exit 1; }
	tool="$(uv tool dir --bin)/cs-image-system"
	have=$("$tool" --version 2>/dev/null | awk '{print $NF}' || true)
	[ "$have" = "$version" ] || { echo "take: the installed tool $tool reports '${have:-nothing}', not $version -- $unchanged"; exit 1; }
	# the sessions before anything is written: the record needs them, and a lapsed one found after the
	# pin moved is a half-done take; each absent or lapsed session's line names the command that renews it
	CSIS="$tool" just preflight || { echo "take: a runtime session is absent or lapsed, or the sessions could not be read (above, with the command that renews each): log in, then run the same command again: $again -- $unchanged"; exit 1; }
	# what the release changed, one `<class> <path>` line each (a module judged by its stamp): anything
	# `edited` in this tree STOPS the take, named alone; `refresh` and `added` are refreshed below
	refreshed=(); added=()
	if [ "$patched" = no ] && [ -n "$old" ] && [ "$old" != "$version" ]; then
		prev=$(uvx ${oldindex[@]+"${oldindex[@]}"} --from "cs-image-system==$old" python -c 'from cs_image_system.system import starters; print(starters.starters_root())' 2>/dev/null) \
			|| { echo "take: the previous release $old could not be fetched to compare with -- $unchanged"; exit 1; }
		rc=0; listing=$("$tool" init-config . --changes-since "$prev" --porcelain) || rc=$?
		if [ "$rc" -eq 1 ]; then
			echo "take: STOP -- the release changed what this tree also edited:"
			printf '%s\n' "$listing" | sed -n 's/^edited /take:   edited /p'
			echo "take: read the release's version beside yours and refresh by hand (\`$tool init-config . --force\` keeps your values where the release has REPLACE-ME; an edited module is kept by naming it under config: module_sources, or deleted to take the release's), read \`git diff\`, then: $after_patch -- $unchanged"
			exit 1
		elif [ "$rc" -ne 0 ]; then
			echo "take: the release's changes could not be listed against $old (above) -- $unchanged"
			exit 1
		fi
		while read -r class path; do
			case "$class" in
				refresh) refreshed+=("$path") ;;
				added) added+=("$path") ;;
				*) ;;
			esac
		done <<< "$listing"
	fi
	# from here a failure puts the tree back as HEAD has it, so the same command runs again; with `patched`
	# only the pin goes back (from HEAD: a refresh may have moved the tree's copy), the rest is your refresh
	back=""; [ "$patched" = patched ] || back=" and the tree as HEAD has it"
	drop() { rm -f -- "$1"; rmdir -p "$(dirname "$1")" 2>/dev/null || true; }
	putback() {
		if [ "$patched" = no ]; then
			git reset -q
			git checkout -q HEAD -- .
			while IFS= read -r -d '' path; do drop "$path"; done < <(git ls-files -z --others --exclude-standard)
		elif git cat-file -e HEAD:.csis-version 2>/dev/null; then
			git show HEAD:.csis-version > .csis-version
		else
			rm -f .csis-version
		fi
	}
	listed=(${refreshed[@]+"${refreshed[@]}"} ${added[@]+"${added[@]}"})
	if [ -n "${listed[*]+x}" ]; then
		"$tool" init-config . --force >/dev/null || { putback; echo "take: \`init-config . --force\` failed (above); the tree is back as HEAD has it -- $unchanged"; exit 1; }
		# the refresh is of what was listed and nothing else: a file the release did not change keeps the tree's text
		while IFS= read -r -d '' path; do
			keep=no
			for entry in "${listed[@]}"; do
				case "$entry" in
					*/) [[ "$path" == "$entry"* ]] && keep=yes ;;
					*) [ "$path" = "$entry" ] && keep=yes ;;
				esac
			done
			[ "$keep" = no ] || continue
			if git cat-file -e "HEAD:$path" 2>/dev/null; then git checkout -q HEAD -- "$path"; else drop "$path"; fi
		done < <(git ls-files -z --modified --others --exclude-standard)
		for entry in ${refreshed[@]+"${refreshed[@]}"}; do echo "take: refresh $entry"; done
		for entry in ${added[@]+"${added[@]}"}; do echo "take: added $entry"; done
	fi
	# the pin is the release that did all of the above; init and validate run as the tree runs them
	printf '%s\n' "$version" > .csis-version
	for step in init validate; do
		CSIS="$tool" just "$step" || {
			putback
			echo "take: \`just $step\` failed (above); .csis-version is back at ${old:-nothing}$back, so run the same command again: $again -- $unchanged"
			exit 1
		}
	done
	git add -A
	git diff --cached --quiet && { echo "take: nothing changed -- $version is already what this tree pins"; exit 0; }
	# the subject is "Take VERSION" alone; the body names what the take refreshed and added, one line per
	# class ("refreshed: Justfile, .gitignore", "added: CI_SETUP.md"), however many entries there are
	message="Take $version"
	joined() { local out="" entry; for entry in "$@"; do out="${out:+$out, }$entry"; done; printf '%s' "$out"; }
	body=""
	list=$(joined ${refreshed[@]+"${refreshed[@]}"}); [ -z "$list" ] || body="refreshed: $list"
	list=$(joined ${added[@]+"${added[@]}"}); [ -z "$list" ] || body="${body:+$body$'\n'}added: $list"
	body_args=(); [ -z "$body" ] || body_args=(-m "$body")
	git commit -q -m "$message" ${body_args[@]+"${body_args[@]}"} || { putback; echo "take: the commit failed (above); .csis-version is back at ${old:-nothing}$back, so run the same command again: $again -- $unchanged"; exit 1; }
	# the record by the same release (a committing run is held to the pin), so the emission the push
	# carries is the new pin's and CI's drift check finds it current; then ONE push of develop with both
	if ! CSIS="$tool" just record; then
		echo "take: the record failed (above): the commit \"$message\" stands on develop, NOT pushed, and whatever the record wrote is uncommitted. To finish: CSIS=\"$tool\" just record, then git push origin develop$([ "$main" = no ] || echo ', then git push origin develop:main')"
		exit 1
	fi
	git push origin develop || { echo "take: develop could not be pushed (above); the take and its record are committed here -- to finish: git push origin develop$([ "$main" = no ] || echo ', then git push origin develop:main')"; exit 1; }
	echo "take: $version is taken and recorded, and develop is pushed"
	if [ "$main" = main ]; then
		git push origin develop:main || { echo "take: main could not be pushed (above); develop is pushed -- to finish: git push origin develop:main"; exit 1; }
		echo "take: main is pushed: main performs (its CI bakes and applies under the write role)"
	else
		echo "take: main was not pushed; when main should perform: git push origin develop:main (or take with 'main')"
	fi

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
[doc("The record: a dry run of every lifecycle, its emission and meta-state committed here (you push)")]
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
[doc("Gated destroy of ONE instance of the runtime, undeclared for this invocation alone; a dry run keeps the record")]
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
[doc("A durable instance takes its image's next build in one gated sequence: pin, replace, proof, release, names")]
cloud-upgrade runtime instance to="": cloud-preflight
	#!/usr/bin/env bash
	set -euo pipefail
	{{cli}} upgrade instance {{instance}} {{ if to != "" { "--to " + to } else { "" } }}
	just cloud-launch {{runtime}}
	just cloud-verify {{runtime}} {{instance}}
	{{cli}} --locked --no-dry-run run release --only-runtime {{runtime}} --commit
	just cloud-launch {{runtime}}
	# the last run regenerates the instance lifecycle alone, so the release read-model the
	# release run moved reaches the committed emission only with a full record (without one,
	# `live` on main fails on config-drift until a record is made by hand)
	just record
	echo "cloud-upgrade: {{instance}} stands on its released build, recorded; run 'just ci-login-proof {{instance}}' to log in by name"

# End-of-cycle assertion: the runtime holds nothing beyond its declared storages, and the strict state query agrees
cloud-empty runtime:
	@{{cli}} empty --runtime {{runtime}}

# Dispose of every recorded image on the runtime through the recorded path
cloud-dispose-images runtime dry="no":
	@{{cli}} {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} dispose image --runtime {{runtime}} --all --commit

# Re-tag cloud images whose lineage tags disagree with their record, from the record, and give the
# configuration's id (csis_config) to standing storages and machines that lack it. Dry by default.
[doc("Re-tag images from their records and give standing storages and machines the configuration's id; dry by default")]
cloud-relabel runtime dry="yes":
	@{{cli}} {{ if dry == "yes" { "--dry-run" } else { "--no-dry-run" } }} lineage relabel --runtime {{runtime}}

# Log into every standing instance (or the ARGS named) through the managed CI policy: as the workload in a
# GitHub Actions job (`workload token` mints the OPA token from this run's OIDC token, the names from the
# configuration), as YOU (the enrolled client, `sft login` first) anywhere else
[doc("Log into every standing instance (or those named) through the managed CI policy, as the workload in CI or as you")]
ci-login-proof *ARGS:
	#!/usr/bin/env bash
	set -euo pipefail
	if [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
		named=$({{cli}} workload describe)
		if [ "$named" != "[]" ]; then
			OPA_TOKEN=$({{cli}} workload token)
			export OPA_TOKEN
		else
			# no group builder names an OPA workload connection (a posix-only tree):
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
[doc("Present the Actions run's OIDC token to the team's workload connection: is a token issued, does it carry the role")]
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

# The one-time initialisation as terraform, from an interview: the answers go to bootstrap.yaml at the
# root of the tree, generated/bootstrap/ is written from them (and rewritten by every run); applying it is yours
[doc("The one-time initialisation as terraform, from an interview: answers to bootstrap.yaml, generated/bootstrap/ from them")]
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
