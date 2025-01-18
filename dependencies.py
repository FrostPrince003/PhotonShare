from database import Database

def get_database():
    """Provide a database instance for route handlers."""
    try:
        db_name = "Photon"  # Replace with your actual database name
        print(f"✅ Accessing database: {db_name}")
        return Database.client[db_name]
    except Exception as e:
        print(f"❌ Failed to access database: {e}")
        raise RuntimeError(f"Failed to access database: {e}")
