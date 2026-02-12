from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import json
from datetime import datetime, timedelta
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
import qrcode
from io import BytesIO
import base64
import os
from itsdangerous import URLSafeTimedSerializer
from werkzeug.exceptions import RequestEntityTooLarge


# ================= APP =================
app = Flask(__name__)

# Max upload size: 5 MB (adjust if needed)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

app.secret_key = "kespo_secret_key"

# Email configuration for Gmail SMTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'koushikreddykesari1@gmail.com'
app.config['MAIL_PASSWORD'] = 'pxpi mnud whpr vnxx'  # App-specific password
app.config['MAIL_DEFAULT_SENDER'] = 'koushikreddykesari1@gmail.com'  # Add this line
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
app.config['MAIL_DEBUG'] = True

# UPI Payment Configuration
UPI_ID = "koushikreddykesari1@oksbi"
UPI_NAME = "KESPO"
UPI_MAX_LIMIT = 99999  # Maximum UPI transaction limit
app.config['MAIL_DEBUG'] = True
app.config['SECURITY_PASSWORD_SALT'] = 'your-unique-password-salt-here'  # Change this to a random string in production

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "kespo.db")
UPLOADS = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOADS, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOADS
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# UPI Configuration
UPI_ID = "koushikreddykesari1@oksbi"
UPI_NAME = "KESPO"

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

def db():
    """Get a database connection (legacy function for backward compatibility)."""
    return get_db_connection()


# ================= AUTH HELPERS =================
from functools import wraps

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "farmer_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view

def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Admin access required.', 'danger')
            return redirect('/admin/login')
        return view_func(*args, **kwargs)
    return wrapped_view

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



