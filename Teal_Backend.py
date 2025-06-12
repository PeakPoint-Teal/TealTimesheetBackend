import os
import datetime
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Configuration ---
DEFAULT_MASTER_KEY = os.environ.get("FLASK_MASTER_KEY", "FallbackMasterKeyForLocalDev")
DEFAULT_TOTAL_LICENSES = 50
ADMIN_SECRET_KEY = os.environ.get("FLASK_ADMIN_KEY", "FallbackAdminKeyForLocalDev")


# --- Database Helper Functions ---
def get_db_connection():
    """Establishes a connection to the database."""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("FATAL ERROR: DATABASE_URL environment variable is not set.")
    conn = psycopg2.connect(db_url)
    return conn

def setup_database():
    """Creates the necessary tables if they don't exist and initializes settings."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            device_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            hostname TEXT,
            activated_at TIMESTAMPTZ DEFAULT NOW(),
            status TEXT NOT NULL DEFAULT 'active'
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INT PRIMARY KEY,
            master_key TEXT NOT NULL,
            total_licenses INT NOT NULL
        );
    ''')
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

# --- Run Database Setup on Startup ---
setup_database()

# --- API Endpoints ---
@app.route('/health', methods=['GET'])
def health_check():
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
        cur.execute("SELECT master_key, total_licenses FROM settings WHERE id = 1;")
        settings = cur.fetchone()
        if license_key != settings["master_key"]:
            return jsonify({"success": False, "message": "Invalid license key"}), 403

        cur.execute("SELECT * FROM licenses WHERE device_id = %s;", (device_id,))
        existing_device = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM licenses WHERE status = 'active';")
        active_count = cur.fetchone()['count']

        if existing_device:
            if existing_device['status'] == 'active':
                return jsonify({"success": True, "message": "License already active on this device"}), 200
            else:
                if active_count >= settings["total_licenses"]:
                    return jsonify({"success": False, "message": "All licenses are currently in use."}), 403
                cur.execute("UPDATE licenses SET status = 'active', activated_at = NOW(), username = %s, hostname = %s WHERE device_id = %s;", (username, hostname, device_id))
                message = "License reactivated successfully!"
                active_count += 1
        else:
            if active_count >= settings["total_licenses"]:
                return jsonify({"success": False, "message": "All licenses are currently in use."}), 403
            cur.execute("INSERT INTO licenses (device_id, username, hostname, status) VALUES (%s, %s, %s, 'active');", (device_id, username, hostname))
            message = "License activated successfully!"
            active_count += 1

        conn.commit()
        return jsonify({"success": True, "message": message, "licenses_remaining": settings["total_licenses"] - active_count}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"An internal server error occurred: {e}"}), 500
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
        elif device:
            return jsonify({"success": False, "message": "This device's license has been deactivated."}), 403
        else:
            return jsonify({"success": False, "message": "License not found for this device."}), 403
    finally:
        cur.close()
        conn.close()

# ... (Your Admin endpoints will also need to be updated to use the database) ...
# This is an example for view_status
@app.route('/admin/view_status', methods=['GET'])
def view_status():
    admin_key = request.args.get('admin_key')
    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT total_licenses FROM settings WHERE id = 1;")
        settings = cur.fetchone()
        total_licenses = settings['total_licenses'] if settings else 0

        cur.execute("SELECT device_id, username, hostname, status, to_char(activated_at, 'YYYY-MM-DD HH24:MI:SS TZ') as activated_at FROM licenses;")
        all_devices = cur.fetchall()

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


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)