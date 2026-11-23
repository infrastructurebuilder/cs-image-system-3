# Test classification for spec 008 (T004)

**Feature**: [spec.md](spec.md) | **Tasks**: [tasks.md](tasks.md)

Made 2026-11-21 by a read-only search of `tests/`, `packages/*/tests`
(the Okta plugin's own tests excluded, they move whole) and
`tests/cloud_starters`, for `okta`, `sftd` and `opa` as a word. 77 test
files and `tests/harness.py` name Okta; 28 import the plugin. "Through
Okta" means a core behaviour proven with an Okta builder or stub; "the
registry" means a group builder's server registry (`can_query_servers`,
`registered_servers`, `retire_servers_named`), which the POSIX identity
plugin does not keep and the test kit does not stand in for.

## Okta-only: 8 files, 37 tests (move whole to the Okta repository's `tests/instance/`)

| File | Tests | Note |
| --- | --- | --- |
| `tests/test_bootstrap_okta.py` | 10 | the Okta bootstrap section, the app check |
| `tests/test_group_release.py` | 7 | the Okta runner's prune of an unmanaged group; imports helpers from `test_stale_attachments` |
| `tests/test_identity_plan_in_mirror.py` | 2 | the Okta roots' plan in the mirror |
| `tests/test_new_group_gid.py` | 6 | the gid shim's wait and the identity root's dependency |
| `tests/test_workload_access.py` | 4 | the workload policy's reconcile and drift |
| `tests/test_okta_identity_gids.py` | 2 | the engine's gid export through the Okta builder (moved out of the plugin's tests at T009) |
| `tests/test_first_apply.py` | 2 | the Okta prune of stale attachments with no state yet |
| `tests/test_workload_probe.py` | 4 | 3 tests are Okta's; the 4th checks the starters' `opa-workload-probe` recipe and stays |

## Mixed: 31 files, 377 tests

About 58 Okta-specific tests move with the plugin (T020, T036); about 107
prove a core behaviour through Okta and are re-hosted (T035). "Registry"
in the last column means the case needs a group builder that keeps a
server registry.

| File | Tests | Core seam | POSIX can carry it? |
| --- | --- | --- | --- |
| `tests/test_identity_roots.py` | 13 | the dummy template builders (3 tests) | yes, by the dummy plugin; 10 tests are Okta's |
| `tests/test_login_proof.py` | 11 | a login proof a builder offers | 4 yes (`ssh_login`), 2 registry; 5 are Okta's |
| `tests/test_membership_removal.py` | 9 | the gate's sanctioned-removal list (4 tests) | yes, pure functions; 5 are Okta's |
| `tests/test_stale_attachments.py` | 6 | `state-migration backup`'s working directory (1 test) | yes, core; 5 are Okta's |
| `tests/test_state_query_verdicts.py` | 8 | group drift and verdicts (6 tests) | 1 yes (POSIX `query_state`); 2 encode OPA shapes; 2 are Okta's |
| `tests/test_state_query.py` | 16 | group drift (all, through the `world` stub) | yes |
| `tests/test_hostname_claims.py` | 12 | hostname claims (8 tests) | registry; 4 pure |
| `tests/test_provider_aliases.py` | 20 | the alias pass (14 tests) | registry; 5 pure; 1 is Okta's |
| `tests/test_canonical_names.py` | 12 | canonical names and retirement (3 tests) | registry |
| `tests/test_alias_pool.py` | 15 | alias pools (1 test) | registry |
| `tests/test_generations.py` | 15 | generation beside identity (1 test) | registry |
| `tests/test_capabilities.py` | 18 | base prerequisites, activation, launch parameters (4 tests) | activation yes; enrollment needs a declared kind; 1 registry |
| `tests/test_image_tests.py` | 4 | in-bake verification (2 tests) | yes |
| `tests/test_launch_playbook.py` | 6 | enrollment rendering (1 test) | needs a declared enrollment kind, as `packages/engine/tests/test_declared_kinds.py` makes one |
| `tests/test_identity_attributes.py` | 11 | identity attributes (6 tests) | no, POSIX refuses attributes; 3 are Okta's |
| `tests/test_identity_leaves_core.py` | 11 | plugin CLI mounts, the container objection, the alias verdict | CLI yes, the objection's accept half yes, the verdict no; 4 are Okta's |
| `tests/test_posix_identity.py` | 38 | enrollment kinds, POSIX id claims (6 tests) | yes; 14 are Okta's |
| `tests/test_container_runtime.py` | 15 | the identity plugin's container objection | no; 1 is Okta's |
| `tests/test_os_types.py` | 9 | — | 1 is Okta's (it refuses alpine) |
| `tests/test_emit_by_reference.py` | 9 | emission by reference (1 test) | needs another root; 2 are Okta's |
| `tests/test_bootstrap_coverage.py` | 9 | bootstrap sections | by the docker and AWS sections; 1 is Okta's |
| `tests/test_committed_files.py` | 8 | the committed-files rule (sanctioned removals) | no |
| `tests/test_release_whole.py` | 32 | — | 4 are Okta's (the workload token) |
| `tests/test_load_failures.py` | 6 | a plugin's `classify_failure` (1 test) | no |
| `tests/test_groups_and_users_name_their_own_builder.py` | 9 | loader parents by type (2 tests) | yes |
| `tests/test_runner_gating.py` | 10 | gating and state bindings (3 tests) | needs another root |
| `tests/test_state_locations.py` | 12 | an identity root's state location (2 tests) | needs another root |
| `tests/test_state_backends.py` | 10 | backend binding (2 tests) | needs another root |
| `tests/test_storage_state_machine.py` | 17 | gid by remote state (1 test) | no, POSIX gids are literal |
| `tests/test_roots_with_a_state_backend.py` | 3 | root init arguments (3 tests) | needs another root |
| `packages/tofu-roots/tests/test_roots.py` | 3 | the default root name (2 tests) | needs another root |

