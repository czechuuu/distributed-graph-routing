from google.cloud.bigtable import Client

def clear_table_data(project_id, instance_id, table_id):
    """Deletes all rows from a specified Bigtable table."""
    client = Client(project=project_id, admin=True)
    instance = client.instance(instance_id)
    table = instance.table(table_id)

    print(f"Attempting to clear all data from table: {table_id}...")

    # Drop all rows in the table. An empty row_key_prefix clears everything.
    for prefix in ["0" , "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
        table.drop_by_prefix(prefix, timeout=200) # Timeout is optional, adjust as needed

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
    
    clear_table_data(project_id, instance_id, "intra_edges")
    clear_table_data(project_id, instance_id, "shortcuts")
