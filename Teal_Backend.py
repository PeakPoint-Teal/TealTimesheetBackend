import os
import datetime
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Configuration ---
# Environment variables are the source of truth now.
DEFAULT_MASTER_KEY = os.environ.get("FLASK_MASTER_KEY", "FallbackMasterKeyForLocalDev")
DEFAULT_TOTAL_LICENSES = 50
ADMIN_SECRET_KEY = os.environ.get("FLASK_ADMIN_KEY", "FallbackAdminKeyForLocalDev")
# A default download URL for new versions
DEFAULT_DOWNLOAD_URL = "https://www.peakpointenterprise.com/download-timesheet"


# --- Database Helper Functions ---

def get_db_connection():
    """
    Establishes a connection to the database.
    Includes robust error handling for the DATABASE_URL environment variable.
    """
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("FATAL ERROR: DATABASE_URL environment variable is not set.")
    conn = psycopg2.connect(db_url)
    return conn


def setup_database():
    """Creates the necessary tables if they don't exist and initializes settings."""
    conn = get_db_connection()
    cur = conn.cursor()

    # --- Licenses Table ---
    cur.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            device_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            hostname TEXT,
            activated_at TIMESTAMPTZ DEFAULT NOW(),
            status TEXT NOT NULL DEFAULT 'active'
        );
    ''')

    # --- Settings Table ---
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INT PRIMARY KEY,
            master_key TEXT NOT NULL,
            total_licenses INT NOT NULL
        );
    ''')

    # --- NEW: Versions Table ---
    cur.execute('''
        CREATE TABLE IF NOT EXISTS versions (
            version_number TEXT PRIMARY KEY,
            release_date TIMESTAMPTZ DEFAULT NOW(),
            download_url TEXT NOT NULL,
            is_latest BOOLEAN NOT NULL DEFAULT FALSE
        );
    ''')

    # Initialize settings if the table is empty
    cur.execute("SELECT id FROM settings WHERE id = 1;")
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO settings (id, master_key, total_licenses) VALUES (%s, %s, %s);",
            (1, DEFAULT_MASTER_KEY, DEFAULT_TOTAL_LICENSES)
        )
        print("Initialized default settings.")

    # Initialize versions if the table is empty
    cur.execute("SELECT COUNT(*) FROM versions;")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO versions (version_number, download_url, is_latest) VALUES (%s, %s, %s);",
            ("3.0.1", DEFAULT_DOWNLOAD_URL, True)
        )
        print("Initialized with default version 3.0.1.")

    conn.commit()
    cur.close()
    conn.close()
    print("Database setup successful: Tables are ready.")


# --- Run Database Setup on Startup ---
setup_database()


# --- Public API Endpoints ---

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "ok", "message": "Backend is running"}), 200


@app.route('/app_version', methods=['GET'])
def get_app_version():
    """Provides the latest version info for the client from the database."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT version_number, download_url FROM versions WHERE is_latest = TRUE LIMIT 1;")
        latest_version = cur.fetchone()
        if latest_version:
            return jsonify({
                "latest_version": latest_version["version_number"],
                "download_url": latest_version["download_url"]
            }), 200
        else:
            return jsonify({"success": False, "message": "No latest version configured."}), 404
    except Exception as e:
        print(f"Error in get_app_version: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
    finally:
        cur.close()
        conn.close()


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
        if not settings:
            return jsonify({"success": False, "message": "Server settings not initialized."}), 500

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
                cur.execute(
                    "UPDATE licenses SET status = 'active', activated_at = NOW(), username = %s, hostname = %s WHERE device_id = %s;",
                    (username, hostname, device_id))
                message = "License reactivated successfully!"
                active_count += 1
        else:
            if active_count >= settings["total_licenses"]:
                return jsonify({"success": False, "message": "All licenses are currently in use."}), 403
            cur.execute("INSERT INTO licenses (device_id, username, hostname, status) VALUES (%s, %s, %s, 'active');",
                        (device_id, username, hostname))
            message = "License activated successfully!"
            active_count += 1

        conn.commit()
        return jsonify({
            "success": True, "message": message,
            "licenses_remaining": settings["total_licenses"] - active_count
        }), 200
    except Exception as e:
        print(f"Error in activate_license: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
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
    except Exception as e:
        print(f"Error in check_license: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
    finally:
        cur.close()
        conn.close()


# --- Admin API Endpoints ---

def update_device_status(device_id, new_status, admin_key):
    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    if not device_id:
        return jsonify({"success": False, "message": "Missing device ID"}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT status FROM licenses WHERE device_id = %s;", (device_id,))
        device = cur.fetchone()
        if not device:
            return jsonify({"success": False, "message": "Device not found."}), 404
        if device['status'] == new_status:
            return jsonify({"success": True, "message": f"Device is already {new_status}."}), 200

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
    except Exception as e:
        print(f"Error in update_device_status: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
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
        cur.execute("SELECT total_licenses FROM settings WHERE id = 1;")
        settings = cur.fetchone()
        total_licenses = settings['total_licenses'] if settings else 0

        cur.execute(
            "SELECT device_id, username, hostname, status, to_char(activated_at, 'YYYY-MM-DD HH24:MI:SS TZ') as activated_at FROM licenses;")
        all_devices = cur.fetchall()

        activated_devices_dict = {d['device_id']: d for d in all_devices}
        active_count = sum(1 for d in all_devices if d['status'] == 'active')

        return jsonify({
            "total_licenses": total_licenses,
            "activated_count": active_count,
            "licenses_remaining": total_licenses - active_count,
            "activated_devices": activated_devices_dict
        }), 200
    except Exception as e:
        print(f"Error in view_status: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
    finally:
        cur.close()
        conn.close()


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
    except Exception as e:
        print(f"Error in set_total_licenses: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
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


# --- NEW: Version Management Admin Endpoints ---

@app.route('/admin/get_versions', methods=['GET'])
def get_versions():
    admin_key = request.args.get('admin_key')
    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT version_number, to_char(release_date, 'YYYY-MM-DD HH24:MI:SS TZ') as release_date, download_url, is_latest FROM versions ORDER BY release_date DESC;")
        versions = cur.fetchall()
        return jsonify({"success": True, "versions": versions}), 200
    except Exception as e:
        print(f"Error in get_versions: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/admin/set_latest_version', methods=['POST'])
def set_latest_version():
    data = request.get_json()
    new_version = data.get('version_number')
    download_url = data.get('download_url')
    admin_key = data.get('admin_key')

    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    if not new_version or not download_url:
        return jsonify({"success": False, "message": "Missing version_number or download_url"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Transaction: Set all other versions to not be the latest
        cur.execute("UPDATE versions SET is_latest = FALSE;")

        # Check if the new version already exists
        cur.execute("SELECT version_number FROM versions WHERE version_number = %s;", (new_version,))
        if cur.fetchone():
            # If it exists, update it to be the latest
            cur.execute(
                "UPDATE versions SET is_latest = TRUE, download_url = %s, release_date = NOW() WHERE version_number = %s;",
                (download_url, new_version))
            message = f"Successfully set version {new_version} as the latest."
        else:
            # If it's a new version, insert it
            cur.execute("INSERT INTO versions (version_number, download_url, is_latest) VALUES (%s, %s, TRUE);",
                        (new_version, download_url))
            message = f"Successfully added and set new version {new_version} as the latest."

        conn.commit()
        return jsonify({"success": True, "message": message}), 200
    except Exception as e:
        conn.rollback()
        print(f"Error in set_latest_version: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
