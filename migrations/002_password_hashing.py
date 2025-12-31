import sqlite3
import os
from werkzeug.security import generate_password_hash

def run_migration():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'kespo.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check if password_hash column already exists
        cursor.execute("PRAGMA table_info(farmer)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'password_hash' not in columns:
            # Add the new column
            cursor.execute("ALTER TABLE farmer ADD COLUMN password_hash TEXT")
            
            # Hash all existing passwords and store them in password_hash
            cursor.execute("SELECT id, password FROM farmer WHERE password_hash IS NULL")
            farmers = cursor.fetchall()
            
            for farmer in farmers:
                hashed_password = generate_password_hash(farmer['password'])
                cursor.execute(
                    "UPDATE farmer SET password_hash = ? WHERE id = ?",
                    (hashed_password, farmer['id'])
                )
            
            conn.commit()
            print("✅ Password hashing migration completed successfully!")
        else:
            print("ℹ️ Password hashing already applied, skipping...")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {str(e)}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
