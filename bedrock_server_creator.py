#!/usr/bin/env python3
"""
Bedrock Server Creator
Crea y gestiona servidores dedicados de Minecraft BEDROCK (Windows / Linux).
- Descarga el Bedrock Dedicated Server oficial (o usa un ZIP local)
- Ajustes del mundo (mundo normal, plano, semilla, dificultad...)
- Addons (.mcaddon / .mcpack / .zip): se instalan y se registran en el mundo
- Mundos: subir tu propio mundo (.mcworld/.zip/carpeta), activarlo, exportarlo
- Staff: operadores, moderadores, helpers (permissions.json)
- Jugadores: kick, ban, op/deop, lista blanca, modo de juego, mensajes
- Comandos personalizados que el owner (creador del servidor) activa si quiere
- Nube: respaldos automáticos a la carpeta de tu nube (Drive, OneDrive, Dropbox, MEGA...) y restauración
- Herramientas: auto-reinicio, actualizar servidor, IP de conexión
- Consola integrada
100% gratis: solo Python, el servidor oficial gratuito y sin cuentas ni APIs de pago.
Requisitos: Python 3.8+ (tkinter incluido). No necesita Java.
Uso: python bedrock_server_creator.py
"""
import os, re, sys, json, stat, time, socket, shutil, zipfile, subprocess, threading, urllib.request
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

BASE = os.path.join(os.path.expanduser("~"), "BedrockServers")
UA = {"User-Agent": "BedrockServerCreator/1.0"}
LINKS_API = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
IS_WIN = sys.platform.startswith("win")
EXE = "bedrock_server.exe" if IS_WIN else "bedrock_server"

ROLES = {"Owner": "operator", "Admin": "operator", "Moderador": "operator", "Helper": "member"}
PERMS = ["operator", "member", "visitor"]

CMD_UUID = "6f1c5a1e-3b7d-4c0a-9a55-0c0ffee0c0de"
CMD_MOD_UUID = "7a2d6b2f-4c8e-4d1b-8b66-1d1ffee1d1ef"
CMD_TAG = "cmd_owner"
CFG_PATH = os.path.join(BASE, "app.json")

# Plantillas de comandos personalizados. {player} = el jugador que lo ejecuta (o el objetivo elegido).
PRESETS = [
    {"name": "curar", "desc": "Cura y sacia al jugador",
     "lines": ["effect {player} instant_health 1 10 true", "effect {player} saturation 1 10 true"]},
    {"name": "dia", "desc": "Pone el día", "lines": ["time set day"]},
    {"name": "noche", "desc": "Pone la noche", "lines": ["time set night"]},
    {"name": "sol", "desc": "Clima despejado", "lines": ["weather clear"]},
    {"name": "kit", "desc": "Kit inicial",
     "lines": ["give {player} bread 16", "give {player} iron_sword 1", "give {player} iron_pickaxe 1",
               "give {player} torch 32"]},
    {"name": "velocidad", "desc": "Velocidad 2 durante 2 minutos", "lines": ["effect {player} speed 120 1 true"]},
    {"name": "limpiar", "desc": "Vacía el inventario", "lines": ["clear {player}"]},
    {"name": "aviso", "desc": "Anuncio del staff", "lines": ["say Atención: mensaje del staff"]},
]


def fn_name(name):
    return re.sub(r"[^a-z0-9_]", "_", name.strip().lower()) or "cmd"


def load_cfg():
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg):
    os.makedirs(BASE, exist_ok=True)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def local_ip():
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sk.connect(("10.255.255.255", 1))
        return sk.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sk.close()

# (etiqueta, clave, tipo, opciones, valor por defecto)
SETTINGS = [
    ("Nombre del servidor", "server-name", "str", None, "Dedicated Server"),
    ("Nombre del mundo", "level-name", "str", None, "Bedrock level"),
    ("Semilla", "level-seed", "str", None, ""),
    ("Tipo de mundo", "level-type", "combo",
     {"Normal": "DEFAULT", "Superplano": "FLAT", "Legacy": "LEGACY"}, "DEFAULT"),
    ("Modo de juego", "gamemode", "combo", ["survival", "creative", "adventure"], "survival"),
    ("Dificultad", "difficulty", "combo", ["peaceful", "easy", "normal", "hard"], "easy"),
    ("Permiso por defecto", "default-player-permission-level", "combo", PERMS, "member"),
    ("Máx. jugadores", "max-players", "int", None, 10),
    ("Puerto IPv4", "server-port", "int", None, 19132),
    ("Puerto IPv6", "server-portv6", "int", None, 19133),
    ("Distancia de visión", "view-distance", "int", None, 32),
    ("Distancia de tick (4-12)", "tick-distance", "int", None, 4),
    ("Permitir cheats", "allow-cheats", "bool", None, False),
    ("Verificar cuentas Xbox", "online-mode", "bool", None, True),
    ("Lista blanca (allow-list)", "allow-list", "bool", None, False),
    ("Texture packs obligatorios", "texturepack-required", "bool", None, False),
]


# ---------- red ----------
def http_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.load(r)


def download(url, dest):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def official_server_url():
    kind = "serverBedrockWindows" if IS_WIN else "serverBedrockLinux"
    for l in http_json(LINKS_API)["result"]["links"]:
        if l["downloadType"] == kind:
            return l["downloadUrl"]
    raise RuntimeError("No se encontró el enlace de descarga oficial")


# ---------- JSON tolerante (los manifest de Bedrock suelen tener comentarios) ----------
def parse_json_loose(text):
    text = text.lstrip("\ufeff")
    out, i, n, instr = [], 0, len(text), False
    while i < n:
        c = text[i]
        if instr:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                instr = False
        elif c == '"':
            instr = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


def read_props(path):
    props = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    props[k] = v
    return props


