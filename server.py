"""Baixou — servidor local que baixa vídeos e áudios usando o yt-dlp.

Rode com:  python server.py
Abre em:   http://127.0.0.1:8765  (landing page)  e  /app  (o downloader)
"""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadCancelled

HOST = "127.0.0.1"
PORT = int(os.environ.get("BAIXOU_PORT", "8765"))
FROZEN = getattr(sys, "frozen", False)  # True quando roda como Baixou.exe
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
# ffmpeg, ffprobe e node: na pasta "bin" ao lado do Baixou.exe (o instalador coloca lá).
BIN_DIR = (Path(sys.executable).parent if FROZEN else Path(__file__).parent / "build") / "bin"
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Baixou" if FROZEN else Path(__file__).parent
DOWNLOAD_DIR = Path.home() / "Downloads" / "Baixou"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

STATIC = {
    "/": ROOT / "site" / "index.html",
    "/app": ROOT / "app" / "index.html",
}
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
        ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}

# O YouTube exige um motor de JavaScript; o Node já instalado no PC resolve.
BASE_OPTS = {"quiet": True, "no_warnings": True, "noprogress": True, "js_runtimes": {"node": {}}}
if (BIN_DIR / "node.exe").exists():
    BASE_OPTS["js_runtimes"] = {"node": {"path": str(BIN_DIR / "node.exe")}}
if (BIN_DIR / "ffmpeg.exe").exists():
    BASE_OPTS["ffmpeg_location"] = str(BIN_DIR)

# ---------- login (cookies) ----------
# Vídeos privados ou que pedem login precisam dos cookies de uma sessão logada.
# Duas fontes: ler direto do navegador, ou um arquivo cookies.txt exportado.
COOKIE_FILE = DATA_DIR / "cookies" / "cookies.txt"
_appdata = Path(os.environ.get("APPDATA", ""))
_local = Path(os.environ.get("LOCALAPPDATA", ""))
BROWSERS = {
    "firefox": ("Firefox", _appdata / "Mozilla" / "Firefox" / "Profiles"),
    "chrome": ("Chrome", _local / "Google" / "Chrome" / "User Data"),
    "edge": ("Edge", _local / "Microsoft" / "Edge" / "User Data"),
    "brave": ("Brave", _local / "BraveSoftware" / "Brave-Browser" / "User Data"),
    "opera": ("Opera", _appdata / "Opera Software" / "Opera Stable"),
    "vivaldi": ("Vivaldi", _local / "Vivaldi" / "User Data"),
}


def installed_browsers():
    return [{"id": k, "label": label} for k, (label, path) in BROWSERS.items() if path.exists()]


def apply_auth(opts, auth, cookiefile=None):
    """auth = 'none' | 'file' | 'browser' (navegador interno) | id de navegador."""
    if cookiefile and Path(cookiefile).exists():
        opts["cookiefile"] = cookiefile
    elif auth == "file" and COOKIE_FILE.exists():
        opts["cookiefile"] = str(COOKIE_FILE)
    elif auth in BROWSERS:
        opts["cookiesfrombrowser"] = (auth,)
    return opts


def friendly_error(msg, auth="none"):
    """Troca os erros técnicos mais comuns por uma explicação em português."""
    low = msg.lower()
    name = BROWSERS.get(auth, (auth,))[0]
    if "could not copy chrome cookie database" in low or "permission denied" in low and "cookies" in low:
        return (f"Não consegui ler o login do {name} porque ele está aberto. Feche o {name} por completo "
                "(inclusive o ícone perto do relógio) e tente de novo, ou use um arquivo cookies.txt.")
    if "dpapi" in low or "app-bound" in low or "decrypt" in low:
        return (f"O {name} protege o login com criptografia do Windows e o yt-dlp não consegue abrir. "
                "Use um arquivo cookies.txt (veja em 🔑 Login).")
    if "could not find" in low and "cookies" in low:
        return f"Não encontrei o login do {name} neste computador."
    if any(k in low for k in ("sign in", "logged-in", "login required", "log in", "private video",
                              "members-only", "cookies", "confirm you")):
        if auth == "none":
            return "Esse vídeo exige login. Abra 🔑 Login, no topo, e escolha seu navegador ou um cookies.txt."
        return ("Mesmo com o login, o site recusou. Confira se você está logado na conta certa e, "
                "se usar cookies.txt, exporte um arquivo novo.")
    return msg

