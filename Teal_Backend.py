import os
import datetime
import psycopg2
import psycopg2.extras  # NEW: Helpful for dictionary-like results
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Configuration ---
# ### --- DELETED --- ###
# DB_FILE = 'licenses.json' - We no longer need this.

# These keys are still loaded from Environment Variables, which is perfect.
DEFAULT_MASTER_KEY = os.environ.get("FLASK_MASTER_KEY", "ChangeThisInProductionMasterKey")
DEFAULT_TOTAL_LICENSES = 50
ADMIN_SECRET_KEY = os.environ.get("FLASK_ADMIN_KEY", "ChangeThisInProductionAdminKey")


# --- NEW: Database Helper Functions ---

def get_db_connection():
    """Establishes a connection to the database using the DATABASE_URL environment variable."""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    return conn


def setup_database():
    """Creates the necessary tables if they don't exist and initializes settings."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Table for storing individual license activations
    cur.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            device_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            hostname TEXT,
            activated_at TIMESTAMPTZ DEFAULT NOW(),
            status TEXT NOT NULL DEFAULT 'active'
        );
    ''')

    # Table for storing global settings like master key and license count
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INT PRIMARY KEY,
            master_key TEXT NOT NULL,
            total_licenses INT NOT NULL
        );
    ''')

    # Check if settings are initialized. If not, insert the default values.
    cur.execute("SELECT id FROM settings WHERE id = 1;")
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO settings (id, master_key, total_licenses) VALUES (%s, %s, %s);",
            (1, DEFAULT_MASTER_KEY, DEFAULT_TOTAL_LICENSES)
        )

    conn.commit()
    cur.close()
    conn.close()
    print("Database setup successful: Tables are ready.")


# ### --- DELETED --- ###
# The `load_licenses` and `save_licenses` functions are no longer needed.
# The `get_active_device_count` function will be replaced by a direct SQL query.

# --- Run Database Setup on Startup ---
# This ensures your tables exist every time the app starts.
setup_database()


# --- API Endpoints (Now Refactored for PostgreSQL) ---

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint for Render's health checks and UptimeRobot."""
    return jsonify({"status": "ok", "message": "Backend is running"}), 200


@app.route('/activate_license', methods=['POST'])
def activate_license():
    data = request.get_json()
    license_key = data.get('license_key')
    device_id = data.get('device_id')
    username = data.get('username')
    hostname = data.get('hostname')

    if not all([license_key, device_id, username, hostname]):
        return jsonify({"success": False, "message": "Missing data"}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Get settings from the database
        cur.execute("SELECT master_key, total_licenses FROM settings WHERE id = 1;")
        settings = cur.fetchone()
        if not settings:
            return jsonify({"success": False, "message": "Server settings not initialized."}), 500

        if license_key != settings["master_key"]:
            return jsonify({"success": False, "message": "Invalid license key"}), 403

        # Check if device already exists
        cur.execute("SELECT * FROM licenses WHERE device_id = %s;", (device_id,))
        existing_device = cur.fetchone()

        # Count currently active licenses
        cur.execute("SELECT COUNT(*) FROM licenses WHERE status = 'active';")
        active_count = cur.fetchone()['count']

        if existing_device:
            if existing_device['status'] == 'active':
                return jsonify({"success": True, "message": "License already active on this device"}), 200
            else:  # Reactivating an inactive license
                if active_count >= settings["total_licenses"]:
                    return jsonify({"success": False, "message": "All licenses are currently in use."}), 403

                cur.execute("""
                    UPDATE licenses
                    SET status = 'active', activated_at = NOW(), username = %s, hostname = %s
                    WHERE device_id = %s;
                """, (username, hostname, device_id))
                message = "License reactivated successfully!"
                active_count += 1
        else:  # Activating a new device
            if active_count >= settings["total_licenses"]:
                return jsonify({"success": False, "message": "All licenses are currently in use."}), 403

            cur.execute("""
                INSERT INTO licenses (device_id, username, hostname, status)
                VALUES (%s, %s, %s, 'active');
            """, (device_id, username, hostname))
            message = "License activated successfully!"
            active_count += 1

        conn.commit()
        return jsonify({
            "success": True, "message": message,
            "licenses_remaining": settings["total_licenses"] - active_count
        }), 200

    finally:
        cur.close()
        conn.close()


@app.route('/check_license', methods=['POST'])
def check_license():
    data = request.get_json()
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"success": False, "message": "Missing device ID"}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT status FROM licenses WHERE device_id = %s;", (device_id,))
        device = cur.fetchone()

        if device and device['status'] == 'active':
            return jsonify({"success": True, "message": "License active"}), 200
        elif device and device['status'] != 'active':
            return jsonify({"success": False, "message": "This device's license has been deactivated."}), 403
        else:
            return jsonify({"success": False, "message": "License not found for this device."}), 403
    finally:
        cur.close()
        conn.close()


