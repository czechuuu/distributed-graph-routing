import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions
from google.cloud.bigtable import row

from .io_wrappers import ReadNodesFromBQ, ReadEdgesFromBQ, WriteToBT
from .algo import build_shard_graph, identify_boundary_nodes, compute_shortcuts

from enum import Enum

from storage_types import bigtable_storage_pb2
        
class EmitShardsForEdge(beam.DoFn):
    """
    Takes (edge, shard_u, shard_v)
    Yields out (shard_id, edge)
    """
    def process(self, element, *args, **kwargs):
        edge, shard_u, shard_v = element
        if shard_u is not None and shard_v is not None:
            yield (shard_u, edge)
            if shard_u != shard_v:
                yield (shard_v, edge)

class ProcessShard(beam.DoFn):
    def process(self, element):
        """
        Takes a (shard_id, {'nodes': nodes, 'edges': edges}) tuple
        Yields out tagged outputs
        shortcut: (shard_id, shortcuts, inter_shard_edges)
        intra: (shard_id, graph)
        """
        shard_id, data = element
        nodes = data['nodes']
        edges = data['edges']
        
        node_list = list(nodes)
        edge_list = list(edges)

        G = build_shard_graph(node_list, edge_list)
        
        in_boundary, out_boundary = identify_boundary_nodes(G, shard_id)
        
        shortcuts = compute_shortcuts(G, in_boundary, out_boundary)

        inter_shard_edges = []
        for edge in edge_list:
            u_node = G.nodes.get(edge.u)
            v_node = G.nodes.get(edge.v)
            
            # If a node is not in G it means it's from another shard - then we'll resolve to None here
            # which is good because then we'll detect None != shard_id and add it to inter_shard_edges
            shard_u = u_node.get('shard_id') if u_node else None
            shard_v = v_node.get('shard_id') if v_node else None
            
            is_internal = (shard_u == shard_id) and (shard_v == shard_id)
            
            if not is_internal:
                inter_shard_edges.append(edge)
        
        yield beam.pvalue.TaggedOutput('shortcuts', (shard_id, shortcuts, inter_shard_edges))
        yield beam.pvalue.TaggedOutput('intra', (shard_id, G))

class MutationType(Enum):
    SHORTCUT = 1
    INTRA = 2

class CreatePathMutations(beam.DoFn):
    def process(self, element):
        shard_id, shortcuts, inter_shard_edges = element
        
        # Iterate over shortcuts and save paths
        for s in shortcuts:
            if s.path:
                path_proto = bigtable_storage_pb2.ShortcutPath()
                path_proto.nodes.extend(s.path)
                
                row_key = f"P#{s.u}#{s.v}".encode('utf-8')
                direct_row = row.DirectRow(row_key)
                direct_row.set_cell('cf', 'val', path_proto.SerializeToString())
                yield direct_row

class ExtractOverlayEdges(beam.DoFn):
    def process(self, element):
        shard_id, shortcuts, inter_shard_edges = element
        
        overlay_proto = bigtable_storage_pb2.OverlayGraph()
        
        # Add Shortcuts
        for s in shortcuts:
            pb_edge = overlay_proto.shortcuts.add()
            pb_edge.from_node_id = s.u
            pb_edge.to_node_id = s.v
            pb_edge.weight = int(s.weight) 
            
        # Add Bridges
        for e in inter_shard_edges:
            pb_edge = overlay_proto.bridges.add()
            pb_edge.from_node_id = e.u
            pb_edge.to_node_id = e.v
            pb_edge.weight = int(e.weight)
            
        yield overlay_proto.SerializeToString()

class MergeOverlayGraphs(beam.CombineFn):
    def create_accumulator(self):
        return []

    def add_input(self, accumulator, element_bytes):
        accumulator.append(element_bytes)
        return accumulator

    def merge_accumulators(self, accumulators):
        merged = []
        for acc in accumulators:
            merged.extend(acc)
        return merged

    def extract_output(self, accumulator):
        merged_proto = bigtable_storage_pb2.OverlayGraph()
        for b in accumulator:
            partial = bigtable_storage_pb2.OverlayGraph()
            partial.ParseFromString(b)
            merged_proto.shortcuts.extend(partial.shortcuts)
            merged_proto.bridges.extend(partial.bridges)
        return merged_proto.SerializeToString()

class CreateOverlayMutation(beam.DoFn):
    def process(self, element_bytes):
        row_key = b"O#"
        direct_row = row.DirectRow(row_key)
        direct_row.set_cell('cf', 'val', element_bytes)
        yield direct_row


class CreateIntraMutations(beam.DoFn):
    def process(self, element):
        shard_id, G = element
        row_key = f"S#{shard_id}".encode('utf-8')
        direct_row = row.DirectRow(row_key)
        
        shard_proto = bigtable_storage_pb2.ShardGraph()
        
        # Add Edges
        for u, v, d in G.edges(data=True):
            # Filter internal edges only
            u_node = G.nodes[u]
            v_node = G.nodes[v]
            if u_node.get('shard_id') == shard_id and v_node.get('shard_id') == shard_id:
                 pb_edge = shard_proto.edges.add()
                 pb_edge.from_node_id = u
                 pb_edge.to_node_id = v
                 pb_edge.weight = int(d['weight'])
        
        # Add Node Locations
        for n, data in G.nodes(data=True):
             if data.get('shard_id') == shard_id:
                 loc = shard_proto.locations.add()
                 loc.node_id = n
                 loc.x = data.get('x', 0.0)
                 loc.y = data.get('y', 0.0)
        
        direct_row.set_cell('cf', 'val', shard_proto.SerializeToString())
        yield direct_row

