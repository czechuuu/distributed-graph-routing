import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions
from google.cloud.bigtable import row

from .io_wrappers import ReadNodesFromBQ, ReadEdgesFromBQ, WriteToBT
from .algo import build_shard_graph, compute_shortcuts

from storage_types import bigtable_storage_pb2


class ClassifyEdges(beam.DoFn):
    """
    Classifies edges after shard assignment.
    
    Input: (edge, shard_u, shard_v)
    
    Outputs:
        - 'bridge': The edge itself (for overlay graph)
        - 'internal': (shard_id, edge) for internal shard processing
        - 'boundary': (shard_id, (node_id, 'IN' or 'OUT')) for boundary node identification
    """
    def process(self, element):
        edge, shard_u, shard_v = element
        
        if shard_u == shard_v:
            # Internal edge - goes only to its shard
            yield beam.pvalue.TaggedOutput('internal', (shard_u, edge))
        else:
            # Bridge edge - goes to overlay graph directly
            yield beam.pvalue.TaggedOutput('bridge', edge)
            
            # Also emit boundary node info for each shard
            # node u is OUT-boundary for shard_u (it has edge going OUT to another shard)
            yield beam.pvalue.TaggedOutput('boundary', (shard_u, (edge.u, 'OUT')))
            # node v is IN-boundary for shard_v (it has edge coming IN from another shard)  
            yield beam.pvalue.TaggedOutput('boundary', (shard_v, (edge.v, 'IN')))


class ProcessShard(beam.DoFn):
    """
    Processes a single shard to compute shortcuts.
    
    Input: (shard_id, {'nodes': [Node], 'edges': [Edge], 'boundary': [(node_id, 'IN'/'OUT')]})
    
    Outputs:
        - 'shortcuts': (shard_id, [Shortcut])
        - 'intra': (shard_id, [Edge], [NodeLocation])
    """
    def process(self, element):
        shard_id, data = element
        
        node_list = list(data.get('nodes', []))
        edge_list = list(data.get('edges', []))
        boundary_info = list(data.get('boundary', []))
        
        # Separate boundary nodes into IN and OUT sets
        in_boundary = set()
        out_boundary = set()
        for node_id, direction in boundary_info:
            if direction == 'IN':
                in_boundary.add(node_id)
            else:
                out_boundary.add(node_id)
        
        # Build graph from internal nodes and edges only (no ghost nodes needed!)
        G, id_to_idx, idx_to_id = build_shard_graph(node_list, edge_list)
        
        # Compute shortcuts between boundary nodes
        shortcuts = compute_shortcuts(G, id_to_idx, idx_to_id, in_boundary, out_boundary)
        
        # Extract node locations
        node_locations = []
        for n in node_list:
            node_locations.append({
                'node_id': n.id,
                'x': n.x,
                'y': n.y
            })
        
        yield beam.pvalue.TaggedOutput('shortcuts', (shard_id, shortcuts))
        yield beam.pvalue.TaggedOutput('intra', (shard_id, edge_list, node_locations))


class CreatePathMutations(beam.DoFn):
    """Creates BigTable rows for shortcut paths."""
    def process(self, element):
        shard_id, shortcuts = element
        
        for s in shortcuts:
            if s.path:
                path_proto = bigtable_storage_pb2.ShortcutPath()
                path_proto.nodes.extend(s.path)
                
                row_key = f"P#{s.u}#{s.v}".encode('utf-8')
                direct_row = row.DirectRow(row_key)
                direct_row.set_cell('cf', 'val', path_proto.SerializeToString())
                yield direct_row


class ExtractShortcutEdges(beam.DoFn):
    """Extracts edge tuples from shortcuts for overlay graph."""
    def process(self, element):
        shard_id, shortcuts = element
        for s in shortcuts:
            # Yield as tuple: (type, from, to, weight)
            yield ('shortcut', s.u, s.v, int(s.weight))


class ExtractBridgeEdge(beam.DoFn):
    """Extracts edge tuple from bridge for overlay graph."""
    def process(self, element):
        # element is an Edge namedtuple
        yield ('bridge', element.u, element.v, int(element.weight))


