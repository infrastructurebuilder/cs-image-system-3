# standard-gce: the smallest GCE configuration

The smallest tree a team writes to get going on the GCE plugin set, in the
shape of a real configuration repository. Copy it, replace every
`REPLACE-ME` value, and it is a configuration:
`just init`, then `just validate`.

What it declares (one of everything):

| Piece | File | Plugin (`type:`) |
| --- | --- | --- |
| the runtime | [`cfg/runtime-builders.yml`](cfg/runtime-builders.yml) | `gcloud` |
| the state backend | [`cfg/state-backends.yml`](cfg/state-backends.yml) | `gcs` (a GCE-only tree needs no AWS account; the file says why the reference deployment chose S3 for its own GCE roots) |
| the base image (OS builder) | [`cfg/os-builders.yml`](cfg/os-builders.yml) | `rhel` |
| the image builder | [`cfg/image-builders.yml`](cfg/image-builders.yml) | `packer-gce` |
| the modification builders | [`cfg/mod-builders.yml`](cfg/mod-builders.yml) | `ansible`, `bash-remote` |
| the instance builder | [`cfg/instance-builders.yml`](cfg/instance-builders.yml) | `tofu-gce` |
| the storage builder | [`cfg/storage-builders.yml`](cfg/storage-builders.yml) | `tf-gcp-pd` |
| the group and user builders | [`cfg/group-builders.yml`](cfg/group-builders.yml) | `okta-tf`, `okta-tf-ro` |
| the tools | [`cfg/executables.yml`](cfg/executables.yml) | |
| the global settings | [`cfg/_config.yml`](cfg/_config.yml) | |
| one group, two users | [`groups/groups.yaml`](groups/groups.yaml), [`groups/users.yaml`](groups/users.yaml) | |
| one storage | [`storages/storages.yaml`](storages/storages.yaml) | |
| one instance image | [`images/images.yaml`](images/images.yaml) | |
| one instance | [`instances/instances.yaml`](instances/instances.yaml) | |
| its playbook and script | [`playbooks/setup-node.yml`](playbooks/setup-node.yml), [`scripts/post-install.sh`](scripts/post-install.sh) | |
| one overlay | [`overlays/launch.yaml`](overlays/launch.yaml) | |

Every file opens with a comment saying what it declares and where
[CONFIGURATION.md](../../CONFIGURATION.md) documents it. Inside the files,
a `REPLACE-ME` value is a placeholder the team must replace (a project, a
subnetwork, a service account, a bucket, a profile, an org); every other
line that could have been written differently carries a `DECISION` comment
saying what was decided and what the alternatives are.

## What is synthetic

- The two users are the frozen fixture's personas (`avery.alpha`,
  `casey.charlie`), encrypted entry by entry as `ENC[age:...]` values to the
  TEST identity committed beside this tree (`.age-identity`, public key
  `.age-recipient`). Export it to load the tree as it stands:
  `CSIS_CONFIG_IDENTITY=<copy>/.age-identity`. Encrypting to a committed
  key protects nothing; replace the recipient in `cfg/_config.yml`, run
  `cs-image-system reencrypt`, and drop the `path:.age-identity` allowance.
- The vendor-image project (`almalinux-cloud`) is a public fact, not a team
  value.

## What travels with the tree

This tree is a whole configuration REPOSITORY, not only the YAML. The
release carries it: `cs-image-system init-config <dir> --from standard-gce`
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
- Application Default Credentials for the project (`gcloud auth
  application-default login`, or `GOOGLE_APPLICATION_CREDENTIALS`): the
  load resolves the project and checks the network and subnetwork.
- A GCS bucket the identity can write, for the `gcs` state backend; no AWS
  account is involved anywhere in this tree.
- The OPA API pair in the environment as `TF_VAR_<team>_key` and
  `TF_VAR_<team>_secret` (`<team>` with non-alphanumerics replaced by `_`):
  the group builder asserts they exist when it loads, not only at apply.
- `CSIS_CONFIG_IDENTITY` pointing at an identity that opens the tree's
  `ENC[age:...]` values.
- `tests/test_docs_examples.py` in the cs-image-system repository loads and
  validates this tree with every cloud and tool stubbed, and holds its
  starter parts to the release's.

The AWS twin is [`../standard-aws/`](../standard-aws/README.md); every field
and variation is in [`../complete/`](../complete/README.md).
