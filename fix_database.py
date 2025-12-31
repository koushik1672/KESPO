import os
import sqlite3
from werkzeug.security import generate_password_hash

def create_fresh_database():
    # Remove existing database files
    for db_file in ['kespo.db', 'kespo.db-shm', 'kespo.db-wal']:
        try:
            if os.path.exists(db_file):
                os.rename(db_file, f"{db_file}.corrupt")
                print(f"Moved {db_file} to {db_file}.corrupt")
        except Exception as e:
            print(f"Error handling {db_file}: {e}")

    # Create new database with schema
    conn = sqlite3.connect('kespo.db')
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Create farmer table
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
    
    # Create other necessary tables
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS harvest (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farmer_id INTEGER NOT NULL,
        quantity TEXT,
        expected_price TEXT,
        image TEXT,
        harvest_date TEXT,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY (farmer_id) REFERENCES farmer(id)
    );

    CREATE TABLE IF NOT EXISTS deal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        harvest_id INTEGER NOT NULL,
        buyer_name TEXT,
        buyer_email TEXT,
        deal_value REAL,
        commission REAL,
        farmer_net REAL,
        status TEXT DEFAULT 'initiated',
        payment_status TEXT DEFAULT 'pending',
        payment_method TEXT,
        payment_reference TEXT,
        paid_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (harvest_id) REFERENCES harvest(id)
    );

    CREATE TABLE IF NOT EXISTS admin_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_email TEXT,
        action TEXT,
        entity_type TEXT,
        entity_id INTEGER,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS platform_config (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    
    INSERT OR IGNORE INTO platform_config (key, value) VALUES ('commission_rate', '0.02');
    """)
    
    conn.commit()
    conn.close()
    print("\nFresh database created successfully!")
    print("Admin credentials:")
    print("Email: admin@kespo.com")
    print("Password: admin123")

if __name__ == "__main__":
    print("Creating fresh database...")
    create_fresh_database()
