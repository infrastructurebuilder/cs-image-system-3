# complete: every plugin, every field, every variation

A configuration root in the shape of a real one that exercises everything
[CONFIGURATION.md](../../CONFIGURATION.md) documents: every plugin the
workspace ships, every field of every model, and every variation the
system distinguishes. It started as a copy of the frozen fixture
(`tests/fixtures/config`) and was extended; it loads and validates with
every cloud and tool stubbed (`tests/test_docs_examples.py` proves it on
every run of the suite). It is a reference to read and copy pieces from,
not a tree to run as it stands: the `REPLACE-ME` values are placeholders,
the people are synthetic, and the two hand-written meta-state files exist
only to make two declarations legal.

Every file opens with a comment saying what it declares and where the
manual documents it, and every field carries a comment giving its meaning
(the manual's section number is beside it where it helps).

## What it declares

| Kind | Count | Where | Plugins (`type:`) |
| --- | --- | --- | --- |
| runtimes | 3 | [`cfg/runtime-builders.yml`](cfg/runtime-builders.yml) | `aws` (a default region and a second one), `gcloud` (ephemeral) |
| state backends | 4 | [`cfg/state-backends.yml`](cfg/state-backends.yml), [`-2`](cfg/state-backends-2.yml), [`-3`](cfg/state-backends-3.yml), [`state-gcs.yml`](cfg/state-gcs.yml) | `s3` (two buckets), `local` (the identity roots), `gcs` (declared, bound to nothing) |
| executables | 10 | [`cfg/executables.yml`](cfg/executables.yml) | checkers by name and by type |
| OS builders (base images) | 3 | [`cfg/os-builders.yml`](cfg/os-builders.yml) | `rhel` (on three runtimes, one from a fixed image id), `debian`, `ubuntu` |
| image builders | 3 | [`cfg/image-builders.yml`](cfg/image-builders.yml) | `packer-ebs` (two regions), `packer-gce` |
| modification builders | 2 | [`cfg/mod-builders.yml`](cfg/mod-builders.yml) | `ansible`, `bash-remote` |
| instance builders | 3 | [`cfg/instance-builders.yml`](cfg/instance-builders.yml) | `tofu` (two regions), `tofu-gce` |
| storage builders | 6 | [`cfg/storage-builders.yml`](cfg/storage-builders.yml) | `tf-aws-ebs`, `tf-aws-efs`, `tf-aws-s3`, `tf-gcp-pd`, `tf-gcp-filestore`, `tf-gcp-gcs` |
| group and user builders | 1 + 2 | [`cfg/group-builders.yml`](cfg/group-builders.yml) | `okta-tf` (with the workload connection and role, an encrypted key pair), `okta-tf-ro` (default, read-only), `okta-tf` (a managed user builder) |
| users | 20 | [`groups/users.yaml`](groups/users.yaml) | nineteen encrypted personas, one managed user with every profile field |
| groups | 6 | [`groups/`](groups/) | the root group, four team groups (`in_both`, `gid`, `attributes`, `include_root_group_in_admins`), one `unmanaged` |
| storages | 9 | [`storages/storages-aws.yaml`](storages/storages-aws.yaml), [`storages-gce.yaml`](storages/storages-gce.yaml) | every kind; `active`, `archived` and `destroyed`; EFS and S3 lifecycles; an adopted filesystem; a public bucket |
| images | 5 | [`images/images-coops.yaml`](images/images-coops.yaml), [`images-other-groups.yaml`](images/images-other-groups.yaml) | `parent_policy` follow and pinned, retention and release intent, post-bake tests, an image chained from an image, a fixed `image_identifier`, ensure and script modifications |
| instances | 5 | [`instances/instances.yaml`](instances/instances.yaml) | durable pinned, durable `image_policy: follow`, ephemeral with `on_failure`/`teardown_after`, the second region, GCE |
| overlays | 5 | [`overlays/`](overlays/README.md) | config-only, a transient instance, the `undeclare` form, updated storages |
| meta-state | 2 | [`meta-state/`](meta-state/README.md) | the alias pool (`aliases.txt`) and a synthetic storage-state record |
| playbooks and scripts | 4 | [`playbooks/`](playbooks/), [`scripts/`](scripts/) | the fixture's modification files |

Global settings, every key the code reads, are in
[`cfg/_config.yml`](cfg/_config.yml) (`require_released_builds`,
`require_image_tests`, `require_mod_tests`, `apply_release`,
`preflight.expected_run_minutes`, an encrypted admin key).
[`base_images/`](base_images/README.md) is present because a real root has
it, and inert because the loader does not read it.

## Encrypted and clear

Any value may be an `ENC[age:...]` marker (section 13). Here the admin
public key, the address domain, the OPA API key pair, every persona's name
and every explicit address are markers; first and last names, the managed
user, and every placeholder are in clear. All markers are encrypted to the
TEST recipient whose identity is committed as `.age-identity`; export
`CSIS_CONFIG_IDENTITY=<copy>/.age-identity` to load the tree, and the
suite does the same. Replacing the recipient and running
`cs-image-system reencrypt` moves every marker to real holders.

## Where the manual and the loader disagree

Building this tree showed a few places the reference manual and the code
part ways; each is worked around here and commented at the spot:

- an `okta-tf` builder whose `key`/`secret` are left at default asserts
  that `TF_VAR_<team>_key` / `_secret` exist **at load**, not only at
  finalize (this tree gives literal encrypted values instead);
- `update:` on an OS builder must be a mapping; a bare policy name is
  refused ([`cfg/os-builders.yml`](cfg/os-builders.yml), `ubuntu-24`);
- the `s3` backend's `assume_role`, `assume_role_with_web_identity` and
  `endpoints` mappings each need a `name`, and the web-identity form has no
  `role_arn`/`duration`/`policy`/`session_name`
  ([`cfg/state-backends.yml`](cfg/state-backends.yml));
- the availability-zone check reads a storage's own `runtime` field, not its
  builder's runtime, so a zonal GCE storage that declares a zone names its
  runtime ([`storages/storages-gce.yaml`](storages/storages-gce.yaml));
- a bash-remote builder's `execute_command` cannot carry packer's own
  `{{ .Path }}`: every string under `cfg/` is rendered with Jinja
  ([`cfg/mod-builders.yml`](cfg/mod-builders.yml)).

The smallest trees are [`../standard-aws/`](../standard-aws/README.md) and
[`../standard-gce/`](../standard-gce/README.md).

## What travels with the tree

This tree is a whole configuration REPOSITORY, not only the YAML. The
release carries it: `cs-image-system init-config <dir> --from complete`
writes it out, and every part a team needs is then there:

| Part | What it is |
| --- | --- |
| `Justfile` | the single entry point: the five contract targets (`init`, `build`, `test`, `full-test`, `release`) and every daily and cycle recipe, each wrapping the released `cs-image-system` command against this tree |
| `.github/workflows/ci.yml` | the repository's own CI: `verify` (no secrets), `live` (read-only against the clouds), `perform` (on `main`, under the write role, records pushed back); every `REPLACE-ME` in it is a team value |
| `.githooks/pre-commit` | the public-safe gate on every commit; `just init` installs it |
| `tfmodules/` | the terraform modules the emitted roots call, at `module_source_base: tfmodules`; the release's, byte for byte (`cs-image-system init-config` writes them, and refreshes them after an upgrade) |
| `scripts/` | the tree's own modification scripts; the recipes need no helper (one tofu process at a time, the CI login token and the emission normaliser are commands of the CLI since stage 64) |
| `.gitignore` | the shell's exports, every credential file, the private mirror, tool residue; `generated/` and `meta-state/` ARE committed |
| `.csis-version` | the release that wrote the tree, which CI installs; `init-config` writes it (absent in this source copy) |

The system itself is installed from a release, never cloned beside the
tree: `uv tool install cs-image-system` puts the command on `PATH`, or a
`pyproject.toml` here that depends on it and `export CSIS="uv run
cs-image-system"`. [DAILY_DRIVER.md](../../../DAILY_DRIVER.md) is the
narrative, from the first command on.

## Before the first run

- The released system: `uv tool install cs-image-system`, then `just init`.
- Sessions for every runtime it declares (two AWS profiles and a GCP
  project), the OPA API pair as `TF_VAR_<team>_key` / `TF_VAR_<team>_secret`,
  and `CSIS_CONFIG_IDENTITY` for its `ENC[age:...]` values. It is a
  catalogue of every field and variation, loadable as it stands; a team
  starts from a standard tree and looks things up here.

The standard trees are [`../standard-aws/`](../standard-aws/README.md) and
[`../standard-gce/`](../standard-gce/README.md).
