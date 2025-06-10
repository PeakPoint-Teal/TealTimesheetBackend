from flask import Flask, request, jsonify
import json
import os
import datetime
import secrets  # Used for initial key generation in old versions, but not for loading now

app = Flask(__name__)

# --- Configuration for your Backend ---
DB_FILE = 'licenses.json'

# IMPORTANT: These keys are now loaded from Environment Variables for production security.
# The second argument to .get() is a fallback for local development if the env var isn't set.
# On your deployment server (e.g., Render), you MUST set FLASK_MASTER_KEY and FLASK_ADMIN_KEY
# in their environment variable settings.
DEFAULT_MASTER_KEY = os.environ.get("FLASK_MASTER_KEY", "ChangeThisInProductionMasterKey")
DEFAULT_TOTAL_LICENSES = 50

ADMIN_SECRET_KEY = os.environ.get("FLASK_ADMIN_KEY", "ChangeThisInProductionAdminKey")


# --- Database Functions (using JSON file as a simple database) ---
def load_licenses():
    if not os.path.exists(DB_FILE):
        # Initialize with default data if file doesn't exist
        initial_data = {
            "master_key": DEFAULT_MASTER_KEY,
            "total_licenses": DEFAULT_TOTAL_LICENSES,
            "activated_devices": []  # MODIFIED: Now a list of device records
        }
        save_licenses(initial_data)
        return initial_data

    with open(DB_FILE, 'r') as f:
        return json.load(f)


def save_licenses(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)


# Ensure the licenses.json file exists and is initialized when the app starts
licenses_data_on_startup = load_licenses()
print(f"Backend started. Master Key: {licenses_data_on_startup['master_key']}")
print(f"Total Licenses: {licenses_data_on_startup['total_licenses']}")
# Calculate activated count by counting 'active' devices
active_devices_count_on_startup = sum(
    1 for d in licenses_data_on_startup['activated_devices'] if d.get('status') == 'active')
print(f"Activated Devices: {active_devices_count_on_startup}")


# --- Helper to count active devices ---
def get_active_device_count(licenses_data):
    return sum(1 for d in licenses_data['activated_devices'] if d.get('status') == 'active')


# --- API Endpoints ---

@app.route('/activate_license', methods=['POST'])
def activate_license():
    data = request.get_json()
    license_key = data.get('license_key')
    device_id = data.get('device_id')
    username = data.get('username')
    hostname = data.get('hostname')

    if not all([license_key, device_id, username, hostname]):
        return jsonify({"success": False, "message": "Missing data"}), 400

    licenses_data = load_licenses()

    if license_key != licenses_data["master_key"]:
        return jsonify({"success": False, "message": "Invalid license key"}), 403

    # Check if this device_id is already in the list
    existing_device = next((d for d in licenses_data["activated_devices"] if d['device_id'] == device_id), None)

    if existing_device:
        if existing_device.get('status') == 'active':
            return jsonify({"success": True, "message": "License already active on this device"}), 200
        else:  # Device exists but is 'inactive' or other status, reactivate it
            current_activated_count = get_active_device_count(licenses_data)
            if current_activated_count >= licenses_data["total_licenses"]:
                return jsonify({"success": False,
                                "message": "All licenses are currently in use. Please contact your administrator to acquire more licenses."}), 403

            existing_device['status'] = 'active'
            existing_device['activated_at'] = datetime.datetime.now().isoformat()
            existing_device['username'] = username  # Update info in case it changed
            existing_device['hostname'] = hostname
            save_licenses(licenses_data)
            return jsonify({"success": True, "message": "License reactivated successfully!",
                            "licenses_remaining": licenses_data["total_licenses"] - (current_activated_count + 1)}), 200

    # If device is new, activate it
    current_activated_count = get_active_device_count(licenses_data)
    if current_activated_count >= licenses_data["total_licenses"]:
        return jsonify({"success": False,
                        "message": "All licenses are currently in use. Please contact your administrator to acquire more licenses."}), 403

    # Add the new device to the list
    licenses_data["activated_devices"].append({
        "device_id": device_id,
        "username": username,
        "hostname": hostname,
        "activated_at": datetime.datetime.now().isoformat(),
        "status": "active"  # New: Set status to active
    })
    save_licenses(licenses_data)

    return jsonify({
        "success": True,
        "message": "License activated successfully!",
        "licenses_remaining": licenses_data["total_licenses"] - (current_activated_count + 1)
    }), 200


