import argparse
import logging
from google.cloud import bigtable

def verify_bigtable_upload(project_id, instance_id):
    """
    Connects to BigTable, lists all tables, and queries 20 rows from each to verify upload.
    """
    try:
        client = bigtable.Client(project=project_id, admin=True)
        instance = client.instance(instance_id)

        print(f"Connecting to BigTable Project: {project_id}, Instance: {instance_id}")
        
        tables = instance.list_tables()
        if not tables:
            print("No tables found in the instance.")
            return

        print(f"Found {len(tables)} tables: {[t.table_id for t in tables]}")

        for table in tables:
            table_id = table.table_id
            print(f"\n--- Verifying Table: {table_id} ---")
            
            # Request 20 rows
            rows = table.read_rows(limit=20)
            
            count = 0
            for row in rows:
                count += 1
                row_key = row.row_key.decode('utf-8')
                # Calculate basic stats about the row
                num_cells = 0
                total_value_size = 0
                for cf, cols in row.cells.items():
                    for col, cells in cols.items():
                         num_cells += len(cells)
                         for cell in cells:
                             total_value_size += len(cell.value)

                print(f"Row {count}: Key='{row_key}', Cells={num_cells}, Total Value Size={total_value_size} bytes")
            
            if count == 0:
                print(f"Table {table_id} is empty (or no rows returned).")
            else:
                print(f"Successfully read {count} rows from {table_id}.")

    except Exception as e:
        print(f"Error accessing BigTable: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify BigTable Uploads")
    parser.add_argument('--project', default='repetitive-shortest-paths', help='GCP Project ID')
    parser.add_argument('--instance', default='routing-instance', help='BigTable Instance ID')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    verify_bigtable_upload(args.project, args.instance)
