import sqlite3
import os
import sys
import traceback
from datetime import datetime, timedelta

class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

def get_db_connection():
    """Create and return a database connection with proper settings."""
    try:
        conn = sqlite3.connect('kespo.db', timeout=30)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.Error as e:
        raise DatabaseError(f"Database connection failed: {e}")

def migration_1_add_reset_columns(cursor):
    """Migration 1: Add reset token columns to farmer table."""
    try:
        cursor.execute("PRAGMA table_info(farmer)")
        farmer_columns = [row['name'] for row in cursor.fetchall()]
        
        if 'reset_token' not in farmer_columns:
            cursor.execute("ALTER TABLE farmer ADD COLUMN reset_token TEXT")
            print("✅ Added reset_token column to farmer table")
        
        if 'reset_token_expiry' not in farmer_columns:
            cursor.execute("ALTER TABLE farmer ADD COLUMN reset_token_expiry TEXT")
            print("✅ Added reset_token_expiry column to farmer table")
            
        return True
    except sqlite3.Error as e:
        print(f"❌ Error in migration_1_add_reset_columns: {e}")
        return False

def migration_2_add_created_updated_timestamps(cursor):
    """Migration 2: Add created_at and updated_at timestamps to all tables."""
    try:
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cursor.fetchall()]
        
        for table in tables:
            if table == 'sqlite_sequence':
                continue
                
            # Check if table has created_at and updated_at
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [row['name'] for row in cursor.fetchall()]
            
            # Add created_at if it doesn't exist
            if 'created_at' not in columns:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN created_at TEXT")
                cursor.execute(f"UPDATE {table} SET created_at = datetime('now') WHERE created_at IS NULL")
                print(f"✅ Added created_at to {table} table")
            
            # Add updated_at if it doesn't exist (except for migration_versions)
            if 'updated_at' not in columns and table != 'migration_versions':
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN updated_at TEXT")
                # Set updated_at to created_at if it exists, otherwise use current time
                if 'created_at' in columns:
                    cursor.execute(f"UPDATE {table} SET updated_at = created_at WHERE updated_at IS NULL")
                else:
                    cursor.execute(f"UPDATE {table} SET updated_at = datetime('now') WHERE updated_at IS NULL")
                print(f"✅ Added updated_at to {table} table")
        
        return True
    except sqlite3.Error as e:
        print(f"❌ Error in migration_2_add_created_updated_timestamps: {e}")
        return False

def run_migrations():
    """Run all pending database migrations."""
    if not os.path.exists('kespo.db'):
        print("❌ Database file not found. Please initialize the database first.")
        return False
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create migration_versions table if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS migration_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT UNIQUE NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Get list of applied migrations
        cursor.execute("SELECT migration_name FROM migration_versions")
        applied_migrations = {row['migration_name'] for row in cursor.fetchall()}
        
        # Define migrations in order
        migrations = [
            ('add_reset_columns', migration_1_add_reset_columns),
            ('add_created_updated_timestamps', migration_2_add_created_updated_timestamps),
            # Add new migrations here
        ]
        
        # Run pending migrations
        any_migrations_run = False
        for migration_name, migration_func in migrations:
            if migration_name not in applied_migrations:
                print(f"\n🚀 Running migration: {migration_name}")
                if migration_func(cursor):
                    cursor.execute(
                        "INSERT INTO migration_versions (migration_name) VALUES (?)",
                        (migration_name,)
                    )
                    conn.commit()
                    print(f"✅ Successfully applied migration: {migration_name}")
                    any_migrations_run = True
                else:
                    print(f"❌ Failed to apply migration: {migration_name}")
                    conn.rollback()
                    return False
        
        if not any_migrations_run:
            print("\n✨ Database is up to date. No new migrations to run.")
        else:
            print("\n✨ All migrations completed successfully!")
        
        return True
        
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"❌ Database error during migrations: {e}")
        return False
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Unexpected error during migrations: {e}")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("\n🚀 Starting database migrations...")
    success = run_migrations()
    if not success:
        print("\n❌ Migrations failed. Please check the error messages above.")
        sys.exit(1)
