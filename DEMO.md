# DEMO.md — stage runbook

Goal: cold start to first query result in under two minutes, zero network
dependency once Docker images are pulled (pull them ahead of time — see
"Before you go on stage").

## Before you go on stage

- [ ] `docker compose pull` once, ahead of time, so the image is cached locally.
- [ ] `python3 -m venv .venv && source .venv/bin/activate && pip install -r loader/requirements.txt` once, ahead of time.
- [ ] Confirm Docker Desktop is running.
- [ ] Confirm `.env` exists (`cp .env.example .env` if not).
- [ ] Do a full dry run of everything below at least once before the talk.
- [ ] Capture the fallback screenshots (see bottom of this file) in case live demo has to be skipped.

## Exact command sequence

```bash
cd ~/Desktop/cloud-as-graph

# 1. Bring up Neo4j (local Docker only — no cloud calls)
docker compose up -d

# 2. Wait for it to be healthy (usually a few seconds)
docker compose ps

# 3. Load the graph (idempotent — safe to re-run if you fumble a step)
source .venv/bin/activate
python loader/load.py
```

Expected loader output — this is your on-stage confirmation the graph built correctly:

```
--- Node counts ---
  Bucket         3
  Firewall       2
  Instance       4
  Internet       1
  Project        1
  ServiceAccount 3
  Subnet         2
--- Edge counts ---
  APPLIES_TO     4
  CAN_IMPERSONATE 1
  HAS_ACCESS     2
  IN_PROJECT     2
  IN_SUBNET      4
  OPENS_TO       1
  RUNS_AS        4
```

## Neo4j Browser setup (do this once, before the audience is watching)

Open http://localhost:7474, log in with the credentials from `.env`.

1. **Font size**: gear icon (bottom left) → increase editor + result font size
   for projector legibility. 20pt+ recommended.
2. **Node captions**: for each label, click the colored legend dot in a result
   view → set caption to the `name` property. Every node in this graph has a
   short, readable `name` (e.g. `vm-bastion`, `sa-default`, `bucket-crownjewels`).
3. **Colors per label** (suggested, high contrast on a dark projector theme):
   - `Internet` — red
   - `Instance` — blue
   - `ServiceAccount` — orange
   - `Bucket` — purple (and consider a distinct shade/border for `sensitive: true`)
   - `Firewall`, `Subnet`, `Project` — muted gray (context nodes, keep them visually quiet)
4. **Cap returned nodes**: keep default row limit (25) or add `LIMIT` in a
   query if you fear a hairball — with only ~16 nodes total this shouldn't
   bite, but the settings panel also has a "initial node display" cap you can
   lower defensively.
5. Run each `.cypher` file's query once now, before going live, so query plans
   are warm and you've seen the layout — then rearrange nodes by hand into a
   clean layout and leave the tab open.

## The four queries, in order

Run these from `queries/`, either pasted into Neo4j Browser or via `cat`:

```bash
cat queries/01_reachability.cypher
cat queries/02_blast_radius.cypher
cat queries/03_single_point_of_failure.cypher
cat queries/04_full_path.cypher
```

1. **`01_reachability.cypher`** — "Here's everything the public bastion VM can
   reach, transitively." Talking point: a resource list shows you the VM and
   the bucket as two unrelated rows; the graph shows the walk between them.
2. **`02_blast_radius.cypher`** — "If this one VM's service account were
   compromised, here's the full downstream blast radius." Returns `sa-deployer`
   at 1 hop, `bucket-crownjewels` at 2 hops.
3. **`03_single_point_of_failure.cypher`** — "Which service account, if
   compromised, hurts the most?" `sa-default` comes out on top — it's not on
   the crown-jewels path at all, but three separate VMs run as it. This is
   the "resource list can't show you this" moment: nothing in a flat asset
   inventory ranks blast radius by graph degree.
4. **`04_full_path.cypher`** — the closing slide. One `shortestPath` call,
   one path, Internet → `vm-bastion` → `sa-bastion` → `sa-deployer` →
   `bucket-crownjewels`.

## Fallback: if live demo has to be skipped

Capture these stills ahead of time (Neo4j Browser, full graph visible, colors
+ captions set as above):

1. Full graph overview (all ~16 nodes, structural + semantic edges visible) —
   sets the scene: "this is one small project."
2. Result of `01_reachability.cypher` — the reachability fan-out from `vm-bastion`.
3. Result of `02_blast_radius.cypher` — table view showing the two affected resources.
4. Result of `03_single_point_of_failure.cypher` — table view with `sa-default` on top.
5. Result of `04_full_path.cypher` — the single highlighted path, Internet to bucket.

Store these under a `screenshots/` folder (not committed by default — add it
locally) so you can drop into slides if Docker, wifi, or the demo gods fail
you on stage.

## Troubleshooting

- **`docker compose up -d` hangs / container unhealthy**: `docker compose logs neo4j`.
  Most common cause: a previous Neo4j container/volume with different auth.
  `docker compose down -v` then `up -d` again (this wipes only the local demo
  volume — no cloud impact).
- **Loader can't connect**: confirm `.env` matches what's in `docker-compose.yml`
  and that port 7687 isn't in use by another local Neo4j instance.
- **Query returns nothing**: re-run `python loader/load.py` — it's idempotent,
  safe to run again — and check the printed summary counts match the table above.
