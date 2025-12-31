import sqlite3
import os
from datetime import datetime

def run_migration():
    # Connect to the database
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'kespo.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Add new columns to farmer table if they don't exist
        cursor.execute("PRAGMA table_info(farmer)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'phone' not in columns:
            cursor.execute("ALTER TABLE farmer ADD COLUMN phone TEXT")
        if 'photo' not in columns:
            cursor.execute("ALTER TABLE farmer ADD COLUMN photo TEXT")
        if 'farm_name' not in columns:
            cursor.execute("ALTER TABLE farmer ADD COLUMN farm_name TEXT")
        if 'farm_address' not in columns:
            cursor.execute("ALTER TABLE farmer ADD COLUMN farm_address TEXT")

        # Create buyer table if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS buyer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            phone TEXT,
            photo TEXT,
            delivery_address TEXT,
            FOREIGN KEY (user_id) REFERENCES farmer (id) ON DELETE CASCADE
        )
        """)

        # Create migration log table if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Log this migration
        cursor.execute(
            "INSERT OR IGNORE INTO migrations (name) VALUES (?)",
            ('001_add_profile_fields',)
        )

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {str(e)}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
