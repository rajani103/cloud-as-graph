// 01 — Reachability
// "From the public VM, what can it reach outward?"
// Walks RUNS_AS / CAN_IMPERSONATE / HAS_ACCESS forward, variable depth, from
// vm-bastion. In this dataset the only thing reachable this way is the
// crown-jewels chain — decoy resources don't connect to vm-bastion at all.

MATCH (start:Instance {name: 'vm-bastion'})
MATCH path = (start)-[:RUNS_AS|CAN_IMPERSONATE|HAS_ACCESS*1..4]->(reachable)
RETURN path
