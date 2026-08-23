#!/usr/bin/env python3
"""
Loads data/sample.json (Cloud Asset Inventory-shaped seed data) into Neo4j and
derives the attack-path graph from it. This script only ever reads a local
JSON file and talks to the local Neo4j container over bolt — it never calls
any Google Cloud API. Safe to re-run: every write uses MERGE.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "changeme-demo-pw")

# CAI assetType -> Neo4j node label. "Internet" has no assetType; it's a
# synthetic node we add ourselves to represent the public internet.
ASSET_TYPE_LABELS = {
    "cloudresourcemanager.googleapis.com/Project": "Project",
    "compute.googleapis.com/Subnetwork": "Subnet",
    "compute.googleapis.com/Firewall": "Firewall",
    "compute.googleapis.com/Instance": "Instance",
    "iam.googleapis.com/ServiceAccount": "ServiceAccount",
    "storage.googleapis.com/Bucket": "Bucket",
}
IMPERSONATION_ROLES = {"roles/iam.serviceAccountTokenCreator", "roles/iam.serviceAccountUser"}


def short_name(data, asset_type):
    """Short id used as the node's `name` (also the Browser caption). SAs are
    keyed by email since that's what IAM bindings and instance configs use."""
    return data["email"] if asset_type == "iam.googleapis.com/ServiceAccount" else data["name"]


def create_constraints(session):
    for label in list(ASSET_TYPE_LABELS.values()) + ["Internet"]:
        session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.name IS UNIQUE")


def create_nodes(tx, resources):
    for asset in resources:
        label = ASSET_TYPE_LABELS[asset["assetType"]]
        data = asset["resource"]["data"]
        name = short_name(data, asset["assetType"])
        sensitive = label == "Bucket" and data.get("labels", {}).get("sensitive") == "true"
        tx.run(
            f"MERGE (n:{label} {{name: $name}}) "
            "SET n.fullResourceName = $full, n.sensitive = $sensitive",
            name=name, full=asset["name"], sensitive=sensitive,
        )
    tx.run("MERGE (:Internet {name: 'internet'})")


def create_structural_context(tx, resources):
    """IN_SUBNET / IN_PROJECT / APPLIES_TO: raw topology, kept for a legible
    graph on screen. NOT used by any of the four attack-path queries."""
    instances = [a for a in resources if a["assetType"] == "compute.googleapis.com/Instance"]
    subnets = [a for a in resources if a["assetType"] == "compute.googleapis.com/Subnetwork"]
    firewalls = [a for a in resources if a["assetType"] == "compute.googleapis.com/Firewall"]

    for inst in instances:
        data = inst["resource"]["data"]
        for nic in data.get("networkInterfaces", []):
            subnet_name = nic["subnetwork"].split("/")[-1]
            tx.run(
                "MATCH (i:Instance {name:$i}), (s:Subnet {name:$s}) MERGE (i)-[:IN_SUBNET]->(s)",
                i=data["name"], s=subnet_name,
            )
    for subnet in subnets:
        tx.run(
            "MATCH (s:Subnet {name:$s}), (p:Project) MERGE (s)-[:IN_PROJECT]->(p)",
            s=subnet["resource"]["data"]["name"],
        )
    for fw in firewalls:
        fdata = fw["resource"]["data"]
        tags = set(fdata.get("targetTags", []))
        for inst in instances:
            idata = inst["resource"]["data"]
            if tags & set(idata.get("tags", {}).get("items", [])):
                tx.run(
                    "MATCH (f:Firewall {name:$f}), (i:Instance {name:$i}) MERGE (f)-[:APPLIES_TO]->(i)",
                    f=fdata["name"], i=idata["name"],
                )