# --- Admin Endpoints (Now Refactored for PostgreSQL) ---

@app.route('/admin/set_total_licenses', methods=['POST'])
def set_total_licenses():
    data = request.get_json()
    new_total = data.get('new_total_licenses')
    admin_key = data.get('admin_key')

    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if not isinstance(new_total, int) or new_total < 0:
        return jsonify({"success": False, "message": "Invalid new_total_licenses"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE settings SET total_licenses = %s WHERE id = 1;", (new_total,))
        conn.commit()
        return jsonify({"success": True, "message": f"Total licenses set to {new_total}"}), 200
    finally:
        cur.close()
        conn.close()


@app.route('/admin/view_status', methods=['GET'])
def view_status():
    admin_key = request.args.get('admin_key')
    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Get settings
        cur.execute("SELECT total_licenses FROM settings WHERE id = 1;")
        settings = cur.fetchone()
        total_licenses = settings['total_licenses'] if settings else 0

        # Get all devices
        cur.execute(
            "SELECT device_id, username, hostname, status, to_char(activated_at, 'YYYY-MM-DD HH24:MI:SS TZ') as activated_at FROM licenses;")
        all_devices = cur.fetchall()

        # Process data
        activated_devices_dict = {d['device_id']: d for d in all_devices}
        active_count = sum(1 for d in all_devices if d['status'] == 'active')

        return jsonify({
            "total_licenses": total_licenses,
            "activated_count": active_count,
            "licenses_remaining": total_licenses - active_count,
            "activated_devices": activated_devices_dict
        }), 200
    finally:
        cur.close()
        conn.close()


def update_device_status(device_id, new_status, admin_key):
    """Helper function to activate/deactivate a device."""
    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    if not device_id:
        return jsonify({"success": False, "message": "Missing device ID"}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Check if device exists first
        cur.execute("SELECT status FROM licenses WHERE device_id = %s;", (device_id,))
        device = cur.fetchone()
        if not device:
            return jsonify({"success": False, "message": "Device not found."}), 404
        if device['status'] == new_status:
            return jsonify({"success": True, "message": f"Device is already {new_status}."}), 200

        # If activating, check license count
        if new_status == 'active':
            cur.execute("SELECT COUNT(*) as count FROM licenses WHERE status = 'active';")
            active_count = cur.fetchone()['count']
            cur.execute("SELECT total_licenses FROM settings WHERE id = 1;")
            total_licenses = cur.fetchone()['total_licenses']
            if active_count >= total_licenses:
                return jsonify({"success": False, "message": "Cannot activate: All licenses are in use."}), 403

        cur.execute("UPDATE licenses SET status = %s WHERE device_id = %s;", (new_status, device_id))
        conn.commit()
        return jsonify({"success": True, "message": f"Device '{device_id}' status set to {new_status}."}), 200
    finally:
        cur.close()
        conn.close()


@app.route('/admin/deactivate_device', methods=['POST'])
def deactivate_device():
    data = request.get_json()
    return update_device_status(data.get('device_id'), 'inactive', data.get('admin_key'))


@app.route('/admin/activate_device', methods=['POST'])
def activate_device_admin():
    data = request.get_json()
    return update_device_status(data.get('device_id'), 'active', data.get('admin_key'))


# --- Main Execution ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)