jobs = {}
jobs_lock = threading.Lock()


# ---------- yt-dlp ----------

def get_info(url, auth="none"):
    """Lê título, miniatura e qualidades disponíveis sem baixar nada."""
    opts = apply_auth({**BASE_OPTS, "skip_download": True, "extract_flat": "in_playlist",
                       "noplaylist": False}, auth)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        thumb = info.get("thumbnails", [{}])[-1].get("url") if info.get("thumbnails") else None
        if not thumb and entries:
            t = entries[0].get("thumbnails") or []
            thumb = t[-1].get("url") if t else None
        return {
            "kind": "playlist",
            "title": info.get("title") or "Playlist",
            "uploader": info.get("uploader") or info.get("channel"),
            "thumbnail": thumb,
            "count": len(entries),
            "heights": [2160, 1440, 1080, 720, 480, 360],
            "site": info.get("extractor_key"),
        }

    heights = sorted({f["height"] for f in info.get("formats") or []
                      if f.get("height") and f.get("vcodec") not in (None, "none")}, reverse=True)
    return {
        "kind": "video",
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "heights": heights,
        "has_subs": bool(info.get("subtitles")),
        "is_live": bool(info.get("is_live")),
        "site": info.get("extractor_key"),
    }


def build_options(job):
    o = job["options"]
    opts = {
        **BASE_OPTS,
        "windowsfilenames": True,
        "noplaylist": not o.get("playlist", False),
        "outtmpl": str(DOWNLOAD_DIR / "%(playlist_title)s" / "%(playlist_index)03d - %(title)s.%(ext)s")
        if o.get("playlist") else str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
        "progress_hooks": [lambda d: on_progress(job["id"], d)],
        "postprocessor_hooks": [lambda d: on_postprocess(job["id"], d)],
        "concurrent_fragment_downloads": 4,
    }

    if o.get("mode") == "audio":
        codec = o.get("format", "mp3")
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": codec,
                                   "preferredquality": "192"}]
    else:
        h = o.get("quality", "best")
        cap = f"[height<={h}]" if str(h).isdigit() else ""
        opts["format"] = f"bv*{cap}+ba/b{cap}/b"
        opts["format_sort"] = ["res", "ext:mp4:m4a"]
        opts["merge_output_format"] = o.get("format", "mp4")

    if o.get("subs"):
        opts.update({"writesubtitles": True, "writeautomaticsub": True,
                     "subtitleslangs": ["pt.*", "en.*"], "subtitlesformat": "srt/best"})
        opts.setdefault("postprocessors", []).append({"key": "FFmpegSubtitlesConvertor", "format": "srt"})
    return apply_auth(opts, o.get("auth", "none"), o.get("cookiefile"))


def update_job(job_id, **fields):
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job.update(fields)
        return job


def fill_meta(job_id, info):
    """No modo "um clique" o job nasce só com o link: título e miniatura chegam depois."""
    job = jobs.get(job_id)
    if not job or not info:
        return
    playlist = job["options"].get("playlist") and info.get("playlist_title")
    update_job(job_id,
               title=job.get("title") or (info.get("playlist_title") if playlist else info.get("title")),
               thumbnail=job.get("thumbnail") or info.get("thumbnail"),
               site=job.get("site") or info.get("extractor_key"))


def on_progress(job_id, d):
    job = jobs.get(job_id)
    if job and job["cancel"]:
        raise DownloadCancelled("Cancelado pelo usuário")

    info = d.get("info_dict") or {}
    item = info.get("title")
    fill_meta(job_id, info)
    if info.get("playlist_index"):
        update_job(job_id, index=info.get("playlist_index"), count=info.get("n_entries") or info.get("playlist_count"))
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0
        update_job(job_id, status="downloading", item=item,
                   percent=round(done / total * 100, 1) if total else None,
                   speed=d.get("speed"), eta=d.get("eta"), total=total)
    elif d["status"] == "finished":
        update_job(job_id, status="processing", percent=100, item=item)


def on_postprocess(job_id, d):
    fill_meta(job_id, d.get("info_dict"))
    if d["status"] == "started":
        update_job(job_id, status="processing")
    elif d["status"] == "finished":
        path = (d.get("info_dict") or {}).get("filepath")
        if path:
            with jobs_lock:
                job = jobs[job_id]
                if path not in job["files"]:
                    job["files"].append(path)


