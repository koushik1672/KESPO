from flask import Flask, render_template, request, redirect, session, flash, url_for
import sqlite3, os, json, sys
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import string
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
import time
import traceback

# ================= APP =================
app = Flask(__name__)
app.secret_key = "kespo_secret_key"

# Email configuration for Gmail SMTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'koushikreddykesari1@gmail.com'
app.config['MAIL_PASSWORD'] = 'pxpi mnud whpr vnxx'  # Your 16-digit app password
app.config['MAIL_DEFAULT_SENDER'] = 'koushikreddykesari1@gmail.com'
app.config['MAIL_DEBUG'] = True
app.config['SECURITY_PASSWORD_SALT'] = 'your-unique-password-salt-here'  # Change this to a random string in production

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "kespo.db")
UPLOADS = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOADS, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOADS
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# ================= DB HELPERS =================
def get_db_connection():
    """Get a database connection with proper settings and error handling."""
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(
                DB,
                timeout=30,              # wait up to 30 seconds
                check_same_thread=False, # allow multi-request
                isolation_level=None     # autocommit mode
            )
            conn.row_factory = sqlite3.Row
            
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            
            # Verify the database is not corrupted
            try:
                conn.execute("PRAGMA integrity_check;")
                return conn
            except sqlite3.DatabaseError as e:
                conn.close()
                if attempt == max_retries - 1:  # Last attempt
                    raise
                print(f"⚠️ Database corruption detected, attempting to recover (attempt {attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
                recover_database()
                
        except sqlite3.Error as e:
            if attempt == max_retries - 1:  # Last attempt
                print(f"❌ Failed to connect to database after {max_retries} attempts: {e}")
                raise
            time.sleep(retry_delay)
    
    # This should never be reached due to the raise above, but just in case
    raise sqlite3.DatabaseError("Failed to establish database connection")

def recover_database():
    """Attempt to recover from a corrupted database by creating a new one."""
    print("🚨 Attempting to recover from database corruption...")
    try:
        # Backup the corrupted database
        if os.path.exists(DB):
            backup_file = f"{DB}.corrupt.{int(time.time())}"
            import shutil
            shutil.copy2(DB, backup_file)
            print(f"⚠️ Created backup of corrupted database at {backup_file}")
        
        # Remove existing database files
        db_files = [DB, f"{DB}-shm", f"{DB}-wal", f"{DB}-journal"]
        for db_file in db_files:
            try:
                if os.path.exists(db_file):
                    os.remove(db_file)
            except Exception as e:
                print(f"⚠️ Could not remove {db_file}: {e}")
        
        # Reinitialize the database
        from db_setup import init_db
        init_db()
        print("✅ Successfully reinitialized the database")
        
    except Exception as e:
        print(f"❌ Failed to recover database: {e}")
        raise

def db():
    """Get a database connection (legacy function for backward compatibility)."""
    return get_db_connection()


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def update_database_schema():
    """Update the database schema to add any missing columns and tables."""
    c = db()
    cur = c.cursor()
    
    try:
        # Check if the columns exist in the farmer table
        cur.execute("PRAGMA table_info(farmer)")
        columns = [col[1] for col in cur.fetchall()]
        
        # Add missing columns if they don't exist
        if 'photo' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN photo TEXT")
        if 'farm_name' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN farm_name TEXT")
        if 'farm_address' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN farm_address TEXT")
        if 'created_at' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")
        if 'updated_at' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP")
        if 'reset_token' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN reset_token TEXT")
        if 'reset_token_expiry' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN reset_token_expiry TEXT")
        if 'status' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN status TEXT DEFAULT 'active'")
            # Update all existing users to have active status
            cur.execute("UPDATE farmer SET status = 'active' WHERE status IS NULL")
        
        # Create password_reset_tokens table if it doesn't exist
        cur.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT 0,
            UNIQUE(token)
        )
        """)
        
        c.commit()
        print("Database schema updated successfully")
    except Exception as e:
        c.rollback()
        print(f"Error updating database schema: {str(e)}")
    finally:
        c.close()

def init_db():
    update_database_schema()
    c = db()
    cur = c.cursor()

    # ---------- FARMER ----------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS farmer(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        phone TEXT,
        password TEXT,
        trust_tier TEXT DEFAULT 'basic',
        photo TEXT,
        farm_name TEXT,
        farm_address TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ---------- HARVEST ----------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS harvest(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farmer_id INTEGER,
        quantity TEXT,
        expected_price TEXT,
        image TEXT,
        harvest_date TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)

    # ---------- DEAL ----------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS deal(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        harvest_id INTEGER,
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
        created_at TEXT
    )
    """)

    # Add payment columns if they don't exist (for existing databases)
    for column in ['payment_status', 'payment_method', 'payment_reference', 'paid_at']:
        try:
            cur.execute(f"ALTER TABLE deal ADD COLUMN {column} TEXT")
            if column == 'payment_status':
                cur.execute("UPDATE deal SET payment_status='pending' WHERE payment_status IS NULL")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

    # ---------- PLATFORM CONFIG ----------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS platform_config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    cur.execute("""
    INSERT OR IGNORE INTO platform_config (key, value)
    VALUES ('commission_rate', '0.02')
    """)

    # ---------- ADMIN AUDIT LOG ----------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_email TEXT,
        action TEXT,
        entity_type TEXT,
        entity_id INTEGER,
        description TEXT,
        created_at TEXT
    )
    """)

    c.commit()
    c.close()

