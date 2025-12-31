import os
import sqlite3
import sys
import traceback
from werkzeug.security import generate_password_hash

def remove_db_files():
    """Remove all database files to ensure clean state."""
    db_files = ['kespo.db', 'kespo.db-shm', 'kespo.db-wal', 'kespo.db-journal']
    for db_file in db_files:
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
                print(f"Removed existing {db_file}")
        except Exception as e:
            print(f"Warning: Could not remove {db_file}: {e}")

def init_db():
    """Initialize a fresh database with schema and default data."""
    # Remove existing database files to prevent corruption
    remove_db_files()
    
    try:
        # Create new database with schema
        conn = sqlite3.connect('kespo.db', timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        cursor = conn.cursor()
        
        # Enable foreign keys and other pragmas
        cursor.execute("PRAGMA foreign_keys = ON")
    
    # Create tables
        # Create tables in a transaction to ensure all or nothing
        cursor.executescript("""
        BEGIN TRANSACTION;

    -- FARMER TABLE
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
    );

    -- HARVEST TABLE
    CREATE TABLE IF NOT EXISTS harvest (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farmer_id INTEGER NOT NULL,
        quantity TEXT,
        expected_price TEXT,
        image TEXT,
        harvest_date TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farmer_id) REFERENCES farmer(id) ON DELETE CASCADE
    );

    -- DEAL TABLE
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
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (harvest_id) REFERENCES harvest(id) ON DELETE CASCADE
    );

    -- ADMIN AUDIT LOG
    CREATE TABLE IF NOT EXISTS admin_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_email TEXT,
        action TEXT,
        entity_type TEXT,
        entity_id INTEGER,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- PASSWORD RESET TOKENS
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(token, email)
    );

    -- PLATFORM CONFIG
    CREATE TABLE IF NOT EXISTS platform_config (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- MIGRATION VERSIONS
    CREATE TABLE IF NOT EXISTS migration_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        migration_name TEXT UNIQUE NOT NULL,
        applied_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

        COMMIT;
        """)
    
        # Insert default config if not exists
        cursor.execute("""
        INSERT OR IGNORE INTO platform_config (key, value, updated_at)
        VALUES 
            ('commission_rate', '0.02', CURRENT_TIMESTAMP),
            ('site_name', 'Kespo', CURRENT_TIMESTAMP),
            ('currency', 'KES', CURRENT_TIMESTAMP);
        """)
        
        # Create admin user if not exists
        hashed_password = generate_password_hash('admin123')
        cursor.execute("""
        INSERT OR IGNORE INTO farmer (name, email, password, role, status, created_at, updated_at)
        VALUES (?, ?, ?, 'admin', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, ('Admin User', 'admin@kespo.com', hashed_password))
        
        # Record initial migration
        cursor.execute("""
        INSERT OR IGNORE INTO migration_versions (migration_name)
        VALUES ('initial_schema')
        """)
        
        conn.commit()
        print("✅ Database initialized successfully!")
        
    except sqlite3.Error as e:
        conn.rollback()
        print(f"❌ Error initializing database: {e}")
        traceback.print_exc()
        # Remove corrupted database files
        conn.close()
        remove_db_files()
        sys.exit(1)
    except Exception as e:
        conn.rollback()
        print(f"❌ Unexpected error: {e}")
        traceback.print_exc()
        conn.close()
        remove_db_files()
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🚀 Initializing database...")
    init_db()
    print("✨ Database setup completed!")
