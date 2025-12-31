import os
import sqlite3
from werkzeug.security import generate_password_hash

def delete_existing_db():
    """Remove existing database files."""
    db_files = ['kespo.db', 'kespo.db-wal', 'kespo.db-shm']
    for db_file in db_files:
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
                print(f"Removed {db_file}")
        except Exception as e:
            print(f"Error removing {db_file}: {e}")

def create_schema():
    """Create a fresh database with the correct schema."""
    conn = sqlite3.connect('kespo.db')
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Create farmer table with all required columns and defaults
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS farmer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'farmer',
        status TEXT DEFAULT 'active',
        trust_tier TEXT DEFAULT 'basic',
        failed_login_attempts INTEGER DEFAULT 0,
        last_login TEXT,
        photo TEXT,
        farm_name TEXT,
        farm_address TEXT,
        reset_token TEXT,
        reset_token_expiry TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create admin user
    hashed_password = generate_password_hash('admin123')
    cursor.execute("""
    INSERT OR IGNORE INTO farmer (name, email, password, role, status)
    VALUES (?, ?, ?, 'admin', 'active')
    """, ('Admin User', 'admin@kespo.com', hashed_password))
    
    conn.commit()
    conn.close()
    print("Database schema created successfully!")

if __name__ == "__main__":
    print("Resetting database...")
    delete_existing_db()
    create_schema()
    print("Database reset complete. You can now start the application.")
