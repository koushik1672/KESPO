"""Add password_reset_tokens table"""

def upgrade(db):
    db.execute("""
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        used BOOLEAN DEFAULT 0,
        FOREIGN KEY (email) REFERENCES farmer (email) ON DELETE CASCADE
    )
    """)

def downgrade(db):
    db.execute("DROP TABLE IF EXISTS password_reset_tokens")
