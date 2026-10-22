import os, json, base64, ctypes, subprocess, sys, urllib.request, hashlib, threading, time
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

APP_VERSION = "1.0.8"
OWNER, REPO = "ryuzacx", "V"
ROOT = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VLauncher")
DATA_FILE = os.path.join(ROOT, "accounts.json")
SETTINGS_FILE = os.path.join(ROOT, "settings.json")
PROFILES_DIR = os.path.join(ROOT, "chrome_profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(ROOT, exist_ok=True)

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

def dpapi(data, decrypt=False):
    raw = ctypes.create_string_buffer(data, len(data))
    inp = DATA_BLOB(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    out = DATA_BLOB()
    c, k = ctypes.windll.crypt32, ctypes.windll.kernel32
    if decrypt:
        ok = c.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out))
    else:
        ok = c.CryptProtectData(ctypes.byref(inp), "V Launcher credentials", None, None, None, 0, ctypes.byref(out))
    if not ok: raise ctypes.WinError()
    try: return ctypes.string_at(out.pbData, out.cbData)
    finally: k.LocalFree(out.pbData)

def load_accounts():
    if not os.path.exists(DATA_FILE): return []
    try:
        rows = json.load(open(DATA_FILE, encoding="utf-8"))
        result = []
        for row in rows:
            try:
                u, p = dpapi(base64.b64decode(row["secret"]), True).decode().split("\n", 1)
                result.append({"username": u, "password": p, "group": str(row.get("group", "Default") or "Default")})
            except Exception: pass
        return result
    except Exception: return []

def save_accounts(accounts):
    rows = [{"secret": base64.b64encode(dpapi((a["username"]+"\n"+a["password"]).encode())).decode(), "group": str(a.get("group", "Default") or "Default")} for a in accounts]
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(rows, f)
    os.replace(tmp, DATA_FILE)