@app.route('/check_license', methods=['POST'])
def check_license():
    data = request.get_json()
    device_id = data.get('device_id')

    if not device_id:
        return jsonify({"success": False, "message": "Missing device ID"}), 400

    licenses_data = load_licenses()
    # Check if device exists and is active
    is_active = any(
        d['device_id'] == device_id and d.get('status') == 'active' for d in licenses_data["activated_devices"])

    if is_active:
        return jsonify({"success": True, "message": "License active"}), 200
    else:
        # If device is found but inactive, or not found at all, return failure with message
        device_found = any(d['device_id'] == device_id for d in licenses_data["activated_devices"])
        if device_found:
            return jsonify({"success": False, "message": "This device's license has been deactivated."}), 403
        else:
            return jsonify({"success": False, "message": "License not found for this device."}), 403


# --- Admin Endpoint (for you to manage licenses) ---

@app.route('/admin/set_total_licenses', methods=['POST'])
def set_total_licenses():
    data = request.get_json()
    new_total = data.get('new_total_licenses')
    admin_key = data.get('admin_key')

    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if not isinstance(new_total, int) or new_total < 0:
        return jsonify({"success": False, "message": "Invalid new_total_licenses"}), 400

    licenses_data = load_licenses()
    licenses_data["total_licenses"] = new_total
    save_licenses(licenses_data)
    return jsonify({"success": True, "message": f"Total licenses set to {new_total}"}), 200


@app.route('/admin/view_status', methods=['GET'])
def view_status():
    admin_key = request.args.get('admin_key')
    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    licenses_data = load_licenses()
    activated_count = get_active_device_count(licenses_data)  # Count only active devices
    licenses_remaining = licenses_data["total_licenses"] - activated_count

    # Prepare activated_devices list to send, showing status
    # Convert list of dicts to a dict for easier consumption by GUI (keyed by device_id)
    activated_devices_dict = {d['device_id']: d for d in licenses_data['activated_devices']}

    return jsonify({
        "total_licenses": licenses_data["total_licenses"],
        "activated_count": activated_count,
        "licenses_remaining": licenses_remaining,
        "activated_devices": activated_devices_dict
    }), 200


@app.route('/admin/deactivate_device', methods=['POST'])
def deactivate_device():
    data = request.get_json()
    device_id = data.get('device_id')
    admin_key = data.get('admin_key')

    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if not device_id:
        return jsonify({"success": False, "message": "Missing device ID"}), 400

    licenses_data = load_licenses()

    device_record = next((d for d in licenses_data["activated_devices"] if d['device_id'] == device_id), None)

    if not device_record:
        return jsonify({"success": False, "message": "Device not found."}), 404

    if device_record.get('status') == 'inactive':
        return jsonify({"success": True, "message": f"Device '{device_id}' is already inactive."}), 200

    device_record['status'] = 'inactive'  # Set status to inactive
    save_licenses(licenses_data)

    return jsonify({"success": True, "message": f"Device '{device_id}' deactivated successfully!"}), 200


# NEW: Admin endpoint to activate a device
@app.route('/admin/activate_device', methods=['POST'])
def activate_device_admin():
    data = request.get_json()
    device_id = data.get('device_id')
    admin_key = data.get('admin_key')

    if admin_key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if not device_id:
        return jsonify({"success": False, "message": "Missing device ID"}), 400

    licenses_data = load_licenses()

    device_record = next((d for d in licenses_data["activated_devices"] if d['device_id'] == device_id), None)

    if not device_record:
        return jsonify({"success": False, "message": "Device not found."}), 404

    if device_record.get('status') == 'active':
        return jsonify({"success": True, "message": f"Device '{device_id}' is already active."}), 200

    # Ensure there's an available license before activating via admin panel
    current_activated_count = get_active_device_count(licenses_data)
    if current_activated_count >= licenses_data["total_licenses"]:
        return jsonify({"success": False, "message": "Cannot activate device: All licenses are currently in use."}), 403

    device_record['status'] = 'active'  # Set status to active
    save_licenses(licenses_data)

    return jsonify({"success": True, "message": f"Device '{device_id}' activated successfully by admin!"}), 200


if __name__ == '__main__':
    # IMPORTANT: DO NOT USE debug=True in a production environment.
    # It enables a debugger that allows arbitrary code execution.
    app.run(host='0.0.0.0', port=5000, debug=False)  # Ensure debug=False for production prep