# Contract: the Okta plugin's repository

**Feature**: [spec.md](../spec.md) | **Decisions**: [research.md](../research.md)

The repository keeps the contract of the Google Cloud family's
([specs/005-relocate-gcp-provider/contracts/family-repository.md](../../005-relocate-gcp-provider/contracts/family-repository.md)):
the five lifecycle targets, ranges on the SDK, the strict session, CI on
every push, the release that refuses a version the index ever held.
What differs:

| Item | The Okta plugin's |
| --- | --- |
| Repository | `infrastructurebuilder/cs-image-system-okta`, work on `develop` |
| Distribution | `cs-image-system-okta-opa-plugin` (one) |
| Entry points | group `okta_opa_plugin`; bootstrap `okta`; commands `okta_opa_plugin` (`workload`, `verify login`); modules |
| `just test` | lint, type check, surface check, `packages/okta-opa-plugin/tests`, `tests/instance` (the last with the AWS family from the index) |
| Live tests | none applied; a read-only lookup against the OPA team only by dispatch, with the Okta triple as secrets, never echoed |
| An operator types | `uv tool install 'cs-image-system[okta]'` (with the extras of the tree's runtimes) |
