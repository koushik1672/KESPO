import sqlite3
import os
from datetime import datetime

def apply_migration():
    """Add payment tracking columns to the deal table."""
    db_path = os.path.join(os.path.dirname(__file__), '..', 'kespo.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(deal)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add amount_paid if it doesn't exist
        if 'amount_paid' not in columns:
            cursor.execute("""
                ALTER TABLE deal 
                ADD COLUMN amount_paid REAL DEFAULT 0
            """)
            print("✅ Added amount_paid column to deal table")
        
        # Add payment_status if it doesn't exist
        if 'payment_status' not in columns:
            cursor.execute("""
                ALTER TABLE deal 
                ADD COLUMN payment_status TEXT DEFAULT 'pending'
            """)
            print("✅ Added payment_status column to deal table")
        
        # Add payment_history table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                upi_transaction_id TEXT,
                notes TEXT,
                verified_by INTEGER,
                verified_at TIMESTAMP,
                FOREIGN KEY (deal_id) REFERENCES deal (id),
                FOREIGN KEY (verified_by) REFERENCES admin (id)
            )
        """)
        print("✅ Created payment_history table")
        
        conn.commit()
        print("✅ Migration completed successfully")
        
    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("🚀 Applying migration: Add payment tracking columns")
    apply_migration()