def update_database_schema():
    """Update the database schema to add any missing columns and tables."""
    c = db()
    cur = c.cursor()
    
    # Add payment tracking columns if they don't exist
    try:
        cur.execute("""
        ALTER TABLE deal 
        ADD COLUMN amount_paid REAL DEFAULT 0,
        ADD COLUMN payment_status TEXT DEFAULT 'pending'
        """)
        c.commit()
        print("Added payment tracking columns to deal table")
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e):
            print(f"Error updating schema: {e}")
    
    # Ensure payment_status has a valid value
    try:
        cur.execute("""
        UPDATE deal 
        SET payment_status = 'pending' 
        WHERE payment_status IS NULL OR payment_status NOT IN ('pending', 'partial', 'paid')
        """)
        c.commit()
    except Exception as e:
        print(f"Error updating payment statuses: {e}")
    
    c.close()
    
    try:
        # Check if the columns exist in the farmer table
        cur.execute("PRAGMA table_info(farmer)")
        columns = [col[1] for col in cur.fetchall()]
        
        # Add missing columns if they don't exist
        if 'photo' not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN photo TEXT")

        if "trust_tier" not in columns:
            cur.execute("ALTER TABLE farmer ADD COLUMN trust_tier TEXT DEFAULT 'Bronze'")

        # Deal table extensions (split payments)
        cur.execute("PRAGMA table_info(deal)")
        deal_cols = [col[1] for col in cur.fetchall()]

        if "amount_paid" not in deal_cols:
            cur.execute("ALTER TABLE deal ADD COLUMN amount_paid REAL DEFAULT 0")

        if "payment_status" not in deal_cols:
            cur.execute("ALTER TABLE deal ADD COLUMN payment_status TEXT DEFAULT 'pending'")

        # Create payment_history table if it doesn't exist
        cur.execute("""
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

        print("✅ Database schema verified/updated successfully")

    except Exception as e:
        # DO NOT rollback — SQLite autocommit is enabled
        print("❌ Schema update error:", e)

    finally:
        try:
            conn.close()
        except:
            pass

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
def generate_upi_qr(amount, note, upi_id=UPI_ID, upi_name=UPI_NAME):
    """
    Generate a UPI payment QR code as base64 encoded image.
    
    Args:
        amount (float): Payment amount (will be rounded to 2 decimal places)
        note (str): Payment note/reference
        upi_id (str): UPI ID to receive payment (default: from config)
        upi_name (str): Name associated with UPI ID (default: from config)
        
    Returns:
        str: Base64 encoded PNG image data with data URL prefix
    """
    # Format amount with 2 decimal places
    amount_str = f"{float(amount):.2f}"
    
    # Create UPI deep link with proper encoding
    upi_uri = (
        f"upi://pay?"
        f"pa={upi_id}&"
        f"pn={upi_name.replace(' ', '%20')}&"
        f"am={amount_str}&"
        f"cu=INR&"
        f"tn={note.replace(' ', '%20')}&"
        f"mode=04&purpose=00"
    )
    
    # Generate QR code with better settings
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=2,
    )
    qr.add_data(upi_uri)
    qr.make(fit=True)
    
    # Create image with better contrast
    img = qr.make_image(fill_color="#1a365d", back_color="#ffffff")
    
    # Convert to base64 with data URL
    buf = BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return img_b64

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


def recalculate_trust_tier(farmer_id):
    c = db()
    cur = c.cursor()

    try:
        # Total completed deals
        cur.execute("""
            SELECT COUNT(*) AS total
            FROM deal
            WHERE status = 'completed'
              AND harvest_id IN (
                  SELECT id FROM harvest WHERE farmer_id = ?
              )
        """, (farmer_id,))
        total_deals = cur.fetchone()["total"]

        # Average rating
        cur.execute("""
            SELECT AVG(rating) AS avg_rating
            FROM deal_ratings
            WHERE farmer_id = ?
        """, (farmer_id,))
        avg_rating = cur.fetchone()["avg_rating"]

        trust = "Bronze"

        if avg_rating is not None:
            if avg_rating >= 4.5 and total_deals >= 10:
                trust = "Gold"
            elif avg_rating >= 3.5 and total_deals >= 5:
                trust = "Silver"

        cur.execute("""
            UPDATE farmer SET trust_tier = ?
            WHERE id = ?
        """, (trust, farmer_id))

        c.commit()

    except Exception as e:
        c.rollback()
        print("TRUST RECALC ERROR:", e)

    finally:
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

        # ---- Validation ----
        if not all([name, email, password, confirm_password]):
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return redirect(url_for("register"))

        try:
            c = db()
            cur = c.cursor()

            # ---- Duplicate email check ----
            cur.execute("SELECT id FROM farmer WHERE email = ?", (email,))
            if cur.fetchone():
                flash("Email already registered. Please log in.", "warning")
                return redirect(url_for("login"))

            # ---- Insert user ----
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

            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            c.rollback()
            print("REGISTER ERROR:", e)
            flash("Registration failed. Please try again.", "danger")
            return redirect(url_for("register"))

        finally:
            c.close()

    return render_template("register.html")



@app.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, redirect to dashboard
    if "farmer_id" in session:
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "warning")
            return redirect(url_for("login"))

        try:
            c = db()
            cur = c.cursor()

            cur.execute("""
                SELECT id, name, password, role, status
                FROM farmer
                WHERE email = ?
            """, (email,))
            farmer = cur.fetchone()

            if not farmer:
                flash("Invalid email or password.", "danger")

                return redirect(url_for("login"))

            if farmer["status"] != "active":
                flash("Your account is inactive. Contact support.", "warning")
                return redirect(url_for("login"))

            if not check_password_hash(farmer["password"], password):
                flash("Invalid email or password.", "danger")

                return redirect(url_for("login"))

            # Successful login
            session.clear()
            session["farmer_id"] = farmer["id"]
            session["farmer_name"] = farmer["name"]
            session["role"] = farmer["role"]

            # Set session to expire after 1 hour of inactivity
            session.permanent = True
            app.permanent_session_lifetime = timedelta(hours=1)
            
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))

        except Exception as e:
            print(f"Login error: {e}")
            flash("An error occurred. Please try again.", "danger")
            return redirect(url_for("login"))
            
        finally:
            c.close()

    return render_template("login.html")


@app.route("/logout")
def logout():
    if "farmer_id" in session:
        # Clear only user-related session data
        session.pop("farmer_id", None)
        session.pop("farmer_name", None)
        session.pop("role", None)
        flash("You have been logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/profile")
def view_profile():
    if "farmer_id" not in session:
        return redirect(url_for("login"))

    c = db()
    cur = c.cursor()

    cur.execute("""
        SELECT id, name, email, phone, photo,
               farm_name, farm_address,
               trust_tier, created_at, updated_at
        FROM farmer
        WHERE id = ?
    """, (session["farmer_id"],))

    user = cur.fetchone()
    c.close()

    if not user:
        session.clear()
        flash("User not found. Please login again.", "warning")
        return redirect(url_for("login"))

    return render_template("profile.html", user=user)






@app.route("/profile/edit", methods=["POST"])
@login_required
def edit_profile():

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    farm_name = request.form.get("farm_name", "").strip()
    farm_address = request.form.get("farm_address", "").strip()
    email = request.form.get("email", "").strip()

    if not name or not phone or not email:
        flash("Name, email and phone are required.", "danger")
        return redirect(url_for("profile"))

    photo_filename = None

    if "profile_photo" in request.files:
        file = request.files["profile_photo"]
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image format.", "danger")
                return redirect(url_for("profile"))

            # Generate a secure filename with timestamp
            filename = secure_filename(file.filename)
            unique_filename = f"{int(time.time())}_{filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
            
            try:
                file.save(filepath)
                photo_filename = unique_filename
                
                # Delete old photo if exists
                cur = db().cursor()
                cur.execute("SELECT photo FROM farmer WHERE id = ?", (session["farmer_id"],))
                row = cur.fetchone()
                old_photo = row["photo"] if row and "photo" in row and row["photo"] else None
                if old_photo:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_photo))
                    except OSError:
                        pass  # Ignore if file doesn't exist
                        
            except Exception as e:
                app.logger.error(f"Error saving file: {str(e)}")
                flash("Error uploading profile picture. Please try again.", "danger")
                return redirect(url_for("profile"))

    c = db()
    cur = c.cursor()

    try:
        query = """
            UPDATE farmer
            SET name=?, email=?, phone=?, farm_name=?, farm_address=?, updated_at=?
        """
        params = [
            name,
            email,
            phone,
            farm_name,
            farm_address,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]

        if photo_filename:
            query = query.replace("updated_at=?", "photo=?, updated=?")
            params.insert(5, photo_filename)

        query += " WHERE id=?"
        params.append(session["farmer_id"])

        cur.execute(query, params)
        c.commit()

        # Update session
        session["farmer_name"] = name

        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    except sqlite3.IntegrityError as e:
        c.rollback()
        if "UNIQUE constraint failed: farmer.email" in str(e):
            flash("This email is already registered. Please use a different email.", "danger")
        else:
            app.logger.error(f"Database error: {str(e)}")
            flash("An error occurred while updating your profile. Please try again.", "danger")
        return redirect(url_for("profile"))

    except Exception as e:
        c.rollback()
        app.logger.error(f"Error updating profile: {str(e)}")
        flash("An error occurred while updating your profile. Please try again.", "error")
        return redirect(url_for("profile"))

    finally:
        c.close()



@app.route("/profile")
def profile():
    if "farmer_id" not in session:
        flash("Please login to access your profile", "warning")
        return redirect("/login")
    
    c = db()
    cur = c.cursor()
    
    try:
        # Get current user data
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
            flash("User not found", "danger")
            return redirect("/logout")
        user = dict(row)
        
        # Format dates for display
        if user.get('created_at'):
            user['created_at_formatted'] = datetime.strptime(user['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y')
        if user.get('updated_at'):
            user['updated_at_formatted'] = datetime.strptime(user['updated_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y')
        
        return render_template("profile.html", user=user)
        
    except Exception as e:
        app.logger.error(f"Error in profile route: {str(e)}")
        flash("An error occurred while processing your request. Please try again.", "danger")
        return redirect(url_for("dashboard"))
    
    finally:
        c.close()

@app.route("/dashboard")
def dashboard():
    # Authentication check
    try:
        c = db()
        cur = c.cursor()

        # Fetch farmer data
        cur.execute("""
            SELECT id, name, trust_tier, status 
            FROM farmer 
            WHERE id = ?
        """, (session["farmer_id"],))
        
        farmer = cur.fetchone()
        
        # Validate session
        if not farmer or farmer["status"] != "active":
            session.clear()
            flash("Session expired or account deactivated. Please login again.", "warning")
            return redirect(url_for("login"))
            
        # Update session name if changed
        if "farmer_name" not in session or session["farmer_name"] != farmer["name"]:
            session["farmer_name"] = farmer["name"]

        # Get harvest count
        cur.execute(
            "SELECT COUNT(*) as count FROM harvest WHERE farmer_id = ?",
            (session["farmer_id"],)
        )
        harvest_count = cur.fetchone()["count"]

        return render_template(
            "dashboard.html",
            farmer_name=session["farmer_name"],
            trust_tier=farmer["trust_tier"] or "basic",
            harvest_count=harvest_count
        )

    except Exception as e:
        print(f"Dashboard error: {e}")
        session.clear()
        flash("An error occurred. Please login again.", "warning")
        return redirect(url_for("login"))
        
    finally:
        c.close()


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        quantity = request.form.get("quantity", "").strip()
        price = request.form.get("price", "").strip()
        harvest_date = request.form.get("date", "").strip()
        image = request.files.get("image")

        # ---- VALIDATION ----
        if not quantity.isdigit() or int(quantity) <= 0:
            flash("Quantity must be a positive number.", "danger")
            return redirect(url_for("upload"))

        try:
            price_val = float(price)
            if price_val <= 0:
                raise ValueError
        except ValueError:
            flash("Expected price must be a positive number.", "danger")
            return redirect(url_for("upload"))

        try:
            date_obj = datetime.strptime(harvest_date, "%Y-%m-%d").date()
            if date_obj < datetime.today().date():
                flash("Harvest date cannot be in the past.", "danger")
                return redirect(url_for("upload"))
        except ValueError:
            flash("Invalid harvest date.", "danger")
            return redirect(url_for("upload"))

        if not image or image.filename == "":
            flash("Harvest image is required.", "danger")
            return redirect(url_for("upload"))

        if not allowed_file(image.filename):
            flash("Invalid image format.", "danger")
            return redirect(url_for("upload"))

        # ---- SAVE IMAGE ----
        filename = secure_filename(image.filename)
        image.save(os.path.join(UPLOADS, filename))

        # ---- INSERT HARVEST ----
        c = db()
        cur = c.cursor()
        cur.execute("""
            INSERT INTO harvest
            (farmer_id, quantity, expected_price, image, harvest_date, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (
            session["farmer_id"],
            quantity,
            price_val,
            filename,
            harvest_date
        ))
        c.commit()
        c.close()

        flash("Harvest submitted successfully and is pending approval.", "success")
        return redirect(url_for("dashboard"))

    # ✅ GET request (ONLY ONE)
    return render_template("upload_harvest.html")



@app.route("/my-harvests")
@login_required
def my_harvests():
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM harvest WHERE farmer_id=?", (session["farmer_id"],))
    rows = cur.fetchall()
    c.close()

    return render_template("my_harvests.html", harvests=rows)

@app.route("/edit-harvest/<int:id>", methods=["GET", "POST"])
@login_required
def edit_harvest(id):
    c = db()
    cur = c.cursor()

    try:
        # Fetch harvest
        cur.execute(
            "SELECT * FROM harvest WHERE id = ? AND farmer_id = ?",
            (id, session["farmer_id"])
        )
        h = cur.fetchone()

        if not h:
            flash("Harvest not found or unauthorized.", "danger")
            return redirect(url_for("my_harvests"))

        # Status guard
        if h["status"] != "pending":
            flash("This harvest can no longer be edited.", "warning")
            return redirect(url_for("my_harvests"))

        if request.method == "POST":
            quantity = request.form.get("quantity", "").strip()
            price = request.form.get("price", "").strip()
            harvest_date = request.form.get("date", "").strip()

            # ---- Validation ----
            if not quantity.isdigit() or int(quantity) <= 0:
                flash("Quantity must be a positive number.", "danger")
                return redirect(url_for("edit_harvest", id=id))

            try:
                price_val = float(price)
                if price_val <= 0:
                    raise ValueError
            except ValueError:
                flash("Expected price must be a positive number.", "danger")
                return redirect(url_for("edit_harvest", id=id))

            try:
                date_obj = datetime.strptime(harvest_date, "%Y-%m-%d").date()
                if date_obj < datetime.today().date():
                    flash("Harvest date cannot be in the past.", "danger")
                    return redirect(url_for("edit_harvest", id=id))
            except ValueError:
                flash("Invalid harvest date.", "danger")
                return redirect(url_for("edit_harvest", id=id))

            # Update
            cur.execute("""
                UPDATE harvest
                SET quantity = ?, expected_price = ?, harvest_date = ?
                WHERE id = ?
            """, (
                quantity,
                price_val,
                harvest_date,
                id
            ))

            c.commit()
            flash("Harvest updated successfully.", "success")
            return redirect(url_for("my_harvests"))

        return render_template("edit_harvest.html", harvest=h)

    except Exception as e:
        c.rollback()
        print("EDIT HARVEST ERROR:", e)
        flash("Failed to edit harvest.", "danger")
        return redirect(url_for("my_harvests"))

    finally:
        c.close()



@app.route("/delete-harvest/<int:id>")
@login_required
def delete_harvest(id):
    c = db()
    cur = c.cursor()

    try:
        # Fetch harvest
        cur.execute(
            "SELECT status FROM harvest WHERE id = ? AND farmer_id = ?",
            (id, session["farmer_id"])
        )
        h = cur.fetchone()

        if not h:
            flash("Harvest not found or unauthorized.", "danger")
            return redirect(url_for("my_harvests"))

        # Status guard
        if h["status"] != "pending":
            flash("This harvest can no longer be deleted.", "warning")
            return redirect(url_for("my_harvests"))

        # Delete
        cur.execute(
            "DELETE FROM harvest WHERE id = ?",
            (id,)
        )
        c.commit()

        flash("Harvest deleted successfully.", "success")

    except Exception as e:
        c.rollback()
        print("DELETE HARVEST ERROR:", e)
        flash("Failed to delete harvest.", "danger")

    finally:
        c.close()

    return redirect(url_for("my_harvests"))



@app.route("/inbox")
@login_required
def inbox():


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



@app.route("/rate-deal/<int:deal_id>", methods=["POST"])
@login_required
def rate_deal(deal_id):
    rating = request.form.get("rating")
    comment = request.form.get("comment", "").strip()

    if not rating or not rating.isdigit() or not (1 <= int(rating) <= 5):
        flash("Invalid rating.", "danger")
        return redirect("/buyer")

    c = db()
    cur = c.cursor()

    try:
        # Fetch deal
        cur.execute("""
            SELECT d.status, h.farmer_id
            FROM deal d
            JOIN harvest h ON d.harvest_id = h.id
            WHERE d.id = ?
        """, (deal_id,))
        d = cur.fetchone()

        if not d:
            flash("Deal not found.", "danger")
            return redirect("/buyer")

        if d["status"] != "completed":
            flash("Only completed deals can be rated.", "warning")
            return redirect("/buyer")

        # Prevent duplicate rating
        cur.execute(
            "SELECT id FROM deal_ratings WHERE deal_id = ?",
            (deal_id,)
        )
        if cur.fetchone():
            flash("You have already rated this deal.", "warning")
            return redirect("/buyer")

        # Insert rating
        cur.execute("""
            INSERT INTO deal_ratings
            (deal_id, farmer_id, buyer_name, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        """, (
            deal_id,
            d["farmer_id"],
            session.get("farmer_name", "Buyer"),
            int(rating),
            comment
        ))

        c.commit()

        # Recalculate trust tier
        recalculate_trust_tier(d["farmer_id"])

        flash("Thank you for your rating.", "success")
        return redirect("/buyer")

    except Exception as e:
        c.rollback()
        print("RATE DEAL ERROR:", e)
        flash("Failed to submit rating.", "danger")
        return redirect("/buyer")

    finally:
        c.close()






#============earnings==================



@app.route("/earnings")
@login_required
def earnings():
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
@login_required
def initiate_deal(hid):
    c = db()
    cur = c.cursor()

    try:
        # ---- Fetch harvest ----
        cur.execute("""
            SELECT id, farmer_id, quantity, expected_price, status
            FROM harvest
            WHERE id = ?
        """, (hid,))
        h = cur.fetchone()

        if not h:
            flash("Harvest not found.", "danger")
            return redirect("/buyer")

        # ---- Status guard ----
        if h["status"] != "approved":
            flash("This harvest is not available for deal initiation.", "warning")
            return redirect("/buyer")

        # ---- Prevent self-dealing ----
        if h["farmer_id"] == session["farmer_id"]:
            flash("You cannot initiate a deal on your own harvest.", "danger")
            return redirect("/buyer")

        # ---- Prevent double deal ----
        cur.execute("""
            SELECT id FROM deal
            WHERE harvest_id = ?
              AND status IN ('initiated', 'delivered', 'completed')
        """, (hid,))
        if cur.fetchone():
            flash("A deal has already been initiated for this harvest.", "warning")
            return redirect("/buyer")

        # ---- Calculate values ----
        value = float(h["quantity"]) * 1000 * float(h["expected_price"])
        rate = get_commission_rate()
        commission = value * rate
        net = value - commission

        # ---- Create deal ----
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

        # ---- Lock harvest ----
        cur.execute("""
            UPDATE harvest
            SET status = 'initiated'
            WHERE id = ?
        """, (hid,))

        c.commit()
        flash("Deal initiated successfully.", "success")
        return redirect("/buyer")

    except Exception as e:
        c.rollback()
        print("INITIATE DEAL ERROR:", e)
        flash("Failed to initiate deal.", "danger")
        return redirect("/buyer")

    finally:
        c.close()


@app.route("/deal/delivered/<int:id>")
@login_required
def delivered(id):
    c = db()
    cur = c.cursor()

    try:
        # ---- Fetch deal + ownership ----
        cur.execute("""
            SELECT d.status, h.farmer_id
            FROM deal d
            JOIN harvest h ON d.harvest_id = h.id
            WHERE d.id = ?
        """, (id,))
        d = cur.fetchone()

        if not d:
            flash("Deal not found.", "danger")
            return redirect("/inbox")

        # ---- Ownership guard ----
        if d["farmer_id"] != session["farmer_id"]:
            flash("Unauthorized action.", "danger")
            return redirect("/inbox")

        # ---- Status guard ----
        if d["status"] != "initiated":
            flash("This deal cannot be marked as delivered.", "warning")
            return redirect("/inbox")

        cur.execute("""
            UPDATE deal SET status = 'delivered' WHERE id = ?
        """, (id,))

        cur.execute("""
            UPDATE harvest SET status = 'delivered'
            WHERE id = (SELECT harvest_id FROM deal WHERE id = ?)
        """, (id,))

        c.commit()
        flash("Deal marked as delivered.", "success")
        return redirect("/inbox")

    except Exception as e:
        c.rollback()
        print("DELIVER DEAL ERROR:", e)
        flash("Failed to update delivery status.", "danger")
        return redirect("/inbox")

    finally:
        c.close()


@app.route("/deal/complete/<int:id>")
def complete(id):
    if not session.get("is_admin"):
        flash("Admin access required.", "danger")
        return redirect("/admin/login")

    c = db()
    cur = c.cursor()

    try:
        # ---- Fetch deal ----
        cur.execute("""
            SELECT d.status, h.farmer_id
            FROM deal d
            JOIN harvest h ON d.harvest_id = h.id
            WHERE d.id = ?
        """, (id,))
        d = cur.fetchone()

        if not d:
            flash("Deal not found.", "danger")
            return redirect("/admin/dashboard")

        # ---- Status guard ----
        if d["status"] != "delivered":
            flash("Only delivered deals can be completed.", "warning")
            return redirect("/admin/dashboard")

        # ---- Complete deal ----
        cur.execute("UPDATE deal SET status='completed' WHERE id=?", (id,))
        cur.execute("""
            UPDATE harvest SET status='completed'
            WHERE id = (SELECT harvest_id FROM deal WHERE id = ?)
        """, (id,))

        c.commit()

        update_trust_tier(d["farmer_id"])
        log_admin_action(
            "COMPLETE", "deal", id, "Deal marked completed by admin"
        )

        flash("Deal completed successfully.", "success")
        return redirect("/admin/dashboard")

    except Exception as e:
        c.rollback()
        print("COMPLETE DEAL ERROR:", e)
        flash("Failed to complete deal.", "danger")
        return redirect("/admin/dashboard")

    finally:
        c.close()


# ================= PAYMENT HELPERS =================

def get_payment_status(deal_value, amount_paid):
    """Determine payment status based on amount paid."""
    if amount_paid is None or amount_paid <= 0:
        return 'pending'
    elif amount_paid >= deal_value:
        return 'paid'
    else:
        return 'partial'

def update_deal_payment(deal_id, amount):
    """Update deal payment information and return new status."""
    c = db()
    try:
        with c:
            # Get current payment status
            cur = c.cursor()
            cur.execute(
                """
                SELECT deal_value, COALESCE(amount_paid, 0) as amount_paid 
                FROM deal WHERE id = ?
                """,
                (deal_id,)
            )
            deal = cur.fetchone()
            
            if not deal:
                return None
                
            new_amount_paid = (deal['amount_paid'] or 0) + amount
            new_status = get_payment_status(deal['deal_value'], new_amount_paid)
            
            # Update deal with new payment
            cur.execute(
                """
                UPDATE deal 
                SET amount_paid = ?, 
                    payment_status = ?,
                    status = CASE 
                        WHEN ? >= deal_value AND status = 'initiated' THEN 'delivered'
                        ELSE status
                    END
                WHERE id = ?
                """,
                (new_amount_paid, new_status, new_amount_paid, deal_id)
            )
            
            return {
                'amount_paid': new_amount_paid,
                'payment_status': new_status,
                'remaining': max(0, deal['deal_value'] - new_amount_paid)
            }
    except Exception as e:
        print(f"Error updating deal payment: {e}")
        c.rollback()
        return None

# ================= PAYMENT ROUTES =================

@app.route("/generate_qr", methods=["POST"])
@login_required
def generate_qr():
    """Generate a UPI QR code for payment and create a pending payment record."""
    try:
        amount = float(request.form.get('amount', 0))
        deal_id = request.form.get('deal_id')
        
        # Validate amount
        if amount <= 0:
            return jsonify({"error": "Invalid amount"}), 400
        
        conn = db()
        cur = conn.cursor()
        
        try:
            # Get deal details
            cur.execute("""
                SELECT d.id, d.deal_value, d.amount_paid, d.payment_status,
                       f.name AS farmer_name, f.phone AS farmer_phone
                FROM deal d
                JOIN harvest h ON d.harvest_id = h.id
                JOIN farmer f ON h.farmer_id = f.id
                WHERE d.id = ? AND d.buyer_id = ?
            """, (deal_id, session['user_id']))
            
            deal = cur.fetchone()
            if not deal:
                return jsonify({"error": "Deal not found"}), 404
            
            # Calculate remaining amount
            remaining = deal['deal_value'] - (deal.get('amount_paid') or 0)
            
            if amount > remaining:
                return jsonify({"error": "Amount exceeds remaining balance"}), 400
            
            # Generate UPI payment link
            note = f"KESPO Deal {deal_id}"
            upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount:.2f}&tn={note}"
            
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(upi_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Save QR code to bytes
            buffered = BytesIO()
            qr_img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            # Create pending payment record
            cur.execute("""
                INSERT INTO payment_history 
                (deal_id, amount, status, payment_date, upi_id, upi_transaction_id, notes)
                VALUES (?, ?, 'pending', datetime('now'), ?, NULL, ?)
            """, (deal_id, amount, UPI_ID, f"Payment for Deal #{deal_id}"))
            
            payment_id = cur.lastrowid
            conn.commit()
            
            return jsonify({
                "qr_code": qr_base64,
                "payment_id": payment_id,
                "amount": amount,
                "upi_id": UPI_ID,
                "note": note
            })
            
        except Exception as e:
            conn.rollback()
            app.logger.error(f"Error generating QR code: {str(e)}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        app.logger.error(f"Unexpected error in generate_qr: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

@app.route("/check_payment/<int:payment_id>")
@login_required
def check_payment(payment_id):
    """Check the status of a payment."""
    conn = db()
    cur = conn.cursor()
    
    try:
        # Get payment details with deal info
        cur.execute("""
            SELECT ph.*, d.buyer_id, d.deal_value, d.amount_paid,
                   a.username as verified_by_name
            FROM payment_history ph
            JOIN deal d ON ph.deal_id = d.id
            LEFT JOIN admin a ON ph.verified_by = a.id
            WHERE ph.id = ? AND d.buyer_id = ?
        """, (payment_id, session['user_id']))
        
        payment = cur.fetchone()
        if not payment:
            return jsonify({"error": "Payment not found"}), 404
        
        # Convert to dict for easier access
        payment_dict = dict(payment)
        
        # Check if payment is verified
        is_verified = payment_dict.get('status') == 'verified'
        response = {
            "paid": is_verified,
            "status": payment_dict.get('status', 'pending'),
            "amount": float(payment_dict.get('amount', 0)),
            "payment_date": payment_dict.get('payment_date'),
            "verified_at": payment_dict.get('verified_at'),
            "verified_by": payment_dict.get('verified_by_name'),
            "transaction_id": payment_dict.get('upi_transaction_id')
        }
        
        # If payment was just verified, update the deal's payment status
        if is_verified and not payment_dict.get('notified', False):
            # Update the payment record to mark as notified
            cur.execute("""
                UPDATE payment_history 
                SET notified = 1 
                WHERE id = ? AND status = 'verified' AND (notified IS NULL OR notified = 0)
            """, (payment_id,))
            
            # Update deal's payment status
            update_deal_payment(payment_dict['deal_id'], payment_dict['amount'])
            
            conn.commit()
            
        return jsonify(response)
        
    except Exception as e:
        app.logger.error(f"Error checking payment status: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route("/deal/pay/<int:deal_id>", methods=['GET', 'POST'])
@login_required
def pay_deal(deal_id):
    """Show payment page with UPI QR code and payment form."""
    conn = None
    try:
        # Get database connection
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get deal details
        cur.execute("""
            SELECT d.id, d.deal_value, d.status, 
                   COALESCE(d.amount_paid, 0) as amount_paid, 
                   d.payment_status,
                   f.name AS farmer_name, 
                   f.phone AS farmer_phone,
                   h.crop_type
            FROM deal d
            JOIN harvest h ON d.harvest_id = h.id
            JOIN farmer f ON h.farmer_id = f.id
            WHERE d.id = ? AND d.buyer_id = ?
        """, (deal_id, session.get('user_id')))
        
        deal = cur.fetchone()
        if not deal:
            flash("Deal not found or access denied.", "danger")
            return redirect(url_for('buyer'))
            
        deal = dict(deal)  # Convert to dict for easier access

        # Check if payment is applicable
        if deal["status"] not in ("initiated", "delivered"):
            flash("Payment not applicable for this deal.", "warning")
            return redirect(url_for('buyer'))

        # Get payment history
        payment_history = []
        cur.execute("""
            SELECT ph.*, a.username as verified_by_name
            FROM payment_history ph
            LEFT JOIN admin a ON ph.verified_by = a.id
            WHERE ph.deal_id = ?
            ORDER BY ph.payment_date DESC
        """, (deal_id,))
        
        for row in cur.fetchall():
            payment = dict(row)
            if payment['payment_date']:
                payment['payment_date'] = datetime.strptime(payment['payment_date'], '%Y-%m-%d %H:%M:%S')
            if payment.get('verified_at'):
                payment['verified_at'] = datetime.strptime(payment['verified_at'], '%Y-%m-%d %H:%M:%S')
            payment_history.append(payment)

        # Calculate remaining amount
        remaining_amount = deal['deal_value'] - deal['amount_paid']
        max_payment = min(remaining_amount, UPI_MAX_LIMIT)
        
        qr_img = None
        amount = None
        
        # Handle POST request (form submission)
        if request.method == 'POST':
            try:
                amount = float(request.form.get('amount', 0))
                
                # Validate amount
                if amount <= 0 or amount > max_payment:
                    flash(f"Amount must be between ₹1 and ₹{max_payment:,.2f}", "danger")
                else:
                    # Generate QR code for the specified amount
                    note = f"{deal['crop_type']} - KESPO Deal #{deal_id}"
                    qr_img = generate_upi_qr(amount, note)
            except (ValueError, TypeError) as e:
                app.logger.error(f"Invalid amount: {e}")
                flash("Please enter a valid payment amount.", "danger")
        
        return render_template(
            "pay_deal.html",
            deal=deal,
            payment_history=payment_history,
            qr_img=qr_img,
            amount=amount,
            upi_id=UPI_ID,
            upi_name=UPI_NAME,
            note=f"{deal.get('crop_type', 'KESPO')} Deal #{deal_id}",
            remaining_amount=remaining_amount,
            max_payment=max_payment
        )

    except Exception as e:
        app.logger.error(f"Error in pay_deal: {str(e)}", exc_info=True)
        flash("An error occurred while processing your request.", "danger")
        return redirect(url_for('buyer'))
    finally:
        if conn:
            conn.close()

@app.route("/deal/pay/<int:deal_id>/process", methods=['POST'])
@login_required
def process_payment(deal_id):
    """Process payment form and redirect to payment page with QR code."""
    c = db()
    cur = c.cursor()
    
    try:
        # Validate amount
        try:
            amount = float(request.form.get('amount', 0))
            if amount <= 0:
                flash("Please enter a valid amount greater than zero.", "danger")
                return redirect(url_for('pay_deal', deal_id=deal_id))
        except (ValueError, TypeError):
            flash("Invalid amount specified. Please enter a valid number.", "danger")
            return redirect(url_for('pay_deal', deal_id=deal_id))
            
        # Get deal to validate amount
        cur.execute(
            """
            SELECT d.id, d.deal_value, COALESCE(d.amount_paid, 0) as amount_paid, 
                   d.payment_status, d.status, h.farmer_id
            FROM deal d
            JOIN harvest h ON d.harvest_id = h.id
            WHERE d.id = ?
            """,
            (deal_id,)
        )
        deal = cur.fetchone()
        
        if not deal:
            flash("Deal not found.", "danger")
            return redirect("/inbox")
            
        # Calculate remaining amount and validate
        remaining = deal['deal_value'] - deal['amount_paid']
        max_allowed = min(UPI_MAX_LIMIT, remaining)
        
        if amount > max_allowed:
            flash(f"Amount cannot exceed ₹{max_allowed:,.2f} (remaining balance: ₹{remaining:,.2f})", "danger")
            return redirect(url_for('pay_deal', deal_id=deal_id))
            
        if amount > UPI_MAX_LIMIT:
            flash(f"UPI payment limit is ₹{UPI_MAX_LIMIT:,.2f} per transaction.", "danger")
            return redirect(url_for('pay_deal', deal_id=deal_id))
            
        # Create a new payment record with 'pending' status
        cur.execute(
            """
            INSERT INTO payment_history 
            (deal_id, amount, status, notes, payment_date)
            VALUES (?, ?, 'pending', 'UPI payment initiated', CURRENT_TIMESTAMP)
            """,
            (deal_id, amount)
        )
        payment_id = cur.lastrowid
        
        # Commit the transaction
        c.commit()
        
        # Redirect to payment page with amount pre-filled
        flash("Payment request created. Please make the payment using the QR code below.", "info")
        return redirect(url_for('pay_deal', deal_id=deal_id, amount=amount, payment_id=payment_id))
        
    except Exception as e:
        c.rollback()
        print(f"PAYMENT PROCESSING ERROR: {e}")
        flash("Failed to process payment. Please try again.", "danger")
        return redirect(url_for('pay_deal', deal_id=deal_id))
    finally:
        c.close()

@app.route("/admin/verify-payment/<int:payment_id>", methods=['POST'])
@admin_required
def verify_payment(payment_id):
    """
    Admin endpoint to verify a payment.
    This updates the payment status and increases the amount_paid in the deal.
    """
    if 'admin_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
        
    try:
        # Get UPI transaction ID from request
        upi_transaction_id = request.form.get('upi_transaction_id', '').strip()
        notes = request.form.get('notes', '').strip()
        
        if not upi_transaction_id:
            return jsonify({
                "success": False,
                "message": "UPI Transaction ID is required"
            }), 400
            
        c = db()
        with c:
            cur = c.cursor()
            
            # Get payment details with deal information
            cur.execute(
                """
                SELECT ph.id, ph.deal_id, ph.amount, ph.status, 
                       d.deal_value, COALESCE(d.amount_paid, 0) as amount_paid,
                       d.status as deal_status
                FROM payment_history ph
                JOIN deal d ON ph.deal_id = d.id
                WHERE ph.id = ?
                """,
                (payment_id,)
            )
            payment = cur.fetchone()
            
            if not payment:
                return jsonify({
                    "success": False, 
                    "message": "Payment not found"
                }), 404
                
            if payment['status'] == 'verified':
                return jsonify({
                    "success": False, 
                    "message": "Payment already verified"
                }), 400
            
            # Update payment status with verification details
            cur.execute(
                """
                UPDATE payment_history 
                SET status = 'verified',
                    verified_by = ?,
                    verified_at = CURRENT_TIMESTAMP,
                    upi_transaction_id = ?,
                    notes = ?
                WHERE id = ?
                RETURNING *
                """,
                (session['admin_id'], upi_transaction_id, notes, payment_id)
            )
            
            verified_payment = dict(cur.fetchone())
            
            # Update deal payment status with the verified amount
            result = update_deal_payment(payment['deal_id'], payment['amount'])
            
            if not result:
                c.rollback()
                return jsonify({
                    "success": False, 
                    "message": "Failed to update deal payment status"
                }), 500
            
            # Get updated payment history for the deal
            cur.execute(
                """
                SELECT ph.*, a.username as verified_by_name
                FROM payment_history ph
                LEFT JOIN admin a ON ph.verified_by = a.id
                WHERE ph.deal_id = ?
                ORDER BY ph.payment_date DESC
                """,
                (payment['deal_id'],)
            )
            
            payment_history = []
            for row in cur.fetchall():
                payment = dict(row)
                # Convert datetime objects to strings for JSON serialization
                if 'payment_date' in payment and payment['payment_date']:
                    payment['payment_date'] = payment['payment_date'].strftime('%Y-%m-%d %H:%M:%S')
                if 'verified_at' in payment and payment['verified_at']:
                    payment['verified_at'] = payment['verified_at'].strftime('%Y-%m-%d %H:%M:%S')
                payment_history.append(payment)
            
            # Log admin action
            log_admin_action(
                "verify_payment", 
                "payment", 
                payment_id, 
                f"Verified payment of ₹{verified_payment['amount']:,.2f} for deal #{verified_payment['deal_id']}. "
                f"Transaction ID: {upi_transaction_id}"
            )
            
            return jsonify({
                "success": True,
                "message": "Payment verified successfully",
                "payment_status": result['payment_status'],
                "amount_paid": result['amount_paid'],
                "remaining": result['remaining'],
                "payment_history": payment_history,
                "verification_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
    except Exception as e:
        print(f"VERIFY PAYMENT ERROR: {e}")
        import traceback
        traceback.print_exc()
        if 'c' in locals():
            c.rollback()
        return jsonify({
            "success": False, 
            "message": f"An error occurred while verifying payment: {str(e)}"
        }), 500
    finally:
        if 'c' in locals():
            c.close()


# ================= ADMIN  login =================
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


# =============== ADMIN DASHBOARD =================
@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect("/admin/login")

    conn = db()
    cur = conn.cursor()

    # ---- Pending harvest approvals ----
    cur.execute("""
        SELECT h.*, f.name AS farmer_name
        FROM harvest h
        JOIN farmer f ON h.farmer_id = f.id
        WHERE h.status = 'pending'
        ORDER BY h.harvest_date DESC
    """)
    harvests = cur.fetchall()

    # ---- Deals (Delivered / Completed) ----
    status = request.args.get("status", "delivered")
    cur.execute("""
        SELECT d.*, f.name AS farmer_name, f.email AS farmer_email
        FROM deal d
        JOIN harvest h ON d.harvest_id = h.id
        JOIN farmer f ON h.farmer_id = f.id
        WHERE d.status = ?
        ORDER BY d.created_at DESC
    """, (status,))
    deals = cur.fetchall()

    # ---- Dashboard stats ----
    cur.execute("SELECT COUNT(*) FROM farmer")
    total_farmers = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM harvest WHERE status = 'pending'")
    pending_harvests = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM deal WHERE status = 'delivered'")
    delivered_deals = cur.fetchone()[0]

    # Commission only from COMPLETED deals
    cur.execute("""
        SELECT IFNULL(SUM(commission), 0)
        FROM deal
        WHERE status = 'completed'
    """)
    total_commission = cur.fetchone()[0]

    # ---- Farmer list with completed deal count ----
    cur.execute("""
        SELECT f.id,
               f.name,
               f.email,
               f.trust_tier,
               COUNT(d.id) AS completed_deals
        FROM farmer f
        LEFT JOIN harvest h ON f.id = h.farmer_id
        LEFT JOIN deal d ON h.id = d.harvest_id AND d.status = 'completed'
        GROUP BY f.id
    """)
    farmers = cur.fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        harvests=harvests,
        deals=deals,
        farmers=farmers,
        total_farmers=total_farmers,
        pending_harvests=pending_harvests,
        delivered_deals=delivered_deals,
        total_commission=total_commission
    )
    
@app.route("/admin/approve/<int:id>")
def approve(id):
    # ---- Admin check ----
    if not session.get("is_admin"):
        flash("Admin access required.", "danger")
        return redirect("/admin/login")

    conn = db()
    cur = conn.cursor()

    try:
        # ---- Fetch harvest safely ----
        cur.execute(
            "SELECT id, status FROM harvest WHERE id = ?",
            (id,)
        )
        harvest = cur.fetchone()

        if not harvest:
            flash("Harvest not found.", "danger")
            return redirect("/admin/dashboard")

        # ---- Status guard ----
        if harvest["status"] != "pending":
            flash("This harvest cannot be approved again.", "warning")
            return redirect("/admin/dashboard")

        # ---- Approve harvest ----
        cur.execute(
            "UPDATE harvest SET status = 'approved' WHERE id = ?",
            (id,)
        )

        conn.commit()
        flash("Harvest approved successfully.", "success")

    except Exception as e:
        conn.rollback()
        print("ADMIN APPROVE ERROR:", e)
        flash("Failed to approve harvest. Please try again.", "danger")

    finally:
        conn.close()

    return redirect("/admin/dashboard")

@app.route("/admin/mark-paid/<int:id>")
def mark_paid(id):
    if not session.get("is_admin"):
        flash("Admin access required.", "danger")
        return redirect("/admin/login")

    c = db()
    cur = c.cursor()

    try:
        # Fetch deal
        cur.execute("SELECT status FROM deal WHERE id = ?", (id,))
        d = cur.fetchone()

        if not d:
            flash("Deal not found.", "danger")
            return redirect("/admin/dashboard")

        if d["status"] != "completed":
            flash("Only completed deals can be marked as paid.", "warning")
            return redirect("/admin/dashboard")

        # Mark as paid
        cur.execute("""
            UPDATE deal
            SET paid = 1
            WHERE id = ?
        """, (id,))

        c.commit()
        flash("Payment marked as paid.", "success")

    except Exception as e:
        c.rollback()
        print("MARK PAID ERROR:", e)
        flash("Failed to mark payment as paid.", "danger")

    finally:
        c.close()

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


    return redirect(url_for("login"))



# ================= RUN =================
@app.route("/change-password", methods=["POST"])
@login_required
def change_password():

    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")
    
    # Input validation
    if not all([current_password, new_password, confirm_password]):
        flash("All fields are required", "danger")
        return redirect("/profile")
    
    if new_password != confirm_password:
        flash("New passwords do not match", "danger")
        return redirect("/profile")
    
    if len(new_password) < 8:
        flash("Password must be at least 8 characters long", "danger")
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
            flash("Current password is incorrect", "danger")
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
        flash("An error occurred while updating your password", "danger")
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
                expires_at = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
                
                # Store token in database
                try:
                    cur.execute("""
                        INSERT INTO password_reset_tokens (email, token, expires_at, used)
                        VALUES (?, ?, ?, 0)
                    """, (email, token, expires_at))
                    c.commit()
                    app.logger.info(f"Password reset token generated for {email}")
                except sqlite3.Error as e:
                    app.logger.error(f"Database error in forgot_password: {str(e)}")
                    flash('An error occurred. Please try again.', 'error')
                    return redirect(url_for('forgot_password'))
                
                # Generate reset URL
                reset_url = url_for('reset_password', token=token, _external=True)
                
                # Send email with reset link
                try:
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
                    
                    with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()
                        server.login(
                            app.config['MAIL_USERNAME'],
                            app.config['MAIL_PASSWORD']
                        )
                        server.send_message(msg)
                    
                    app.logger.info(f"Password reset email sent to {email}")
                    flash('If an account exists with this email, a password reset link has been sent', 'info')
                except Exception as e:
                    app.logger.error(f"Failed to send email to {email}: {str(e)}")
                    flash('Failed to send reset email. Please try again later.', 'error')
            else:
                # Don't reveal if email exists or not
                app.logger.info(f"Password reset requested for non-existent email: {email}")
                flash('If an account exists with this email, a password reset link has been sent', 'info')
                
        except Exception as e:
            app.logger.error(f"Error in forgot_password: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
        finally:
            c.close()
            
        return redirect(url_for('login'))
        
    return render_template('forgot_password.html')
        
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
    init_db()
    ensure_admin()
    port = int(os.environ.get("PORT", 5003))
    app.run(host="0.0.0.0", port=port)

@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(e):
    flash("Image size is too large. Maximum allowed size is 5 MB.", "danger")
    return redirect(request.url)


