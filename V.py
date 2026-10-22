import os, json, base64, ctypes, subprocess, sys, urllib.request, hashlib, threading
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox

APP_VERSION = "1.0.2"
OWNER, REPO = "ryuzacx", "V"
ROOT = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VLauncher")
DATA_FILE = os.path.join(ROOT, "accounts.json")
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
                result.append({"username": u, "password": p})
            except Exception: pass
        return result
    except Exception: return []

def save_accounts(accounts):
    rows = [{"secret": base64.b64encode(dpapi((a["username"]+"\n"+a["password"]).encode())).decode()} for a in accounts]
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
        root.title("V"); root.geometry("680x500"); root.minsize(600, 420)
        f = ttk.Frame(root, padding=12); f.pack(fill="both", expand=True)
        ttk.Label(f, text="V — Roblox Manual Session Launcher", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(f, text="Save accounts as username:password. Login is manual.").pack(anchor="w", pady=(3,10))
        row = ttk.Frame(f); row.pack(fill="x", pady=(0,8))
        self.entry = ttk.Entry(row); self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.add())
        ttk.Button(row, text="Add account", command=self.add).pack(side="left", padx=(8,0))
        self.tree = ttk.Treeview(f, columns=("username","status"), show="headings", selectmode="extended", height=13)
        self.tree.heading("username", text="Username"); self.tree.heading("status", text="Status")
        self.tree.column("username", width=260); self.tree.column("status", width=300)
        self.tree.pack(fill="both", expand=True)
        b = ttk.Frame(f); b.pack(fill="x", pady=(10,0))
        ttk.Button(b, text="Open browser", command=lambda: self.open("https://www.roblox.com/home")).pack(side="left")
        ttk.Button(b, text="Open manual login", command=lambda: self.open("https://www.roblox.com/login")).pack(side="left", padx=8)
        ttk.Button(b, text="Delete selected", command=self.delete).pack(side="left", padx=8)
        ttk.Button(b, text="Select all", command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="left")
        ttk.Button(b, text="Clear selection", command=lambda: self.tree.selection_remove(self.tree.selection())).pack(side="left", padx=8)
        self.status = tk.StringVar(value="Ready")
        ttk.Label(f, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", pady=(10,0))
        ttk.Label(f, text="CAPTCHA and 2FA must be completed manually.").pack(anchor="w", pady=(6,0))
        self.refresh()
        root.after(1500, self.check_update)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i,a in enumerate(self.accounts): self.tree.insert("", "end", iid=str(i), values=(a["username"], "Saved"))

    def add(self):
        value = self.entry.get().strip()
        if ":" not in value: return messagebox.showerror("Invalid format", "Use username:password")
        u,p = value.split(":",1)
        if not u or not p: return messagebox.showerror("Invalid format", "Username and password cannot be empty.")
        if any(a["username"].casefold()==u.casefold() for a in self.accounts):
            return messagebox.showinfo("Duplicate account", "That username is already saved.")
        self.accounts.append({"username":u,"password":p})
        try: save_accounts(self.accounts)
        except Exception as e:
            self.accounts.pop(); return messagebox.showerror("Save failed", str(e))
        self.entry.delete(0,"end"); self.refresh(); self.status.set("Account saved.")

    def delete(self):
        ids = sorted((int(i) for i in self.tree.selection()), reverse=True)
        if not ids: return
        if not messagebox.askyesno("Delete accounts", "Delete selected saved accounts? Chrome profile folders are kept."): return
        for i in ids: self.accounts.pop(i)
        save_accounts(self.accounts); self.refresh(); self.status.set("Selected accounts deleted.")

    def open(self, url):
        ids = [int(i) for i in self.tree.selection()]
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
