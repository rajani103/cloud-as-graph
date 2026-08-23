// 03 — Single point of failure
// "Which service account, if compromised, affects the most other resources?"
// Ranks ServiceAccounts by inbound-edge count (RUNS_AS from instances that
// run as it, CAN_IMPERSONATE from SAs that can impersonate it) using the
// built-in COUNT{} subquery — plain Cypher, no GDS plugin required.
// sa-default wins: three separate VMs RUNS_AS it, versus one inbound edge
// each for sa-bastion and sa-deployer. That's the over-connected default
// node-pool service account a resource list would never flag as a SPOF.
//
// If the GDS plugin were installed, the same ranking could be produced with
// degree centrality instead, e.g.:
//   CALL gds.degree.stream('myGraph', {orientation: 'REVERSE'})
//   YIELD nodeId, score
//   RETURN gds.util.asNode(nodeId).name AS service_account, score
//   ORDER BY score DESC

MATCH (sa:ServiceAccount)
RETURN sa.name AS service_account,
       COUNT { (sa)<--() } AS inbound_dependencies
ORDER BY inbound_dependencies DESC
