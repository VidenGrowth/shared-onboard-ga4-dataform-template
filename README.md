# shared-onboard-ga4-dataform-template

Copies the `template-shared-ga4-dataform` template into a GCP Dataform repository that has **no git remote**, all in one atomic commit (Dataform API `repositories.commit`).

Every name is built from the GA4 export dataset, so all clients follow the same pattern:

| Item | Value |
|---|---|
| Source dataset | `<project>.analytics_<property_id>` |
| Output dataset | `<project>.analytics_processed_data_<property_id>` |
| Dataform repo ID | `ga4_data_processing_<property_id>` |
| Dataform project | Same as the source project |
| Dataform region | `us-central1` (change with `--region`) |
| BigQuery location | `US`, checked against the source dataset's actual location |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) and the [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- Permissions in the target project:
  - Dataform: `roles/dataform.admin`, or a role that grants `dataform.repositories.get`, `dataform.repositories.create` (new repos only) and `dataform.repositories.commit`
  - BigQuery: `bigquery.datasets.get` on the source dataset (for example `roles/bigquery.metadataViewer`)

## Step by step

### 1. Clone both repos

```bash
git clone https://github.com/VidenGrowth/shared-onboard-ga4-dataform-template
git clone https://github.com/VidenGrowth/template-shared-ga4-dataform
```

### 2. Check the template config

The script fills these placeholders in the template's `workflow_settings.yaml`, and stops if any of them is missing:

| Placeholder | Replaced with |
|---|---|
| `<project_id>` | Source project ID |
| `<location>` | BigQuery location (`--bq-location`) |
| `<GA4_DATASCHEMA>` | `analytics_<property_id>` |

The output dataset `analytics_processed_data_<property_id>` is derived by the template from `GA4_DATASCHEMA`.

Other settings are copied as they are in the template. Review them for each client and edit them in the Dataform repo after landing:

| Setting | Template value | Check |
|---|---|---|
| `TIME_ZONE` | `America/Los_Angeles` | Set to the GA4 property time zone |
| `START_DATE` | `""` (full history) | Set a date to limit the first backfill |
| `ADD_RATES` | `"true"` | Needs read access to `videnglobe.utilities.currency_rates` in the same BigQuery location; set `"false"` otherwise |
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
  --region <region> \
  --dry-run
```

Check the names it prints and the list of files.

### 5. Land the template

```bash
uv run land_template.py ../template-shared-ga4-dataform \
  --source <project>.analytics_<property_id> \
  --region <region>
```

The repository is created if it does not exist yet (`--create` is on by default; pass `--no-create` to only update existing repos); otherwise a new commit is added on top. Add `--sync` to also delete repo files that are not in the template.

If the source dataset is not in `US`, the script stops before writing anything and prints the `--bq-location` value to pass.

### 6. Verify

1. In the BigQuery console, go to **Dataform** → `<region>` → `ga4_data_processing_<property_id>`.
2. Open the commit history and confirm there is a commit named *Land template-shared-ga4-dataform …*.
3. Create a development workspace and check that the project compiles.
4. Make sure the Dataform service agent (`service-<project_number>@gcp-sa-dataform.iam.gserviceaccount.com`) has `roles/bigquery.jobUser` and `roles/bigquery.dataEditor`, or set a custom service account on the repo, before scheduling runs.

## Updating a client after template changes

```bash
cd ../template-shared-ga4-dataform && git pull && cd -
uv run land_template.py ../template-shared-ga4-dataform \
  --source <project>.analytics_<property_id> --region <region> --sync
```

This writes one new commit on top of the existing history.

## Options

| Flag | Default | Notes |
|---|---|---|
| `--source` | required | `<project>.analytics_<property_id>` |
| `--region` | `us-central1` | Dataform region |
| `--project` | Source project | Dataform project, if it differs |
| `--bq-location` | `US` | Must match the source dataset |
| `--repo` | `ga4_data_processing_<property_id>` | |
| `--create` / `--no-create` | on | Create the repo if it does not exist |
| `--sync` | off | Delete repo files that are not in the template |
| `--dry-run` | off | Print the plan only |

Files and folders that are never copied: `.git`, `.github`, `node_modules`, `.df-credentials.json`, `.DS_Store`.
