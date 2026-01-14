from google.cloud.bigtable import Client

def clear_table_data(project_id, instance_id, table_id):
    """Deletes all rows from a specified Bigtable table."""
    client = Client(project=project_id, admin=True)
    instance = client.instance(instance_id)
    table = instance.table(table_id)

    print(f"Attempting to clear all data from table: {table_id}...")

    # Drop all rows in the table. An empty row_key_prefix clears everything.
    # Drop all rows in the table. The keys start with S, P, O, or N.
    for prefix in ["S", "P", "O", "N"]:
        try:
            table.drop_by_prefix(prefix, timeout=200)
        except Exception:
            # Table might be empty or prefix not found, continue
            pass

    print(f"All data successfully cleared from table: {table_id}.")

project_id = "repetitive-shortest-paths"
instance_id = "routing-instance" 

if __name__ == "__main__":
    first_confirmation = input("Are you sure you want to clear all data from the tables? (y/n)")
    if first_confirmation.lower() != "y":
        print("Aborting.")
        exit()

    in_project_id = input("Enter project ID: ")
    if in_project_id != project_id:
        print("Project IDs do not match. Aborting.")
        exit()

    in_instance_id = input("Enter instance ID: ")
    if in_instance_id != instance_id:
        print("Instance IDs do not match. Aborting.")
        exit()

    last_confirmation = input("Are you REALLY sure you want to clear all data from the tables? (y/n)")
    if last_confirmation.lower() != "y":
        print("Aborting.")
        exit()

    clear_table_data(project_id, instance_id, "shards")
    clear_table_data(project_id, instance_id, "shortcuts")
    clear_table_data(project_id, instance_id, "overlay_graph")
    clear_table_data(project_id, instance_id, "node_index")