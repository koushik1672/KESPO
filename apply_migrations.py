import sqlite3
import os
import importlib.util
from datetime import datetime

def get_db_connection():
    return sqlite3.connect("kespo.db")

def get_migration_files():
    """Get all migration files in the migrations directory"""
    migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
    if not os.path.exists(migrations_dir):
        return []
    
    migration_files = [f for f in os.listdir(migrations_dir) 
                      if f.endswith('.py') and f != '__init__.py']
    return sorted(migration_files)

def get_applied_migrations(db):
    """Get list of applied migrations"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("SELECT name FROM migrations")
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error getting applied migrations: {e}")
        return []

def apply_migration(db, migration_file):
    """Apply a single migration"""
    try:
        module_name = f"migrations.{os.path.splitext(migration_file)[0]}"
        spec = importlib.util.spec_from_file_location(
            module_name, 
            os.path.join("migrations", migration_file)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Apply the migration
        module.upgrade(db)
        
        # Record the migration
        cursor = db.cursor()
        cursor.execute("INSERT INTO migrations (name) VALUES (?)", (migration_file,))
        db.commit()
        
        print(f"Applied migration: {migration_file}")
        return True
    except Exception as e:
        print(f"Error applying migration {migration_file}: {e}")
        db.rollback()
        return False

def main():
    print("Starting database migrations...")
    db = get_db_connection()
    db.row_factory = sqlite3.Row  # Enable column access by name
    
    try:
        applied_migrations = set(get_applied_migrations(db))
        migration_files = get_migration_files()
        
        for migration_file in migration_files:
            if migration_file not in applied_migrations:
                print(f"Applying {migration_file}...")
                if apply_migration(db, migration_file):
                    print(f"Successfully applied {migration_file}")
                else:
                    print(f"Failed to apply {migration_file}")
                    return
        
        print("All migrations applied successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    main()