def run_job(job_id):
    job = jobs[job_id]
    try:
        with yt_dlp.YoutubeDL(build_options(job)) as ydl:
            info = ydl.extract_info(job["url"], download=True)
            fill_meta(job_id, info)
        # Arquivos intermediários (ex.: .m4a antes de virar .mp3) são apagados pelo yt-dlp.
        final = [f for f in job["files"] if os.path.exists(f)]
        update_job(job_id, status="done", percent=100, files=final, finished_at=time.time())
    except DownloadCancelled:
        update_job(job_id, status="cancelled")
    except Exception as e:  # noqa: BLE001 — qualquer erro vira mensagem na tela
        msg = friendly_error(str(e).replace("ERROR: ", "").strip(), job["options"].get("auth", "none"))
        update_job(job_id, status="cancelled" if job["cancel"] else "error", error=msg[:400])
    finally:
        # O login copiado do navegador interno vale só para este download: apaga.
        if job["options"].get("cookiefile"):
            Path(job["options"]["cookiefile"]).unlink(missing_ok=True)


def find_active(url, options):
    """Mesmo link com o mesmo formato já baixando? (evita clique duplo)."""
    keys = ("mode", "format", "quality", "playlist")
    with jobs_lock:
        for j in jobs.values():
            if j["url"] == url and j["status"] in ("queued", "downloading", "processing") and \
                    all(j["options"].get(k) == options.get(k) for k in keys):
                return j
    return None


def start_job(url, options, title=None, thumbnail=None):
    job_id = uuid.uuid4().hex[:10]
    job = {"id": job_id, "url": url, "options": options, "title": title, "thumbnail": thumbnail,
           "status": "queued", "percent": 0, "speed": None, "eta": None, "item": None,
           "index": None, "count": None, "site": None, "total": None,
           "files": [], "error": None, "cancel": False, "created_at": time.time()}
    with jobs_lock:
        jobs[job_id] = job
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return job


def read_clipboard():
    """Lê texto da área de transferência do Windows (sem depender do navegador)."""
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr) if ptr else ""
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def public(job):
    data = {k: v for k, v in job.items() if k not in ("cancel",)}
    data["options"] = {k: v for k, v in job["options"].items() if k != "cookiefile"}
    return data


# ---------- navegador interno ----------
# Uma segunda janela do pywebview onde a pessoa entra nas contas dela.
# O login fica guardado no perfil do Baixou (separado do Chrome) e, na hora de
# baixar, os cookies da página aberta viram um cookies.txt temporário.
BROWSER = {"webview": None, "window": None, "preset": {"mode": "video", "format": "mp4", "quality": "best"}}
TOOLBAR_JS = ROOT / "app" / "browser-toolbar.js"


def write_cookie_file(cookies, url):
    """Converte os cookies do WebView2 para o formato Netscape que o yt-dlp lê."""
    host = urlparse(url).hostname or ""
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        for name, m in c.items():
            domain = m["domain"] or host
            try:
                expires = int(parsedate_to_datetime(m["expires"]).timestamp()) if m["expires"] else 0
            except (TypeError, ValueError, OverflowError):
                expires = 0
            lines.append("\t".join([
                domain, "TRUE" if domain.startswith(".") else "FALSE", m["path"] or "/",
                "TRUE" if m["secure"] else "FALSE", str(max(expires, 0)), name, m.value]))
    path = DATA_DIR / "cookies" / "browser" / f"{uuid.uuid4().hex}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path), len(lines) - 1


