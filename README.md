# cloud-as-graph

A small demo modeling a GCP project as a graph in Neo4j, so you can ask
questions a flat resource list can't answer: reachability, blast radius,
single point of failure, and a full internet-to-crown-jewels attack path.

Built for the talk **"Your GCP Project Is a Graph: Finding the attack paths a
resource list can't show you."**

## What this is (and isn't)

- The "GCP data" is `data/sample.json`, a hand-authored seed file written in
  the real [Cloud Asset Inventory](https://cloud.google.com/asset-inventory/docs/overview)
  export shape: resource assets (`name` / `assetType` / `resource.data`) plus
  IAM policy bindings — the same shape you'd get from
  `gcloud asset search-all-resources` and `gcloud asset search-all-iam-policies`.
- **This repo never calls the Google Cloud API and never touches a real GCP
  project.** Everything runs locally: Neo4j in Docker, and a Python loader
  that reads the local JSON file. The `gcloud` commands below are
  **documentation only** — they show what you'd run against a real project to
  produce data in the same shape. They are not invoked by anything here.
- No cloud credentials, no `gcloud auth`, no billing.

## Architecture

```
data/sample.json  --(loader/load.py, local bolt connection)-->  Neo4j (Docker, local)
```

## Graph schema

**Node labels:** `Internet`, `Project`, `Subnet`, `Firewall`, `Instance`, `ServiceAccount`, `Bucket`

**Derived semantic edges** (the ones the four demo queries use):

| Edge | From → To | Derived from |
|---|---|---|
| `OPENS_TO` | `Internet` → `Instance` | a firewall rule with `sourceRanges` containing `0.0.0.0/0`, targeting an instance that has an external IP |
| `RUNS_AS` | `Instance` → `ServiceAccount` | the instance's `serviceAccounts[].email` |
| `CAN_IMPERSONATE` | `ServiceAccount` → `ServiceAccount` | an IAM binding granting `roles/iam.serviceAccountTokenCreator` (or `serviceAccountUser`) on SA-B to SA-A |
| `HAS_ACCESS` | `ServiceAccount` → `Bucket` | an IAM binding granting a `roles/storage.*` role on a bucket to an SA |

**Structural context edges** (`IN_SUBNET`, `IN_PROJECT`, `APPLIES_TO`) are also
loaded so the graph looks like real infrastructure in Neo4j Browser, but the
four demo queries don't rely on them.

The full derivation logic lives in `loader/load.py`, commented function by
function.

## Prerequisites

- Docker + Docker Compose (running)
- Python 3.10+
- `jq` (optional, handy for poking at `data/sample.json`)

No `gcloud` install or auth required.

## Quickstart

```bash
cd ~/Desktop/cloud-as-graph
cp .env.example .env
docker compose up -d
python3 -m venv .venv && source .venv/bin/activate
pip install -r loader/requirements.txt
python loader/load.py
```

Then open http://localhost:7474 (user/pass from `.env`) and run the queries
in `queries/`. See `DEMO.md` for the exact on-stage sequence.

## Real GCP export commands (documentation only — never run by this repo)

If you wanted to produce a `resources` + `iam_policies` file like
`data/sample.json` from an actual project, this is what you'd run. These
commands are shown for context in the talk; nothing in this repo executes
them.

```bash
# Resource inventory (assetType + resource.data for every resource in the project)
gcloud asset search-all-resources \
  --scope=projects/PROJECT_ID \
  --format=json > resources.json

# IAM bindings, resource by resource
gcloud asset search-all-iam-policies \
  --scope=projects/PROJECT_ID \
  --format=json > iam_policies.json

# Firewall rules specifically (subset of the above, useful on its own)
gcloud compute firewall-rules list \
  --project=PROJECT_ID \
  --format=json > firewalls.json
```

## Repo layout

```
cloud-as-graph/
  docker-compose.yml    # Neo4j 5 community, ports 7474 + 7687, auth via .env
  .env.example
  data/sample.json      # seed dataset, Cloud Asset Inventory shape
  loader/load.py         # reads sample.json, derives + loads the graph
  loader/requirements.txt
  queries/*.cypher       # the four demo queries
  DEMO.md                # exact stage runbook + fallback
```