# ================= BUSINESS HELPERS =================
def get_commission_rate():
    c = db()
    cur = c.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key='commission_rate'")
    row = cur.fetchone()
    c.close()
    return float(row["value"]) if row else 0.02


def update_trust_tier(farmer_id):
    c = db()
    cur = c.cursor()

    cur.execute("""
        SELECT COUNT(*) AS total
        FROM deal d
        JOIN harvest h ON d.harvest_id = h.id
        WHERE h.farmer_id = ? AND d.status = 'completed'
    """, (farmer_id,))
    completed = cur.fetchone()["total"]

    if completed >= 15:
        tier = "elite"
    elif completed >= 7:
        tier = "trusted"
    elif completed >= 3:
        tier = "verified"
    else:
        tier = "basic"

    cur.execute(
        "UPDATE farmer SET trust_tier=? WHERE id=?",
        (tier, farmer_id)
    )

    c.commit()
    c.close()


def log_admin_action(action, entity_type, entity_id, description):
    c = db()
    cur = c.cursor()

    cur.execute("""
        INSERT INTO admin_audit_log
        (admin_email, action, entity_type, entity_id, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "admin@kespo.com",
        action,
        entity_type,
        entity_id,
        description,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    c.commit()
    c.close()

# ================= ROUTES =================
@app.route("/")
def root():
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").lower().strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        print("REGISTER ATTEMPT >>>", email)

        if not all([name, email, password, confirm_password]):
            flash("All fields are required", "error")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters long", "error")
            return redirect(url_for("register"))

        c = db()
        cur = c.cursor()

        try:
            # Check if email already exists
            cur.execute("SELECT id FROM farmer WHERE email = ?", (email,))
            if cur.fetchone():
                flash("Email already registered. Please login.", "error")
                c.close()
                return redirect(url_for("login"))

            hashed_password = generate_password_hash(password)

            cur.execute("""
                INSERT INTO farmer (
                    name, email, phone, password,
                    role, status, trust_tier,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'farmer', 'active', 'basic', datetime('now'), datetime('now'))
            """, (name, email, phone, hashed_password))

            c.commit()
            c.close()

            print("REGISTER SUCCESS >>>", email)
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            c.rollback()
            c.close()
            print("REGISTER ERROR >>>", e)
            flash("Registration failed. Please try again.", "error")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")
        
        if not email or not password:
            flash("Email and password are required", "error")
            return redirect("/login")
            
        try:
            c = db()
            cur = c.cursor()
            
            # Get user by email with account status check
            cur.execute("""
                SELECT * FROM farmer 
                WHERE email = ? AND status = 'active'
            """, (email,))
            
            farmer = cur.fetchone()
            
            # Rate limiting: Check for too many failed attempts
            if farmer and farmer["failed_login_attempts"] >= 5:

                # Account is temporarily locked
                lockout_time = 15  # minutes
                flash(f"Account temporarily locked. Try again in {lockout_time} minutes.", "error")
                c.close()
                return redirect("/login")
            
            # Verify password
            if farmer and check_password_hash(farmer["password"], password):
                # Reset failed login attempts on successful login
                cur.execute("""
                    UPDATE farmer 
                    SET failed_login_attempts = 0,
                        last_login = datetime('now'),
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (farmer["id"],))
                c.commit()
                
                # Set session variables
                session.clear()
                session["farmer_id"] = farmer["id"]
                session["farmer_name"] = farmer["name"]
                session["trust_tier"] = farmer["trust_tier"]

                
                # Log the login
                log_admin_action(
                    action="login", 
                    entity_type="farmer", 
                    entity_id=farmer["id"], 
                    description=f"Successful login from {request.remote_addr}"
                )
                
                # Redirect to intended URL or dashboard
                next_url = request.args.get('next') or '/dashboard'
                return redirect(next_url)
                
            else:
                # Increment failed login attempts
                if farmer:
                    cur.execute("""
                        UPDATE farmer 
                        SET failed_login_attempts = failed_login_attempts + 1,
                            updated_at = datetime('now')
                        WHERE id = ?
                    """, (farmer["id"],))
                    c.commit()
                
                # Log failed login attempt
                log_admin_action(
                    action="login_failed", 
                    entity_type="farmer", 
                    entity_id=farmer["id"] if farmer else None,
                    description=f"Failed login attempt for {email} from {request.remote_addr}"
                )
                
                flash("Invalid email or password", "error")
                
        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash("An error occurred during login. Please try again.", "error")
        finally:
            c.close()
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "farmer_id" not in session:
        flash("Please login to access your profile", "error")
        return redirect("/login")
    
    c = db()
    cur = c.cursor()
    
    try:
        if request.method == "POST":
            form_type = request.form.get("form_type")
            
            if form_type == "profile":
                # Handle profile update
                name = request.form.get("name")
                email = request.form.get("email")
                phone = request.form.get("phone")
                farm_name = request.form.get("farm_name", "")
                farm_address = request.form.get("farm_address", "")
                
                # Validate required fields
                if not all([name, email, phone]):
                    flash("Name, email, and phone are required fields", "error")
                    return redirect(url_for("profile"))
                
                # Handle profile picture upload
                photo_filename = None
                if 'profile_photo' in request.files:
                    file = request.files['profile_photo']
                    if file and file.filename != '':
                        if not allowed_file(file.filename):
                            flash("Invalid file type. Allowed types are: " + ", ".join(ALLOWED_EXTENSIONS), "error")
                            return redirect(url_for("profile"))
                            
                        # Generate a secure filename
                        filename = secure_filename(file.filename)
                        # Add timestamp to make filename unique
                        unique_filename = f"{int(time.time())}_{filename}"
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        
                        try:
                            file.save(filepath)
                            photo_filename = unique_filename
                            
                            # Delete old photo if exists - SAFE FETCH
                            cur.execute("SELECT photo FROM farmer WHERE id = ?", (session["farmer_id"],))
                            row = cur.fetchone()
                            old_photo = row["photo"] if row and "photo" in row else None
                            if old_photo:
                                try:
                                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_photo))
                                except OSError:
                                    pass  # Ignore if file doesn't exist
                            
                        except Exception as e:
                            app.logger.error(f"Error saving file: {str(e)}")
                            flash("Error uploading profile picture. Please try again.", "error")
                            return redirect(url_for("profile"))
                
                # Update database with new profile data
                update_query = """
                    UPDATE farmer SET 
                        name = ?, 
                        email = ?, 
                        phone = ?,
                        farm_name = ?,
                        farm_address = ?,
                        updated_at = ?
                """
                params = [
                    name, 
                    email, 
                    phone, 
                    farm_name, 
                    farm_address,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
                
                # Add photo to query if it was uploaded
                if photo_filename:
                    update_query = update_query.replace("farm_address = ?,", "farm_address = ?, photo = ?,")
                    params.insert(5, photo_filename)
                    # Only set photo in session if we have a new one
                    session["farmer_photo"] = photo_filename
                
                update_query += " WHERE id = ?"
                params.append(session["farmer_id"])
                
                try:
                    cur.execute(update_query, tuple(params))
                    c.commit()
                    
                    # Update session data - only set what we need
                    session["farmer_name"] = name
                    # Removed session["farmer_email"] as per FIX 3
                    
                    flash("Profile updated successfully!", "success")
                    return redirect(url_for("profile"))
                    
                except sqlite3.IntegrityError as e:
                    c.rollback()
                    if "UNIQUE constraint failed: farmer.email" in str(e):
                        flash("This email is already registered. Please use a different email.", "error")
                    else:
                        app.logger.error(f"Database error: {str(e)}")
                        flash("An error occurred while updating your profile. Please try again.", "error")
                    return redirect(url_for("profile"))
                
            elif form_type == "password":
                # Handle password change
                current_password = request.form.get("current_password")
                new_password = request.form.get("new_password")
                confirm_password = request.form.get("confirm_password")
                
                # Validate inputs
                if not all([current_password, new_password, confirm_password]):
                    flash("All fields are required", "error")
                    return redirect("#password")
                
                if new_password != confirm_password:
                    flash("New passwords do not match", "error")
                    return redirect("#password")
                
                if len(new_password) < 8:
                    flash("Password must be at least 8 characters long", "error")
                    return redirect("#password")
                
                # Verify current password
                cur.execute(
                    "SELECT password FROM farmer WHERE id = ?",
                    (session["farmer_id"],)
                )
                result = cur.fetchone()
                
                if not result or not check_password_hash(result["password"], current_password):
                    flash("Current password is incorrect", "error")
                    return redirect("#password")
                
                # Check if new password is different from current
                if check_password_hash(result["password"], new_password):
                    flash("New password must be different from current password", "error")
                    return redirect("#password")
                
                # Update password
                try:
                    hashed_password = generate_password_hash(new_password)
                    cur.execute(
                        """
                        UPDATE farmer 
                        SET password = ?, 
                            updated_at = ? 
                        WHERE id = ?
                        """,
                        (hashed_password, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session["farmer_id"])
                    )
                    c.commit()
                    
                    # Send email notification about password change
                    try:
                        msg = MIMEMultipart()
                        msg['From'] = app.config['MAIL_DEFAULT_SENDER']
                        msg['To'] = session["farmer_email"]
                        msg['Subject'] = 'Password Changed Successfully'
                        
                        body = f"""
                        <h2>Password Changed Successfully</h2>
                        <p>Hello {session['farmer_name']},</p>
                        <p>Your password was successfully changed on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</p>
                        <p>If you did not make this change, please contact support immediately.</p>
                        <br>
                        <p>Best regards,<br>KESPO Team</p>
                        """
                        
                        msg.attach(MIMEText(body, 'html'))
                        
                        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                            server.starttls()
                            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                            server.send_message(msg)
                    except Exception as e:
                        app.logger.error(f"Error sending email: {str(e)}")
                        # Don't fail the request if email fails
                    
                    flash("Password changed successfully! A confirmation email has been sent to your registered email address.", "success")
                    return redirect("#password")
                    
                except Exception as e:
                    c.rollback()
                    app.logger.error(f"Error updating password: {str(e)}")
                    flash("An error occurred while updating your password. Please try again.", "error")
                    return redirect("#password")
        
        # Get current user data for both GET and POST requests - SAFE USER FETCH
        cur.execute(
            """
            SELECT id, name, email, phone, photo, farm_name, farm_address, 
                   created_at, updated_at, trust_tier 
            FROM farmer 
            WHERE id = ?
            """,
            (session["farmer_id"],)
        )
        row = cur.fetchone()
        if not row:
            flash("User not found", "error")
            return redirect("/logout")
        user = dict(row)
        
        # Format dates for display
        if user.get('created_at'):
            user['created_at_formatted'] = datetime.strptime(user['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y')
        if user.get('updated_at'):
            user['updated_at_formatted'] = datetime.strptime(user['updated_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y')
        
        return render_template("profile.html", user=user)
        
    except Exception as e:
        print("PROFILE ERROR >>>", e)  # Added detailed error logging
        app.logger.error(f"Error in profile route: {str(e)}")
        flash("An error occurred while processing your request. Please try again.", "error")
        return redirect(url_for("profile"))
    
    finally:
        c.close()

@app.route("/dashboard")
def dashboard():
    if "farmer_id" not in session:
        flash("Please login to access your dashboard", "error")
        return redirect("/login")
    
    c = db()
    cur = c.cursor()
    cur.execute("SELECT trust_tier FROM farmer WHERE id=?", (session["farmer_id"],))
    tier = cur.fetchone()["trust_tier"]
    cur.execute("SELECT COUNT(*) FROM harvest WHERE farmer_id=?", (session["farmer_id"],))
    count = cur.fetchone()[0]
    c.close()

    return render_template(
        "dashboard.html",
        farmer_name=session["farmer_name"],
        trust_tier=tier,
        harvest_count=count
    )


@app.route("/upload", methods=["GET","POST"])
def upload():
    if "farmer_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        img = request.files["image"]
        img.save(os.path.join(UPLOADS, img.filename))

        c = db()
        cur = c.cursor()
        cur.execute("""
            INSERT INTO harvest
            (farmer_id, quantity, expected_price, image, harvest_date)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["farmer_id"],
            request.form["quantity"],
            request.form["price"],
            img.filename,
            request.form["date"]
        ))
        c.commit()
        c.close()
        return redirect("/dashboard")

    return render_template("upload_harvest.html")


@app.route("/my-harvests")
def my_harvests():
    if "farmer_id" not in session:
        return redirect("/login")

    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM harvest WHERE farmer_id=?", (session["farmer_id"],))
    rows = cur.fetchall()
    c.close()

    return render_template("my_harvests.html", harvests=rows)


@app.route("/edit-harvest/<int:id>", methods=["GET","POST"])
def edit_harvest(id):
    if "farmer_id" not in session:
        return redirect("/login")

    c = db()
    cur = c.cursor()
    cur.execute(
        "SELECT * FROM harvest WHERE id=? AND farmer_id=?",
        (id, session["farmer_id"])
    )
    h = cur.fetchone()

    if not h:
        c.close()
        return "Unauthorized", 403

    if request.method == "POST":
        cur.execute("""
            UPDATE harvest
            SET quantity=?, expected_price=?, harvest_date=?, status='pending'
            WHERE id=?
        """, (
            request.form["quantity"],
            request.form["price"],
            request.form["date"],
            id
        ))
        c.commit()
        c.close()
        return redirect("/my-harvests")

    c.close()
    return render_template("edit_harvest.html", harvest=h)


@app.route("/inbox")
def inbox():
    if "farmer_id" not in session:
        return redirect("/login")

    status = request.args.get("status")

    conn = db()
    cur = conn.cursor()

    query = """
        SELECT d.*, h.quantity, h.expected_price
        FROM deal d
        JOIN harvest h ON d.harvest_id = h.id
        WHERE h.farmer_id = ?
    """
    params = [session["farmer_id"]]

    if status:
        query += " AND d.status = ?"
        params.append(status)

    query += " ORDER BY d.created_at DESC"

    cur.execute(query, params)
    deals = cur.fetchall()

    conn.close()

    return render_template("inbox.html", deals=deals)



#============earnings==================



@app.route("/earnings")
def earnings():
    if "farmer_id" not in session:
        return redirect("/login")

    c = db()
    cur = c.cursor()

    # Summary of completed deals
    cur.execute("""
        SELECT 
            COUNT(*) AS total_deals,
            IFNULL(SUM(farmer_net), 0) AS total_earned,
            IFNULL(SUM(commission), 0) AS total_commission
        FROM deal d
        JOIN harvest h ON d.harvest_id = h.id
        WHERE h.farmer_id = ? AND d.status = 'completed'
    """, (session["farmer_id"],))
    summary = cur.fetchone()

    # Full deal history
    cur.execute("""
        SELECT d.*, h.quantity, h.expected_price
        FROM deal d
        JOIN harvest h ON d.harvest_id = h.id
        WHERE h.farmer_id = ?
        ORDER BY d.created_at DESC
    """, (session["farmer_id"],))
    deals = cur.fetchall()

    c.close()

    return render_template(
        "earnings.html",
        summary=summary,
        deals=deals
    )


# ================= BUYER =================
@app.route("/buyer")
def buyer():
    min_p = request.args.get("min_price")
    max_p = request.args.get("max_price")
    min_q = request.args.get("min_qty")
    sort = request.args.get("sort")

    query = """
        SELECT h.*, f.name, f.trust_tier
        FROM harvest h
        JOIN farmer f ON h.farmer_id = f.id
        WHERE h.status = 'approved'
    """
    params = []

    # ---------- FILTERS ----------
    if min_p:
        query += " AND CAST(h.expected_price AS INTEGER) >= ?"
        params.append(min_p)

    if max_p:
        query += " AND CAST(h.expected_price AS INTEGER) <= ?"
        params.append(max_p)

    if min_q:
        query += " AND CAST(h.quantity AS INTEGER) >= ?"
        params.append(min_q)

    # ---------- SORTING ----------
    if sort == "price_asc":
        query += " ORDER BY CAST(h.expected_price AS INTEGER) ASC"
    elif sort == "price_desc":
        query += " ORDER BY CAST(h.expected_price AS INTEGER) DESC"
    elif sort == "qty_asc":
        query += " ORDER BY CAST(h.quantity AS INTEGER) ASC"
    elif sort == "qty_desc":
        query += " ORDER BY CAST(h.quantity AS INTEGER) DESC"
    elif sort == "trust":
        query += """
            ORDER BY CASE f.trust_tier
                WHEN 'elite' THEN 4
                WHEN 'trusted' THEN 3
                WHEN 'verified' THEN 2
                ELSE 1
            END DESC
        """
    else:
        query += " ORDER BY h.harvest_date DESC"

    conn = db()
    cur = conn.cursor()
    cur.execute(query, params)
    harvests = cur.fetchall()
    conn.close()

    return render_template(
        "buyer_dashboard.html",
        harvests=harvests,
        min_price=min_p,
        max_price=max_p,
        min_qty=min_q,
        sort=sort
    )


# ================= DEAL =================
@app.route("/initiate-deal/<int:hid>", methods=["POST"])
def initiate_deal(hid):
    c = db()
    cur = c.cursor()

    cur.execute("SELECT quantity, expected_price FROM harvest WHERE id=?", (hid,))
    h = cur.fetchone()

    value = float(h["quantity"]) * 1000 * float(h["expected_price"])
    rate = get_commission_rate()
    commission = value * rate
    net = value - commission

    cur.execute("""
        INSERT INTO deal
        (harvest_id, buyer_name, buyer_email, deal_value,
         commission, farmer_net, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'initiated', ?)
    """, (
        hid,
        request.form["name"],
        request.form["email"],
        value,
        commission,
        net,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    c.commit()
    c.close()
    return redirect("/buyer")


@app.route("/deal/delivered/<int:id>")
def delivered(id):
    if "farmer_id" not in session:
        return redirect("/login")

    c = db()
    cur = c.cursor()
    cur.execute("UPDATE deal SET status='delivered' WHERE id=?", (id,))
    c.commit()
    c.close()
    return redirect("/inbox")


@app.route("/deal/complete/<int:id>")
def complete(id):
    if session.get("role") != "admin":

        return redirect("/admin/login")

    c = db()
    cur = c.cursor()

    cur.execute("UPDATE deal SET status='completed' WHERE id=?", (id,))

    cur.execute("""
        SELECT h.farmer_id
        FROM deal d
        JOIN harvest h ON d.harvest_id = h.id
        WHERE d.id=?
    """, (id,))
    farmer_id = cur.fetchone()["farmer_id"]

    c.commit()
    c.close()

    update_trust_tier(farmer_id)

    log_admin_action(
        "COMPLETE", "deal", id, "Deal marked completed by admin"
    )

    return redirect("/admin/dashboard")

# ================= ADMIN  login =================
def admin_required():
    if session.get("role") != "admin":

        return redirect("/admin/login")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if email == "admin@kespo.com" and password == "admin123":
            session["is_admin"] = True   # ✅ DO NOT clear session
            return redirect("/admin/dashboard")

        return render_template(
            "admin_login.html",
            error="Invalid admin credentials"
        )

    return render_template("admin_login.html")


#===============admin dashboard================
@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect("/admin/login")

    conn = db()
    cur = conn.cursor()

    # Pending harvest approvals
    cur.execute("""
        SELECT h.*, f.name AS farmer_name
        FROM harvest h
        JOIN farmer f ON h.farmer_id = f.id
        WHERE h.status = 'pending'
        ORDER BY h.harvest_date DESC
    """)
    harvests = cur.fetchall()

    # Delivered deals (ready for payment)
    status = request.args.get("status", "delivered")
    cur.execute("""
        SELECT *
        FROM deal
        WHERE status = ?
        ORDER BY created_at DESC
    """, (status,))
    deals = cur.fetchall()


    # Dashboard stats
    cur.execute("SELECT COUNT(*) FROM farmer")
    total_farmers = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM harvest WHERE status='pending'")
    pending_harvests = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM deal WHERE status='delivered'")
    delivered_deals = cur.fetchone()[0]

    cur.execute("SELECT IFNULL(SUM(commission),0) FROM deal WHERE status='completed'")
    total_commission = cur.fetchone()[0]

    # Farmer list
    cur.execute("""
        SELECT f.id, f.name, f.email, f.trust_tier,
               COUNT(h.id) AS harvest_count
        FROM farmer f
        LEFT JOIN harvest h ON f.id = h.farmer_id
        GROUP BY f.id
    """)
    farmers = cur.fetchall()

    cur.close()
    conn.close()

    users = []
    recent_activity = []



    return render_template(
        "admin_dashboard.html",
        harvests=harvests,
        deals=deals,
        users=users or [],
        recent_activity=recent_activity or [],
        total_farmers=total_farmers,
        pending_harvests=pending_harvests,
        delivered_deals=delivered_deals,
        total_commission=total_commission
    )


@app.route("/admin/approve/<int:id>")
def approve(id):
    if not session.get("is_admin"):
        return redirect("/admin/login")

    conn = db()
    cur = conn.cursor()
    
    # Update harvest status to approved
    cur.execute("UPDATE harvest SET status='approved' WHERE id=?", (id,))
    
    # Log the admin action
    cur.execute("""
        INSERT INTO admin_logs (admin_id, action, target_type, target_id, details)
        VALUES (?, 'APPROVE', 'harvest', ?, 'Harvest approved')
    """, (session.get("admin_id"), id))
    
    conn.commit()
    cur.close()
    conn.close()

    return redirect("/admin/dashboard")


@app.route("/admin/mark-paid/<int:id>")
def mark_paid(id):
    if not session.get("is_admin"):
        return redirect("/admin/login")

    conn = db()
    cur = conn.cursor()
    
    # Update deal payment status
    cur.execute("""
        UPDATE deal
        SET payment_status='paid',
            payment_method='manual',
            paid_at=?
        WHERE id=?
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id))
    
    # Log the admin action
    cur.execute("""
        INSERT INTO admin_logs (admin_id, action, target_type, target_id, details)
        VALUES (?, 'PAYMENT', 'deal', ?, 'Deal marked as paid to farmer')
    """, (session.get("admin_id"), id))
    
    conn.commit()
    cur.close()
    conn.close()

    return redirect("/admin/dashboard")



@app.route("/admin/audit")
def admin_audit():
    if not session.get("is_admin"):
        return redirect("/admin/login")

    action = request.args.get("action")
    entity = request.args.get("entity")

    query = "SELECT * FROM admin_audit_log WHERE 1=1"
    params = []

    if action:
        query += " AND action = ?"
        params.append(action)

    if entity:
        query += " AND entity_type = ?"
        params.append(entity)

    query += " ORDER BY created_at DESC LIMIT 200"

    conn = db()
    cur = conn.cursor()
    cur.execute(query, params)
    logs = cur.fetchall()
    conn.close()

    return render_template(
        "admin_audit.html",
        logs=logs,
        action=action,
        entity=entity
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect("/admin/login")


# ================= RUN =================
@app.route("/change-password", methods=["POST"])
def change_password():
    if "farmer_id" not in session:
        return redirect("/login")
    
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")
    
    # Input validation
    if not all([current_password, new_password, confirm_password]):
        flash("All fields are required", "error")
        return redirect("/profile")
    
    if new_password != confirm_password:
        flash("New passwords do not match", "error")
        return redirect("/profile")
    
    if len(new_password) < 8:
        flash("Password must be at least 8 characters long", "error")
        return redirect("/profile")
    
    c = db()
    cur = c.cursor()
    
    try:
        # Get current password hash
        cur.execute(
            "SELECT password FROM farmer WHERE id = ?",
            (session["farmer_id"],)
        )
        result = cur.fetchone()
        
        if not result or not check_password_hash(result["password"], current_password):
            flash("Current password is incorrect", "error")
            return redirect("/profile")
        
        # Update password with hashed version
        hashed_password = generate_password_hash(new_password)
        cur.execute(
            "UPDATE farmer SET password = ? WHERE id = ?",
            (hashed_password, session["farmer_id"])
        )
        c.commit()
        flash("Password updated successfully", "success")
        
    except Exception as e:
        c.rollback()
        flash("An error occurred while updating your password", "error")
    finally:
        c.close()
    
    return redirect("/profile")

# Initialize the serializer after app.config is set
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

def generate_token(email):
    """Generate a secure token for password reset"""
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])

def confirm_token(token, expiration=3600):
    """Verify the token and return the email if valid"""
    try:
        email = serializer.loads(
            token,
            salt=app.config['SECURITY_PASSWORD_SALT'],
            max_age=expiration
        )
        return email
    except (SignatureExpired, BadSignature):
        return None

def send_reset_email(email, token):
    """Send password reset email to the user using Gmail SMTP"""
    try:
        reset_url = url_for('reset_password', token=token, _external=True)
        
        # Get user's name for personalization
        c = db()
        cur = c.cursor()
        cur.execute("SELECT name FROM farmer WHERE email = ?", (email,))
        user = cur.fetchone()
        user_name = user['name'] if user else 'User'
        c.close()
        
        # Email content with HTML formatting
        subject = 'Password Reset Request'
        
        msg = MIMEMultipart()
        msg['From'] = app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = email
        msg['Subject'] = subject
        
        body = f"""
        <h2>Password Reset Request</h2>
        <p>Hello {user_name},</p>
        <p>You have requested to reset your password. Click the link below to proceed:</p>
        <p><a href='{reset_url}' style='color: #4CAF50; text-decoration: none;'>{reset_url}</a></p>
        <p>This link will expire in 1 hour.</p>
        <p>If you didn't request this, please ignore this email.</p>
        <p>Best regards,<br>KESPO Team</p>
        """
        
        # Add HTML body to email
        msg.attach(MIMEText(body, 'html'))
        
        # Create SMTP session
        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            server.starttls()
            server.login(
                app.config['MAIL_USERNAME'],
                app.config['MAIL_PASSWORD']
            )
            server.send_message(msg)
            
        app.logger.info(f"Password reset email sent to {email}")
        return True
        
    except Exception as e:
        app.logger.error(f"Error sending email to {email}: {str(e)}")
        return False

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle password reset request"""
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        if not email:
            flash('Email is required', 'error')
            return redirect(url_for('forgot_password'))
            
        c = db()
        try:
            # Check if user exists
            cur = c.cursor()
            cur.execute("SELECT id, name FROM farmer WHERE email = ?", (email,))
            user = cur.fetchone()
            
            if user:
                # Generate a secure token
                token = secrets.token_urlsafe(32)
                expires_at = datetime.now() + timedelta(hours=1)
                
                # Store token in database
                cur.execute("""
                    INSERT INTO password_reset_tokens (email, token, expires_at)
                    VALUES (?, ?, ?)
                """, (email, token, expires_at))
                c.commit()
                
                # Generate reset URL
                reset_url = url_for('reset_password', token=token, _external=True)
                
                # Send email with reset link
                msg = MIMEMultipart()
                msg['From'] = app.config['MAIL_DEFAULT_SENDER']
                msg['To'] = email
                msg['Subject'] = 'Password Reset Request - KESPO'
                
                body = f"""
                <h2>Password Reset Request</h2>
                <p>Hello {user['name']},</p>
                <p>You have requested to reset your password. Click the link below to proceed:</p>
                <p><a href='{reset_url}' style='color: #4CAF50; text-decoration: none;'>{reset_url}</a></p>
                <p>This link will expire in 1 hour.</p>
                <p>If you didn't request this, please ignore this email.</p>
                <p>Best regards,<br>KESPO Team</p>
                """
                
                msg.attach(MIMEText(body, 'html'))
                
                try:
                    with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                        server.starttls()
                        server.login(
                            app.config['MAIL_USERNAME'],
                            app.config['MAIL_PASSWORD']
                        )
                        server.send_message(msg)
                    flash('If an account exists with this email, a password reset link has been sent', 'info')
                except Exception as e:
                    app.logger.error(f"Failed to send email to {email}: {str(e)}")
                    flash('Failed to send reset email. Please try again later.', 'error')
            else:
                # Don't reveal if email exists or not
                flash('If an account exists with this email, a password reset link has been sent', 'info')
                
        except Exception as e:
            app.logger.error(f"Error in forgot_password: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
        finally:
            c.close()
            
        return redirect(url_for('login'))
        
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset with token"""
    c = db()
    try:
        # Check if token is valid and not expired
        cur = c.cursor()
        cur.execute("""
            SELECT email FROM password_reset_tokens 
            WHERE token = ? AND used = 0 AND expires_at > datetime('now')
        """, (token,))
        
        token_data = cur.fetchone()
        if not token_data:
            flash('The reset link is invalid or has expired', 'error')
            return redirect(url_for('forgot_password'))
            
        email = token_data['email']
        
        if request.method == 'POST':
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            if not password or not confirm_password:
                flash('Both password fields are required', 'error')
                return redirect(request.url)
                
            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return redirect(request.url)
                
            if len(password) < 8:
                flash('Password must be at least 8 characters long', 'error')
                return redirect(request.url)
                
            try:
                # Update password
                hashed_password = generate_password_hash(password)
                cur.execute("""
                    UPDATE farmer 
                    SET password = ?, 
                        updated_at = datetime('now')
                    WHERE email = ?
                """, (hashed_password, email))
                
                # Mark token as used
                cur.execute("""
                    UPDATE password_reset_tokens 
                    SET used = 1 
                    WHERE token = ?
                """, (token,))
                
                c.commit()
                
                flash('Your password has been reset successfully. You can now log in with your new password.', 'success')
                return redirect(url_for('login'))
                
            except Exception as e:
                c.rollback()
                app.logger.error(f"Error resetting password for {email}: {str(e)}")
                flash('An error occurred while resetting your password', 'error')
        
        return render_template('reset_password.html', token=token)
        
    except Exception as e:
        app.logger.error(f"Error in reset_password: {str(e)}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('forgot_password'))
    finally:
        c.close()

def ensure_admin():
    """Ensure admin user exists in the database."""
    c = db()
    try:
        cur = c.cursor()
        cur.execute("SELECT id FROM farmer WHERE email = ?", ("admin@kespo.com",))
        if not cur.fetchone():
            from werkzeug.security import generate_password_hash
            cur.execute("""
                INSERT INTO farmer (name, email, password, role, status, created_at, updated_at)
                VALUES (?, ?, ?, 'admin', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                "Admin User",
                "admin@kespo.com",
                generate_password_hash("admin123")
            ))
            c.commit()
            print("✅ Admin user created successfully")
        else:
            print("✅ Admin user already exists")
    finally:
        c.close()

def ensure_db_initialized():
    """Ensure database is properly initialized and migrated."""
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            # Check if database exists, if not create it
            if not os.path.exists(DB):
                print("🚀 Initializing new database...")
                from db_setup import init_db
                init_db()
            
            # Verify database is not corrupted
            try:
                conn = get_db_connection()
                conn.execute("PRAGMA integrity_check;")
                conn.close()
            except sqlite3.DatabaseError as e:
                if attempt == max_attempts - 1:  # Last attempt
                    print(f"❌ Database is corrupted and could not be recovered: {e}")
                    raise
                print(f"⚠️ Database corruption detected, attempting recovery (attempt {attempt + 1}/{max_attempts})...")
                recover_database()
                continue
            
            # Run migrations
            print("🔄 Running database migrations...")
            from migrations import run_migrations
            if not run_migrations():
                raise RuntimeError("Database migrations failed")
            
            # Ensure admin user exists
            ensure_admin()
            
            print("✨ Database initialization completed successfully!")
            return
            
        except sqlite3.DatabaseError as e:
            if attempt == max_attempts - 1:  # Last attempt
                print(f"❌ Failed to initialize database after {max_attempts} attempts: {e}")
                import traceback
                traceback.print_exc()
                sys.exit(1)
            print(f"⚠️ Database error, retrying... (attempt {attempt + 1}/{max_attempts})")
            import time
            time.sleep(1)  # Wait before retry
            
        except Exception as e:
            print(f"❌ Unexpected error during database initialization: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    import os
    init_db()   # 👈 REQUIRED for Render
    ensure_admin()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


