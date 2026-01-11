import apache_beam as beam
from apache_beam.io.gcp.bigquery import ReadFromBigQuery
from apache_beam.io.gcp.bigtableio import WriteToBigTable
from google.cloud.bigtable import row
from shared.model import Node, Edge

class ReadNodesFromBQ(beam.PTransform):
    def __init__(self, table):
        self.table = table

    def expand(self, pcoll):
        return (
            pcoll 
            | "ReadNodes" >> ReadFromBigQuery(table=self.table)
            | "ParseNode" >> beam.Map(lambda row: Node(
                id=row['id'], 
                x=row['x'], 
                y=row['y'], 
                shard_id=row['ShardId']
            ))
        )

class ReadEdgesFromBQ(beam.PTransform):
    def __init__(self, table):
        self.table = table

    def expand(self, pcoll):
        return (
            pcoll 
            | "ReadEdges" >> ReadFromBigQuery(table=self.table)
            | "ParseEdge" >> beam.Map(lambda row: Edge(
                u=row['u'], 
                v=row['v'], 
                weight=row['weight']
            ))
        )

class WriteToBT(beam.PTransform):
    def __init__(self, project_id, instance_id, table_id):
        self.project_id = project_id
        self.instance_id = instance_id
        self.table_id = table_id

    def expand(self, pcoll):
        # Expects pcoll of DirectRow objects
        return pcoll | WriteToBigTable(
            project_id=self.project_id,
            instance_id=self.instance_id,
            table_id=self.table_id
        )
