# The team's workload connection: setup checklist

*Stage 56 step 1. Executed by the operator in the Okta Privileged Access
(OPA) admin console as a security admin. Once the proof has run, this
checklist moves into [docs/OPERATIONS.md](docs/OPERATIONS.md) and this
file is removed.*

## What this builds, and what it deliberately does not

CI has to prove that the policy the system manages grants login to the
machines the system launches, by logging in the way a scientist does:
`sft ssh`, a short-lived OPA certificate, no static key. A GitHub-hosted
runner does that through OPA's **workload** route: the runner presents
GitHub's own OIDC token, OPA validates it against a **Workload
Connection**, maps it to a **Workload Role**, and a **Security Policy**
names that role as a principal for the servers.

Only the **connection** is made by hand. It is the trust anchor for
GitHub's token signer, it is scoped to the OPA team, and promoting it from
draft to active is a security-admin act by design. There is one CI, so
there is one connection, and it is a bootstrap object like the OPA API key
pair: created once, named in the live configuration, referenced by the
system from then on.

**Do not create a workload role or a security policy by hand.** Those are
per group, and the system manages them beside the `<group>_user` and
`<group>_admin` policies it already emits: one `<group>_ci` role bound to
this connection and one `<group>_v1_security_policy_ci` policy naming it
(TODO §56 steps 3 and 4). The Terraform provider cannot create them
(okta/oktapam 0.7.1 has no workload resources and accepts only groups as
policy principals), so the system does it through the OPA API, the same
way it retires server registrations.

The connection is created as a **draft** and left there. A draft validates
tokens but issues no usable access token, so nothing can be reached before
a real token from a real workflow run has been seen to pass (step 3).

## Values to enter

Every value below is decided from the repository or read from GitHub's
published discovery document; none is a guess.

| Item | Value | Source |
| --- | --- | --- |
| GitHub Owner | `infrastructurebuilder` | `git remote get-url origin` |
| Repository the claim must match | `infrastructurebuilder/cs-image-system-3` | same |
| JWKS URL | `https://token.actions.githubusercontent.com/.well-known/jwks` | [GitHub OIDC discovery document][gh-disc] |
| Claim name | `repository` | listed under `claims_supported` in the same document |
| Connection name | `github-cs-image-system` | chosen here; URL-friendly |
| Token TTL | 1 hour | the proof leg runs for minutes |
| OPA team | `nos-coastal-modeling-cloud-sandbox` | `sft list-teams`; `team:` on the okta-tf group builder |
| OPA address (for the CI step, not the console) | `https://noaa.pam.okta.com` | `sft list-teams` |

## 1. Workload Connection (draft)

Source: [Configure workload connection][wc]. Field labels below are quoted
from that page.

- [ ] 1.1 In the dashboard go to **DevOps Administration > Workload
      connections**.
- [ ] 1.2 Click **Create Workload Connection**.
- [ ] 1.3 Connection type: **GitHub Actions**.
- [ ] 1.4 **Enter your GitHub Owner**: `infrastructurebuilder`. Click
      **Next**.
- [ ] 1.5 **Connection name**: `github-cs-image-system`.
- [ ] 1.6 **Connection description**: `cs-image-system CI proves that the
      managed policies grant login`.
- [ ] 1.7 **Token TTL**: Amount `1`, Unit `hours`.
- [ ] 1.8 **JWKS URL** tab: if the field is empty, enter
      `https://token.actions.githubusercontent.com/.well-known/jwks`. If the
      GitHub Actions type pre-filled it, leave it exactly as shown.
- [ ] 1.9 **Required Claims**: add ONE claim. Source field name
      `repository`, operator **Equals**, value
      `infrastructurebuilder/cs-image-system-3`. Do **not** add a `ref`
      claim here: branch restriction belongs on the per-group role the
      system manages, where it can be tightened without touching the trust
      anchor.
- [ ] 1.10 If the form shows an **Audience** value anywhere, copy it down
      for the hand-back. GitHub's default audience is
      `https://github.com/infrastructurebuilder`; the CI step must request
      its token with whatever OPA expects.
- [ ] 1.11 Click **Create Workload Connection**. The connection is now a
      **draft**. Do **not** activate it yet.

## 2. Hand-back

- [ ] 2.1 The connection name exactly as saved.
- [ ] 2.2 The audience value, if step 1.10 showed one.

## 3. What happens next

- [ ] 3.1 (Claude) The connection name goes into the live configuration on
      the okta-tf group builder beside `team`, as
      `workload_connection: github-cs-image-system`.
- [ ] 3.2 (Claude) A dispatch-only CI step requests GitHub's OIDC token
      (`permissions: id-token: write`, already granted to the live and
      perform jobs) and runs `sft workload authenticate --team
      nos-coastal-modeling-cloud-sandbox --connection github-cs-image-system
      --jwt-env <VAR>` against the **draft**. The command is documented in
      [CLI command for workload authentication][cli]. The run's log shows
      the token validate.
- [ ] 3.3 (Operator) Activate the connection: **Workload connections**, the
      draft, promote to active. From here the system refuses the proof when
      the named connection is absent or still a draft.
- [ ] 3.4 (Claude) The identity lifecycle learns the per-group role and CI
      policy (TODO §56 steps 3 and 4), then the generic `sft ssh` proof leg
      lands as `cloud-verify ... sft` (steps 5 and 6).
- [ ] 3.5 (Claude) This checklist moves into OPERATIONS and the file is
      deleted.

[wc]: https://help.okta.com/oie/en-us/content/topics/privileged-access/pam-configure-workload-connection.htm
[cli]: https://help.okta.com/en-us/content/topics/privileged-access/pam-configure-workload-cli.htm
[gh-disc]: https://token.actions.githubusercontent.com/.well-known/openid-configuration
