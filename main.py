import os, json, time, threading, shutil, uvicorn, httpx, random, re, sys, webbrowser, ctypes
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
import requests as req_lib
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

app = FastAPI()

def get_chrome_major_version():
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
            v, _ = winreg.QueryValueEx(key, "version")
            return int(v.split('.')[0])
    except: pass
    return None

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class TikTokSession:
    def __init__(self):
        self.session = req_lib.Session()
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        self.cookies_loaded = False

    def load_cookies_from_browser(self, cookies_list):
        for c in cookies_list:
            self.session.cookies.set(c['name'], c['value'], domain=c.get('domain', '.tiktok.com'), path=c.get('path', '/'))
        self.apply_headers()
        self.cookies_loaded = True

    def apply_headers(self):
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Referer': 'https://www.tiktok.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })

    def save_cookies(self, path):
        cks = []
        for c in self.session.cookies:
            cks.append({'name': c.name, 'value': c.value, 'domain': c.domain, 'path': c.path})
        with open(path, 'w') as f: json.dump(cks, f)

    def load_cookies_from_file(self, path):
        with open(path, 'r') as f: cks = json.load(f)
        self.load_cookies_from_browser(cks)

    def get_profile(self, username):
        self.apply_headers()
        resp = self.session.get(f'https://www.tiktok.com/@{username}', timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        script = soup.find('script', id='__UNIVERSAL_DATA_FOR_REHYDRATION__')
        if not script: raise Exception("Profilo non trovato o protezione anti-bot attiva.")
        data = json.loads(script.string)
        scope = data.get('__DEFAULT_SCOPE__', {})
        detail = scope.get('webapp.user-detail', {})
        user_info = detail.get('userInfo', {})
        user = user_info.get('user', {})
        stats = user_info.get('stats', {})
        return {
            'uniqueId': user.get('uniqueId', username),
            'nickname': user.get('nickname', ''),
            'avatar': user.get('avatarLarger', ''),
            'bio': user.get('signature', '')[:100],
            'videoCount': stats.get('videoCount', 0),
            'secUid': user.get('secUid', ''),
            'id': user.get('id', ''),
        }

    def get_user_videos(self, sec_uid, cursor=0, count=30):
        url = 'https://www.tiktok.com/api/post/item_list/'
        params = {'WebIdLastTime': str(int(time.time())), 'aid': '1988', 'count': str(count), 'cursor': str(cursor), 'secUid': sec_uid}
        resp = self.session.get(url, params=params, timeout=20)
        data = resp.json()
        return data.get('itemList', []), data.get('cursor', 0), data.get('hasMore', False)

    def download_file(self, url, path):
        try:
            headers = {'User-Agent': self.user_agent, 'Referer': 'https://www.tiktok.com/'}
            resp = self.session.get(url, timeout=30, headers=headers)
            if resp.status_code == 200:
                with open(path, 'wb') as f: f.write(resp.content)
                return True
            else:
                log(f"Download fallito: HTTP {resp.status_code}", "error")
        except Exception as e:
            log(f"Eccezione download: {str(e)}", "error")
        return False

class ScraperState:
    def __init__(self):
        self.tiktok = TikTokSession()
        self.current_user = None
        self.current_user_avatar = ""
        self.is_running = False
        self.stop_requested = False
        self.logs = []
        self.log_counter = 0
        self.post_count = 0
        self.target_info = {"name": "", "avatar": "", "bio": ""}
        self.session_dir = ".sessions"
        self.driver = None
        if not os.path.exists(self.session_dir): os.makedirs(self.session_dir)

state = ScraperState()

def log(msg, type="info"):
    state.log_counter += 1
    t = time.strftime("%H:%M:%S")
    if len(state.logs) > 500: state.logs.pop(0)
    state.logs.append({"id": state.log_counter, "time": t, "msg": msg, "type": type})

def try_auto_login():
    if not os.path.exists(state.session_dir): return
    files = [f for f in os.listdir(state.session_dir) if f.startswith("session_") and f.endswith(".json")]
    if files:
        try:
            state.tiktok.load_cookies_from_file(os.path.join(state.session_dir, files[0]))
            state.current_user = files[0].replace("session_", "").replace(".json", "")
            try:
                p = state.tiktok.get_profile(state.current_user)
                state.current_user_avatar = p['avatar']
            except: pass
            log(f"Sessione ripristinata per @{state.current_user}", "success")
        except: pass

def start_unified_browser():
    update_loader(80, "Sincronizzazione Browser...")
    try:
        # Pulizia preventiva cartella temporanea se bloccata
        p_path = os.path.join(os.environ['LOCALAPPDATA'], 'Google', 'Chrome', 'User Data', 'TikScrapePro')
        
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-popup-blocking")
        options.add_argument(f"--user-data-dir={p_path}")
        
        major_v = get_chrome_major_version()
        log(f"Versione Chrome rilevata: {major_v}", "info")

        # Tentativo con uc
        try:
            state.driver = uc.Chrome(options=options, use_subprocess=True, version_main=major_v)
        except Exception as e_uc:
            log(f"UC Fallito: {e_uc}. Riprovo senza opzioni...", "info")
            state.driver = uc.Chrome(use_subprocess=True, version_main=major_v)
            
        state.driver.get("http://127.0.0.1:8000")
        update_loader(100, "Dashboard Operativa")
    except Exception as e:
        err_msg = str(e)[:30]
        log(f"Errore Fatale Browser: {str(e)}", "error")
        update_loader(100, f"Errore: {err_msg}")

# --- GUI LOGIC (IDENTICA A INSTASCRAPE) ---
loader_root = None
progress_bar = None
status_label = None
btn_frame = None

def shutdown_app():
    if state.driver:
        try: state.driver.quit()
        except: pass
    os._exit(0)

def manual_open():
    webbrowser.open("http://127.0.0.1:8000")

def minimize_app():
    hwnd = ctypes.windll.user32.GetParent(loader_root.winfo_id())
    ctypes.windll.user32.ShowWindow(hwnd, 6) # 6 = SW_MINIMIZE

def create_loader():
    global loader_root, progress_bar, status_label, btn_frame
    loader_root = tk.Tk()
    loader_root.title("980 COMMAND CENTER")
    loader_root.overrideredirect(True)
    loader_root.attributes('-topmost', True)
    loader_root.configure(bg='#0a0a0f')

    # Forza visibilità taskbar
    def set_appwindow():
        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        hwnd = ctypes.windll.user32.GetParent(loader_root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
        loader_root.withdraw(); loader_root.after(10, loader_root.deiconify)
    loader_root.after(100, set_appwindow)

    # Icona
    try:
        icon_path = resource_path("logo.png")
        icon_img = ImageTk.PhotoImage(Image.open(icon_path))
        loader_root.iconphoto(False, icon_img)
    except: pass

    # Dimensioni e Posizione
    w, h = 400, 320
    sw, sh = loader_root.winfo_screenwidth(), loader_root.winfo_screenheight()
    loader_root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # Title Bar
    title_bar = tk.Frame(loader_root, bg='#16161e', height=30)
    title_bar.pack(fill='x', side='top')
    def start_move(event): loader_root.x, loader_root.y = event.x, event.y
    def on_move(event):
        x = loader_root.winfo_x() + (event.x - loader_root.x)
        y = loader_root.winfo_y() + (event.y - loader_root.y)
        loader_root.geometry(f"+{x}+{y}")
    title_bar.bind('<Button-1>', start_move); title_bar.bind('<B1-Motion>', on_move)
    tk.Label(title_bar, text=" 980 COMMAND CENTER", fg="#9CA3AF", bg='#16161e', font=("Outfit", 7, "bold")).pack(side='left', padx=10)
    tk.Button(title_bar, text="—", command=minimize_app, bg='#16161e', fg='white', relief='flat', font=("Arial", 8), bd=0, padx=10).pack(side='right')

    # Logo
    try:
        img_path = resource_path("logo.png")
        img = Image.open(img_path).resize((70, 70), Image.LANCZOS)
        logo_img = ImageTk.PhotoImage(img)
        tk.Label(loader_root, image=logo_img, bg='#0a0a0f').pack(pady=(20, 5))
        loader_root.logo_img = logo_img 
    except: pass

    tk.Label(loader_root, text="980 TIKSCRAPE PRO", fg="white", bg='#0a0a0f', font=("Outfit", 12, "bold")).pack()
    status_label = tk.Label(loader_root, text="Inizializzazione Core...", fg="#9CA3AF", bg='#0a0a0f', font=("Outfit", 9))
    status_label.pack(pady=(15, 5))

    style = ttk.Style()
    style.theme_use('default')
    style.configure("TProgressbar", thickness=4, troughcolor='#1f1f2e', background='#7C3AED', bordercolor='#0a0a0f', lightcolor='#7C3AED', darkcolor='#7C3AED')
    progress_bar = ttk.Progressbar(loader_root, style="TProgressbar", orient="horizontal", length=300, mode="determinate")
    progress_bar.pack(pady=10)
    
    btn_frame = tk.Frame(loader_root, bg='#0a0a0f')
    tk.Button(btn_frame, text="APRI DASHBOARD", command=manual_open, bg='#7C3AED', fg='white', font=("Outfit", 8, "bold"), relief='flat', padx=15, pady=8).pack(side='left', padx=10)
    tk.Button(btn_frame, text="SHUTDOWN", command=shutdown_app, bg='#1f1f2e', fg='#EF4444', font=("Outfit", 8, "bold"), relief='flat', padx=15, pady=8, highlightbackground='#EF4444', highlightthickness=1).pack(side='left', padx=10)

    # Boot Sequence Simulata
    def boot():
        for i in range(1, 81):
            update_loader(i, "Caricamento moduli...")
            time.sleep(0.01)
    threading.Thread(target=boot, daemon=True).start()
    
    loader_root.mainloop()

def update_loader(val, text):
    if loader_root and progress_bar and status_label:
        progress_bar['value'] = val
        status_label.config(text=text)
        if val >= 100 and btn_frame: btn_frame.pack(pady=20)
        loader_root.update()

# --- API ---
@app.get("/")
async def get_index():
    path = resource_path("index.html")
    with open(path, "r", encoding="utf-8") as f: return HTMLResponse(f.read())

@app.get("/logo.png")
async def get_logo():
    path = resource_path("logo.png")
    if not os.path.exists(path):
        # Prova percorso relativo se resource_path fallisce in dev
        path = "logo.png"
    if os.path.exists(path): return FileResponse(path)
    return Response(status_code=404)

@app.get("/api/status")
async def get_status():
    return {"user": state.current_user, "avatar": state.current_user_avatar, "is_running": state.is_running, "logs": state.logs, "post_count": state.post_count, "target": state.target_info}

@app.post("/api/login")
async def api_login():
    threading.Thread(target=run_browser_login, daemon=True).start()
    return {"status": "started"}

@app.post("/api/logout")
async def api_logout():
    state.current_user = None
    state.current_user_avatar = ""
    state.tiktok.session = req_lib.Session() # Reset session
    state.tiktok.cookies_loaded = False
    
    # Pulizia file sessione
    if os.path.exists(state.session_dir):
        for f in os.listdir(state.session_dir):
            try: os.remove(os.path.join(state.session_dir, f))
            except: pass
            
    log("Sessione chiusa correttamente.", "info")
    return {"status": "ok"}

def run_browser_login():
    if not state.driver: return
    state.driver.get("https://www.tiktok.com/login")
    start = time.time()
    while time.time() - start < 600:
        try:
            cks = state.driver.get_cookies()
            sid = next((c for c in cks if c['name'] == 'sessionid'), None)
            if sid:
                state.tiktok.load_cookies_from_browser(cks)
                state.driver.get("https://www.tiktok.com/profile")
                time.sleep(3)
                cur = state.driver.current_url
                if '/@' in cur:
                    state.current_user = cur.split('/@')[1].split('?')[0]
                    # Tentativo di recuperare l'avatar dal profilo
                    try:
                        p = state.tiktok.get_profile(state.current_user)
                        state.current_user_avatar = p['avatar']
                    except: pass
                    
                    state.tiktok.save_cookies(os.path.join(state.session_dir, f"session_{state.current_user}.json"))
                    log(f"Login completato: @{state.current_user}", "success")
                    state.driver.get("http://127.0.0.1:8000")
                    break
        except: break
        time.sleep(3)

@app.post("/api/set_target")
async def set_target(req: Request):
    data = await req.json(); t = data.get("username")
    try:
        p = state.tiktok.get_profile(t)
        state.target_info = {"name": p['uniqueId'], "avatar": p['avatar'], "bio": p['bio'], "id": p['id'], "count": p['videoCount'], "secUid": p['secUid']}
        log(f"Target @{t} acquisito.", "success")
        return {"status": "ok", "target": state.target_info}
    except Exception as e: return {"status": "error", "msg": str(e)}

@app.post("/api/start")
async def start_scrape(req: Request):
    data = await req.json()
    state.is_running = True; state.stop_requested = False
    threading.Thread(target=worker, args=(data,), daemon=True).start()
    return {"status": "started"}

@app.post("/api/stop")
async def stop_scrape(): state.stop_requested = True; return {"status": "ok"}

@app.get("/api/proxy_image")
async def proxy_image(url: str):
    try:
        resp = req_lib.get(url, timeout=10)
        return Response(content=resp.content, media_type="image/jpeg")
    except: return Response(status_code=404)

def worker(opt):
    try:
        t = state.target_info["name"]; sec = state.target_info["secUid"]
        root = os.path.join("downloads", t); os.makedirs(root, exist_ok=True)
        state.post_count = 0; cursor = 0
        while not state.stop_requested:
            items, cursor, has_more = state.tiktok.get_user_videos(sec, cursor)
            if not items: break
            for item in items:
                if state.stop_requested: break
                vid = item.get('id', ''); date = time.strftime("%Y%m%d_%H%M%S", time.gmtime(int(item.get('createTime', 0))))
                img_p = item.get('imagePost')
                if img_p and opt.get('posts'):
                    d = os.path.join(root, "foto"); os.makedirs(d, exist_ok=True)
                    for i, img in enumerate(img_p.get('images', [])):
                        url = img.get('imageURL', {}).get('urlList', [''])[0]
                        if url: state.tiktok.download_file(url, os.path.join(d, f"{date}_{vid}_{i}.jpg"))
                elif not img_p and opt.get('videos'):
                    d = os.path.join(root, "video"); os.makedirs(d, exist_ok=True)
                    v = item.get('video', {}); url = v.get('playAddr') or v.get('downloadAddr')
                    if url:
                        success = state.tiktok.download_file(url, os.path.join(d, f"{date}_{vid}.mp4"))
                        if not success: log(f"Errore download video {vid}", "error")
                
                state.post_count += 1
                if state.post_count % 5 == 0: log(f"Scaricati {state.post_count} elementi...")
                time.sleep(random.uniform(0.5, 1.2))
            if not has_more: break
        log(f"Completato per @{t}.", "success")
    finally: state.is_running = False

if __name__ == "__main__":
    try_auto_login()
    threading.Thread(target=lambda: uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None), daemon=True).start()
    threading.Thread(target=start_unified_browser, daemon=True).start()
    create_loader()