class CreateNodeIndexMutation(beam.DoFn):
    def process(self, element):
        # element is a Node object
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

def create_pipeline(project, temp_location, input_nodes, input_edges, instance, shortcuts_table, shards_table, overlay_table, node_index_table, setup_file, pipeline_args=None):
    if pipeline_args is None:
        pipeline_args = []

    # Automatically enable Cloud Build for DataflowRunner if not explicitly set
    # This prevents installing dependencies on every worker boot, speeding up scaling.
    is_dataflow = any('DataflowRunner' in arg for arg in pipeline_args)
    if is_dataflow:
        pipeline_args.append('--prebuild_sdk_container_engine=cloud_build')
        pipeline_args.append(f'--docker_registry_push_url=gcr.io/{project}/dataflow/graph-routing-worker-sdk')
        pipeline_args.append('--experiments=use_runner_v2')
        pipeline_args.append(f'--sdk_container_image=docker.io/apache/beam_python3.11_sdk:{beam.version.__version__}')

    # Initialize PipelineOptions with passed args (e.g. --runner, --region) using flags argument.
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
        
        # (NodeID, ShardID)
        node_id_shard = nodes | "KeyNodesById" >> beam.Map(lambda n: (n.id, n.shard_id))
        
        # (Edge.u, Edge)
        edges_keyed_by_u = edges | "KeyEdgesByU" >> beam.Map(lambda e: (e.u, e))
        
        def attach_shard_u(element):
            """
            Takes co-grouped
            (Edge.u, {node_id_shard: [ShardID], edges_u: [Edge]}),
            Yields (Edge.v, (Edge, ShardU))
            """
            node_id, data = element
            shard_ids = data['node_id_shard']
            edge_list = data['edges_u']
            if shard_ids:
                shard_u = shard_ids[0]
                for e in edge_list:
                    yield (e.v, (e, shard_u))

        # (Edge.v, (Edge, shard_u))
        edges_with_u_shard = (
            {'node_id_shard': node_id_shard, 'edges_u': edges_keyed_by_u}
            | "GroupEdgesAndNodesByU" >> beam.CoGroupByKey()
            | "AttachShardU" >> beam.FlatMap(attach_shard_u)
        )
        
        def attach_shard_v(element):
            """
            Takes co-grouped
            (Edge.v, {node_id_shard: [ShardID], edges_with_u: [(edge, shard_u)]})
            Yields (Edge, shard_u, shard_v)
            """
            node_id, data = element
            shard_ids = data['node_id_shard']
            edges_data = data['edges_with_u']
            if shard_ids:
                shard_v = shard_ids[0]
                for (e, shard_u) in edges_data:
                    yield (e, shard_u, shard_v)
                
        edges_with_shards = (
            {'node_id_shard': node_id_shard, 'edges_with_u': edges_with_u_shard}
            | "GroupEdgesAndNodesByV" >> beam.CoGroupByKey()
            | "AttachShardV" >> beam.FlatMap(attach_shard_v)
        )
        
        # (shard_id, edge)
        assigned_edges = (
            edges_with_shards 
            | beam.ParDo(EmitShardsForEdge())
        )
        
        # (shard_id, node) pairs
        nodes_by_shard = nodes | "KeyNodesByShardId" >> beam.Map(lambda n: (n.shard_id, n))
        
        # (shard_id, (nodes, edges)) pairs
        grouped = (
            {'nodes': nodes_by_shard, 'edges': assigned_edges}
            | beam.CoGroupByKey()
        )
        
        # yields out the 
        # shortcut: (shard_id, shortcuts, inter_shard_edges)
        # intra: (shard_id, graph)
        results = grouped | beam.ParDo(ProcessShard()).with_outputs('shortcuts', 'intra')
        
        # Write Shortcut Paths
        (results.shortcuts 
         | "CreatePathMutations" >> beam.ParDo(CreatePathMutations())
         | "WritePaths" >> WriteToBT(project, instance, shortcuts_table)
        )
        
        # Extract, Merge and Write Overlay Graph
        (results.shortcuts
         | "ExtractOverlayEdges" >> beam.ParDo(ExtractOverlayEdges())
         | "MergeOverlayGraphs" >> beam.CombineGlobally(MergeOverlayGraphs())
         | "CreateOverlayMutation" >> beam.ParDo(CreateOverlayMutation())
         | "WriteOverlay" >> WriteToBT(project, instance, overlay_table)
        )
        
        (results.intra 
         | "CreateIntraMutations" >> beam.ParDo(CreateIntraMutations())
         | "WriteIntra" >> WriteToBT(project, instance, shards_table)
        )
        
        # Write Node Index
        (nodes
         | "CreateNodeIndexMutation" >> beam.ParDo(CreateNodeIndexMutation())
         | "WriteNodeIndex" >> WriteToBT(project, instance, node_index_table)
        )
