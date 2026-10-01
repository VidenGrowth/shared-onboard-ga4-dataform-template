#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth[requests]>=2.30"]
# ///
"""Land a Dataform template into a GCP Dataform repo that has NO git remote.

Everything is derived from the GA4 export dataset, so names stay consistent:

  source   <project>.analytics_<property_id>
  output   <project>.analytics_processed_data_<property_id>
  repo     ga4_data_processing_<property_id>
  bq loc   US by default, verified against the source dataset

Creates the repo if missing, then uses repositories.commit – one atomic commit,
no workspace, no remote.
Placeholders replaced in every text file (the template's workflow_settings.yaml):
  <project_id> <location> <GA4_DATASCHEMA>
The output dataset is derived by the template itself (includes/constants.js).

  uv run land_template.py ./template-shared-ga4-dataform \
      --source <project>.analytics_<property_id> --region <region>
      # add --bq-location <loc> if the source is not in US
"""
from __future__ import annotations

import argparse
import base64
import pathlib
import re
import sys

import google.auth
from google.auth.transport.requests import AuthorizedSession

DATAFORM = "https://dataform.googleapis.com/v1"
BIGQUERY = "https://bigquery.googleapis.com/bigquery/v2"
SKIP = {".git", ".github", "node_modules", ".df-credentials.json", ".DS_Store"}
AUTHOR_NAME = "template-lander"
SOURCE_RE = re.compile(r"^(?P<project>[a-z][a-z0-9-]{4,28}[a-z0-9])\.analytics_(?P<pid>\d+)$")


def collect(root: pathlib.Path, subs: dict[str, str]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    found: set[str] = set()
    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root)
        if not f.is_file() or SKIP & set(rel.parts):
            continue
        data = f.read_bytes()
        try:
            text = data.decode()
        except UnicodeDecodeError:  # binary – copy as is
            files[rel.as_posix()] = data
            continue
        for k, v in subs.items():
            if k in text:
                found.add(k)
                text = text.replace(k, v)
        files[rel.as_posix()] = text.encode()
    if missing := sorted(subs.keys() - found):
        sys.exit(f"placeholders not found in template: {' '.join(missing)}")
    return files


def repo_files(s: AuthorizedSession, repo: str, path: str = "") -> list[str]:
    out, token = [], ""
    while True:
        r = s.get(f"{DATAFORM}/{repo}:queryDirectoryContents", params={"path": path, "pageToken": token})
        if r.status_code in (400, 404) and not path:  # empty repo, no commits yet
            return []
        r.raise_for_status()
        body = r.json()
        for e in body.get("directoryEntries", []):
            out += [e["file"]] if "file" in e else repo_files(s, repo, e["directory"])
        token = body.get("nextPageToken", "")
        if not token:
            return out


def dataset_location(s: AuthorizedSession, project: str, dataset: str) -> str:
    r = s.get(f"{BIGQUERY}/projects/{project}/datasets/{dataset}")
    if not r.ok:
        sys.exit(f"cannot read {project}.{dataset}: {r.status_code} {r.text}")
    return r.json()["location"]


def caller_email(s: AuthorizedSession, creds) -> str:
    """Service-account email, or the user's email from the ADC token."""
    if email := getattr(creds, "service_account_email", None):
        if email != "default":
            return email
    r = s.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": creds.token})
    if r.ok and (email := r.json().get("email")):
        return email
    sys.exit("cannot detect your email from the gcloud credentials")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("template_dir", type=pathlib.Path)
    p.add_argument("--source", required=True, help="GA4 export, <project>.analytics_<property_id>")
    p.add_argument("--region", default="us-central1", help="Dataform region")
    p.add_argument("--project", help="Dataform project (default: source project)")
    p.add_argument("--bq-location", default="US", help="BigQuery location (checked against source)")
    p.add_argument("--repo", help="default: ga4_data_processing_<property_id>")
    p.add_argument("--service-account", help="SA email that runs workflows (default: Dataform service agent)")
    p.add_argument("--create", action=argparse.BooleanOptionalAction, default=True,
                   help="create repo if missing (default: on)")
    p.add_argument("--sync", action="store_true", help="delete files absent in template")
    p.add_argument("--dry-run", action="store_true", help="print plan, no API calls")
    a = p.parse_args()

    m = SOURCE_RE.match(a.source)
    if not m:
        sys.exit(f"--source must look like <project>.analytics_<property_id>, got {a.source!r}")
    data_project, pid = m["project"], m["pid"]
    ga4_dataset = f"analytics_{pid}"
    output_dataset = f"analytics_processed_data_{pid}"
    repo_id = a.repo or f"ga4_data_processing_{pid}"
    df_project = a.project or data_project
    parent = f"projects/{df_project}/locations/{a.region}"
    repo = f"{parent}/repositories/{repo_id}"

    s, author_email = None, "<your gcloud identity>"
    if not a.dry_run:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        s = AuthorizedSession(creds)
        src_location = dataset_location(s, data_project, ga4_dataset)
        if src_location.upper() != a.bq_location.upper():
            sys.exit(f"source is in {src_location}, --bq-location is {a.bq_location}: "
                     f"pass --bq-location {src_location}")
        author_email = caller_email(s, creds)

    subs = {
        "<project_id>": data_project,
        "<location>": a.bq_location,
        "<GA4_DATASCHEMA>": ga4_dataset,
    }
    files = collect(a.template_dir, subs)

    print(f"source  {data_project}.{ga4_dataset}  ({a.bq_location})")
    print(f"output  {data_project}.{output_dataset}")
    print(f"repo    {repo}")
    print(f"author  {AUTHOR_NAME} <{author_email}>")
    print(f"sa      {a.service_account or '<Dataform service agent>'}")
    print(f"files   {len(files)}")
    if a.dry_run:
        print("\n".join(f"  {f}" for f in files))
        return

    r = s.get(f"{DATAFORM}/{repo}")
    if r.status_code == 404 and a.create:
        body = {"setAuthenticatedUserAdmin": True}
        if a.service_account:
            body["serviceAccount"] = a.service_account
        r = s.post(f"{DATAFORM}/{parent}/repositories", params={"repositoryId": repo_id}, json=body)
        if not r.ok:
            sys.exit(f"create failed: {r.status_code} {r.text}")
        print(f"created {repo}")
    elif r.status_code == 404:
        sys.exit(f"{repo} does not exist; drop --no-create to create it")
    elif not r.ok:
        sys.exit(f"cannot read repo: {r.status_code} {r.text}")
    elif a.service_account and r.json().get("serviceAccount") != a.service_account:
        r = s.patch(f"{DATAFORM}/{repo}", params={"updateMask": "serviceAccount"},
                    json={"serviceAccount": a.service_account})
        if not r.ok:
            sys.exit(f"cannot set service account: {r.status_code} {r.text}")
        print(f"service account set to {a.service_account}")

    ops = {path: {"writeFile": {"contents": base64.b64encode(data).decode()}}
           for path, data in files.items()}
    if a.sync:
        ops |= {f: {"deleteFile": {}} for f in repo_files(s, repo) if f not in files}

    r = s.post(f"{DATAFORM}/{repo}:commit", json={
        "commitMetadata": {
            "author": {"name": AUTHOR_NAME, "emailAddress": author_email},
            "commitMessage": f"Land template-shared-ga4-dataform for {data_project}.{ga4_dataset}",
        },
        "fileOperations": ops,
    })
    if not r.ok:
        sys.exit(f"commit failed: {r.status_code} {r.text}")
    print(f"committed {len(ops)} file ops: {r.json().get('commitSha', '')}")


if __name__ == "__main__":
    main()
