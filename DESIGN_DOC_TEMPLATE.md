Writing Design doc

Context and scope
Describe the problem here. This is where you should lay out the high-level "why" of the project. This can be a bit more specific version of the main problem statement (PROJECT_STATEMENT.md) , clarifying what constraints you are planning to address. Try to describe the specific problem space you chose to tackle and the boundaries you set for the solution. If you decided to focus heavily on one constraint (like strict memory limits) over another (like dynamic graph changes), mention that here. The goal is to set the stage for what the system is intended to do and, just as importantly, what it isn't trying to do.
Architecture and Design
 Describe the solution in detail here as well as tradeoffs. Why did you choose your specific sharding strategy over a more basic approach? How does the algorithm actually navigate the distributed state once a query comes in? 


System Diagram
It’s nice to have some visual representation, a diagram or graph showing how the system works.  where the query enters the system, how it gets routed to the specific shards, and how those shards talk to one another or a central coordinator to produce the final result.

Deployment
Describe how the chosen solution is actually deployed in GCP, which components are using which GCP services and the rationale behind choosing this specific GCP service for the task. 
APIs
Describe the surface area of your system. What do the endpoints look like? You should detail the contract between the client and the server, as well as any internal APIs or protocols (like gRPC) used for communication between the distributed components. 

Frontend

Talk about the user-facing side of the project. How are you visualizing the graph and the paths? If your frontend helps demonstrate the sharding—like showing which nodes are handling which geographic regions—definitely highlight that. This is a great place to drop in some screenshots or a link to a demo to show the system in action.


Testing

Describe how you are planning to test the implementation and results, including unit tests or any manual tests performed, if you have any data on stabilization times, memory usage under load, or query latency, include those results here to prove the system meets the original goals.

