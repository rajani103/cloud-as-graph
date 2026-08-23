// 04 — Full path: internet to crown jewels
// "Show me the one path from the public internet to the sensitive bucket."
// shortestPath over the four semantic edge types. In this dataset there is
// exactly one such path — this is the headline slide of the talk.

MATCH (start:Internet {name: 'internet'}), (target:Bucket {name: 'bucket-crownjewels'})
MATCH p = shortestPath(
  (start)-[:OPENS_TO|RUNS_AS|CAN_IMPERSONATE|HAS_ACCESS*]->(target)
)
RETURN p
