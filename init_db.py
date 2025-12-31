import os
import sqlite3
from datetime import datetime

def init_db():
    db_path = 'kespo.db'
    
    # Remove existing database if it exists
    if os.path.exists(db_path):
        os.remove(db_path)
        print("Removed existing database")
    
    # Connect to SQLite database (creates a new database if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Create farmer table with all required columns
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS farmer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password TEXT NOT NULL,
        trust_tier TEXT DEFAULT 'basic',
        photo TEXT,
        farm_name TEXT,
        farm_address TEXT,
        status TEXT DEFAULT 'active',
        last_login TEXT,
        failed_login_attempts INTEGER DEFAULT 0,
        reset_token TEXT,
        reset_token_expiry TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_status CHECK (status IN ('active', 'suspended', 'deleted'))
    )
    """)
    
    # Create other necessary tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS harvest (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farmer_id INTEGER,
        crop_type TEXT NOT NULL,
        quantity REAL NOT NULL,
        unit TEXT NOT NULL,
        price_per_unit REAL NOT NULL,
        location TEXT,
        description TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farmer_id) REFERENCES farmer (id)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        harvest_id INTEGER,
        buyer_id INTEGER,
        seller_id INTEGER,
        quantity REAL NOT NULL,
        price_per_unit REAL NOT NULL,
        total_amount REAL NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (harvest_id) REFERENCES harvest (id),
        FOREIGN KEY (buyer_id) REFERENCES farmer (id),
        FOREIGN KEY (seller_id) REFERENCES farmer (id)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id INTEGER,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (admin_id) REFERENCES admin (id)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create an admin user (you should change this password in production)
    admin_password = "admin123"  # In production, use a secure password hashing
    cursor.execute(
        "INSERT OR IGNORE INTO admin (username, password, email) VALUES (?, ?, ?)",
        ("admin", admin_password, "admin@example.com")
    )
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print("Database initialized successfully!")

if __name__ == "__main__":
    init_db()