class MergeOverlayGraph(beam.CombineFn):
    """Combines all overlay edge tuples into one OverlayGraph proto."""
    def create_accumulator(self):
        return {'shortcuts': [], 'bridges': []}
    
    def add_input(self, accumulator, element):
        edge_type, from_id, to_id, weight = element
        edge_tuple = (from_id, to_id, weight)
        if edge_type == 'shortcut':
            accumulator['shortcuts'].append(edge_tuple)
        else:
            accumulator['bridges'].append(edge_tuple)
        return accumulator
    
    def merge_accumulators(self, accumulators):
        merged = {'shortcuts': [], 'bridges': []}
        for acc in accumulators:
            merged['shortcuts'].extend(acc['shortcuts'])
            merged['bridges'].extend(acc['bridges'])
        return merged
    
    def extract_output(self, accumulator):
        # Serialize
        overlay_proto = bigtable_storage_pb2.OverlayGraph()
        
        for from_id, to_id, weight in accumulator['shortcuts']:
            edge = overlay_proto.shortcuts.add()
            edge.from_node_id = from_id
            edge.to_node_id = to_id
            edge.weight = weight
            
        for from_id, to_id, weight in accumulator['bridges']:
            edge = overlay_proto.bridges.add()
            edge.from_node_id = from_id
            edge.to_node_id = to_id
            edge.weight = weight
            
        return overlay_proto.SerializeToString()


class CreateOverlayMutation(beam.DoFn):
    def process(self, element_bytes):
        row_key = b"O#"
        direct_row = row.DirectRow(row_key)
        direct_row.set_cell('cf', 'val', element_bytes)
        yield direct_row


class CreateIntraMutations(beam.DoFn):
    """Creates BigTable mutations for shard graphs."""
    def process(self, element):
        shard_id, edges, node_locations = element
        row_key = f"S#{shard_id}".encode('utf-8')
        direct_row = row.DirectRow(row_key)
        
        shard_proto = bigtable_storage_pb2.ShardGraph()
        
        for edge in edges:
            pb_edge = shard_proto.edges.add()
            pb_edge.from_node_id = edge.u
            pb_edge.to_node_id = edge.v
            pb_edge.weight = int(edge.weight)
        
        for loc_data in node_locations:
            loc = shard_proto.locations.add()
            loc.node_id = loc_data['node_id']
            loc.x = loc_data['x']
            loc.y = loc_data['y']
        
        direct_row.set_cell('cf', 'val', shard_proto.SerializeToString())
        yield direct_row


class CreateNodeIndexMutation(beam.DoFn):
    def process(self, element):
        row_key = f"N#{element.id}".encode('utf-8')
        direct_row = row.DirectRow(row_key)
        
        lookup_proto = bigtable_storage_pb2.ShardLookup()
        lookup_proto.shard_id = element.shard_id
        
        direct_row.set_cell('cf', 'val', lookup_proto.SerializeToString())
        
        # Add Node Location
        loc_proto = bigtable_storage_pb2.NodeLocation()
        loc_proto.node_id = element.id
        loc_proto.x = element.x
        loc_proto.y = element.y
        direct_row.set_cell('cf', 'loc', loc_proto.SerializeToString())

        yield direct_row


