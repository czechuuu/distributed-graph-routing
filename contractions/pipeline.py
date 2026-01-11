
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions, GoogleCloudOptions
from google.cloud.bigtable import row
import struct

from contractions.io_wrappers import ReadNodesFromBQ, ReadEdgesFromBQ, WriteToBT
from shared.model import Node, Edge
from shared.algo import build_shard_graph, identify_boundary_nodes, compute_shortcuts

from enum import Enum

class EmitShardsForEdge(beam.DoFn):
    def process(self, element):
        """
        Takes (edge, shard_u, shard_v)
        Yields out (shard_id, edge)
        """
        edge, shard_u, shard_v = element
        
        if shard_u is None or shard_v is None:
            return

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
            if edge.u in out_boundary or edge.v in in_boundary:
                inter_shard_edges.append(edge)
        
        yield beam.pvalue.TaggedOutput('shortcuts', (shard_id, shortcuts, inter_shard_edges))
        yield beam.pvalue.TaggedOutput('intra', (shard_id, G))

class MutationType(Enum):
    SHORTCUT = 1
    INTRA = 2

class CreateMutations(beam.DoFn):
    def __init__(self, table_type):
        self.table_type = table_type # MutationType.SHORTCUT or MutationType.INTRA

    def process(self, element):
        if self.table_type == MutationType.SHORTCUT:
            shard_id, shortcuts, inter_shard_edges = element
            row_key = f"{shard_id}".encode('utf-8')
            direct_row = row.DirectRow(row_key)
            
            # Serialize Shortcuts
            # TODO(mrolbiecki) - use protobufs
            import json
            shortcuts_json = json.dumps([s._asdict() for s in shortcuts])
            direct_row.set_cell('cf', 'shortcuts', shortcuts_json.encode('utf-8'))
    
            # Serialize inter-shard edges not covered by shortcuts
            # (e.g. boundary edges connecting to other shards)
            inter_shard_edges_json = json.dumps([e._asdict() for e in inter_shard_edges])
            direct_row.set_cell('cf', 'inter_shard_edges', inter_shard_edges_json.encode('utf-8'))  

            yield direct_row

        elif self.table_type == MutationType.INTRA:
            shard_id, G = element
            row_key = f"{shard_id}".encode('utf-8')
            direct_row = row.DirectRow(row_key)
            
            # TODO(mrolbiecki) - use protobufs
            intra_edges = []
            for u, v, d in G.edges(data=True):
                u_node = G.nodes[u]
                v_node = G.nodes[v]
                if u_node.get('shard_id') == shard_id and v_node.get('shard_id') == shard_id:
                     intra_edges.append({'u': u, 'v': v, 'w': d['weight']})
            
            import json
            direct_row.set_cell('cf', 'edges', json.dumps(intra_edges).encode('utf-8'))
            yield direct_row

def create_pipeline(project, temp_location, input_nodes, input_edges, instance, shortcuts_table, intra_table, pipeline_args=None):
    # Initialize PipelineOptions with passed args (e.g. --runner, --region) using flags argument.
    options = PipelineOptions(flags=pipeline_args)
    options.view_as(SetupOptions).save_main_session = True
    
    google_cloud_options = options.view_as(beam.options.pipeline_options.GoogleCloudOptions) 
    google_cloud_options.project = project
    google_cloud_options.temp_location = temp_location
    
    setup_options = options.view_as(SetupOptions)
    setup_options.setup_file = './setup.py'
    
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
            if not shard_ids:
                return
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
            if not shard_ids:
                return  
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
            edges 
            | beam.ParDo(EmitShardsForEdge(), nodes_side_input=node_map)
        )
        
        # (shard_id, node) pairs
        nodes_by_shard = nodes | "KeyNodesById" >> beam.Map(lambda n: (n.shard_id, n))
        
        # (shard_id, (nodes, edges)) pairs
        grouped = (
            {'nodes': nodes_by_shard, 'edges': assigned_edges}
            | beam.CoGroupByKey()
        )
        
        # yields out the 
        # shortcut: (shard_id, shortcuts, inter_shard_edges)
        # intra: (shard_id, graph)
        results = grouped | beam.ParDo(ProcessShard()).with_outputs('shortcuts', 'intra')
        
        # Write Shortcuts
        (results.shortcuts 
         | "CreateShortcutMutations" >> beam.ParDo(CreateMutations(MutationType.SHORTCUT))
         | "WriteShortcuts" >> WriteToBT(project, instance, shortcuts_table)
        )
        
        # Write Intra-shard edges
        (results.intra 
         | "CreateIntraMutations" >> beam.ParDo(CreateMutations(MutationType.INTRA))
         | "WriteIntra" >> WriteToBT(project, instance, intra_table)
        )