def derive_opens_to(tx, resources):
    """Internet -[:OPENS_TO]-> Instance: a firewall rule allows ingress from
    0.0.0.0/0, targets this instance's tag, and the instance has an
    accessConfig (i.e. an external/public IP)."""
    instances = [a for a in resources if a["assetType"] == "compute.googleapis.com/Instance"]
    firewalls = [a for a in resources if a["assetType"] == "compute.googleapis.com/Firewall"]
    for fw in firewalls:
        fdata = fw["resource"]["data"]
        if fdata.get("direction") != "INGRESS" or "0.0.0.0/0" not in fdata.get("sourceRanges", []):
            continue
        tags = set(fdata.get("targetTags", []))
        for inst in instances:
            idata = inst["resource"]["data"]
            is_public = any(nic.get("accessConfigs") for nic in idata.get("networkInterfaces", []))
            if (tags & set(idata.get("tags", {}).get("items", []))) and is_public:
                tx.run(
                    "MATCH (net:Internet {name:'internet'}), (i:Instance {name:$i}) "
                    "MERGE (net)-[:OPENS_TO]->(i)",
                    i=idata["name"],
                )


def derive_runs_as(tx, resources):
    """Instance -[:RUNS_AS]-> ServiceAccount, from instance.serviceAccounts[].email."""
    for inst in resources:
        if inst["assetType"] != "compute.googleapis.com/Instance":
            continue
        data = inst["resource"]["data"]
        for sa in data.get("serviceAccounts", []):
            tx.run(
                "MATCH (i:Instance {name:$i}), (sa:ServiceAccount {name:$e}) MERGE (i)-[:RUNS_AS]->(sa)",
                i=data["name"], e=sa["email"],
            )


def derive_iam_edges(tx, iam_policies):
    """
    CAN_IMPERSONATE: SA-A -[:CAN_IMPERSONATE]-> SA-B, from a binding on SA-B
      granting roles/iam.serviceAccountTokenCreator (or serviceAccountUser) to SA-A.
    HAS_ACCESS: SA -[:HAS_ACCESS]-> Bucket, from a binding on a Bucket
      granting any roles/storage.* role to that SA.
    """
    for entry in iam_policies:
        asset_type, resource_name = entry["assetType"], entry["resource"]
        for binding in entry["policy"]["bindings"]:
            role = binding["role"]
            for member in binding["members"]:
                if not member.startswith("serviceAccount:"):
                    continue
                member_email = member.split(":", 1)[1]
                if asset_type == "iam.googleapis.com/ServiceAccount" and role in IMPERSONATION_ROLES:
                    target_email = resource_name.split("/")[-1]
                    tx.run(
                        "MATCH (a:ServiceAccount {name:$a}), (b:ServiceAccount {name:$b}) "
                        "MERGE (a)-[:CAN_IMPERSONATE]->(b)",
                        a=member_email, b=target_email,
                    )
                elif asset_type == "storage.googleapis.com/Bucket" and role.startswith("roles/storage."):
                    bucket_name = resource_name.split("/")[-1]
                    tx.run(
                        "MATCH (sa:ServiceAccount {name:$a}), (b:Bucket {name:$b}) "
                        "MERGE (sa)-[:HAS_ACCESS]->(b)",
                        a=member_email, b=bucket_name,
                    )


def print_summary(session):
    print("\n--- Node counts ---")
    for row in session.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label"):
        print(f"  {row['label']:<14} {row['n']}")
    print("--- Edge counts ---")
    for row in session.run("MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY rel"):
        print(f"  {row['rel']:<14} {row['n']}")


def main():
    with open(ROOT / "data" / "sample.json") as f:
        seed = json.load(f)

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        create_constraints(session)
        session.execute_write(create_nodes, seed["resources"])
        session.execute_write(create_structural_context, seed["resources"])
        session.execute_write(derive_opens_to, seed["resources"])
        session.execute_write(derive_runs_as, seed["resources"])
        session.execute_write(derive_iam_edges, seed["iam_policies"])
        print_summary(session)
    driver.close()
    print("\nDone. Open http://localhost:7474 to explore the graph.")


if __name__ == "__main__":
    main()