def create_pipeline(project, temp_location, input_nodes, input_edges, instance, 
                    shortcuts_table, shards_table, overlay_table, node_index_table, 
                    setup_file, pipeline_args=None):
    if pipeline_args is None:
        pipeline_args = []

    is_dataflow = any('DataflowRunner' in arg for arg in pipeline_args)
    if is_dataflow:
        pipeline_args.append('--prebuild_sdk_container_engine=cloud_build')
        pipeline_args.append(f'--docker_registry_push_url=gcr.io/{project}/dataflow/graph-routing-worker-sdk')
        pipeline_args.append('--experiments=use_runner_v2')
        pipeline_args.append(f'--sdk_container_image=docker.io/apache/beam_python3.11_sdk:{beam.version.__version__}')

    options = PipelineOptions(flags=pipeline_args)
    options.view_as(SetupOptions).save_main_session = True
    
    google_cloud_options = options.view_as(beam.options.pipeline_options.GoogleCloudOptions) 
    google_cloud_options.project = project
    google_cloud_options.temp_location = temp_location
    
    setup_options = options.view_as(SetupOptions)
    setup_options.setup_file = setup_file
    
    with beam.Pipeline(options=options) as p:
        nodes = p | "ReadNodes" >> ReadNodesFromBQ(input_nodes)
        edges = p | "ReadEdges" >> ReadEdgesFromBQ(input_edges)
        
        # === STEP 1: Attach shard IDs to edges ===
        
        node_id_shard = nodes | "KeyNodesById" >> beam.Map(lambda n: (n.id, n.shard_id))
        edges_keyed_by_u = edges | "KeyEdgesByU" >> beam.Map(lambda e: (e.u, e))
        
        def attach_shard_u(element):
            node_id, data = element
            shard_ids = data['node_id_shard']
            edge_list = data['edges_u']
            
            if not edge_list:
                return  # No edges for this node, that's fine
                
            if not shard_ids:
                raise ValueError(f"Node {node_id} referenced by edge(s) but not found in nodes table. "
                               f"Edges: {list(edge_list)}")
            
            shard_u = shard_ids[0]
            for e in edge_list:
                yield (e.v, (e, shard_u))

        edges_with_u_shard = (
            {'node_id_shard': node_id_shard, 'edges_u': edges_keyed_by_u}
            | "GroupEdgesAndNodesByU" >> beam.CoGroupByKey()
            | "AttachShardU" >> beam.FlatMap(attach_shard_u)
        )
        
        def attach_shard_v(element):
            node_id, data = element
            shard_ids = data['node_id_shard']
            edges_data = list(data['edges_with_u'])
            
            if not edges_data:
                return  # No edges targeting this node, that's fine
                
            if not shard_ids:
                raise ValueError(f"Node {node_id} referenced as edge target but not found in nodes table. "
                               f"Edges: {edges_data}")
            
            shard_v = shard_ids[0]
            for (e, shard_u) in edges_data:
                yield (e, shard_u, shard_v)
                
        edges_with_shards = (
            {'node_id_shard': node_id_shard, 'edges_with_u': edges_with_u_shard}
            | "GroupEdgesAndNodesByV" >> beam.CoGroupByKey()
            | "AttachShardV" >> beam.FlatMap(attach_shard_v)
        )
        
        # === STEP 2: Classify edges into bridges vs internal, extract boundary nodes ===
        
        classified = edges_with_shards | "ClassifyEdges" >> beam.ParDo(ClassifyEdges()).with_outputs(
            'bridge', 'internal', 'boundary'
        )
        
        bridges = classified.bridge          # Edge objects (for overlay)
        internal_edges = classified.internal  # (shard_id, Edge)
        boundary_info = classified.boundary   # (shard_id, (node_id, 'IN'/'OUT'))
        
        # === STEP 3: Group by shard and process ===
        
        nodes_by_shard = nodes | "KeyNodesByShardId" >> beam.Map(lambda n: (n.shard_id, n))
        
        grouped = (
            {'nodes': nodes_by_shard, 'edges': internal_edges, 'boundary': boundary_info}
            | "GroupByShardId" >> beam.CoGroupByKey()
        )
        
        shard_results = grouped | "ProcessShard" >> beam.ParDo(ProcessShard()).with_outputs(
            'shortcuts', 'intra'
        )
        
        # === STEP 4: Write outputs ===
        
        # Write shortcut paths to BigTable
        (shard_results.shortcuts
         | "CreatePathMutations" >> beam.ParDo(CreatePathMutations())
         | "WritePaths" >> WriteToBT(project, instance, shortcuts_table)
        )
        
        # Create overlay edges from shortcuts
        shortcut_overlay_edges = (
            shard_results.shortcuts
            | "ExtractShortcutEdges" >> beam.ParDo(ExtractShortcutEdges())
        )
        
        # Create overlay edges from bridges
        bridge_overlay_edges = (
            bridges
            | "ExtractBridgeEdge" >> beam.ParDo(ExtractBridgeEdge())
        )
        
        # Merge all overlay edges and write
        ((shortcut_overlay_edges, bridge_overlay_edges)
         | "FlattenOverlayEdges" >> beam.Flatten()
         | "MergeOverlayGraph" >> beam.CombineGlobally(MergeOverlayGraph())
         | "CreateOverlayMutation" >> beam.ParDo(CreateOverlayMutation())
         | "WriteOverlay" >> WriteToBT(project, instance, overlay_table)
        )
        
        # Write intra-shard graphs
        (shard_results.intra
         | "CreateIntraMutations" >> beam.ParDo(CreateIntraMutations())
         | "WriteIntra" >> WriteToBT(project, instance, shards_table)
        )
        
        # Write node index
        (nodes
         | "CreateNodeIndexMutation" >> beam.ParDo(CreateNodeIndexMutation())
         | "WriteNodeIndex" >> WriteToBT(project, instance, node_index_table)
        )
