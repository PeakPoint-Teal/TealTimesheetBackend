import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import requests
import json

# --- Configuration for the Admin GUI ---
LICENSE_ADMIN_API_URL = "https://teal-timesheet-licensing-api.onrender.com"
ADMIN_SECRET_KEY = "q/9^}H=W:HJ;%}t>$`YR$g1["  # <<-- IMPORTANT: Use your actual secret key
DEFAULT_DOWNLOAD_URL = "https://www.peakpointenterprise.com/download-timesheet"


class AdminGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Teal Timesheet Admin Console")
        self.root.geometry("850x750")
        self.root.resizable(True, True)

        self.admin_key = None
        self._create_login_ui()

    def _create_login_ui(self):
        """Creates the initial login interface for the admin."""
        self.login_frame = ttk.Frame(self.root, padding="20")
        self.login_frame.pack(expand=True, fill="both")

        ttk.Label(self.login_frame, text="Admin Login", font=("Arial", 16, "bold")).pack(pady=20)
        ttk.Label(self.login_frame, text="Admin Secret Key:").pack(pady=5)

        self.admin_key_entry = ttk.Entry(self.login_frame, show="*", width=30)
        self.admin_key_entry.pack(pady=5)
        self.admin_key_entry.bind("<Return>", lambda event: self._attempt_login())

        login_button = ttk.Button(self.login_frame, text="Login", command=self._attempt_login)
        login_button.pack(pady=10)

    def _attempt_login(self):
        """Attempts to log in the admin using the provided key."""
        entered_key = self.admin_key_entry.get()
        if entered_key == ADMIN_SECRET_KEY:
            self.admin_key = entered_key
            self.login_frame.destroy()
            self._create_main_admin_ui()
            self.refresh_license_status()  # Refresh both on login
            self.refresh_version_status()
        else:
            messagebox.showerror("Login Failed", "Incorrect Admin Secret Key.", parent=self.root)
            self.admin_key_entry.delete(0, tk.END)

    def _create_main_admin_ui(self):
        """Creates the main admin dashboard interface with tabs."""
        self.main_notebook = ttk.Notebook(self.root)
        self.main_notebook.pack(expand=True, fill="both", padx=10, pady=10)

        # --- Tab 1: License Management ---
        license_tab_frame = ttk.Frame(self.main_notebook, padding="10")
        self.main_notebook.add(license_tab_frame, text="License Management")
        self._create_license_management_tab(license_tab_frame)

        # --- Tab 2: Version Management ---
        version_tab_frame = ttk.Frame(self.main_notebook, padding="10")
        self.main_notebook.add(version_tab_frame, text="Version Management")
        self._create_version_management_tab(version_tab_frame)

    def _create_license_management_tab(self, parent_frame):
        """Populates the license management tab."""
        # Status Display
        status_frame = ttk.LabelFrame(parent_frame, text="License Status", padding="10")
        status_frame.pack(pady=10, fill="x")
        self.total_licenses_label = ttk.Label(status_frame, text="Total Licenses: N/A", font=("Arial", 12))
        self.total_licenses_label.pack(anchor="w", pady=2)
        self.activated_count_label = ttk.Label(status_frame, text="Activated Count: N/A", font=("Arial", 12))
        self.activated_count_label.pack(anchor="w", pady=2)
        self.licenses_remaining_label = ttk.Label(status_frame, text="Licenses Remaining: N/A",
                                                  font=("Arial", 12, "bold"))
        self.licenses_remaining_label.pack(anchor="w", pady=5)

        # Set Total Licenses
        set_licenses_frame = ttk.LabelFrame(parent_frame, text="Set Total Licenses", padding="10")
        set_licenses_frame.pack(pady=10, fill="x")
        ttk.Label(set_licenses_frame, text="New Total:").pack(side="left", padx=5)
        self.new_total_entry = ttk.Entry(set_licenses_frame, width=10)
        self.new_total_entry.pack(side="left", padx=5)
        ttk.Button(set_licenses_frame, text="Set", command=self._set_total_licenses).pack(side="left", padx=5)

        # Activated Devices List
        devices_frame = ttk.LabelFrame(parent_frame, text="Activated/Inactive Devices", padding="10")
        devices_frame.pack(pady=10, fill="both", expand=True)
        columns = ("device_id", "username", "hostname", "status", "activated_at")
        self.devices_tree = ttk.Treeview(devices_frame, columns=columns, show="headings", selectmode="extended")

        for col_name in columns: self.devices_tree.heading(col_name, text=col_name.replace("_", " ").title())
        for col_name, width in [("device_id", 150), ("username", 100), ("hostname", 100), ("status", 80),
                                ("activated_at", 150)]:
            self.devices_tree.column(col_name, width=width, stretch=tk.YES if col_name != "status" else tk.NO)

        self.devices_tree.pack(side="left", fill="both", expand=True)
        tree_scrollbar = ttk.Scrollbar(devices_frame, command=self.devices_tree.yview)
        tree_scrollbar.pack(side="right", fill="y")
        self.devices_tree.config(yscrollcommand=tree_scrollbar.set)

        # Action Buttons
        action_buttons_frame = ttk.Frame(parent_frame)
        action_buttons_frame.pack(pady=10, fill="x")
        ttk.Button(action_buttons_frame, text="Activate Selected",
                   command=lambda: self._process_selected_devices("activate")).pack(side="left", expand=True, padx=5)
        ttk.Button(action_buttons_frame, text="Deactivate Selected",
                   command=lambda: self._process_selected_devices("deactivate")).pack(side="left", expand=True, padx=5)
        ttk.Button(action_buttons_frame, text="Refresh Licenses", command=self.refresh_license_status).pack(side="left",
                                                                                                            expand=True,
                                                                                                            padx=5)

    def _create_version_management_tab(self, parent_frame):
        """Populates the new version management tab."""
        # Version History
        history_frame = ttk.LabelFrame(parent_frame, text="Version History", padding="10")
        history_frame.pack(pady=10, fill="both", expand=True)

        columns = ("is_latest", "version_number", "release_date", "download_url")
        self.versions_tree = ttk.Treeview(history_frame, columns=columns, show="headings")

        self.versions_tree.heading("is_latest", text="Latest")
        self.versions_tree.heading("version_number", text="Version")
        self.versions_tree.heading("release_date", text="Release Date")
        self.versions_tree.heading("download_url", text="Download URL")

        self.versions_tree.column("is_latest", width=60, stretch=tk.NO, anchor="center")
        self.versions_tree.column("version_number", width=100, stretch=tk.NO)
        self.versions_tree.column("release_date", width=160, stretch=tk.NO)
        self.versions_tree.column("download_url", width=400, stretch=tk.YES)

        self.versions_tree.pack(side="left", fill="both", expand=True)
        ver_scrollbar = ttk.Scrollbar(history_frame, command=self.versions_tree.yview)
        ver_scrollbar.pack(side="right", fill="y")
        self.versions_tree.config(yscrollcommand=ver_scrollbar.set)

        # New Version Frame
        new_ver_frame = ttk.LabelFrame(parent_frame, text="Set Latest Version", padding="10")
        new_ver_frame.pack(pady=10, fill="x")

        ttk.Label(new_ver_frame, text="New Version #:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.new_version_entry = ttk.Entry(new_ver_frame, width=20)
        self.new_version_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(new_ver_frame, text="Download URL:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.download_url_entry = ttk.Entry(new_ver_frame, width=50)
        self.download_url_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.download_url_entry.insert(0, DEFAULT_DOWNLOAD_URL)
        new_ver_frame.columnconfigure(1, weight=1)

        # Action Buttons
        ver_action_frame = ttk.Frame(parent_frame)
        ver_action_frame.pack(pady=10, fill="x")
        ttk.Button(ver_action_frame, text="Set as Latest Version", command=self._set_latest_version).pack(side="left",
                                                                                                          padx=5)
        ttk.Button(ver_action_frame, text="Refresh Versions", command=self.refresh_version_status).pack(side="left",
                                                                                                        padx=5)

    def refresh_license_status(self):
        """Fetches and updates license status from the backend."""
        try:
            response = requests.get(f"{LICENSE_ADMIN_API_URL}/admin/view_status?admin_key={self.admin_key}")
            response.raise_for_status()
            status_data = response.json()
            self.total_licenses_label.config(text=f"Total Licenses: {status_data['total_licenses']}")
            self.activated_count_label.config(text=f"Activated Count: {status_data['activated_count']}")
            self.licenses_remaining_label.config(text=f"Licenses Remaining: {status_data['licenses_remaining']}")

            for i in self.devices_tree.get_children(): self.devices_tree.delete(i)
            if status_data.get("activated_devices"):
                for device_id, info in status_data["activated_devices"].items():
                    self.devices_tree.insert("", "end", values=(
                    device_id, info.get("username", "N/A"), info.get("hostname", "N/A"), info.get("status", "N/A"),
                    info.get("activated_at", "N/A")))
            else:
                self.devices_tree.insert("", "end", values=("No devices activated.", "", "", "", ""))
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Connection Error", f"Could not connect to the backend: {e}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self.root)

    def _set_total_licenses(self):
        """Sends request to set new total license count."""
        try:
            new_total = int(self.new_total_entry.get())
            if new_total < 0:
                messagebox.showwarning("Invalid Input", "Total licenses cannot be negative.", parent=self.root)
                return
            payload = {"new_total_licenses": new_total, "admin_key": self.admin_key}
            response = requests.post(f"{LICENSE_ADMIN_API_URL}/admin/set_total_licenses", json=payload)
            response.raise_for_status()
            result = response.json()
            if result.get("success"):
                messagebox.showinfo("Success", result.get("message"), parent=self.root)
                self.new_total_entry.delete(0, tk.END)
                self.refresh_license_status()
            else:
                messagebox.showerror("Update Failed", result.get("message"), parent=self.root)
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a whole number for total licenses.", parent=self.root)
        except requests.exceptions.RequestException as e:
            messagebox.showerror("API Error", f"Failed to set total licenses: {e}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self.root)

    def _process_selected_devices(self, action_type):
        """Activates or deactivates selected devices."""
        selected_items = self.devices_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select one or more devices.", parent=self.root)
            return

        device_ids = [self.devices_tree.item(item)['values'][0] for item in selected_items]
        endpoint = f"{LICENSE_ADMIN_API_URL}/admin/{action_type}_device"

        success_count, fail_count = 0, 0
        for device_id in device_ids:
            try:
                payload = {"device_id": device_id, "admin_key": self.admin_key}
                response = requests.post(endpoint, json=payload)
                response.raise_for_status()
                if response.json().get("success"):
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                print(f"Failed to {action_type} {device_id}: {e}")
                fail_count += 1

        if success_count > 0:
            messagebox.showinfo("Operation Complete", f"Successfully {action_type}d {success_count} device(s).",
                                parent=self.root)
        if fail_count > 0:
            messagebox.showerror("Operation Failed", f"Failed to {action_type} {fail_count} device(s). Check console.",
                                 parent=self.root)

        self.refresh_license_status()

    def refresh_version_status(self):
        """Fetches and updates the version history from the backend."""
        try:
            response = requests.get(f"{LICENSE_ADMIN_API_URL}/admin/get_versions?admin_key={self.admin_key}")
            response.raise_for_status()
            data = response.json()

            for i in self.versions_tree.get_children(): self.versions_tree.delete(i)

            if data.get("success") and data.get("versions"):
                for ver in data["versions"]:
                    latest_marker = "✅" if ver.get("is_latest") else ""
                    self.versions_tree.insert("", "end", values=(
                        latest_marker,
                        ver.get("version_number", "N/A"),
                        ver.get("release_date", "N/A"),
                        ver.get("download_url", "N/A")
                    ))
            else:
                self.versions_tree.insert("", "end", values=("", "Could not load versions.", "", ""))

        except requests.exceptions.RequestException as e:
            messagebox.showerror("Connection Error", f"Could not connect to the backend: {e}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self.root)

    def _set_latest_version(self):
        """Sends a request to set the new latest version."""
        new_version = self.new_version_entry.get().strip()
        download_url = self.download_url_entry.get().strip()

        if not new_version:
            messagebox.showwarning("Input Required", "Please enter a version number.", parent=self.root)
            return

        if not download_url:
            messagebox.showwarning("Input Required", "Please enter a download URL.", parent=self.root)
            return

        payload = {
            "version_number": new_version,
            "download_url": download_url,
            "admin_key": self.admin_key
        }

        try:
            response = requests.post(f"{LICENSE_ADMIN_API_URL}/admin/set_latest_version", json=payload)
            response.raise_for_status()
            result = response.json()
            if result.get("success"):
                messagebox.showinfo("Success", result.get("message"), parent=self.root)
                self.new_version_entry.delete(0, tk.END)
                self.refresh_version_status()  # Refresh the list to show the change
            else:
                messagebox.showerror("Update Failed", result.get("message", "An unknown error occurred."),
                                     parent=self.root)
        except requests.exceptions.RequestException as e:
            messagebox.showerror("API Error", f"Failed to set latest version: {e}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self.root)


if __name__ == "__main__":
    root = tk.Tk()
    app = AdminGUI(root)
    root.mainloop()
