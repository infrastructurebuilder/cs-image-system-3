# 115. The services behind the context

**Status: OPEN 2026-11-03. Waits for "do 115", after [§114](STAGE-114.md). Kept apart
from [§116](STAGE-116.md) (below) on the recommendation of 2026-11-03: this stage is
inside the workspace and its proof is byte-identical emission; [§116](STAGE-116.md)
reaches outside it.**

After [§114](STAGE-114.md) a runtime still imports the engine's knowledge by module,
read from the sources on 2026-11-03: from `lineage` seventeen names
(`owner_of`, `belongs_to_another_configuration`, `config_tags`,
`pinned_instance_build`, `pinned_parent_build`, `record_build`,
`series_of`, `pending_instance_replacements`, `instance_follow_target`,
`ours_or_unlabelled`, `mod_records`, `lineage_tags`,
`configuration_tag`, `bake_disk_size`, `TAG_PREFIX`, `CONFIG_TAG`,
`FINGERPRINT_TAG_LENGTH`; seven plugins); from `launch_params` five
(`compute_launch_params`, `user_data_template`, `detachments`,
`ENROLLMENT_TOKEN_VARIABLE`, `MOUNT_MARK`; four plugins); from
`encryption` four (`emit`, `is_marker`, `decrypt_marker`,
`EncryptedStr`; four); from `bake_steps` two (`execute_command_line`,
`settle_commands`); from `capabilities` two (`image_chain`,
`group_builder_of`); from `materialize` one (`mirror_path`); from
`launch_enrollment` one (`register_enrollment_kind`); from `posix_ids`
one; and the power states (`RUNNING`, `STOPPED`, `STOPPING`,
`STARTING`, `SUSPENDED`, `ABSENT`, `UNKNOWN`, `is_off`, `describe`).
Each has one of three homes.

1. Vocabulary goes to the contract: the tag names and length, the
   enrollment variable, the mount mark, the storage states, the
   cardinalities, the gid policies, the power states (the enum and its
   two helpers), `EncryptedStr` (the type a model declares a secret
   field with). Constants and types only; the shim pattern at the old
   paths.
2. Run-bound services go behind the context, as members of
   `RunContextProtocol` typed by service protocols in `contract.context`:
   `lineage` (the fourteen functions, which read the run's
   configuration id and the lineage records), `launch` (the three
   launch-parameter functions), `secrets` (`emit`, `is_marker`,
   `decrypt_marker`), `files` (`mirror_path`), `commands`
   (`execute_command_line`, `settle_commands`), and
   `register_enrollment_kind`, `image_chain`, `group_builder_of`. The
   kit's `GlobalTypeContext` supplies them from the modules where they
   live today; the modules do not move. **YOUR DECISION:** the grouping
   and the names (the default above), or one flat protocol.
3. The measure, as a test: a plugin's imports from the kit are confined
   to `basic/*` (the base classes), `models/*` (the models it
   subclasses) and the two metadata abstractions; every other kit
   module is reached through the context or not at all. The test
   lists the exceptions it finds, so "do 115" ends when the list is
   empty.
4. The plugin author's page in OPERATIONS says the three homes and
   what a runtime may import.

**Out of scope**: moving the service modules themselves (they stay in
the kit; the engine still calls them directly); the shims; [§116](STAGE-116.md).

**Acceptance**: code only, emission byte-identical; the test of item 3
green with an empty exception list; the proof plugin unchanged (it
already imports nothing from the kit); one squash, branch kept,
bracketed by tags. Records: the squash message; this section goes at
"merge 115".