class BrowserApi:
    """Funções que o botão "Baixar" (injetado nas páginas) pode chamar."""

    def download(self, url):
        win = BROWSER["window"]
        if not win:
            return {"ok": False, "error": "O navegador foi fechado."}
        # Segurança: um site só consegue pedir o download da própria página aberta.
        current = win.get_current_url() or ""
        if not url or url.split("#")[0] != current.split("#")[0]:
            url = current
        if not url.startswith(("http://", "https://")):
            return {"ok": False, "error": "Abra a página do vídeo primeiro."}
        try:
            cookiefile, n = write_cookie_file(win.get_cookies() or [], url)
        except Exception:  # noqa: BLE001 — sem cookies ainda dá para baixar vídeo público
            cookiefile, n = None, 0
        options = {**BROWSER["preset"], "auth": "browser", "cookiefile": cookiefile, "source": "browser"}
        if find_active(url, options):
            if cookiefile:
                Path(cookiefile).unlink(missing_ok=True)
            return {"ok": False, "error": "Esse vídeo já está baixando. Acompanhe na janela principal."}
        start_job(url, options)
        return {"ok": True, "cookies": n}

    def back(self):
        if BROWSER["window"]:
            BROWSER["window"].evaluate_js("history.back()")


def inject_toolbar():
    win = BROWSER["window"]
    if win and TOOLBAR_JS.exists():
        try:
            win.evaluate_js(TOOLBAR_JS.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — página ainda carregando
            pass


def open_browser(url):
    webview = BROWSER["webview"]
    if webview is None:
        raise RuntimeError("O navegador interno só funciona no programa Baixou (não no modo navegador).")
    win = BROWSER["window"]
    if win:
        win.load_url(url)
        win.restore()
        win.show()
        return
    win = webview.create_window("Baixou · Navegador", url, js_api=BrowserApi(), width=1180, height=800,
                                min_size=(420, 520), text_select=True)
    BROWSER["window"] = win
    win.events.loaded += inject_toolbar
    win.events.closed += lambda: BROWSER.update(window=None)


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def host_ok(self):
        # Bloqueia "DNS rebinding": só aceita quem chama pelo endereço local.
        return self.headers.get("Host") in (f"{HOST}:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/") and not self.host_ok():
            return self.send_json({"error": "Host não permitido"}, 403)
        if path == "/api/jobs":
            with jobs_lock:
                data = sorted((public(j) for j in jobs.values()), key=lambda j: -j["created_at"])
            return self.send_json({"jobs": data, "folder": str(DOWNLOAD_DIR)})
        if path == "/api/clipboard":
            try:
                return self.send_json({"text": read_clipboard().strip()[:2000]})
            except Exception:  # noqa: BLE001
                return self.send_json({"text": ""})
        if path == "/api/settings":
            return self.send_json({"browsers": installed_browsers(), "has_cookie_file": COOKIE_FILE.exists(),
                                   "browser_available": BROWSER["webview"] is not None})

        file = STATIC.get(path.rstrip("/") or "/")
        if file is None:
            candidate = (ROOT / path.lstrip("/")).resolve()
            if ROOT in candidate.parents and candidate.is_file() and candidate.suffix in MIME:
                file = candidate
        if file is None or not file.exists():
            self.send_error(404)
            return
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(file.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # Só aceita pedidos vindos da própria página (protege contra sites de fora).
        origin = self.headers.get("Origin")
        if not self.host_ok() or origin and origin not in (f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"):
            return self.send_json({"error": "Origem não permitida"}, 403)

        try:
            data = self.read_json()
        except json.JSONDecodeError:
            return self.send_json({"error": "JSON inválido"}, 400)

        if self.path == "/api/info":
            url = (data.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return self.send_json({"error": "Cole um link que comece com http:// ou https://"}, 400)
            auth = data.get("auth") or "none"
            try:
                return self.send_json(get_info(url, auth))
            except Exception as e:  # noqa: BLE001
                msg = friendly_error(str(e).replace("ERROR: ", "").strip(), auth)
                return self.send_json({"error": msg[:400]}, 422)

        if self.path == "/api/cookies-file":
            content = data.get("content") or ""
            if len(content) > 5_000_000:
                return self.send_json({"error": "Arquivo grande demais"}, 400)
            lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
            looks_ok = "Netscape HTTP Cookie File" in content[:200] or (
                lines and all(len(ln.split("\t")) >= 7 for ln in lines[:20]))
            if not looks_ok:
                return self.send_json({"error": "Esse arquivo não parece um cookies.txt (formato Netscape). "
                                                "Exporte de novo com a extensão indicada."}, 400)
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(content, encoding="utf-8")
            return self.send_json({"ok": True, "count": len(lines)})

        if self.path == "/api/cookies-file/delete":
            COOKIE_FILE.unlink(missing_ok=True)
            return self.send_json({"ok": True})

        if self.path == "/api/download":
            url = (data.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return self.send_json({"error": "Link inválido"}, 400)
            options = data.get("options") or {}
            options.pop("cookiefile", None)  # só o navegador interno define isso
            if find_active(url, options):
                return self.send_json({"error": "Esse vídeo já está baixando."}, 409)
            job = start_job(url, options, data.get("title"), data.get("thumbnail"))
            return self.send_json(public(job))

        if self.path == "/api/cancel":
            job = update_job(data.get("id"), cancel=True)
            return self.send_json({"ok": bool(job)})

        if self.path == "/api/clear":
            with jobs_lock:
                for jid in [j["id"] for j in jobs.values() if j["status"] in ("done", "error", "cancelled")]:
                    del jobs[jid]
            return self.send_json({"ok": True})

        if self.path == "/api/browser/open":
            url = (data.get("url") or "").strip()
            if url and not url.startswith(("http://", "https://")):
                url = "https://" + url
            if not url.startswith(("http://", "https://")) or " " in url:
                return self.send_json({"error": "Endereço inválido"}, 400)
            try:
                open_browser(url)
            except Exception as e:  # noqa: BLE001
                return self.send_json({"error": str(e)}, 409)
            return self.send_json({"ok": True})

        if self.path == "/api/browser/logout":
            win = BROWSER["window"]
            if not win:
                return self.send_json({"error": "Abra o navegador primeiro."}, 409)
            win.clear_cookies()
            win.evaluate_js("location.reload()")
            return self.send_json({"ok": True})

        if self.path == "/api/preset":
            p = data.get("preset") or {}
            BROWSER["preset"] = {k: p[k] for k in ("mode", "format", "quality", "playlist", "subs") if k in p}
            return self.send_json({"ok": True})

        if self.path == "/api/remove":
            with jobs_lock:
                job = jobs.get(data.get("id"))
                if job and job["status"] in ("done", "error", "cancelled"):
                    del jobs[job["id"]]
            return self.send_json({"ok": True})

        if self.path == "/api/retry":
            old = jobs.get(data.get("id"))
            if not old:
                return self.send_json({"error": "Download não encontrado"}, 404)
            with jobs_lock:
                jobs.pop(old["id"], None)
            return self.send_json(public(start_job(old["url"], old["options"], old["title"], old["thumbnail"])))

        if self.path == "/api/open-file":
            target = Path(data.get("path") or "")
            if not target.is_file() or DOWNLOAD_DIR not in target.parents:
                return self.send_json({"error": "Arquivo não encontrado (foi movido ou apagado?)"}, 404)
            if data.get("reveal"):
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                os.startfile(target)  # type: ignore[attr-defined]
            return self.send_json({"ok": True})

        if self.path == "/api/open-folder":
            target = Path(data.get("path") or DOWNLOAD_DIR)
            target = target.parent if target.is_file() else target
            if DOWNLOAD_DIR not in [target, *target.parents]:
                target = DOWNLOAD_DIR
            os.startfile(target)  # type: ignore[attr-defined]  # Windows
            return self.send_json({"ok": True})

        self.send_error(404)


def start_server():
    """Liga o servidor numa thread. Se já tiver um Baixou aberto, reaproveita."""
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        return None  # porta ocupada: outro Baixou já está rodando
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    url = f"http://{HOST}:{PORT}/app"

    # Modo servidor puro (usado no desenvolvimento / preview).
    if "--no-browser" in sys.argv or "--server" in sys.argv:
        if not start_server():
            sys.exit(f"A porta {PORT} já está em uso.")
        print(f"Baixou rodando em {url}")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return

    start_server()

    # Modo programa: abre numa janela própria (usa o Edge WebView2 do Windows).
    if "--browser" not in sys.argv:
        try:
            import webview
            BROWSER["webview"] = webview
            webview.create_window("Baixou", url, width=1120, height=740, min_size=(380, 520),
                                  background_color="#14110E")
            webview.start(private_mode=False, storage_path=str(DATA_DIR / "webview"))
            return  # fechou a janela: o programa termina
        except Exception as e:  # noqa: BLE001 — sem WebView2: cai para o navegador
            print("Janela própria indisponível, abrindo no navegador:", e)

    webbrowser.open(url)
    print(f"Baixou rodando em {url}  (feche esta janela para desligar)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
