# GCP account housekeeping (csis-sandbox)

The operator's standing reference for the GCP account's cost: the fixed
facts, how budget alerts are known to be read, the lookups that attribute
every charge, and the reminders that make the checks happen. The standing
rule behind all of it: the AWS account is not the operator's money, GCP
**is**. Nothing may keep running there beyond the bare minimum, a change
cycle that touches GCP ends by deleting what it created, and a run that
leaves a billable GCP resource standing says so.

## Fixed facts

- Project `csis-sandbox` (number 86233086783), region `us-east1`.
- Billing account **`csis-sandbox-test-billing-account`**, id
  `01C44E-196399-20313D`. The other account on the login,
  `0044EB-274140-3BF82B`, is closed.
- Billing export (standard) to the BigQuery table
  `csis-sandbox.csis_sandbox_billing_export.gcp_billing_export_v1_01C44E_196399_20313D`.
- **There are no credits on this billing account**: no trial, no
  promotion. Every charge is real money against the payment method. The
  only "credits" in the export are Google's automatic 100 % SKU discounts
  on Network Intelligence Center, which exactly cancel the charges they
  are attached to.
- What stands by decision: one released instance image and one base
  image (a few cents a week of image storage each), and the declared
  persistent disk `gce-data`, inside the Always-Free tier. No instance
  runs between cycles.

## Budget alerts, and how they are known to be read

GCP records that an alert was *sent*, never that it was *read*; the check
is on the receiving side.

