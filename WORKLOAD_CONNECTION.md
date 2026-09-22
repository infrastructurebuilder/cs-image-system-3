# Workload connection for CI: setup checklist

*Stage 56 step 1. Executed by the operator in the Okta Privileged Access
(OPA) admin console as a security admin. Once the proof has run, this
checklist moves into [docs/OPERATIONS.md](docs/OPERATIONS.md) and this
file is removed.*

## What this builds and why

CI has to prove that the coops policy grants login to `coops-model`, by
logging in the same way a scientist does: `sft ssh`, a short-lived OPA
certificate, no static key. A GitHub-hosted runner cannot use the legacy
ASA service-user route (that needs the runner itself to be an enrolled
`sftd` server). It can use OPA's **workload** route: the runner presents
GitHub's own OIDC token, OPA validates it against a **Workload Connection**,
maps it to a **Workload Role**, and a **Security Policy** names that role
as a principal for the server.

Three objects, in this order. The connection is created as a **draft** and
tested from a workflow before it is activated: a draft validates tokens but
issues no usable access token, so nothing can be reached before a real token
has been seen to pass.

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
| Workload role name | `cs-image-system-ci` | chosen here |
| Policy name | `cs-image-system-ci-login` | chosen here |
| Resource group | `Sandbox_Login` | `OKTA_RESOURCE_GROUP` in `.envrc` |
| Server | `coops-model` (project `coops_rg_login`) | `sft resolve coops-model` |
| OPA address (for the CI step, not the console) | `https://noaa.pam.okta.com` | `sft list-teams` |
| Team (for the CI step) | `nos-coastal-modeling-cloud-sandbox` | `sft list-teams` |

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
      coops policy grants login`.
- [ ] 1.7 **Token TTL**: Amount `1`, Unit `hours`.
- [ ] 1.8 **JWKS URL** tab: if the field is empty, enter
      `https://token.actions.githubusercontent.com/.well-known/jwks`. If the
      GitHub Actions type pre-filled it, leave it exactly as shown.
- [ ] 1.9 **Required Claims**: add ONE claim. Source field name
      `repository`, operator **Equals**, value
      `infrastructurebuilder/cs-image-system-3`. Do **not** add a `ref`
      claim here: branch restriction belongs in the role (step 2), where it
      can be tightened later without touching the trust anchor.
- [ ] 1.10 If the form shows an **Audience** value anywhere, copy it down
      for the hand-back (step 4). GitHub's default audience is
      `https://github.com/infrastructurebuilder`; the CI step must request
      its token with whatever OPA expects.
- [ ] 1.11 Click **Create Workload Connection**. The connection is now a
      **draft**. Do **not** activate it yet.

## 2. Workload Role

Source: [Configure workload roles][wr].

- [ ] 2.1 Go to **Security Administration > Workload roles** and create a
      role.
- [ ] 2.2 **Name**: `cs-image-system-ci`. **Description**: `GitHub Actions
      runs of cs-image-system`.
- [ ] 2.3 Under the requirement, **Select a workload connection**:
      `github-cs-image-system`.
- [ ] 2.4 Click **Filter with additional conditions**. **Source field
      name** `repository`, **Operator** Equals, **Value**
      `infrastructurebuilder/cs-image-system-3`. This repeats the
      connection's claim on purpose: policy reads identity from the role, so
      the role should state who it is on its own.
- [ ] 2.5 Add no other conditions now. (A `ref` Equals `refs/heads/main`
      condition can be added once the proof runs on `main`.)
- [ ] 2.6 Click **Save Workload role**.

## 3. Security Policy

Sources: [Security policy][pol] and [Add rules to a policy][rules].

Recommended: a **new** policy that mirrors the rule granting `coops_user`,
rather than adding the role to the existing coops policy. It proves the
same thing (the rule is the same) and a mistake in it cannot lock a
scientist out. The purist alternative is to add the role as a principal to
the existing policy, which is literally "the same rule" that
[TODO.md](TODO.md) §56 describes. Either is acceptable; say which in the
hand-back. The steps below are for the new policy.

- [ ] 3.1 First open the existing policy that grants `coops_user`. Note its
      resource group, how its server rule selects `coops-model` (by label or
      by name), and its account and permission settings. Steps 3.7 and 3.8
      mirror them.
- [ ] 3.2 Go to **Security Administration > Policies**. Click **Create
      policy**, then select **Default**.
- [ ] 3.3 Name `cs-image-system-ci-login`. Description `CI proof that the
      coops policy grants login`.
- [ ] 3.4 Resource groups: **Specific resource groups**, select
      `Sandbox_Login`.
- [ ] 3.5 **How access is granted**: **Direct principals**.
- [ ] 3.6 **Select Workload roles** dropdown: `cs-image-system-ci`. Add no
      users and no groups.
- [ ] 3.7 Click **Add rule**, type **Server rule**. Select the resource the
      same way the coops policy does: if it uses a label, the same label; if
      by name, `coops-model`.
- [ ] 3.8 Account: **Access resources by individual account**, **User-level
      permissions**. No sudo command bundles, no session recording, no MFA,
      no approval request. The proof runs `id` and `findmnt` and nothing
      else.
- [ ] 3.9 Click **Save policy**. Open the policy and click **Publish**.

The docs do not state which Unix account a workload role lands in under
individual-account access (a workload has no personal account). The first
successful login will show it, and it gets recorded in OPERATIONS.

## 4. Hand-back

- [ ] 4.1 The connection name and role name exactly as saved.
- [ ] 4.2 The audience value, if step 1.10 showed one.
- [ ] 4.3 Whether the policy is new (3.x) or the role was added to the
      existing coops policy.

## 5. What happens next (Claude, not the console)

- [ ] 5.1 A dispatch-only CI step requests GitHub's OIDC token
      (`permissions: id-token: write`, already granted to the live and
      perform jobs) and runs `sft workload authenticate --team
      nos-coastal-modeling-cloud-sandbox --connection github-cs-image-system
      --jwt-env <VAR>` against the **draft**. The command is documented in
      [CLI command for workload authentication][cli].
- [ ] 5.2 When that passes, the operator activates the connection
      (**Workload connections**, the draft, promote to active).
- [ ] 5.3 The `sft ssh coops-model --command 'id && findmnt -n /mnt/data'`
      proof leg lands as `cloud-verify ... sft`, per §56 steps 3 and 4.
- [ ] 5.4 This checklist moves into OPERATIONS and the file is deleted.

[wc]: https://help.okta.com/oie/en-us/content/topics/privileged-access/pam-configure-workload-connection.htm
[wr]: https://help.okta.com/oie/en-us/content/topics/privileged-access/pam-configure-workload-role.htm
[pol]: https://help.okta.com/oie/en-us/content/topics/privileged-access/pam-policy.htm
[rules]: https://help.okta.com/oie/en-us/content/topics/privileged-access/pam-add-rules.htm
[cli]: https://help.okta.com/en-us/content/topics/privileged-access/pam-configure-workload-cli.htm
[gh-disc]: https://token.actions.githubusercontent.com/.well-known/openid-configuration
