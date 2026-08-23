// 02 — Blast radius
// "If sa-bastion were compromised, what's the full downstream impact?"
// Walks CAN_IMPERSONATE / HAS_ACCESS forward from a chosen service account,
// variable depth, and lists every resource it can eventually touch.
// Swap the {name:'sa-bastion@...'} value to try a different starting SA.

MATCH (compromised:ServiceAccount {name: 'sa-bastion@cloud-as-graph-demo.iam.gserviceaccount.com'})
MATCH path = (compromised)-[:CAN_IMPERSONATE|HAS_ACCESS*1..4]->(affected)
RETURN affected.name AS affected_resource,
       labels(affected)[0] AS resource_type,
       length(path) AS hops,
       [n IN nodes(path) | n.name] AS chain
ORDER BY hops
