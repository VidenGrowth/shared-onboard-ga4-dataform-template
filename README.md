# shared-onboard-ga4-dataform-template

Copies the `template-shared-ga4-dataform` template into a GCP Dataform repository that has **no git remote**, all in one atomic commit (Dataform API `repositories.commit`).

Every name is built from the GA4 export dataset, so all clients follow the same pattern:

| Item | Value |
|---|---|
| Source dataset | `<project>.analytics_<property_id>` |
| Output dataset | `<project>.analytics_processed_data_<property_id>` |
| Dataform repo ID | `ga4_data_processing_<property_id>` |
| Dataform project | Same as the source project |
| Dataform repo location | `us-central1` (change with `--repo-location`, see [Dataform locations](https://cloud.google.com/dataform/docs/locations)) |
| BigQuery location | `US`, checked against the source dataset's actual location (see [BigQuery locations](https://cloud.google.com/bigquery/docs/locations)) |

## What the script does

1. Reads the project and property ID from `--source` and builds all names from them.
2. Looks up the source dataset in BigQuery and stops if its location differs from `--bq-location`.
3. Detects your gcloud email and uses it as the commit author. `name.surname@…` becomes `Name Surname`; any other email keeps the part before `@` as is.
4. Reads the template files (skipping `.git`, `.github`, `node_modules`, …) and fills the placeholders in `workflow_settings.yaml`.
5. Prints the plan. With `--dry-run` it stops here, and steps 2–3 are skipped.
6. Checks the Dataform repo and creates it if it is missing (`--create`, on by default). With `--service-account`, sets it as the repo's service account (also on existing repos).
7. With `--sync`, lists the repo files and marks those not in the template for deletion.
8. Writes everything in one commit and prints the commit SHA.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) and the [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- Permissions in the target project:
  - Dataform: `roles/dataform.admin`, or a role that grants `dataform.repositories.get`, `dataform.repositories.create` (new repos only) and `dataform.repositories.commit`
  - BigQuery: `bigquery.datasets.get` on the source dataset (for example `roles/bigquery.metadataViewer`)
- With `--service-account`:
  - You: `roles/iam.serviceAccountUser` on that service account, plus `dataform.repositories.update` for existing repos
  - Dataform service agent (`service-<project_number>@gcp-sa-dataform.iam.gserviceaccount.com`): `roles/iam.serviceAccountTokenCreator` on that service account

## Quickstart

### 1. Clone and sync the repos

Clone this repo, then run `sync_repos.sh` to clone the template next to it:

```bash
git clone https://github.com/VidenGrowth/shared-onboard-ga4-dataform-template
cd shared-onboard-ga4-dataform-template
./sync_repos.sh
```

`sync_repos.sh` keeps both repos (`shared-onboard-ga4-dataform-template` and `template-shared-ga4-dataform`) up to date. Run it again any time to get the latest changes:

- A repo that is missing is cloned. A repo that is already cloned is pulled with `git pull --ff-only`, so it never creates merge commits.
- If a pull fails, for example because of local changes or a branch that differs from `origin`, the script stops and suggests `--force`. The other repo is still synced.
- If a folder with the repo's name exists but is not a git repo, the script stops for that repo and does not touch the folder.

| Flag | Default | Notes |
|---|---|---|
| `--dir <path>` | Parent folder of this repo | Folder to clone into and sync |
| `--force`, `-f` | off | If a pull fails, reset the repo to the `origin` default branch. **This drops local commits, uncommitted changes and untracked files.** Files in `.gitignore` are kept |

### 2. Check the template config

The script fills these placeholders in the template's `workflow_settings.yaml`, and stops if any of them is missing:

| Placeholder | Replaced with |
|---|---|
| `<project_id>` | Source project ID |
| `<location>` | BigQuery location (`--bq-location`) |
| `<GA4_DATASCHEMA>` | `analytics_<property_id>` |

The output dataset `analytics_processed_data_<property_id>` is derived by the template from `GA4_DATASCHEMA`.

Other settings are copied from the template unless a flag sets them. Review them for each client; anything without a flag is edited in the Dataform repo after landing:

| Setting | Template value | Check |
|---|---|---|
| `TIME_ZONE` | `America/Los_Angeles` | Set with `--time-zone` to the GA4 property time zone (GA4 Admin → Property details), using a [time zone name](https://docs.cloud.google.com/looker/docs/reference/param-view-timezone-values) |
| `START_DATE` | `""` (full history) | Set a date to limit the first backfill |
| `ADD_RATES` | `"true"` | Needs read access to `videnglobe.utilities.currency_rates`, which is in `US`. Set with `--add-rates` / `--no-add-rates` |
| `RATES_CURRENCIES` | `"EUR,GBP,CHF"` | Set with `--rates-currencies` |
| `includes/params.json` | Example params (`event_category`, `src`, …) | Replace with the client's custom params |

### 3. Authenticate

```bash
gcloud auth application-default login
```

### 4. Dry-run (no API calls)

```bash
cd shared-onboard-ga4-dataform-template
uv run land_template.py ../template-shared-ga4-dataform \
  --source <project>.analytics_<property_id> \
  --repo-location <repo-location> \
  --time-zone <time-zone> \
  --dry-run
```

Check the names it prints and the list of files.

### 5. Land the template

```bash
uv run land_template.py ../template-shared-ga4-dataform \
  --source <project>.analytics_<property_id> \
  --repo-location <repo-location> \
  --time-zone <time-zone>
```

The repository is created if it does not exist yet (`--create` is on by default; pass `--no-create` to only update existing repos); otherwise a new commit is added on top. Add `--sync` to also delete repo files that are not in the template.

If the source dataset is not in `US`, the script stops before writing anything and prints the `--bq-location` value to pass.

A detailed run that sets every option looks like this:

```bash
uv run land_template.py ../template-shared-ga4-dataform \
  --source <project>.analytics_<property_id> \
  --project <dataform-project> \
  --repo <repo-id> \
  --repo-location <repo-location> \
  --bq-location <bq-location> \
  --service-account <service-account> \
  --time-zone <time-zone> \
  --add-rates \
  --rates-currencies <currencies> \
  --sync
```

| Placeholder | Example |
|---|---|
| `<project>` | `my-client-project` |
| `<property_id>` | `123456789` |
| `<dataform-project>` | `my-client-project` (omit to use the source project) |
| `<repo-id>` | `ga4_data_processing_123456789` (omit to use this default) |
| `<repo-location>` | `us-central1` |
| `<bq-location>` | `US` |
| `<service-account>` | `dataform-runner@my-client-project.iam.gserviceaccount.com` |
| `<time-zone>` | `America/New_York` |
| `<currencies>` | `EUR,GBP` |

The rates table is in `US`, so outside `US` use `--no-add-rates` instead of `--add-rates`. Add `--dry-run` to check the plan before writing.

### 6. Verify

1. In the BigQuery console, go to **Dataform** → `<repo-location>` → `ga4_data_processing_<property_id>`.
2. Open the commit history and confirm there is a commit named *Land template-shared-ga4-dataform …*.
3. Create a development workspace and check that the project compiles.
4. Before scheduling runs, make sure the account that runs workflows has `roles/bigquery.jobUser` and `roles/bigquery.dataEditor`. That is the service account from `--service-account`, or else the Dataform service agent (`service-<project_number>@gcp-sa-dataform.iam.gserviceaccount.com`).

## Updating a client after template changes

```bash
./sync_repos.sh
uv run land_template.py ../template-shared-ga4-dataform \
  --source <project>.analytics_<property_id> --repo-location <repo-location> \
  --time-zone <time-zone> --sync
```

This writes one new commit on top of the existing history.

## Options

| Flag | Default | Notes |
|---|---|---|
| `--source` | required | `<project>.analytics_<property_id>` |
| `--repo-location` | `us-central1` | Dataform region, e.g. `us-central1`, `europe-west1` (not `US`/`EU`) |
| `--project` | Source project | Dataform project, if it differs |
| `--bq-location` | `US` | Must match the source dataset |
| `--repo` | `ga4_data_processing_<property_id>` | |
| `--service-account` | Dataform service agent | Service account email that runs the repo's workflows |
| `--create` / `--no-create` | on | Create the repo if it does not exist |
| `--time-zone` | Template value (`America/Los_Angeles`) | Sets `TIME_ZONE`, e.g. `Europe/Berlin`. [Time zone names](https://docs.cloud.google.com/looker/docs/reference/param-view-timezone-values) |
| `--add-rates` / `--no-add-rates` | Template value (`true`) | Sets `ADD_RATES`. The rates table is in `US`, so use `--no-add-rates` for other locations |
| `--rates-currencies` | Template value (`EUR,GBP,CHF`) | Sets `RATES_CURRENCIES`, e.g. `EUR,GBP` |
| `--sync` | off | Delete repo files that are not in the template |
| `--dry-run` | off | Print the plan only |

Files and folders that are never copied: `.git`, `.github`, `node_modules`, `.df-credentials.json`, `.DS_Store`.