# ---------- modelo ----------
class ServerData:
    def __init__(self, folder):
        self.folder = folder
        self.meta_path = os.path.join(folder, "mcsc.json")
        self.meta = {"version": "", "props": {}, "staff": [], "packs": [], "seen": {}, "bans": [],
                     "cloud": {"auto": False, "minutes": 30, "on_stop": True, "keep": 10, "hook": ""},
                     "cmds": {"enabled": False, "owner": "", "items": []}, "auto_restart": False}
        if os.path.exists(self.meta_path):
            with open(self.meta_path, encoding="utf-8") as f:
                self.meta.update(json.load(f))

    def save(self):
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2, ensure_ascii=False)

    def path(self, *p):
        return os.path.join(self.folder, *p)

    def write_properties(self):
        with open(self.path("server.properties"), "w", encoding="utf-8") as f:
            for k, v in self.meta["props"].items():
                f.write(f"{k}={v}\n")

    def write_permissions(self):
        entries = [{"permission": s["permission"], "xuid": s["xuid"]} for s in self.meta["staff"] if s.get("xuid")]
        with open(self.path("permissions.json"), "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)

    def sync_packs(self, remove_ids=()):
        """Registra los addons gestionados por la app en el mundo actual."""
        world = self.path("worlds", self.meta["props"].get("level-name", "Bedrock level"))
        os.makedirs(world, exist_ok=True)
        managed = {p["uuid"] for p in self.meta["packs"]} | set(remove_ids)
        for kind, fname in (("behavior", "world_behavior_packs.json"), ("resource", "world_resource_packs.json")):
            fp = os.path.join(world, fname)
            existing = []
            if os.path.exists(fp):
                try:
                    with open(fp, encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            keep = [e for e in existing if e.get("pack_id") not in managed]
            new = [{"pack_id": p["uuid"], "version": p["version"]} for p in self.meta["packs"] if p["type"] == kind]
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(keep + new, f, indent=2)

    def install_addon(self, zpath):
        """Instala los packs de un .mcaddon/.mcpack/.zip. Devuelve los nombres instalados."""
        z = zipfile.ZipFile(zpath)
        manifests = sorted((n for n in z.namelist() if n.endswith("manifest.json")), key=len)
        roots, done = [], []
        for m in manifests:
            root = m[: -len("manifest.json")]
            if any(root.startswith(r) for r in roots if r):
                continue
            try:
                mf = parse_json_loose(z.read(m).decode("utf-8", errors="replace"))
                head = mf["header"]
                mods = [x.get("type") for x in mf.get("modules", [])]
            except Exception:
                continue
            if "skin_pack" in mods or "world_template" in mods:
                continue
            kind = "resource" if "resources" in mods else "behavior"
            ver = head.get("version", [1, 0, 0])
            if isinstance(ver, str):
                ver = [int(x) if x.isdigit() else 0 for x in ver.split(".")][:3]
            pid = head["uuid"]
            safe = re.sub(r"[^\w\- ]", "", str(head.get("name", "pack"))).strip() or "pack"
            folder = f"{safe}_{pid[:8]}"
            dest = self.path("resource_packs" if kind == "resource" else "behavior_packs", folder)
            shutil.rmtree(dest, ignore_errors=True)
            for member in z.namelist():
                if member.startswith(root) and not member.endswith("/"):
                    target = os.path.join(dest, member[len(root):])
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
            self.meta["packs"] = [p for p in self.meta["packs"] if p["uuid"] != pid]
            self.meta["packs"].append({"name": head.get("name", safe), "uuid": pid, "version": ver,
                                       "type": kind, "folder": folder})
            roots.append(root)
            done.append(f"{head.get('name', safe)} ({'RP' if kind == 'resource' else 'BP'})")
        self.save()
        self.sync_packs()
        return done

    # --- mundos
    def worlds(self):
        d = self.path("worlds")
        return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))) if os.path.isdir(d) else []

    def unique_world(self, base):
        base = re.sub(r"[^\w\- ]", "", base).strip() or "Mundo"
        name, i = base, 2
        while os.path.exists(self.path("worlds", name)):
            name = f"{base}_{i}"
            i += 1
        return name

    def import_world_zip(self, zpath):
        with zipfile.ZipFile(zpath) as z:
            lv = sorted((n for n in z.namelist() if os.path.basename(n) == "level.dat"), key=len)
            if not lv:
                raise ValueError("No es un mundo de Bedrock (falta level.dat).")
            root = lv[0][: -len("level.dat")]
            name = self.unique_world(os.path.splitext(os.path.basename(zpath))[0])
            dest = os.path.abspath(self.path("worlds", name))
            for m in z.namelist():
                if m.startswith(root) and not m.endswith("/"):
                    target = os.path.abspath(os.path.join(dest, m[len(root):]))
                    if not target.startswith(dest + os.sep):
                        continue
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(m) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
        return name

    def import_world_folder(self, src):
        if not os.path.exists(os.path.join(src, "level.dat")):
            raise ValueError("Esa carpeta no es un mundo de Bedrock (falta level.dat).")
        name = self.unique_world(os.path.basename(os.path.normpath(src)))
        shutil.copytree(src, self.path("worlds", name))
        return name

    def export_world(self, name, dest):
        root = self.path("worlds", name)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for dp, _, files in os.walk(root):
                for fn in files:
                    full = os.path.join(dp, fn)
                    z.write(full, os.path.relpath(full, root))

    # --- respaldos (nube)
    def make_backup(self, dest_dir, files=None):
        """files: {ruta relativa a worlds/: longitud} para respaldo en caliente; None si el servidor está apagado."""
        os.makedirs(dest_dir, exist_ok=True)
        level = self.meta["props"].get("level-name", "Bedrock level")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(dest_dir, f"{os.path.basename(self.folder)}_{stamp}.zip")
        wroot = self.path("worlds")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            if files:
                for rel, length in files.items():
                    full = os.path.join(wroot, rel)
                    if os.path.isfile(full):
                        with open(full, "rb") as fh:
                            z.writestr("worlds/" + rel.replace("\\", "/"), fh.read(length))
            else:
                base = os.path.join(wroot, level)
                for dp, _, fns in os.walk(base):
                    for fn in fns:
                        full = os.path.join(dp, fn)
                        z.write(full, "worlds/" + level + "/" + os.path.relpath(full, base).replace(os.sep, "/"))
            for name in ("server.properties", "permissions.json", "allowlist.json", "mcsc.json"):
                if os.path.exists(self.path(name)):
                    z.write(self.path(name), "config/" + name)
            for p in self.meta["packs"]:
                sub = "resource_packs" if p["type"] == "resource" else "behavior_packs"
                base = self.path(sub, p["folder"])
                for dp, _, fns in os.walk(base):
                    for fn in fns:
                        full = os.path.join(dp, fn)
                        z.write(full, f"{sub}/{p['folder']}/" + os.path.relpath(full, base).replace(os.sep, "/"))
        return dest

    def prune_backups(self, dest_dir, keep):
        prefix = os.path.basename(self.folder) + "_"
        files = sorted(f for f in os.listdir(dest_dir) if f.startswith(prefix) and f.endswith(".zip"))
        for f in files[:-max(1, keep)]:
            try:
                os.remove(os.path.join(dest_dir, f))
            except OSError:
                pass

    def restore_backup(self, zpath):
        version = self.meta.get("version", "")
        root = os.path.abspath(self.folder)
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            if not any(n.startswith("worlds/") for n in names):
                raise ValueError("Ese ZIP no es un respaldo de esta app (no contiene worlds/).")
            for lvl in {n.split("/")[1] for n in names if n.startswith("worlds/") and n.count("/") >= 2}:
                shutil.rmtree(self.path("worlds", lvl), ignore_errors=True)
            for n in names:
                if n.endswith("/"):
                    continue
                if n.startswith("config/"):
                    target = os.path.join(root, n[len("config/"):])
                elif n.startswith(("worlds/", "behavior_packs/", "resource_packs/")):
                    target = os.path.join(root, n)
                else:
                    continue
                target = os.path.abspath(target)
                if not target.startswith(root + os.sep):
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(n) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
        fresh = ServerData(self.folder)
        fresh.meta["version"] = version
        fresh.save()

    # --- comandos personalizados (behavior pack con funciones)
    def deploy_cmd_pack(self):
        c = self.meta["cmds"]
        folder = "CustomCommands_" + CMD_UUID[:8]
        pdir = self.path("behavior_packs", folder)
        self.meta["packs"] = [p for p in self.meta["packs"] if p["uuid"] != CMD_UUID]
        shutil.rmtree(pdir, ignore_errors=True)
        active = [i for i in c["items"] if i.get("active")]
        if c["enabled"] and active:
            os.makedirs(os.path.join(pdir, "functions"))
            manifest = {"format_version": 2,
                        "header": {"name": "Comandos personalizados",
                                   "description": "Generado por Bedrock Server Creator",
                                   "uuid": CMD_UUID, "version": [1, 0, 0], "min_engine_version": [1, 20, 0]},
                        "modules": [{"type": "data", "uuid": CMD_MOD_UUID, "version": [1, 0, 0]}]}
            with open(os.path.join(pdir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            for it in active:
                out = []
                for ln in it["lines"]:
                    ln = ln.strip().lstrip("/")
                    if not ln or ln.startswith("#"):
                        continue
                    ln = ln.replace("{player}", "@s")
                    if it.get("owner_only"):
                        ln = f"execute as @s[tag={CMD_TAG}] run {ln}"
                    out.append(ln)
                with open(os.path.join(pdir, "functions", fn_name(it["name"]) + ".mcfunction"), "w",
                          encoding="utf-8") as f:
                    f.write("\n".join(out) + "\n")
            self.meta["packs"].append({"name": "Comandos personalizados", "uuid": CMD_UUID, "version": [1, 0, 0],
                                       "type": "behavior", "folder": folder})
        self.save()
        self.sync_packs(remove_ids=[CMD_UUID])

    # --- lista blanca (sin servidor encendido)
    def allowlist_edit(self, name, add, xuid=""):
        fp = self.path("allowlist.json")
        lst = []
        if os.path.exists(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    lst = json.load(f)
            except Exception:
                lst = []
        lst = [e for e in lst if e.get("name", "").lower() != name.lower()]
        if add:
            e = {"ignoresPlayerLimit": False, "name": name}
            if xuid:
                e["xuid"] = xuid
            lst.append(e)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(lst, f, indent=2)


# ---------- interfaz ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bedrock Server Creator")
        self.geometry("840x660")
        os.makedirs(BASE, exist_ok=True)
        self.data = None
        self.proc = None
        self.online = {}
        self.cfg = load_cfg()
        self.capture = None
        self.backing_up = False
        self.user_stop = False
        self.restart_times = []
        self.pending_op = set()
        self.last_backup = time.time()

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Servidor:").pack(side="left")
        self.server_var = tk.StringVar()
        self.server_box = ttk.Combobox(top, textvariable=self.server_var, state="readonly", width=30)
        self.server_box.pack(side="left", padx=6)
        self.server_box.bind("<<ComboboxSelected>>", lambda e: self.load_server())
        ttk.Button(top, text="Abrir carpeta", command=self.open_folder).pack(side="left")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.build_create_tab()
        self.build_settings_tab()
        self.build_worlds_tab()
        self.build_addons_tab()
        self.build_staff_tab()
        self.build_players_tab()
        self.build_cmds_tab()
        self.build_cloud_tab()
        self.build_tools_tab()
        self.build_console_tab()

        self.status = tk.StringVar(value="Listo")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x")
        self.refresh_servers()
        self.after(30000, self.tick)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- helpers
    def set_status(self, msg):
        self.after(0, lambda: self.status.set(msg))

    def refresh_servers(self):
        names = [d for d in sorted(os.listdir(BASE)) if os.path.exists(os.path.join(BASE, d, "mcsc.json"))]
        self.server_box["values"] = names

    def need_server(self):
        if not self.data:
            messagebox.showinfo("Servidor", "Crea o selecciona un servidor primero.")
            return False
        return True

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def open_folder(self):
        if not self.need_server():
            return
        try:
            if IS_WIN:
                os.startfile(self.data.folder)
            else:
                subprocess.Popen(["xdg-open", self.data.folder])
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # --- pestaña crear
    def build_create_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Crear")
        self.name_var = tk.StringVar(value="MiServidorBedrock")
        self.eula_var = tk.BooleanVar()
        self.owner_var = tk.StringVar()
        ttk.Label(f, text="Nombre de la carpeta").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.name_var, width=32).grid(row=0, column=1, padx=8, sticky="w")
        ttk.Label(f, text="Tu gamertag (owner)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.owner_var, width=32).grid(row=1, column=1, padx=8, sticky="w")
        ttk.Checkbutton(f, variable=self.eula_var,
                        text="Acepto el EULA y la política de privacidad de Minecraft (minecraft.net/eula)"
                        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=8)
        b = ttk.Frame(f)
        b.grid(row=3, column=0, columnspan=2, pady=8, sticky="w")
        ttk.Button(b, text="Descargar última versión oficial", command=lambda: self.create_server(None)).pack(side="left", padx=4)
        ttk.Button(b, text="Usar ZIP descargado…", command=self.create_from_zip).pack(side="left", padx=4)
        ttk.Label(f, foreground="gray", justify="left",
                  text="Servidor dedicado oficial de Bedrock (Windows y Linux). En macOS no existe: usa Docker.\n"
                       "Si la descarga falla, baja el ZIP desde minecraft.net/download/server/bedrock y usa el segundo botón."
                  ).grid(row=4, column=0, columnspan=2, sticky="w", pady=8)

    def create_from_zip(self):
        p = filedialog.askopenfilename(filetypes=[("ZIP del servidor", "*.zip")])
        if p:
            self.create_server(p)

    def create_server(self, local_zip):
        name = self.name_var.get().strip()
        if sys.platform == "darwin":
            return messagebox.showwarning("macOS", "Bedrock Dedicated Server no existe para macOS.")
        if not name:
            return messagebox.showwarning("Datos", "Indica un nombre.")
        if not self.eula_var.get():
            return messagebox.showwarning("EULA", "Debes aceptar el EULA para continuar.")
        folder = os.path.join(BASE, name)
        if os.path.exists(folder):
            return messagebox.showwarning("Existe", "Ya hay un servidor con ese nombre.")
        os.makedirs(folder)
        owner = self.owner_var.get().strip()

        def work():
            try:
                zpath = local_zip or os.path.join(folder, "_server.zip")
                version = ""
                if not local_zip:
                    self.set_status("Descargando Bedrock Dedicated Server...")
                    url = official_server_url()
                    download(url, zpath)
                    version = (re.search(r"bedrock-server-([\d.]+)\.zip", url) or [None, ""])[1]
                else:
                    version = (re.search(r"bedrock-server-([\d.]+)\.zip", os.path.basename(zpath)) or [None, ""])[1]
                self.set_status("Extrayendo...")
                with zipfile.ZipFile(zpath) as z:
                    z.extractall(folder)
                if not local_zip:
                    os.remove(zpath)
                exe = os.path.join(folder, EXE)
                if not IS_WIN and os.path.exists(exe):
                    os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
                sd = ServerData(folder)
                sd.meta["version"] = version
                sd.meta["props"] = read_props(sd.path("server.properties"))
                sd.meta["props"]["server-name"] = name
                if owner:
                    sd.meta["cmds"]["owner"] = owner
                    sd.meta["staff"].append({"name": owner, "xuid": "", "role": "Owner", "permission": "operator"})
                sd.save()
                sd.write_properties()
                self.set_status(f"Servidor '{name}' creado.")
                self.after(0, lambda: (self.refresh_servers(), self.server_var.set(name), self.load_server()))
            except Exception as e:
                self.set_status(f"Error: {e}")
                shutil.rmtree(folder, ignore_errors=True)
        threading.Thread(target=work, daemon=True).start()

    # --- pestaña ajustes
    def build_settings_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Ajustes")
        self.sv = {}
        for r, (label, key, kind, opts, default) in enumerate(SETTINGS):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=2)
            if kind == "bool":
                var = tk.BooleanVar()
                w = ttk.Checkbutton(f, variable=var)
            elif kind == "combo":
                var = tk.StringVar()
                w = ttk.Combobox(f, textvariable=var, values=list(opts), state="readonly")
            else:
                var = tk.StringVar()
                w = ttk.Entry(f, textvariable=var, width=30)
            w.grid(row=r, column=1, sticky="w", padx=8)
            self.sv[key] = (var, kind, opts, default)
        b = ttk.Frame(f)
        b.grid(row=len(SETTINGS), column=0, columnspan=2, pady=12)
        ttk.Button(b, text="Guardar ajustes", command=self.save_settings).pack(side="left", padx=4)

    def fill_settings(self):
        p = self.data.meta["props"]
        for key, (var, kind, opts, default) in self.sv.items():
            val = p.get(key, str(default).lower() if kind == "bool" else str(default))
            if kind == "bool":
                var.set(val == "true")
            elif kind == "combo" and isinstance(opts, dict):
                var.set({v: k for k, v in opts.items()}.get(val, list(opts)[0]))
            else:
                var.set(val)

    def save_settings(self):
        if not self.need_server():
            return
        p = self.data.meta["props"]
        for key, (var, kind, opts, default) in self.sv.items():
            v = var.get()
            if kind == "bool":
                v = "true" if v else "false"
            elif kind == "combo" and isinstance(opts, dict):
                v = opts[v]
            elif kind == "int":
                if not str(v).isdigit():
                    return messagebox.showwarning("Valor", f"'{key}' debe ser un número entero.")
            p[key] = str(v)
        self.data.save()
        self.data.write_properties()
        self.data.sync_packs()
        self.set_status("Ajustes guardados (reinicia el servidor para aplicarlos).")

    # --- pestaña mundos
    def build_worlds_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Mundos")
        self.world_names = []
        self.world_list = tk.Listbox(f, height=14)
        self.world_list.pack(fill="both", expand=True)
        b = ttk.Frame(f)
        b.pack(pady=8)
        for text, cmd in (("Subir mundo (.mcworld/.zip)", self.upload_world_zip),
                          ("Subir carpeta de mundo", self.upload_world_folder),
                          ("Usar como activo", self.activate_world),
                          ("Exportar / respaldar", self.export_world),
                          ("Eliminar", self.delete_world)):
            ttk.Button(b, text=text, command=cmd).pack(side="left", padx=3)
        ttk.Label(f, foreground="gray", justify="left",
                  text="★ = mundo activo (el que carga el servidor). Reinicia el servidor tras cambiarlo.\n"
                       "Para sacar un mundo de tu Minecraft: Editar mundo → Exportar mundo (.mcworld)."
                  ).pack(anchor="w")

    def refresh_worlds(self):
        self.world_names = self.data.worlds()
        active = self.data.meta["props"].get("level-name", "")
        self.world_list.delete(0, "end")
        for n in self.world_names:
            self.world_list.insert("end", ("★ " if n == active else "    ") + n)

    def selected_world(self):
        if not self.need_server():
            return None
        sel = self.world_list.curselection()
        if not sel:
            messagebox.showinfo("Mundos", "Elige un mundo de la lista.")
            return None
        return self.world_names[sel[0]]

    def upload_world_zip(self):
        if not self.need_server():
            return
        p = filedialog.askopenfilename(filetypes=[("Mundo Bedrock", "*.mcworld *.zip")])
        if p:
            self.finish_upload(lambda: self.data.import_world_zip(p))

    def upload_world_folder(self):
        if not self.need_server():
            return
        p = filedialog.askdirectory(title="Carpeta del mundo (la que contiene level.dat)")
        if p:
            self.finish_upload(lambda: self.data.import_world_folder(p))

    def finish_upload(self, fn):
        def work():
            try:
                name = fn()
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: messagebox.showerror("Mundo", m))
                return
            self.after(0, lambda: self.after_upload(name))
        self.set_status("Subiendo mundo...")
        threading.Thread(target=work, daemon=True).start()

    def after_upload(self, name):
        self.refresh_worlds()
        self.set_status(f"Mundo '{name}' subido.")
        if messagebox.askyesno("Mundo", f"Mundo '{name}' subido. ¿Usarlo como mundo activo?"):
            self.set_active_world(name)

    def set_active_world(self, name):
        self.data.meta["props"]["level-name"] = name
        self.data.save()
        self.data.write_properties()
        self.data.sync_packs()
        self.fill_settings()
        self.refresh_worlds()
        self.set_status(f"Mundo activo: '{name}' (reinicia el servidor).")

    def activate_world(self):
        n = self.selected_world()
        if n:
            self.set_active_world(n)

    def export_world(self):
        n = self.selected_world()
        if not n:
            return
        if self.running() and not messagebox.askokcancel(
                "Servidor encendido", "Para un respaldo seguro, detén el servidor antes. ¿Continuar igualmente?"):
            return
        dest = filedialog.asksaveasfilename(defaultextension=".mcworld", initialfile=f"{n}.mcworld",
                                            filetypes=[("Mundo Bedrock", "*.mcworld")])
        if not dest:
            return

        def work():
            try:
                self.data.export_world(n, dest)
                self.set_status(f"Mundo exportado: {dest}")
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: messagebox.showerror("Exportar", m))
        self.set_status("Exportando mundo...")
        threading.Thread(target=work, daemon=True).start()

    def delete_world(self):
        n = self.selected_world()
        if not n:
            return
        if n == self.data.meta["props"].get("level-name"):
            return messagebox.showwarning("Mundos", "No puedes eliminar el mundo activo.")
        if self.running():
            return messagebox.showwarning("Mundos", "Detén el servidor antes de eliminar mundos.")
        if messagebox.askyesno("Eliminar", f"¿Eliminar '{n}' para siempre? No se puede deshacer."):
            shutil.rmtree(self.data.path("worlds", n), ignore_errors=True)
            self.refresh_worlds()

    # --- pestaña addons
    def build_addons_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Addons")
        self.pack_list = tk.Listbox(f, height=18)
        self.pack_list.pack(fill="both", expand=True)
        b = ttk.Frame(f)
        b.pack(pady=8)
        ttk.Button(b, text="Instalar addon (.mcaddon/.mcpack/.zip)", command=self.add_addon).pack(side="left", padx=4)
        ttk.Button(b, text="Eliminar seleccionado", command=self.remove_addon).pack(side="left", padx=4)
        ttk.Label(f, foreground="gray", justify="left",
                  text="BP = behavior pack, RP = resource pack. Se registran solos en el mundo actual.\n"
                       "Los addons con scripts/beta APIs pueden exigir activar 'Experimentos' en el mundo (level.dat)."
                  ).pack(anchor="w")

    def refresh_packs(self):
        self.pack_list.delete(0, "end")
        for p in self.data.meta["packs"]:
            tag = "RP" if p["type"] == "resource" else "BP"
            self.pack_list.insert("end", f"[{tag}] {p['name']}  v{'.'.join(map(str, p['version']))}")

    def add_addon(self):
        if not self.need_server():
            return
        paths = filedialog.askopenfilenames(filetypes=[("Addons", "*.mcaddon *.mcpack *.zip")])
        total = []
        for p in paths:
            try:
                total += self.data.install_addon(p)
            except Exception as e:
                messagebox.showerror("Addon", f"{os.path.basename(p)}: {e}")
        self.refresh_packs()
        if total:
            self.set_status("Instalado: " + ", ".join(total))

    def remove_addon(self):
        if not self.need_server() or not self.pack_list.curselection():
            return
        p = self.data.meta["packs"][self.pack_list.curselection()[0]]
        d = "resource_packs" if p["type"] == "resource" else "behavior_packs"
        shutil.rmtree(self.data.path(d, p["folder"]), ignore_errors=True)
        self.data.meta["packs"].remove(p)
        self.data.save()
        self.data.sync_packs(remove_ids=[p["uuid"]])
        self.refresh_packs()

    # --- pestaña staff
    def build_staff_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Staff")
        self.tree = ttk.Treeview(f, columns=("name", "xuid", "role", "perm"), show="headings", height=13)
        for c, t, w in (("name", "Jugador", 160), ("xuid", "XUID", 190), ("role", "Rol", 100), ("perm", "Permiso", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)
        b = ttk.Frame(f)
        b.pack(pady=8, fill="x")
        self.s_name, self.s_xuid = tk.StringVar(), tk.StringVar()
        self.s_role, self.s_perm = tk.StringVar(value="Moderador"), tk.StringVar(value="operator")
        ttk.Entry(b, textvariable=self.s_name, width=16).pack(side="left", padx=2)
        ttk.Entry(b, textvariable=self.s_xuid, width=19).pack(side="left", padx=2)
        rc = ttk.Combobox(b, textvariable=self.s_role, values=list(ROLES), state="readonly", width=10)
        rc.pack(side="left", padx=2)
        rc.bind("<<ComboboxSelected>>", lambda e: self.s_perm.set(ROLES[self.s_role.get()]))
        ttk.Combobox(b, textvariable=self.s_perm, values=PERMS, state="readonly", width=9).pack(side="left", padx=2)
        ttk.Button(b, text="Añadir/actualizar", command=self.add_staff).pack(side="left", padx=4)
        ttk.Button(b, text="Quitar", command=self.remove_staff).pack(side="left")
        ttk.Label(f, foreground="gray", justify="left",
                  text="Bedrock solo tiene 3 permisos: operator, member, visitor. El rol es una etiqueta tuya.\n"
                       "El XUID se completa solo si el jugador ya entró al servidor (se lee de la consola).\n"
                       "Jugador, XUID: campos de la izquierda. Con el servidor encendido también se envía op/deop."
                  ).pack(anchor="w")

    def refresh_staff(self):
        self.tree.delete(*self.tree.get_children())
        for s in self.data.meta["staff"]:
            self.tree.insert("", "end", values=(s["name"], s.get("xuid", ""), s["role"], s["permission"]))

    def add_staff(self):
        if not self.need_server():
            return
        name = self.s_name.get().strip()
        if not name:
            return
        xuid = self.s_xuid.get().strip() or self.data.meta["seen"].get(name, "")
        if xuid and not xuid.isdigit():
            return messagebox.showwarning("XUID", "El XUID solo contiene números.")
        self.data.meta["staff"] = [s for s in self.data.meta["staff"] if s["name"].lower() != name.lower()]
        self.data.meta["staff"].append({"name": name, "xuid": xuid, "role": self.s_role.get(),
                                        "permission": self.s_perm.get()})
        self.save_staff([name])
        if not xuid:
            self.set_status("Sin XUID: solo se aplica con op/deop con el jugador conectado.")

    def remove_staff(self):
        if not self.need_server() or not self.tree.selection():
            return
        name = str(self.tree.item(self.tree.selection()[0])["values"][0])
        self.data.meta["staff"] = [s for s in self.data.meta["staff"] if s["name"] != name]
        self.save_staff([])
        self.send_cmd_raw(f'deop "{name}"')

    def save_staff(self, changed):
        self.data.save()
        self.data.write_permissions()
        self.refresh_staff()
        for s in self.data.meta["staff"]:
            if s["name"] in changed:
                self.send_cmd_raw(f'{"op" if s["permission"] == "operator" else "deop"} "{s["name"]}"')

    # --- pestaña jugadores / moderación
    def build_players_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Jugadores")
        left = ttk.Frame(f)
        left.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(left, text="Conectados (clic para elegir)").pack(anchor="w")
        self.online_list = tk.Listbox(left, height=22, width=22)
        self.online_list.pack(fill="y")
        self.online_list.bind("<<ListboxSelect>>", self.pick_online)

        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True)
        self.p_name, self.p_reason = tk.StringVar(), tk.StringVar()
        self.p_mode, self.p_msg = tk.StringVar(value="survival"), tk.StringVar()
        g = ttk.Frame(right)
        g.pack(fill="x")
        ttk.Label(g, text="Jugador").grid(row=0, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.p_name, width=26).grid(row=0, column=1, padx=6, pady=2, sticky="w")
        ttk.Label(g, text="Motivo").grid(row=1, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.p_reason, width=44).grid(row=1, column=1, padx=6, pady=2, sticky="w")
        rows = [(("Expulsar (kick)", self.mod_kick), ("Banear", self.mod_ban), ("Desbanear", self.mod_unban)),
                (("Hacer OP", lambda: self.mod_op(True)), ("Quitar OP", lambda: self.mod_op(False)),
                 ("A lista blanca", lambda: self.mod_allow(True)), ("Fuera de lista blanca", lambda: self.mod_allow(False)))]
        for row in rows:
            b = ttk.Frame(right)
            b.pack(fill="x", pady=3)
            for text, cmd in row:
                ttk.Button(b, text=text, command=cmd).pack(side="left", padx=2)
        m = ttk.Frame(right)
        m.pack(fill="x", pady=3)
        ttk.Combobox(m, textvariable=self.p_mode, values=["survival", "creative", "adventure"],
                     state="readonly", width=10).pack(side="left", padx=2)
        ttk.Button(m, text="Cambiar modo", command=self.mod_mode).pack(side="left", padx=2)
        ttk.Entry(m, textvariable=self.p_msg, width=24).pack(side="left", padx=(12, 2))
        ttk.Button(m, text="Mensaje global", command=self.mod_say).pack(side="left", padx=2)

        ttk.Label(right, text="Lista de baneados").pack(anchor="w", pady=(10, 0))
        self.ban_tree = ttk.Treeview(right, columns=("name", "xuid", "reason", "date"), show="headings", height=8)
        for c, t, w in (("name", "Jugador", 120), ("xuid", "XUID", 150), ("reason", "Motivo", 160), ("date", "Fecha", 110)):
            self.ban_tree.heading(c, text=t)
            self.ban_tree.column(c, width=w)
        self.ban_tree.pack(fill="both", expand=True)
        ttk.Label(right, foreground="gray", justify="left",
                  text="Bedrock no trae /ban: la app expulsa al baneado cada vez que intenta entrar\n"
                       "(funciona con la app abierta y el servidor encendido; se compara por XUID y nombre).\n"
                       "Bloqueo total: activa la lista blanca en Ajustes."
                  ).pack(anchor="w", pady=6)

    def pick_online(self, _e):
        s = self.online_list.curselection()
        if s:
            self.p_name.set(self.online_list.get(s[0]))

    def refresh_online(self):
        self.online_list.delete(0, "end")
        for n in sorted(self.online):
            self.online_list.insert("end", n)

    def refresh_bans(self):
        self.ban_tree.delete(*self.ban_tree.get_children())
        for b in self.data.meta["bans"]:
            self.ban_tree.insert("", "end", values=(b["name"], b.get("xuid", ""), b["reason"], b.get("date", "")))

    def target(self):
        if not self.need_server():
            return None
        n = self.p_name.get().strip()
        if not n:
            messagebox.showinfo("Jugador", "Escribe o elige un jugador.")
            return None
        return n

    def need_running(self):
        if not self.running():
            messagebox.showinfo("Servidor", "El servidor debe estar encendido para esta acción.")
            return False
        return True

    def mod_kick(self):
        n = self.target()
        if n and self.need_running():
            self.send_cmd_raw(f'kick "{n}" {self.p_reason.get().strip()}'.strip())

    def mod_ban(self):
        n = self.target()
        if not n:
            return
        xuid = self.online.get(n) or self.data.meta["seen"].get(n, "")
        reason = self.p_reason.get().strip() or "Baneado por el staff"
        bans = [b for b in self.data.meta["bans"] if b["name"].lower() != n.lower()]
        bans.append({"name": n, "xuid": xuid, "reason": reason, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
        self.data.meta["bans"] = bans
        self.data.save()
        self.refresh_bans()
        if n in self.online:
            self.send_cmd_raw(f'kick "{n}" {reason}')
        self.set_status(f"'{n}' baneado" + ("" if xuid else " (sin XUID: se compara por nombre)") + ".")

    def mod_unban(self):
        if not self.need_server():
            return
        sel = self.ban_tree.selection()
        n = str(self.ban_tree.item(sel[0])["values"][0]) if sel else self.p_name.get().strip()
        if not n:
            return messagebox.showinfo("Baneos", "Elige un baneado de la lista o escribe su nombre.")
        self.data.meta["bans"] = [b for b in self.data.meta["bans"] if b["name"].lower() != n.lower()]
        self.data.save()
        self.refresh_bans()
        self.set_status(f"'{n}' desbaneado.")

    def mod_op(self, give):
        n = self.target()
        if n and self.need_running():
            self.send_cmd_raw(f'{"op" if give else "deop"} "{n}"')

    def mod_allow(self, add):
        n = self.target()
        if not n:
            return
        if self.running():
            self.send_cmd_raw(f'allowlist {"add" if add else "remove"} "{n}"')
        else:
            self.data.allowlist_edit(n, add, self.data.meta["seen"].get(n, ""))
            self.set_status(f"Lista blanca actualizada para '{n}'.")

    def mod_mode(self):
        n = self.target()
        if n and self.need_running():
            self.send_cmd_raw(f'gamemode {self.p_mode.get()} "{n}"')

    def mod_say(self):
        msg = self.p_msg.get().strip()
        if msg and self.need_running():
            self.send_cmd_raw(f"say {msg}")
            self.p_msg.set("")

    def open_path(self, path):
        try:
            if IS_WIN:
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # --- pestaña comandos personalizados
    def build_cmds_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Comandos")
        self.cm_enabled = tk.BooleanVar()
        self.cm_owner = tk.StringVar()
        self.cm_name, self.cm_desc, self.cm_target = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.cm_active, self.cm_owner_only = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        self.cm_names = []
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Checkbutton(top, text="Activar comandos personalizados", variable=self.cm_enabled).pack(side="left")
        ttk.Label(top, text="   Creador (owner):").pack(side="left")
        ttk.Entry(top, textvariable=self.cm_owner, width=18).pack(side="left", padx=4)
        ttk.Button(top, text="Aplicar al servidor", command=self.cm_apply).pack(side="left", padx=8)
        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, pady=8)
        self.cm_list = tk.Listbox(mid, width=26, height=14)
        self.cm_list.pack(side="left", fill="y", padx=(0, 10))
        self.cm_list.bind("<<ListboxSelect>>", self.cm_select)
        ed = ttk.Frame(mid)
        ed.pack(side="left", fill="both", expand=True)
        ttk.Label(ed, text="Nombre (se usa como /function nombre)").grid(row=0, column=0, sticky="w")
        ttk.Entry(ed, textvariable=self.cm_name, width=24).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(ed, text="Descripción").grid(row=1, column=0, sticky="w")
        ttk.Entry(ed, textvariable=self.cm_desc, width=40).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(ed, text="Comandos (uno por línea, {player} = quien lo usa)").grid(row=2, column=0, columnspan=2, sticky="w")
        self.cm_lines = tk.Text(ed, height=8, width=50)
        self.cm_lines.grid(row=3, column=0, columnspan=2, sticky="we", pady=4)
        ck = ttk.Frame(ed)
        ck.grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(ck, text="Activo", variable=self.cm_active).pack(side="left")
        ttk.Checkbutton(ck, text="Solo el owner puede usarlo en el juego", variable=self.cm_owner_only).pack(side="left", padx=10)
        bb = ttk.Frame(ed)
        bb.grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        for text, cmd in (("Guardar comando", self.cm_save), ("Nuevo", self.cm_new), ("Eliminar", self.cm_delete),
                          ("Añadir plantillas", self.cm_templates)):
            ttk.Button(bb, text=text, command=cmd).pack(side="left", padx=2)
        rr = ttk.Frame(ed)
        rr.grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(rr, text="Ejecutar desde la app para:").pack(side="left")
        ttk.Entry(rr, textvariable=self.cm_target, width=16).pack(side="left", padx=4)
        ttk.Button(rr, text="Ejecutar ahora", command=self.cm_run).pack(side="left")
        ttk.Label(f, foreground="gray", justify="left",
                  text="Dentro del juego se usan con /function nombre (hay que ser operator) tras reiniciar el servidor.\n"
                       "'Solo owner': solo funciona para el jugador con la etiqueta cmd_owner, que se le da al creador al entrar.\n"
                       "Objetivo al ejecutar desde la app: un gamertag o @a (todos); vacío = el owner."
                  ).pack(anchor="w")

    def fill_cmds(self):
        c = self.data.meta["cmds"]
        self.cm_enabled.set(c["enabled"])
        self.cm_owner.set(c["owner"])
        self.cm_new()
        self.cm_refresh()

    def cm_refresh(self):
        items = self.data.meta["cmds"]["items"]
        self.cm_names = [i["name"] for i in items]
        self.cm_list.delete(0, "end")
        for i in items:
            self.cm_list.insert("end", ("[x] " if i.get("active") else "[ ] ") + i["name"])

    def cm_select(self, _e=None):
        sel = self.cm_list.curselection()
        if not sel:
            return
        it = self.data.meta["cmds"]["items"][sel[0]]
        self.cm_name.set(it["name"])
        self.cm_desc.set(it.get("desc", ""))
        self.cm_lines.delete("1.0", "end")
        self.cm_lines.insert("1.0", "\n".join(it["lines"]))
        self.cm_active.set(it.get("active", True))
        self.cm_owner_only.set(it.get("owner_only", True))

    def cm_new(self):
        self.cm_name.set("")
        self.cm_desc.set("")
        self.cm_lines.delete("1.0", "end")
        self.cm_active.set(True)
        self.cm_owner_only.set(True)

    def cm_save(self):
        if not self.need_server():
            return
        name = fn_name(self.cm_name.get()) if self.cm_name.get().strip() else ""
        lines = [x.strip() for x in self.cm_lines.get("1.0", "end").splitlines() if x.strip()]
        if not name or not lines:
            return messagebox.showinfo("Comandos", "Pon un nombre y al menos un comando.")
        item = {"name": name, "desc": self.cm_desc.get().strip(), "lines": lines,
                "active": self.cm_active.get(), "owner_only": self.cm_owner_only.get()}
        items = self.data.meta["cmds"]["items"]
        for i, old in enumerate(items):
            if old["name"] == name:
                items[i] = item
                break
        else:
            items.append(item)
        self.data.save()
        self.cm_refresh()
        self.set_status(f"Comando guardado: /function {name}. Pulsa 'Aplicar al servidor'.")

    def cm_delete(self):
        if not self.need_server():
            return
        name = fn_name(self.cm_name.get())
        c = self.data.meta["cmds"]
        c["items"] = [i for i in c["items"] if i["name"] != name]
        self.data.save()
        self.cm_new()
        self.cm_refresh()

    def cm_templates(self):
        if not self.need_server():
            return
        items = self.data.meta["cmds"]["items"]
        have = {i["name"] for i in items}
        for pr in PRESETS:
            if pr["name"] not in have:
                items.append({"name": pr["name"], "desc": pr["desc"], "lines": list(pr["lines"]),
                              "active": True, "owner_only": True})
        self.data.save()
        self.cm_refresh()

    def cm_apply(self):
        if not self.need_server():
            return
        c = self.data.meta["cmds"]
        c["enabled"] = self.cm_enabled.get()
        c["owner"] = self.cm_owner.get().strip()
        self.data.deploy_cmd_pack()
        self.refresh_packs()
        if self.running() and c["enabled"] and c["owner"]:
            self.send_cmd_raw(f'tag "{c["owner"]}" add {CMD_TAG}')
        self.set_status("Comandos " + ("activados" if c["enabled"] else "desactivados") +
                        " (reinicia el servidor para que se carguen).")

    def cm_run(self):
        if not self.need_server():
            return
        sel = self.cm_list.curselection()
        if not sel:
            return messagebox.showinfo("Comandos", "Elige un comando de la lista.")
        if not self.need_running():
            return
        it = self.data.meta["cmds"]["items"][sel[0]]
        target = self.cm_target.get().strip() or self.data.meta["cmds"]["owner"]
        if not target:
            return messagebox.showinfo("Comandos", "Indica un jugador (o @a) o define el owner.")
        tgt = target if target.startswith("@") else f'"{target}"'
        for ln in it["lines"]:
            ln = ln.strip().lstrip("/")
            if ln and not ln.startswith("#"):
                self.send_cmd_raw(ln.replace("{player}", tgt))
        self.set_status(f"Ejecutado '{it['name']}' para {target}.")

    # --- pestaña nube
    def build_cloud_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Nube")
        self.backup_files = []
        self.c_dir = tk.StringVar(value=self.cfg.get("cloud_dir", ""))
        self.c_auto, self.c_stop = tk.BooleanVar(), tk.BooleanVar(value=True)
        self.c_min, self.c_keep, self.c_hook = tk.StringVar(value="30"), tk.StringVar(value="10"), tk.StringVar()
        r = ttk.Frame(f)
        r.pack(fill="x")
        ttk.Label(r, text="Carpeta de tu nube:").pack(side="left")
        ttk.Entry(r, textvariable=self.c_dir, width=48, state="readonly").pack(side="left", padx=6)
        ttk.Button(r, text="Elegir...", command=self.pick_cloud_dir).pack(side="left")
        o = ttk.Frame(f)
        o.pack(fill="x", pady=6)
        ttk.Checkbutton(o, text="Respaldo automático cada", variable=self.c_auto).pack(side="left")
        ttk.Spinbox(o, from_=5, to=1440, textvariable=self.c_min, width=5).pack(side="left", padx=4)
        ttk.Label(o, text="min (servidor encendido)  ·  Conservar los últimos").pack(side="left")
        ttk.Spinbox(o, from_=1, to=200, textvariable=self.c_keep, width=4).pack(side="left", padx=4)
        ttk.Checkbutton(f, text="Respaldar también al detener el servidor", variable=self.c_stop).pack(anchor="w")
        h = ttk.Frame(f)
        h.pack(fill="x", pady=6)
        ttk.Label(h, text="Comando tras respaldar (opcional, usa {file}):").pack(side="left")
        ttk.Entry(h, textvariable=self.c_hook, width=44).pack(side="left", padx=6)
        self.backup_list = tk.Listbox(f, height=10)
        self.backup_list.pack(fill="both", expand=True, pady=6)
        b = ttk.Frame(f)
        b.pack()
        for text, cmd in (("Respaldar ahora", lambda: self.backup_now()), ("Restaurar seleccionado", self.restore_backup_ui),
                          ("Actualizar lista", self.refresh_backups), ("Guardar opciones", self.store_cloud_opts),
                          ("Abrir carpeta", self.open_backup_dir)):
            ttk.Button(b, text=text, command=cmd).pack(side="left", padx=3)
        ttk.Label(f, foreground="gray", justify="left",
                  text="Elige una carpeta que ya sincronice tu nube (Google Drive, OneDrive, Dropbox, MEGA, Syncthing...).\n"
                       "La app guarda ahí respaldos .zip (mundo + ajustes + addons). El servidor corre en tu PC;\n"
                       "la nube guarda las copias, así puedes recuperarlo o moverlo a otro equipo."
                  ).pack(anchor="w")

    def fill_cloud(self):
        c = self.data.meta["cloud"]
        self.c_auto.set(c.get("auto", False))
        self.c_min.set(str(c.get("minutes", 30)))
        self.c_stop.set(c.get("on_stop", True))
        self.c_keep.set(str(c.get("keep", 10)))
        self.c_hook.set(c.get("hook", ""))
        self.auto_restart.set(self.data.meta.get("auto_restart", False))
        self.c_dir.set(self.cfg.get("cloud_dir", ""))
        self.refresh_backups()

    def store_cloud_opts(self):
        if not self.data:
            return
        try:
            mins = max(5, int(self.c_min.get()))
        except ValueError:
            mins = 30
        try:
            keep = max(1, int(self.c_keep.get()))
        except ValueError:
            keep = 10
        self.data.meta["cloud"] = {"auto": self.c_auto.get(), "minutes": mins, "on_stop": self.c_stop.get(),
                                   "keep": keep, "hook": self.c_hook.get().strip()}
        self.data.meta["auto_restart"] = self.auto_restart.get()
        self.data.save()

    def pick_cloud_dir(self):
        p = filedialog.askdirectory(title="Carpeta que sincroniza tu nube")
        if p:
            self.cfg["cloud_dir"] = p
            save_cfg(self.cfg)
            self.c_dir.set(p)
            if self.data:
                self.refresh_backups()

    def backup_dir(self):
        return os.path.join(self.cfg["cloud_dir"], "BedrockServerCreator", os.path.basename(self.data.folder))

    def open_backup_dir(self):
        if self.need_server() and self.cfg.get("cloud_dir"):
            os.makedirs(self.backup_dir(), exist_ok=True)
            self.open_path(self.backup_dir())

    def refresh_backups(self):
        self.backup_files = []
        self.backup_list.delete(0, "end")
        if not (self.data and self.cfg.get("cloud_dir")):
            return
        d = self.backup_dir()
        if os.path.isdir(d):
            prefix = os.path.basename(self.data.folder) + "_"
            for fn in sorted((x for x in os.listdir(d) if x.startswith(prefix) and x.endswith(".zip")), reverse=True):
                full = os.path.join(d, fn)
                self.backup_files.append(full)
                self.backup_list.insert("end", f"{fn}   ({os.path.getsize(full) / 1048576:.1f} MB)")

    def hold_and_query(self):
        """Congela el guardado del mundo y devuelve {archivo: longitud} listo para copiar (hilo aparte)."""
        self.send_cmd_raw("save hold")
        time.sleep(1)
        for _ in range(30):
            self.capture = []
            self.send_cmd_raw("save query")
            time.sleep(1.5)
            lines, self.capture = self.capture, None
            for i, ln in enumerate(lines):
                if "Data saved" in ln:
                    rest = [re.sub(r"^\[[^\]]*\]\s*", "", x).strip() for x in lines[i + 1:]]
                    items = re.findall(r"([^,]+?):(\d+)", ", ".join(x for x in rest if x))
                    return {a.strip(): int(b) for a, b in items}
        raise RuntimeError("El servidor no confirmó el guardado del mundo.")

    def backup_now(self, quiet=False):
        if not self.need_server():
            return
        cdir = self.cfg.get("cloud_dir", "")
        if not cdir or not os.path.isdir(cdir):
            if not quiet:
                messagebox.showinfo("Nube", "Primero elige la carpeta de tu nube.")
            return
        if self.backing_up:
            self.set_status("Ya hay un respaldo en curso.")
            return
        self.store_cloud_opts()
        data, dest_dir, live = self.data, self.backup_dir(), self.running()
        keep, hook = data.meta["cloud"]["keep"], data.meta["cloud"]["hook"]
        self.backing_up = True
        self.set_status("Respaldando en la nube...")

        def work():
            try:
                files = None
                if live:
                    try:
                        files = self.hold_and_query() or None
                    except Exception:
                        self.send_cmd_raw("save resume")
                        raise
                try:
                    path = data.make_backup(dest_dir, files)
                finally:
                    if live:
                        self.send_cmd_raw("save resume")
                data.prune_backups(dest_dir, keep)
                extra = ""
                if hook:
                    r = subprocess.run(hook.replace("{file}", f'"{path}"'), shell=True, timeout=900)
                    extra = f" · comando posterior: código {r.returncode}"
                self.set_status(f"Respaldo listo: {os.path.basename(path)}{extra}")
            except Exception as e:
                msg = str(e)
                self.set_status(f"Error en el respaldo: {msg}")
                if not quiet:
                    self.after(0, lambda m=msg: messagebox.showerror("Respaldo", m))
            finally:
                self.backing_up = False
                self.after(0, self.refresh_backups)
        threading.Thread(target=work, daemon=True).start()

    def restore_backup_ui(self):
        if not self.need_server():
            return
        sel = self.backup_list.curselection()
        if not sel:
            return messagebox.showinfo("Nube", "Elige un respaldo de la lista.")
        if self.running():
            return messagebox.showwarning("Nube", "Detén el servidor antes de restaurar.")
        if not messagebox.askyesno("Restaurar", "Se reemplazará el mundo activo y los ajustes por este respaldo. ¿Continuar?"):
            return
        path, data = self.backup_files[sel[0]], self.data

        def work():
            try:
                data.restore_backup(path)
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: messagebox.showerror("Restaurar", m))
                return

            def done():
                self.data = None
                self.load_server()
                self.set_status("Respaldo restaurado.")
            self.after(0, done)
        self.set_status("Restaurando...")
        threading.Thread(target=work, daemon=True).start()

    def tick(self):
        try:
            if self.data and self.running() and self.c_auto.get() and self.cfg.get("cloud_dir"):
                mins = max(5, int(self.c_min.get()))
                if time.time() - self.last_backup >= mins * 60:
                    self.last_backup = time.time()
                    self.backup_now(quiet=True)
        except Exception:
            pass
        self.after(30000, self.tick)

    def on_server_stopped(self):
        self.online.clear()
        self.refresh_online()
        if self.data and self.cfg.get("cloud_dir") and self.c_stop.get():
            self.backup_now(quiet=True)
        if self.auto_restart.get() and not self.user_stop:
            now = time.time()
            self.restart_times = [t for t in self.restart_times if now - t < 600]
            if len(self.restart_times) >= 3:
                self.set_status("El servidor se cayó 3 veces en 10 min: no se reinicia más.")
            else:
                self.restart_times.append(now)
                self.set_status("El servidor se detuvo solo; reiniciando en 5 s...")
                self.after(5000, self.restart_when_idle)

    def restart_when_idle(self):
        if self.backing_up:
            self.after(2000, self.restart_when_idle)
        elif not self.running():
            self.start_server()

    # --- pestaña herramientas
    def build_tools_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Herramientas")
        self.auto_restart = tk.BooleanVar()
        ttk.Checkbutton(f, text="Reiniciar el servidor automáticamente si se cae",
                        variable=self.auto_restart).pack(anchor="w", pady=4)
        for text, cmd in (("Mi conexión (IP y puerto)", self.show_connection),
                          ("Actualizar servidor a la última versión", self.update_server),
                          ("Abrir carpeta del servidor", self.open_folder)):
            ttk.Button(f, text=text, command=cmd).pack(anchor="w", pady=4)
        ttk.Label(f, foreground="gray", justify="left",
                  text="Actualizar conserva tus mundos, ajustes, staff y addons; solo reemplaza los archivos del servidor.\n"
                       "Auto-reinicio: máximo 3 reinicios cada 10 minutos para evitar bucles.\n"
                       "Para jugar desde internet abre el puerto UDP del servidor (por defecto 19132) en tu router."
                  ).pack(anchor="w", pady=10)

    def show_connection(self):
        if not self.need_server():
            return
        port = self.data.meta["props"].get("server-port", "19132")

        def work():
            pub = ""
            try:
                req = urllib.request.Request("https://api.ipify.org", headers=UA)
                pub = urllib.request.urlopen(req, timeout=8).read().decode().strip()
            except Exception:
                pass
            msg = f"Misma red (Wi-Fi/LAN):\n  {local_ip()}  puerto {port}\n\n"
            msg += (f"Desde internet:\n  {pub}  puerto {port}  (abre UDP {port} en el router)" if pub
                    else "Desde internet: no se pudo consultar tu IP pública.")
            self.after(0, lambda: messagebox.showinfo("Mi conexión", msg))
        threading.Thread(target=work, daemon=True).start()

    def update_server(self):
        if not self.need_server():
            return
        if self.running():
            return messagebox.showwarning("Actualizar", "Detén el servidor antes de actualizar.")
        if not messagebox.askyesno("Actualizar", "Se descargará la última versión oficial y se conservarán tus mundos y ajustes. ¿Continuar?"):
            return
        data = self.data

        def work():
            try:
                self.set_status("Descargando la última versión...")
                url = official_server_url()
                tmp = data.path("_update.zip")
                download(url, tmp)
                protected = {"worlds", "server.properties", "permissions.json", "allowlist.json", "mcsc.json"}
                root = os.path.abspath(data.folder)
                with zipfile.ZipFile(tmp) as z:
                    for m in z.infolist():
                        if m.filename.endswith("/") or m.filename.split("/")[0] in protected:
                            continue
                        target = os.path.abspath(os.path.join(root, m.filename))
                        if not target.startswith(root + os.sep):
                            continue
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with z.open(m) as src, open(target, "wb") as out:
                            shutil.copyfileobj(src, out)
                os.remove(tmp)
                exe = data.path(EXE)
                if not IS_WIN and os.path.exists(exe):
                    os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
                data.meta["version"] = (re.search(r"bedrock-server-([\d.]+)\.zip", url) or [None, ""])[1]
                data.save()
                self.set_status(f"Servidor actualizado a v{data.meta['version'] or '?'}.")
            except Exception as e:
                msg = str(e)
                self.set_status(f"Error al actualizar: {msg}")
                self.after(0, lambda m=msg: messagebox.showerror("Actualizar", m))
        threading.Thread(target=work, daemon=True).start()

    # --- pestaña consola
    def build_console_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Consola")
        b = ttk.Frame(f)
        b.pack(fill="x")
        ttk.Button(b, text="Iniciar", command=self.start_server).pack(side="left", padx=4)
        ttk.Button(b, text="Detener", command=lambda: self.send_cmd_raw("stop")).pack(side="left", padx=4)
        self.log = tk.Text(f, height=22, bg="black", fg="#00ff66", state="disabled")
        self.log.pack(fill="both", expand=True, pady=8)
        self.cmd_var = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.cmd_var)
        e.pack(fill="x")
        e.bind("<Return>", lambda ev: (self.send_cmd_raw(self.cmd_var.get().strip()), self.cmd_var.set("")))

    def handle_line(self, line):
        self.log.config(state="normal")
        self.log.insert("end", line)
        self.log.see("end")
        self.log.config(state="disabled")
        if self.capture is not None:
            self.capture.append(line)
        if line.startswith("[Servidor detenido]"):
            self.on_server_stopped()
        m = re.search(r"Player connected: (.+), xuid: (\d*)", line)
        if m and self.data:
            name, xuid = m.group(1), m.group(2)
            if xuid:
                self.data.meta["seen"][name] = xuid
            self.online[name] = xuid
            self.refresh_online()
            for b in self.data.meta["bans"]:
                if (xuid and b.get("xuid") == xuid) or b["name"].lower() == name.lower():
                    if xuid and not b.get("xuid"):
                        b["xuid"] = xuid
                    self.send_cmd_raw(f'kick "{name}" {b["reason"]}')
                    self.set_status(f"'{name}' está baneado: expulsado al intentar entrar.")
                    break
            for s in self.data.meta["staff"]:
                if xuid and not s.get("xuid") and s["name"].lower() == name.lower():
                    s["xuid"] = xuid
                    self.data.write_permissions()
                    self.refresh_staff()
                    if s["permission"] == "operator":
                        self.pending_op.add(name)
            self.data.save()
            self.refresh_bans()
        m = re.search(r"Player disconnected: (.+), xuid: (\d*)", line)
        if m:
            self.online.pop(m.group(1), None)
            self.refresh_online()
        m = re.search(r"Player Spawned: (.+?) xuid: (\d*)", line)
        if m and self.data:
            name = m.group(1)
            c = self.data.meta["cmds"]
            if c["enabled"] and c["owner"] and c["owner"].lower() == name.lower():
                self.send_cmd_raw(f'tag "{name}" add {CMD_TAG}')
            if name in self.pending_op:
                self.pending_op.discard(name)
                self.send_cmd_raw(f'op "{name}"')

    def start_server(self):
        if not self.need_server():
            return
        if self.running():
            return messagebox.showinfo("Servidor", "Ya está en marcha.")
        exe = self.data.path(EXE)
        if not os.path.exists(exe):
            return messagebox.showerror("Servidor", f"No se encontró {EXE}.")
        env = dict(os.environ)
        if not IS_WIN:
            env["LD_LIBRARY_PATH"] = "."
        self.proc = subprocess.Popen([exe], cwd=self.data.folder, env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", bufsize=1)
        self.user_stop = False
        self.last_backup = time.time()
        threading.Thread(target=self.read_output, args=(self.proc,), daemon=True).start()
        self.set_status("Servidor iniciado.")

    def read_output(self, proc):
        for line in proc.stdout:
            self.after(0, self.handle_line, line)
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        self.after(0, self.handle_line, "[Servidor detenido]\n")

    def send_cmd_raw(self, cmd):
        if cmd and self.running():
            if cmd.strip() == "stop":
                self.user_stop = True
            try:
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError):
                pass

    # --- carga
    def load_server(self):
        self.store_cloud_opts()
        self.data = ServerData(os.path.join(BASE, self.server_var.get()))
        self.fill_settings()
        self.fill_cloud()
        self.fill_cmds()
        self.refresh_packs()
        self.refresh_staff()
        self.refresh_worlds()
        self.refresh_bans()
        self.set_status(f"Servidor '{self.server_var.get()}' cargado (v{self.data.meta['version'] or '?'}).")

    def on_close(self):
        self.store_cloud_opts()
        if self.running():
            if not messagebox.askyesno("Salir", "El servidor sigue en marcha. ¿Detenerlo y salir?"):
                return
            self.send_cmd_raw("stop")
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