1. **The mailbox filter.** Budget alerts come from
   `CloudPlatform-noreply@google.com` (display name "Google Cloud Billing
   Alerts"; the envelope sender rotates and is not a usable key). The
   filter matches that From address and stars, marks important and never
   archives, so a threshold mail cannot slide past unread.
2. **Delivery is proven.** The 1 % threshold has fired and been delivered
   to `mykel.alvis@gmail.com` with SPF, DKIM and DMARC passing; nothing on
   the account side needs changing. The Google Chat notification on the
   "csis billing" Monitoring channel is not useful and is ignored; email is
   the path.
3. **Five thresholds, five mails.** The budget "$10 Monthly Budget Alert"
   is a specified amount of **$10 a month** with thresholds on *actual*
   spend at 1 % ($0.10, the "something ran this month" ping), 25 %, 50 %,
   90 % and 100 %; a real overrun produces separate mails. "Email alerts to
   billing admins and users" is the only active recipient path; the
   Monitoring channel is linked; Pub/Sub is not.

The budget compares its thresholds against **net** spend (gross plus
credits), so the Network Intelligence Center discounts never push it toward
a threshold.

Console pages (three, not one):

- Budgets: Billing → the account → **Budgets & alerts**
  (`https://console.cloud.google.com/billing/01C44E-196399-20313D/budgets`);
  a budget's *Actions* step holds the thresholds and **Manage
  notifications**.
- Who receives "billing admins and users": Billing → the account →
  **Account management** → the Permissions panel
  (`https://console.cloud.google.com/billing/01C44E-196399-20313D/manage`).
  Expected: only the monitored mailbox; anyone else listed receives every
  alert.
- Credits: Billing → the account → **Credits**
  (`https://console.cloud.google.com/billing/01C44E-196399-20313D/credits`);
  its CSV is the record. Re-read only if Google announces a credit (it
  arrives by mail to the billing admin).

Neither a budget nor a notification channel has a "send test" button. The
reliable test is to make the budget fire: add a threshold below the month's
current net spend, save, and wait; budgets are evaluated a few times a day
and the mail arrives within hours, once per threshold per month.

## Lookups

### Monthly gross spend and discounts

Run from any shell with `bq` (read-only):

```sh
bq query --project_id=csis-sandbox --use_legacy_sql=false --format=pretty '
SELECT FORMAT_DATE("%Y-%m", DATE(usage_start_time)) AS month,
       ROUND(SUM(cost), 2) AS gross_cost_usd,
       ROUND(SUM((SELECT IFNULL(SUM(c.amount), 0) FROM UNNEST(credits) c)), 2) AS credits_usd,
       STRING_AGG(DISTINCT (SELECT STRING_AGG(DISTINCT c.name) FROM UNNEST(credits) c), ", ") AS credit_names
FROM `csis-sandbox.csis_sandbox_billing_export.gcp_billing_export_v1_01C44E_196399_20313D`
GROUP BY month ORDER BY month'
```

| Column | Meaning |
| --- | --- |
| `gross_cost_usd` | What the month's usage lists at before any credit. Not what the budget watches. |
| `credits_usd` | Everything Google took off; negative is good. Expected: the Network Intelligence Center discounts only. |
| `credit_names` | The credits present. Only "100 % discount for Network Intelligence Center …" strings are expected (their "until 2023" wording is Google's stale label; the discount still applies). A new name such as "Free Trial" would mean a credit appeared. |

Net spend for the month is `gross_cost_usd + credits_usd`; that is the
figure the budget compares against $10.

### What is costing money right now (per SKU, by csis label)

```sh
bq query --project_id=csis-sandbox --use_legacy_sql=false --format=pretty '
SELECT service.description AS service, sku.description AS sku,
       (SELECT value FROM UNNEST(labels) WHERE key = "csis_series") AS csis_series,
       ROUND(SUM(cost), 4) AS cost_usd
FROM `csis-sandbox.csis_sandbox_billing_export.gcp_billing_export_v1_01C44E_196399_20313D`
WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY service, sku, csis_series HAVING cost_usd > 0
ORDER BY cost_usd DESC LIMIT 25'
```

What a line can be:

| SKU | What it is | Expected? |
| --- | --- | --- |
| Licensing Fee for RHEL … | A per-hour RHEL licence: a RHEL-licensed VM is or was running. The images are AlmaLinux, so any RHEL line means an unexpected VM. | No |
| E2 Instance Core / Ram running in Americas | vCPU and RAM hours of instances: a bake, or `gce-test` while it is up. | Only on bake days and while a cycle instance stands |
| Network Intelligence Center — Network Analyzer, Topology & Performance, Internet to Google Cloud Performance | Google meters these for every project with a VPC; each is cancelled by a matching 100 % discount, so its net is $0. Not a csis resource; nothing to delete. | Always, always with a matching credit |
| Storage Image (`csis_series` = an image name) | Storage of a standing image, a few cents a week each. A disposed image stays in the 30-day window but must not grow. | The released instance image and the current base image |
| Storage Image (`csis_series` NULL) | An unlabeled, foreign image: run `state query`. | No |
| Persistent disk | The declared 30 GB `gce-data` disk is inside the Always-Free tier and shows no line; a line means a bigger or foreign disk (a cycle instance's 200 GB boot disk bills about $8 a month while it stands). | No |

The two queries round differently and the second drops lines that net to
zero; use the first for the month's total and the second for attribution.

The weekly acceptance rule: **every line maps to a row in the table above
or to something you launched on purpose this week**. Anything else is an
orphan: find it with `cs-image-system state query`, then
`gcloud compute images list --no-standard-images` and
`gcloud compute disks list`, and dispose of it through the sanctioned
decommission, never by hand.

## Reminders

Each with an alert time; the title is the reminder, the note its body.

| Cadence | Title | Note |
| --- | --- | --- |
| Weekly, Monday 09:00 | csis billing review | Run the per-SKU query. Every line must match the table or something launched on purpose this week; the Network Intelligence Center lines must still net to $0 in the monthly query. `gcloud compute instances list --project csis-sandbox` must be empty unless something is meant to be running. |
| Monthly, 1st | csis budget-alert recipients | The budget is still $10 a month with its thresholds and the admin-email box ticked; the Permissions panel still lists only the monitored mailbox. Run the monthly query for last month's net total and compare it to $10. |
| After every bake day | csis orphan sweep | `cs-image-system state query` must show no foreign images or disks; `gcloud compute images list --no-standard-images` and `disks list` must match the recorded chain. |
| Whenever a GCE instance is launched | csis instance running | Its boot disk bills about $8 a month at 200 GB, plus vCPU and RAM hours, until torn down; tear down when the evidence is captured. |
