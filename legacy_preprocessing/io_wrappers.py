import apache_beam as beam
from apache_beam.io.gcp.bigtableio import WriteToBigTable


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
            table_id=self.table_id,
        )
