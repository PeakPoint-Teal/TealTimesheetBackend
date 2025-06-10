import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import requests
import json
import getpass
import datetime  # For formatting timestamps

# --- Configuration for the Admin GUI ---
LICENSE_ADMIN_API_URL = "http://127.0.0.1:5000"  # <--- Set to localhost
ADMIN_SECRET_KEY = "q/9^}H=W:HJ;%}t>$`YR$g1["  # <<-- UPDATE THIS!


class AdminGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Teal Timesheet License Admin")
        self.root.geometry("800x750")  # Increased width for Treeview
        self.root.resizable(True, True)  # Allow resizing now for better usability

        self.admin_key = None
        # No longer need to store all activated_devices here, Treeview will manage
        # self.activated_devices = {}

        self._create_login_ui()

    def _create_login_ui(self):
        """Creates the initial login interface for the admin."""
        self.login_frame = ttk.Frame(self.root, padding="20")
        self.login_frame.pack(expand=True, fill="both")

        ttk.Label(
            self.login_frame, text="Admin Login", font=("Arial", 16, "bold")
        ).pack(pady=20)

        admin_key_label = ttk.Label(self.login_frame, text="Admin Secret Key:")
        admin_key_label.pack(pady=5)

        self.admin_key_entry = ttk.Entry(self.login_frame, show="*", width=30)
        self.admin_key_entry.pack(pady=5)
        self.admin_key_entry.bind(
            "<Return>", lambda event: self._attempt_login()
        )
        login_button = ttk.Button(
            self.login_frame, text="Login", command=self._attempt_login
        )
        login_button.pack(pady=10)

    def _attempt_login(self):
        """Attempts to log in the admin using the provided key."""
        entered_key = self.admin_key_entry.get()
        if entered_key == ADMIN_SECRET_KEY:
            self.admin_key = entered_key
            self.login_frame.destroy()
            self._create_main_admin_ui()
            self.refresh_status()
        else:
            messagebox.showerror(
                "Login Failed", "Incorrect Admin Secret Key.", parent=self.root
            )
            self.admin_key_entry.delete(0, tk.END)

    def _create_main_admin_ui(self):
        """Creates the main admin dashboard interface."""
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(expand=True, fill="both")

        # --- Status Display ---
        status_frame = ttk.LabelFrame(
            self.main_frame, text="License Status", padding="10"
        )
        status_frame.pack(pady=10, fill="x")  # Removed expand=True to prevent vertical stretch

        self.total_licenses_label = ttk.Label(
            status_frame, text="Total Licenses: N/A", font=("Arial", 12)
        )
        self.total_licenses_label.pack(anchor="w", pady=2)
        self.activated_count_label = ttk.Label(
            status_frame, text="Activated Count: N/A", font=("Arial", 12)
        )
        self.activated_count_label.pack(anchor="w", pady=2)
        self.licenses_remaining_label = ttk.Label(
            status_frame, text="Licenses Remaining: N/A", font=("Arial", 12, "bold")
        )
        self.licenses_remaining_label.pack(anchor="w", pady=5)

        # --- Set Total Licenses ---
        set_licenses_frame = ttk.LabelFrame(
            self.main_frame, text="Set Total Licenses", padding="10"
        )
        set_licenses_frame.pack(pady=10, fill="x")  # Removed expand=True

        ttk.Label(set_licenses_frame, text="New Total:").pack(side="left", padx=5)
        self.new_total_entry = ttk.Entry(set_licenses_frame, width=10)
        self.new_total_entry.pack(side="left", padx=5)

        set_button = ttk.Button(
            set_licenses_frame, text="Set", command=self._set_total_licenses
        )
        set_button.pack(side="left", padx=5)

        # --- Activated Devices List (Treeview) ---
        devices_frame = ttk.LabelFrame(
            self.main_frame, text="Activated/Inactive Devices", padding="10"
        )
        devices_frame.pack(pady=10, fill="both", expand=True)  # THIS FRAME NOW EXPANDS

        # Define Treeview Columns
        columns = (
            "device_id",
            "username",
            "hostname",
            "status",
            "activated_at",
        )
        self.devices_tree = ttk.Treeview(
            devices_frame, columns=columns, show="headings", selectmode="extended"
        )

        # Setup Headings
        self.devices_tree.heading("device_id", text="Device ID")
        self.devices_tree.heading("username", text="Username")
        self.devices_tree.heading("hostname", text="Hostname")
        self.devices_tree.heading("status", text="Status")
        self.devices_tree.heading("activated_at", text="Activated At")

        # Setup Column Widths (adjust as needed)
        self.devices_tree.column("device_id", width=150, stretch=tk.YES)
        self.devices_tree.column("username", width=100, stretch=tk.YES)
        self.devices_tree.column("hostname", width=100, stretch=tk.YES)
        self.devices_tree.column("status", width=80, stretch=tk.NO)
        self.devices_tree.column("activated_at", width=150, stretch=tk.YES)

        self.devices_tree.pack(side="left", fill="both", expand=True)

        # Add Scrollbar to Treeview
        tree_scrollbar = ttk.Scrollbar(
            devices_frame, command=self.devices_tree.yview
        )
        tree_scrollbar.pack(side="right", fill="y")
        self.devices_tree.config(yscrollcommand=tree_scrollbar.set)

        # --- Activation/Deactivation Buttons ---
        action_buttons_frame = ttk.Frame(self.main_frame)
        action_buttons_frame.pack(pady=10, fill="x")

        activate_button = ttk.Button(
            action_buttons_frame, text="Activate Selected", command=self._activate_selected_devices
        )
        activate_button.pack(side="left", expand=True, padx=5)

        deactivate_button = ttk.Button(
            action_buttons_frame, text="Deactivate Selected", command=self._deactivate_selected_devices
        )
        deactivate_button.pack(side="left", expand=True, padx=5)

        # --- Action Buttons (Refresh) ---
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(pady=10, fill="x")  # Moved below activate/deactivate buttons

        refresh_button = ttk.Button(
            button_frame, text="Refresh Status", command=self.refresh_status
        )
        refresh_button.pack(side="left", expand=True, padx=5)

    def refresh_status(self):
        """Fetches and updates license status from the backend."""
        try:
            response = requests.get(
                f"{LICENSE_ADMIN_API_URL}/admin/view_status?admin_key={self.admin_key}"
            )
            response.raise_for_status()
            status_data = response.json()

            self.total_licenses_label.config(
                text=f"Total Licenses: {status_data['total_licenses']}"
            )
            self.activated_count_label.config(
                text=f"Activated Count: {status_data['activated_count']}"
            )
            self.licenses_remaining_label.config(
                text=f"Licenses Remaining: {status_data['licenses_remaining']}"
            )

            # Clear Treeview
            for i in self.devices_tree.get_children():
                self.devices_tree.delete(i)

            # Populate Treeview
            if status_data["activated_devices"]:
                for device_id, info in status_data[
                    "activated_devices"].items():  # Backend sends dict, not list of dicts
                    self.devices_tree.insert(
                        "",
                        "end",
                        values=(
                            device_id,
                            info.get("username", "N/A"),
                            info.get("hostname", "N/A"),
                            info.get("status", "N/A"),
                            info.get("activated_at", "N/A"),
                        ),
                    )
            else:
                # Insert a placeholder row if no devices
                self.devices_tree.insert(
                    "", "end", values=("No devices activated.", "", "", "", "")
                )

        except requests.exceptions.ConnectionError:
            messagebox.showerror(
                "Connection Error",
                f"Could not connect to the backend at {LICENSE_ADMIN_API_URL}. Is it running?",
                parent=self.root,
            )
        except requests.exceptions.HTTPError as e:
            messagebox.showerror(
                "API Error",
                f"Failed to fetch status: HTTP {e.response.status_code} - {e.response.text}",
                parent=self.root,
            )
        except Exception as e:
            messagebox.showerror(
                "Error", f"An unexpected error occurred: {e}", parent=self.root
            )

    def _set_total_licenses(self):
        """Sends request to set new total license count."""
        try:
            new_total_str = self.new_total_entry.get()
            new_total = int(new_total_str)
            if new_total < 0:
                messagebox.showwarning(
                    "Invalid Input", "Total licenses cannot be negative.", parent=self.root
                )
                return

            payload = {"new_total_licenses": new_total, "admin_key": self.admin_key}
            response = requests.post(
                f"{LICENSE_ADMIN_API_URL}/admin/set_total_licenses", json=payload
            )
            response.raise_for_status()
            result = response.json()
            if result.get("success"):
                messagebox.showinfo(
                    "Success",
                    result.get("message", "Total licenses updated successfully!"),
                    parent=self.root,
                )
                self.new_total_entry.delete(0, tk.END)
                self.refresh_status()
            else:
                messagebox.showerror(
                    "Update Failed",
                    result.get("message", "Unknown error setting total licenses."),
                    parent=self.root,
                )

        except ValueError:
            messagebox.showwarning(
                "Invalid Input",
                "Please enter a whole number for total licenses.",
                parent=self.root,
            )
        except requests.exceptions.ConnectionError:
            messagebox.showerror(
                "Connection Error",
                f"Could not connect to the backend at {LICENSE_ADMIN_API_URL}. Is it running?",
                parent=self.root,
            )
        except requests.exceptions.HTTPError as e:
            messagebox.showerror(
                "API Error",
                f"Failed to set total licenses: HTTP {e.response.status_code} - {e.response.text}",
                parent=self.root,
            )
        except Exception as e:
            messagebox.showerror(
                "Error", f"An unexpected error occurred: {e}", parent=self.root
            )

    def _process_selected_devices(self, action_type):
        """Activates or deactivates selected devices."""
        selected_items = self.devices_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select one or more devices.", parent=self.root)
            return

        device_ids_to_process = [self.devices_tree.item(item)['values'][0] for item in selected_items]

        success_count = 0
        fail_count = 0

        for device_id in device_ids_to_process:
            try:
                payload = {"device_id": device_id, "admin_key": self.admin_key}
                endpoint = ""
                if action_type == "activate":
                    endpoint = f"{LICENSE_ADMIN_API_URL}/admin/activate_device"
                elif action_type == "deactivate":
                    endpoint = f"{LICENSE_ADMIN_API_URL}/admin/deactivate_device"

                if not endpoint:  # Safety check
                    continue

                response = requests.post(endpoint, json=payload)
                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"Failed to {action_type} {device_id}: {result.get('message')}")

            except requests.exceptions.RequestException as e:
                fail_count += 1
                print(f"Network/API Error for {device_id}: {e}")
            except Exception as e:
                fail_count += 1
                print(f"Unexpected error for {device_id}: {e}")

        if success_count > 0:
            messagebox.showinfo(
                "Operation Complete",
                f"Successfully {action_type}d {success_count} device(s).",
                parent=self.root,
            )
        if fail_count > 0:
            messagebox.showerror(
                "Operation Failed",
                f"Failed to {action_type} {fail_count} device(s). Check console for details.",
                parent=self.root,
            )

        self.refresh_status()  # Always refresh after processing

    def _activate_selected_devices(self):
        self._process_selected_devices("activate")

    def _deactivate_selected_devices(self):
        self._process_selected_devices("deactivate")


if __name__ == "__main__":
    root = tk.Tk()
    app = AdminGUI(root)
    root.mainloop()