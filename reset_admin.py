import sqlite3
from werkzeug.security import generate_password_hash

def reset_admin_password():
    # Connect to the database
    conn = sqlite3.connect('kespo.db')
    cursor = conn.cursor()
    
    try:
        # Check if admin table exists
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Hash the password
        hashed_password = generate_password_hash('admin123')
        
        # Insert or update admin user
        cursor.execute("""
        INSERT OR REPLACE INTO admin (id, username, password, email)
        VALUES (1, 'admin', ?, 'admin@example.com')
        """, (hashed_password,))
        
        # Commit changes
        conn.commit()
        print("Admin password has been reset to 'admin123'")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    reset_admin_password()