## Passing mention: 38 files, 342 tests (T037)

The Okta words appear as data, a comment, a starter stub or a listed
name. Six of them assume the plugin is installed here and become false
when it leaves: `tests/test_bootstrap.py`, `tests/test_bootstrap_docker.py`,
`tests/test_module_sources.py`, `tests/test_registration_namespaces.py`,
`tests/test_extras.py` and `tests/test_package_metadata.py`. The rest:
`packages/dummy-plugin/tests/test_dummy_only_identity.py`,
`packages/hashicorp-utils/tests/test_blocks.py`,
`packages/local-state-plugin/tests/test_local_backend.py`,
`packages/posix-identity-plugin/tests/test_posix_accounts.py`,
`tests/cloud_starters/test_complete_starter.py`,
`tests/test_a_load_enters_every_child_under_its_own_key.py`,
`tests/test_aws_parity.py`, `tests/test_bake_steps.py`,
`tests/test_ci_workflow.py` (the Okta triple, which changes with T043),
`tests/test_config_owned_images.py`, `tests/test_config_resolution_e2e.py`,
`tests/test_contract.py`, `tests/test_convergent_bakes.py`,
`tests/test_core_names_no_runtime.py` (its guard regex stays),
`tests/test_decommission.py`, `tests/test_dev_pin_install.py`,
`tests/test_docs_examples.py`, `tests/test_headless_cli.py`,
`tests/test_in_bake_tests_enforce.py`, `tests/test_justfile_contract.py`,
`tests/test_lineage_pins.py`, `tests/test_pins_per_runtime.py`,
`tests/test_posix_containers.py`, `tests/test_post_bake_tests.py`,
`tests/test_registry_index_holds_current_ids_after_a_load.py`,
`tests/test_release_lifecycle.py`, `tests/test_retention.py`,
`tests/test_run_scoping.py`, `tests/test_runtime_facts.py`,
`tests/test_starter_skeleton.py`, `tests/test_starters_by_declaration.py`,
`tests/test_terraform_collector.py`.

## The shared fixture and golden

- **Declare Okta**: `cfg/group-builders.yml` (`oktagroups`,
  `okta-groups-ro`, `okta-tf-users`); `groups/test-group.yaml`,
  `group-tcmet.yaml`, `group-secofs.yaml`, `group-stofs.yaml` (on the
  default `oktagroups` builder), `group-lookup.yaml` (on
  `okta-groups-ro`); `groups/users.yaml` (21 entries, 19 on
  `okta-tf-users`); Okta lines in `cfg/_config.yml`, `os-builders.yml`
  and `runtime-builders.yml`.
- **Images owned by Okta groups**: `imgfile-basic-cloudflow`,
  `imgfile-basic-dask` (coops), `imgfile-basic-cloudflow-two` (tcmet),
  `imgfile-basic-dask-two` (stofs), `imgfile-basic-cloudflow-notdocker`
  (secofs). The instances `test` and `test2` run on them.
- **Golden**: 39 files carry Okta content: the identity roots' 15
  (`oktagroups` 9, `okta-tf-users` 3, `okta-groups-ro` 3) and
  `run-identity.sh`, and 23 more (bakes, instance roots, storage roots
  reading the gid, three meta-state records).
