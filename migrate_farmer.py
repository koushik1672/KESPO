import sqlite3

def migrate_farmer_table():
    """Ensure all required columns exist in the farmer table."""
    conn = sqlite3.connect('kespo.db')
    cursor = conn.cursor()
    
    try:
        # Get existing columns
        cursor.execute("PRAGMA table_info(farmer)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Define required columns with their types and defaults
        required_columns = [
            ('role', 'TEXT DEFAULT "farmer"'),
            ('status', 'TEXT DEFAULT "active"'),
            ('trust_tier', 'TEXT DEFAULT "basic"'),
            ('failed_login_attempts', 'INTEGER DEFAULT 0'),
            ('last_login', 'TEXT'),
            ('photo', 'TEXT'),
            ('farm_name', 'TEXT'),
            ('farm_address', 'TEXT'),
            ('reset_token', 'TEXT'),
            ('reset_token_expiry', 'TEXT'),
            ('created_at', 'TEXT DEFAULT CURRENT_TIMESTAMP'),
            ('updated_at', 'TEXT DEFAULT CURRENT_TIMESTAMP')
        ]
        
        # Add any missing columns
        for col, col_type in required_columns:
            if col not in columns:
                print(f"Adding missing column: {col}")
                cursor.execute(f"ALTER TABLE farmer ADD COLUMN {col} {col_type}")
        
        conn.commit()
        print("Farmer table migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_farmer_table()
