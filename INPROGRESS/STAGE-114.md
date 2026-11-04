# 114. Tier C: the run context is a protocol

**Status: OPEN 2026-11-03. Waits for "do 114", after [§113](STAGE-113.md). This is
the commitment to the contract in substance: DESIGN §3P names it the
one stream an undo of §30 would have to reverse.**

Seven plugins and hashicorp-utils import `GlobalTypeContext` (1,588
lines in the kit) and reach it at 61 `_get_context()` sites (32 in
tf-ebs-instance, 9 in tf-gcp, 7 in okta-opa, 5 in tf-docker, 3 each in
docker-runtime and gcloud-runtime, 1 each in aws-runtime and
posix-identity). The surface they touch is about twenty names, read
from the sources on 2026-11-03: `runtime_builders` (17 uses),
`meta_state` (10), `generation_path` (10), `os_builders` (8),
`get_provider_specific_image` (7), `run_id` (5), `mod_builders` (4),
`storage_builders`, `images_map`, `group_builders` (3 each),
`start_time`, `executables` (2 each), `working_path`, `users`,
`user_builders`, `storages`, `root_group`, `read_config`, `instances`,
`extend_finalization_phase` (1 each). Of `meta_state` they use four
members: `storage_state`, `storage_states`, `state_locations`,
`current_generation`. That is the protocol's whole size.

1. `contract.context`: `RunContextProtocol` with exactly those members,
   typed by the contract's own protocols (the builder collections as
   the contract's builder protocols, the provider-specific image as its
   `image` protocol, the paths as `Path`, the executables as the
   contract's executables) and a `MetaStateProtocol` of the four
   members; nothing typed `Any`, nothing named after a kit class. The
   list is re-read from the sources at "do 114" and the protocol holds
   what is used, not what `GlobalTypeContext` has.
2. The kit's `GlobalTypeContext` implements the protocol nominally (it
   lists it as a base, so pyright's override check compares every
   member), `assert_conforms` covers it, and `BuilderBase._get_context`
   returns the protocol type. **YOUR DECISION:** the accessor stays and
   is retyped (the default: the 61 call sites keep their text, the
   plugins change only their 18 imports and annotations from the kit's
   class to the contract's protocol), or the context is injected
   (`bind(ctx)`, DESIGN's phrase) and the sites become a field. The
   default is the smaller diff with the same end: a plugin names no
   kit type for the context.
3. The proof: `contract-example-plugin` gains a builder that reads the
   run context through the protocol alone (its test
   `test_the_sources_import_nothing_from_the_core` keeps holding) and
   is exercised in the dry `run --all` the plugin already runs in.
4. A test that no plugin and not hashicorp-utils names
   `GlobalTypeContext`, beside the direction test.
5. DESIGN §3P: the deferred list loses "the run context's protocol";
   the Reversibility paragraph records that Tier C is landed and the
   soft undo of §30 no longer applies; the plugin author's page in
   OPERATIONS names the protocol. **YOUR DECISION:** this stage is the
   commitment the standing decision speaks of. The standing decision
   says the shims go together with the contract's own repository; both
   are left to [§116](STAGE-116.md)'s last item, and this stage changes neither.

**Out of scope**: the services the plugins import by module ([§115](STAGE-115.md));
the shims; any emission change.

**Acceptance**: code only, emission byte-identical; the four tests
above green; the proof plugin's builder reads the context in the dry
run; the five starters unchanged. One squash, branch kept, bracketed
by tags as [§113](STAGE-113.md). Records: the squash message; this section goes at
"merge 114".