def find_chrome():
    paths = [
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe")]
    return next((p for p in paths if os.path.isfile(p)), None)

class App:
    def __init__(self, root):
        self.root, self.accounts = root, load_accounts()
        root.title("V"); root.geometry("1000x760"); root.minsize(875, 700)
        self.settings = {}
        self.bg_path = ""
        self.bg_photo = None
        self.bg_label = tk.Label(root, bd=0, bg="#071326")
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            if os.path.isfile(SETTINGS_FILE):
                with open(SETTINGS_FILE, encoding="utf-8") as sf:
                    self.settings = json.load(sf)
                self.bg_path = self.settings.get("background", "")
        except Exception:
            self.settings = {}
            self.bg_path = ""
        root.bind("<Configure>", self._resize_background)
        style = ttk.Style(root)
        style.theme_use("clam")
        root.configure(bg="#071326")
        style.configure("TFrame", background="#071326")
        style.configure("TLabel", background="#071326", foreground="#dbeafe")
        style.configure("TButton", background="#17365d", foreground="#eaf2ff", bordercolor="#2b4d78", padding=(8,5))
        style.map("TButton", background=[("active", "#24558a"), ("pressed", "#102b4d")])
        style.configure("TEntry", fieldbackground="#10213b", foreground="#eaf2ff", insertcolor="#ffffff")
        style.configure("TSpinbox", fieldbackground="#10213b", foreground="#eaf2ff", arrowcolor="#dbeafe")
        style.configure("Treeview", background="#0b1b31", fieldbackground="#0b1b31", foreground="#e2eaf7",
                        bordercolor="#203653", rowheight=27, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#183b66", foreground="#ffffff",
                        relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Treeview.Heading", background=[("active", "#24558a")])
        style.map("Treeview", background=[("selected", "#24558a")], foreground=[("selected", "#ffffff")])
        f = ttk.Frame(root, padding=12)
        f.place(x=0, y=0, width=875)
        title_row = ttk.Frame(f)
        title_row.pack(fill="x")
        ttk.Label(title_row, text="V — Roblox Manual Session Launcher", font=("Segoe UI", 15, "bold")).pack(side="left", anchor="w")
        ttk.Button(title_row, text="Show Controls", command=self.show_control_panel).pack(side="right")
        ttk.Label(f, text="Save accounts as username:password. Login is manual.").pack(anchor="w", pady=(3,10))
        row = ttk.Frame(f); row.pack(fill="x", pady=(0,8))
        self.entry = ttk.Entry(row); self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.add())
        ttk.Button(row, text="Add account", command=self.add).pack(side="left", padx=(8,0))
        joinrow = ttk.Frame(f); joinrow.pack(fill="x", pady=(0,8))
        ttk.Label(joinrow, text="Game URL:").pack(side="left")
        self.url_entry = ttk.Entry(joinrow)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(6,10))
        ttk.Label(joinrow, text="Interval (detik):").pack(side="left")
        self.interval = tk.StringVar(value="10")
        ttk.Spinbox(joinrow, from_=1, to=3600, width=6, textvariable=self.interval).pack(side="left", padx=(6,0))

        self.auto_join_users = set()
        table_frame = ttk.Frame(f, width=850, height=300)
        table_frame.pack(anchor="w", fill="none", expand=False)
        table_frame.pack_propagate(False)
        self.tree = ttk.Treeview(table_frame, columns=("username","auto_join"), show="tree headings", selectmode="extended", height=10)
        self.tree.heading("#0", text="Group / Account", anchor="w")
        self.tree.heading("username", text="Username", anchor="w")
        self.tree.heading("auto_join", text="Auto Join", anchor="center")
        self.tree.column("#0", width=300, minwidth=180, stretch=False)
        self.tree.column("username", width=260, minwidth=140, stretch=False)
        self.tree.column("auto_join", width=100, minwidth=90, stretch=False, anchor="center")
        self.tree.tag_configure("group", background="#172b46", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("row_even", background="#0b1b31", foreground="#dce8f8")
        self.tree.tag_configure("row_odd", background="#10243e", foreground="#dce8f8")
        self.tree.bind("<Button-1>", self.on_tree_click, True)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.context_menu = tk.Menu(root, tearoff=0, bg="#10243e", fg="#eaf2ff",
                                     activebackground="#24558a", activeforeground="#ffffff",
                                     bd=0, relief="flat")
        self.context_menu.add_command(label="Copy username", command=lambda: self.copy_selected("username"))
        self.context_menu.add_command(label="Copy password", command=lambda: self.copy_selected("password"))
        self.context_menu.add_command(label="Copy username:password", command=lambda: self.copy_selected("combo"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Ganti Group / Move To Group", command=self.move_selected_to_group)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.status = tk.StringVar(value="Ready")
        self._panel_save_job = None
        self._build_control_panel()

        self.join_queue = []
        self.queue_active = False
        self.refresh()
        root.after(1500, self.check_update)

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE + ".tmp", "w", encoding="utf-8") as sf:
                json.dump(self.settings, sf, indent=2)
            os.replace(SETTINGS_FILE + ".tmp", SETTINGS_FILE)
        except Exception:
            pass

    def _build_control_panel(self):
        self.control_panel = tk.Toplevel(self.root)
        self.control_panel.title("V — Controls & Activity")
        self.control_panel.configure(bg="#071326")
        self.control_panel.minsize(560, 220)
        self.control_panel.geometry(self.settings.get("control_geometry", "900x300+20+500"))
        try:
            self.panel_opacity = max(20, min(100, int(self.settings.get("control_opacity", 75))))
        except (TypeError, ValueError):
            self.panel_opacity = 75
        self.control_panel.attributes("-alpha", self.panel_opacity / 100)
        panel = ttk.Frame(self.control_panel, padding=10)
        panel.pack(fill="both", expand=True)
        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", pady=(0,8))
        ttk.Button(buttons, text="Open browser", command=lambda: self.open("https://www.roblox.com/home")).pack(side="left")
        ttk.Button(buttons, text="Auto Join", command=self.auto_join).pack(side="left", padx=(8,0))
        ttk.Button(buttons, text="Stop queue", command=self.stop_queue).pack(side="left", padx=(8,0))
        ttk.Button(buttons, text="Open manual login", command=lambda: self.open("https://www.roblox.com/login")).pack(side="left", padx=8)
        ttk.Button(buttons, text="Delete selected", command=self.delete).pack(side="left", padx=8)
        ttk.Button(buttons, text="Select all", command=self.select_all_accounts).pack(side="left")
        ttk.Button(buttons, text="Clear selection", command=lambda: self.tree.selection_remove(self.tree.selection())).pack(side="left", padx=8)
        ttk.Button(buttons, text="Ganti BG", command=self.change_background).pack(side="left", padx=(8,0))

        opacity_row = ttk.Frame(panel)
        opacity_row.pack(fill="x", pady=(0,6))
        ttk.Label(opacity_row, text="Opacity:").pack(side="left")
        self.opacity_value = tk.StringVar(value=f"{self.panel_opacity}%")
        ttk.Label(opacity_row, textvariable=self.opacity_value, width=5).pack(side="left", padx=(4,8))
        self.opacity_scale = tk.Scale(opacity_row, from_=20, to=100, orient="horizontal",
                                      showvalue=False, resolution=1, length=180,
                                      bg="#071326", fg="#dbeafe", troughcolor="#183b66",
                                      highlightthickness=0, bd=0, command=self._set_panel_opacity)
        self.opacity_scale.set(self.panel_opacity)
        self.opacity_scale.pack(side="left")
        ttk.Label(opacity_row, text="Drag the panel to move; resize its edges. Position, size and opacity save automatically.").pack(side="left", padx=(10,0))

        status_row = ttk.Frame(panel)
        status_row.pack(fill="x", pady=(0,6))
        ttk.Label(status_row, textvariable=self.status, relief="sunken", anchor="w").pack(side="left", fill="x", expand=True)
        log_header = ttk.Frame(panel)
        log_header.pack(fill="x", pady=(0,3))
        ttk.Label(log_header, text="Activity Log", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.live_clock = ttk.Label(log_header, text="--:--:--", font=("Consolas", 10, "bold"))
        self.live_clock.pack(side="right")
        log_frame = ttk.Frame(panel)
        log_frame.pack(fill="both", expand=True)
        self.log_box = tk.Text(log_frame, height=6, wrap="word", state="disabled",
                               bg="#08172a", fg="#cbdcf3", insertbackground="#ffffff",
                               selectbackground="#24558a", relief="flat", bd=0,
                               font=("Consolas", 9), padx=8, pady=6)
        self.log_box.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_box.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_box.configure(yscrollcommand=log_scroll.set)
        self.status.trace_add("write", self._status_changed)
        self.root.after(250, self._update_clock)
        self.control_panel.bind("<Configure>", self._schedule_panel_save)
        self.control_panel.protocol("WM_DELETE_WINDOW", self._hide_control_panel)
        self.control_panel.update_idletasks()
        if "control_geometry" not in self.settings:
            screen_h = self.control_panel.winfo_screenheight()
            self.control_panel.geometry(f"900x300+20+{max(0, screen_h - 330)}")
        self._schedule_panel_save()

    def _set_panel_opacity(self, value):
        try:
            self.panel_opacity = max(20, min(100, int(float(value))))
            self.opacity_value.set(f"{self.panel_opacity}%")
            self.control_panel.attributes("-alpha", self.panel_opacity / 100)
            self.settings["control_opacity"] = self.panel_opacity
            self._schedule_panel_save()
        except (tk.TclError, ValueError):
            pass

    def _schedule_panel_save(self, event=None):
        if event is not None and event.widget is not self.control_panel:
            return
        if self._panel_save_job is not None:
            try:
                self.root.after_cancel(self._panel_save_job)
            except tk.TclError:
                pass
        self._panel_save_job = self.root.after(450, self._persist_panel_settings)

    def _persist_panel_settings(self):
        self._panel_save_job = None
        try:
            if self.control_panel.winfo_exists() and self.control_panel.state() != "withdrawn":
                self.settings["control_geometry"] = self.control_panel.geometry()
            self.settings["control_opacity"] = self.panel_opacity
            self._save_settings()
        except tk.TclError:
            pass

    def _hide_control_panel(self):
        self._persist_panel_settings()
        self.control_panel.withdraw()
        self.status.set("Controls hidden. Click Show Controls to reopen.")

    def show_control_panel(self):
        if not self.control_panel.winfo_exists():
            return
        self.control_panel.deiconify()
        self.control_panel.lift()
        self.status.set("Controls panel opened.")

    def _resize_background(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if not self.bg_path or not os.path.isfile(self.bg_path):
            self.bg_label.configure(image="", bg="#071326")
            self.bg_photo = None
            return
        try:
            image = Image.open(self.bg_path).convert("RGB")
            width = max(1, self.root.winfo_width())
            height = max(1, self.root.winfo_height())
            scale = max(width / image.width, height / image.height)
            size = (max(width, int(image.width * scale)), max(height, int(image.height * scale)))
            image = image.resize(size, Image.Resampling.LANCZOS)
            left = max(0, (image.width - width) // 2)
            top = max(0, (image.height - height) // 2)
            image = image.crop((left, top, left + width, top + height))
            self.bg_photo = ImageTk.PhotoImage(image)
            self.bg_label.configure(image=self.bg_photo)
            self.bg_label.lower()
        except Exception as e:
            self.bg_label.configure(image="", bg="#071326")
            self.bg_photo = None
            self.log_activity(f"Background image could not be loaded: {e}")

    def change_background(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Pilih background",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("All files", "*.*")])
        if not path:
            return
        try:
            with Image.open(path) as im:
                im.verify()
            self.bg_path = path
            self.settings["background"] = self.bg_path
            self._save_settings()
            self._resize_background()
            self.status.set("Background changed.")
        except Exception as e:
            messagebox.showerror("Background gagal", str(e), parent=self.root)

    def _update_clock(self):
        self.live_clock.configure(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._update_clock)

    def _status_changed(self, *_):
        message = self.status.get().strip()
        if message:
            self.log_activity(message)

    def log_activity(self, message):
        if not hasattr(self, "log_box"):
            return
        stamp = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {message}\n")
        self.log_box.see("end")
        # Keep the activity panel bounded during long sessions.
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 300:
            self.log_box.delete("1.0", f"{lines-300}.0")
        self.log_box.configure(state="disabled")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        grouped = {}
        for i, account in enumerate(self.accounts):
            group = str(account.get("group", "Default") or "Default").strip() or "Default"
            account["group"] = group
            key = group.casefold()
            if key not in grouped:
                grouped[key] = {"name": group, "accounts": []}
            grouped[key]["accounts"].append((i, account))
        for group_index, group_data in enumerate(grouped.values()):
            group_id = f"group_{group_index}"
            members = group_data["accounts"]
            self.tree.insert("", "end", iid=group_id, text=f'{group_data["name"]} ({len(members)})',
                             values=("", ""), open=True, tags=("group",))
            for row_index, (i, account) in enumerate(members):
                username = account["username"]
                checkbox = "☑" if username in self.auto_join_users else "☐"
                tag = "row_even" if row_index % 2 == 0 else "row_odd"
                self.tree.insert(group_id, "end", iid=str(i), text=username,
                                 values=(username, checkbox), tags=(tag,))

    def select_all_accounts(self):
        self.tree.selection_set([str(i) for i in range(len(self.accounts))])

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item or not item.isdigit():
            return
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        self.tree.focus(item)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def copy_selected(self, kind):
        ids = sorted(int(item) for item in self.tree.selection() if item.isdigit())
        if not ids:
            return
        values = []
        for i in ids:
            account = self.accounts[i]
            if kind == "username":
                values.append(account["username"])
            elif kind == "password":
                values.append(account["password"])
            else:
                values.append(account["username"] + ":" + account["password"])
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(values))
        self.status.set(f"Copied {len(values)} account(s) to clipboard.")

    def move_selected_to_group(self):
        ids = sorted(int(item) for item in self.tree.selection() if item.isdigit())
        if not ids:
            return
        existing = sorted({str(a.get("group", "Default") or "Default") for a in self.accounts}, key=str.casefold)
        dialog = tk.Toplevel(self.root)
        dialog.title("Ganti Group / Move To Group")
        dialog.configure(bg="#071326")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Pindahkan {len(ids)} akun ke group:").pack(anchor="w", pady=(0,8))
        group_var = tk.StringVar(value=str(self.accounts[ids[0]].get("group", "Default") or "Default"))
        entry = ttk.Combobox(frame, textvariable=group_var, values=existing, width=30)
        entry.pack(fill="x", pady=(0,12))
        entry.focus_set()
        def apply_group():
            name = group_var.get().strip()
            if not name:
                messagebox.showerror("Nama group kosong", "Masukkan nama group terlebih dahulu.", parent=dialog)
                return
            canonical = next((g for g in existing if g.casefold() == name.casefold()), name)
            for i in ids:
                self.accounts[i]["group"] = canonical
            try:
                save_accounts(self.accounts)
            except Exception as e:
                messagebox.showerror("Save failed", str(e), parent=dialog)
                return
            dialog.destroy()
            self.refresh()
            self.status.set(f"{len(ids)} akun dipindahkan ke group {canonical}.")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Move", command=apply_group).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(8,0))
        entry.bind("<Return>", lambda event: apply_group())

    def on_tree_click(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item or item == "group_default":
            return
        if column == "#2":
            try:
                username = self.accounts[int(item)]["username"]
            except (ValueError, IndexError):
                return "break"
            if username in self.auto_join_users:
                self.auto_join_users.remove(username)
            else:
                self.auto_join_users.add(username)
            self.tree.set(item, "auto_join", "☑" if username in self.auto_join_users else "☐")
            return "break"

    def add(self):
        value = self.entry.get().strip()
        if ":" not in value: return messagebox.showerror("Invalid format", "Use username:password")
        u,p = value.split(":",1)
        if not u or not p: return messagebox.showerror("Invalid format", "Username and password cannot be empty.")
        if any(a["username"].casefold()==u.casefold() for a in self.accounts):
            return messagebox.showinfo("Duplicate account", "That username is already saved.")
        self.accounts.append({"username":u,"password":p,"group":"Default"})
        try: save_accounts(self.accounts)
        except Exception as e:
            self.accounts.pop(); return messagebox.showerror("Save failed", str(e))
        self.entry.delete(0,"end"); self.refresh(); self.status.set("Account saved.")

    def delete(self):
        ids = sorted((int(i) for i in self.tree.selection() if i.isdigit()), reverse=True)
        if not ids: return
        if not messagebox.askyesno("Delete accounts", "Delete selected saved accounts? Chrome profile folders are kept."): return
        removed = {self.accounts[i]["username"] for i in ids}
        for i in ids: self.accounts.pop(i)
        self.auto_join_users.difference_update(removed)
        save_accounts(self.accounts); self.refresh(); self.status.set("Selected accounts deleted.")

    def open(self, url):
        ids = [int(i) for i in self.tree.selection() if i.isdigit()]
        if not ids: return messagebox.showinfo("Select accounts", "Select one or more account rows first.")
        chrome = find_chrome()
        if not chrome: return messagebox.showerror("Chrome not found", "Install Google Chrome, then restart V.")
        for i in ids:
            u = self.accounts[i]["username"]
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in u)
            profile = os.path.join(PROFILES_DIR, safe); os.makedirs(profile, exist_ok=True)
            try: subprocess.Popen([chrome, "--user-data-dir="+profile, "--no-first-run", "--no-default-browser-check", url])
            except Exception as e: return messagebox.showerror("Chrome launch failed", str(e))
        self.status.set(f"Opened {len(ids)} selected account browser(s).")

    def auto_join(self):
        url = self.url_entry.get().strip()
        if not (url.startswith("https://") or url.startswith("http://")):
            return messagebox.showerror("Invalid game URL", "Paste the full Roblox game URL, starting with https://")
        ids = [i for i, a in enumerate(self.accounts) if a["username"] in self.auto_join_users]
        if not ids:
            return messagebox.showinfo("Auto Join", "Tick the Auto Join checkbox for at least one account.")
        try:
            interval = int(self.interval.get().strip())
            if interval < 1 or interval > 3600: raise ValueError()
        except ValueError:
            return messagebox.showerror("Invalid interval", "Interval must be a whole number from 1 to 3600 seconds.")
        chrome = find_chrome()
        if not chrome:
            return messagebox.showerror("Chrome not found", "Install Google Chrome, then restart V.")
        if self.queue_active:
            return messagebox.showinfo("Queue running", "Stop the current queue before starting another.")
        self.join_queue = [(i, url) for i in ids]
        self.queue_active = True
        self.queue_chrome = chrome
        self.queue_interval_ms = interval * 1000
        self.status.set(f"Auto Join started: {len(ids)} account(s), interval {interval}s.")
        self._launch_next_join()

    def _launch_next_join(self):
        if not self.queue_active:
            return
        if not self.join_queue:
            self.queue_active = False
            self.status.set("Auto Join queue completed.")
            return
        i, url = self.join_queue.pop(0)
        username = self.accounts[i]["username"]
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in username)
        profile = os.path.join(PROFILES_DIR, safe)
        os.makedirs(profile, exist_ok=True)
        try:
            subprocess.Popen([self.queue_chrome, "--user-data-dir=" + profile,
                              "--no-first-run", "--no-default-browser-check", url])
            remaining = len(self.join_queue)
            self.status.set(f"Auto Join: opened {username}; {remaining} account(s) waiting.")
        except Exception as e:
            self.status.set(f"Auto Join failed for {username}: {e}")
        if self.join_queue and self.queue_active:
            self.root.after(self.queue_interval_ms, self._launch_next_join)
        else:
            self.queue_active = False
            self.status.set("Auto Join queue completed.")

    def stop_queue(self):
        if self.queue_active:
            self.queue_active = False
            self.join_queue = []
            self.status.set("Auto Join queue stopped.")
        else:
            self.status.set("No Auto Join queue is running.")
    def check_update(self):
        if not getattr(sys, "frozen", False):
            self.status.set(f"V {APP_VERSION} — updater requires packaged V.exe."); return
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        try:
            req=urllib.request.Request(f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest", headers={"User-Agent":"V-Updater"})
            with urllib.request.urlopen(req, timeout=8) as r: rel=json.loads(r.read().decode())
            ver=rel.get("tag_name","").lstrip("vV")
            if not ver or tuple(map(int,ver.split("."))) <= tuple(map(int,APP_VERSION.split("."))):
                self.root.after(0, lambda: self.status.set(f"V {APP_VERSION} — up to date.")); return
            assets={a["name"]:a["browser_download_url"] for a in rel.get("assets",[])}
            if "V.exe" not in assets or "V.exe.sha256" not in assets: return
            self.root.after(0, lambda: self.offer_update(ver,assets["V.exe"],assets["V.exe.sha256"]))
        except Exception: pass

    def offer_update(self, ver, exe_url, hash_url):
        if messagebox.askyesno("V update available", f"V {ver} is available. Download and verify now?"):
            self.status.set("Downloading update…")
            threading.Thread(target=self.download_update,args=(ver,exe_url,hash_url),daemon=True).start()

    def download_update(self, ver, exe_url, hash_url):
        try:
            def get(url,path):
                req=urllib.request.Request(url,headers={"User-Agent":"V-Updater"})
                with urllib.request.urlopen(req,timeout=60) as r, open(path,"wb") as f:
                    while True:
                        block=r.read(1024*1024)
                        if not block: break
                        f.write(block)
            stage=os.path.join(ROOT,"V_update_staged.exe"); hpath=os.path.join(ROOT,"V_update_staged.sha256")
            get(hash_url,hpath); get(exe_url,stage)
            expected=open(hpath,encoding="utf-8-sig").read().strip().split()[0].lower()
            digest=hashlib.sha256(open(stage,"rb").read()).hexdigest()
            if len(expected)!=64 or digest!=expected: raise ValueError("SHA-256 verification failed; update rejected.")
            helper=os.path.join(os.path.dirname(sys.executable),"VUpdater.exe")
            if not os.path.isfile(helper): raise FileNotFoundError("VUpdater.exe is missing beside V.exe.")
            subprocess.Popen([helper,sys.executable,stage,str(os.getpid()),ver],close_fds=True)
            self.root.after(0,self.root.destroy)
        except Exception as e:
            self.root.after(0,lambda:messagebox.showerror("Update failed",str(e)))
            self.root.after(0,lambda:self.status.set("Update failed; current V unchanged."))

if __name__ == "__main__":
    if os.name != "nt": print("V is designed for Windows.")
    else:
        root=tk.Tk(); App(root); root.mainloop()
