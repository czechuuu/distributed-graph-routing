THIS IS A DRAFT design doc - don't treat it to literally. When making changes to the code make sure to update this doc so that it remains consistent with the code. 

1. Assume we are given two csv files nodes.csv and edges.csv. Load them into BigQuery tables RawNodes (NodeId, Lon, Lat), edges (u, v,w) 
2. We can then use BigQuery builtin S2 functions to create new table (because updates on BQare presumably slow) Nodes (id, x, y, ShardId=S2CellId for now)
3. Use DataFlow to compute the shortcuts for each shard. I.e. in each shard use dijkstra to compute the shortest paths from each in-boundary node to each out-boundary node. It should save two things under its shard id to BigTable (to different tables say Shortcuts and EntireShards)
a.  The shortcuts - from each in-boundary node to each out-boundary node. Should also include edges between the out-boundary nodes of this shard and the in-boundary nodes of other shards. Merging the shortcuts for all the shards should give us a complete overlay graph.
b.  The shard state - ALL the connections within the shard
4.   The serving layer consists of GKE instances which 
    a. On startup fetch all the Shortcuts from bigtable and merge it into the overlay graph
    b. On query it loads the EntireShards of the shard of the source and destination nodes
    c. It has some facade to treat the overlay graph and the two EntireShard graphs as a single merged graph
    d. It runs a bidirectional dijkstra on this facade-graph to find the shortest path (which uses shortcut edges) between the given nodes
    e. It traverses the shortest path fetching the EntireShard graphs as it goes to reconstruct the precise shortest path - substituting the shortcut edges for exact fetching the pre-calculated shortcut expansions (path sequences) from Bigtable (???)

