import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json, time, hashlib, os, re
try:
    import bcrypt # pip install bcrypt zorunludur
except ImportError:
    st.error("🚨 'bcrypt' kütüphanesi eksik! Terminale 'pip install bcrypt' yazmalısın."); st.stop()
from datetime import datetime, timedelta
from PIL import Image

# --- 1. YAPILANDIRMA ---
st.set_page_config(page_title="T-BOZKURT", layout="wide", page_icon="🐺")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tbozkurt_master_v60.db")

AI_KOTALARI = {"free": 2, "premium": 35, "admin": 999}
RATE_LIMITS = {"free": 15, "premium": 5, "admin": 0}
SALT_OLD = "v57_ultra_secure_salt_2026"

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
    ADMIN_VERIFY_KEY = st.secrets.get("ADMIN_VERIFY_KEY", "KIZILELMA_2026")
except Exception:
    st.error("⚠️ Secrets (GEMINI_KEY, ADMIN_KEY) yapılandırması eksik!"); st.stop()

# --- 2. VERİTABANI MOTORU ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    try:
        with sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            c = conn.cursor()
            c.execute(sorgu, parametre)
            if commit: 
                conn.commit()
                return c.rowcount > 0
            res = c.fetchall()
            return res if res else []
    except Exception:
        return False if commit else []

def vt_kurulum():
    vt_sorgu("""CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, password TEXT, sinif TEXT, role TEXT DEFAULT 'user',
        kayit_tarihi TEXT, xp INTEGER DEFAULT 0, deneme_bitis TEXT, streak INTEGER DEFAULT 0, 
        son_giris TEXT, rozetler TEXT DEFAULT '[]', son_islem_zamani TEXT DEFAULT '', 
        ai_sayaci INTEGER DEFAULT 0, aktif INTEGER DEFAULT 1,
        hatali_giris INTEGER DEFAULT 0, kilit_suresi TEXT)""", commit=True)
    
    vt_sorgu("""CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, islem TEXT, detay TEXT, tarih TEXT)""", commit=True)
    
    if not vt_sorgu("SELECT 1 FROM users WHERE username='t_admin'"):
        h_adm = bcrypt.hashpw(ADMIN_SIFRE.encode(), bcrypt.gensalt()).decode()
        vt_sorgu("INSERT INTO users (username, password, role, aktif, deneme_bitis) VALUES (?,?,?,?,?)", 
                 ("t_admin", h_adm, "admin", 1, "2099-12-31"), commit=True)

vt_kurulum()

# --- 3. GÜVENLİK ---
def sifre_dogrula(u, p, stored_hash):
    if stored_hash.startswith("$2b$"):
        return bcrypt.checkpw(p.encode(), stored_hash.encode())
    return hashlib.sha256((u + p + SALT_OLD).encode()).hexdigest() == stored_hash

def sistem_kontrol(u):
    today = str(datetime.now().date())
    res = vt_sorgu("SELECT son_giris, streak FROM users WHERE username=?", (u,))
    if res and res[0][0] and res[0][0] != today:
        vt_sorgu("UPDATE users SET ai_sayaci=0, son_giris=? WHERE username=?", (today, u), commit=True)
        try:
            fark = (datetime.now().date() - datetime.strptime(res[0][0], "%Y-%m-%d").date()).days
            yeni = res[0][1] + 1 if fark == 1 else 1
            vt_sorgu("UPDATE users SET streak=? WHERE username=?", (yeni, u), commit=True)
        except: pass
    elif res and not res[0][0]:
        vt_sorgu("UPDATE users SET son_giris=? WHERE username=?", (today, u), commit=True)

# --- 4. GİRİŞ / KAYIT ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Karargah")
    t1, t2 = st.tabs(["🔑 Giriş", "📝 Nefer Kaydı"])
    with t1:
        u, p = st.text_input("Alfa Adı"), st.text_input("Şifre", type="password")
        if st.button("Sisteme Gir"):
            u_info = vt_sorgu("SELECT password, hatali_giris, kilit_suresi, aktif, role FROM users WHERE username=?", (u,))
            if u_info:
                pw, h_giris, kilit, aktif, u_role = u_info[0]
                if aktif == 0: st.error("Pasif hesap."); st.stop()
                if kilit and datetime.now() < datetime.strptime(kilit, "%Y-%m-%d %H:%M:%S"):
                    st.error(f"🔒 Kilitli: {kilit}"); st.stop()
                if sifre_dogrula(u, p, pw):
                    vt_sorgu("UPDATE users SET hatali_giris=0, kilit_suresi=NULL WHERE username=?", (u,), commit=True)
                    st.session_state.user, st.session_state.role = u, u_role
                    sistem_kontrol(u); st.rerun()
                else:
                    yeni_h = h_giris + 1
                    if yeni_h >= 5:
                        kilit_vakti = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
                        vt_sorgu("UPDATE users SET hatali_giris=0, kilit_suresi=? WHERE username=?", (kilit_vakti, u), commit=True)
                    else:
                        vt_sorgu("UPDATE users SET hatali_giris=? WHERE username=?", (yeni_h, u), commit=True)
                    st.error("Hatalı şifre!")
    with t2:
        nu, np = st.text_input("Yeni Alfa Adı"), st.text_input("Şifre", type="password")
        if st.button("Kaydol") and len(np) >= 6:
            if not vt_sorgu("SELECT 1 FROM users WHERE username=?", (nu,)):
                h_np = bcrypt.hashpw(np.encode(), bcrypt.gensalt()).decode()
                vt_sorgu("INSERT INTO users (username, password, kayit_tarihi, streak) VALUES (?,?,?,?)", (nu, h_np, str(datetime.now().date()), 1), commit=True)
                st.success("Kayıt başarılı!")
            else: st.error("Ad alınmış.")
    st.stop()

# --- 5. ANA VERİ ÇEKME (Düzeltildi: streak eklendi) ---
sistem_kontrol(st.session_state.user)
res = vt_sorgu("SELECT xp, deneme_bitis, ai_sayaci, son_islem_zamani, streak FROM users WHERE username=?", (st.session_state.user,))
u_xp, u_bitis, u_ai_kota, u_son_islem, u_streak = res[0]

premium = False
if u_bitis:
    try: premium = datetime.now().date() <= datetime.strptime(u_bitis, "%Y-%m-%d").date()
    except: pass

k_tipi = st.session_state.role if st.session_state.role == "admin" else ("premium" if premium else "free")
max_kota, limit_sn = AI_KOTALARI.get(k_tipi, 2), RATE_LIMITS.get(k_tipi, 15)

# --- 6. SIDEBAR VE MENÜ ---
with st.sidebar:
    st.title(f"🎖️ {st.session_state.user}")
    st.metric("🤖 AI Kotası", f"{u_ai_kota}/{max_kota}")
    menu = st.radio("Operasyon", ["📊 Karargah", "📸 Soru Çöz", "🛠️ Admin"])
    if st.button("🚪 Çıkış"): st.session_state.clear(); st.rerun()

# --- 7. MODÜLLER ---
if menu == "📸 Soru Çöz":
    if u_ai_kota >= max_kota: st.warning("Limit doldu."); st.stop()
    if u_son_islem:
        try:
            fark = (datetime.now() - datetime.strptime(u_son_islem, "%Y-%m-%d %H:%M:%S")).total_seconds()
            if fark < limit_sn: st.warning(f"🕒 Bekle: {int(limit_sn-fark)}s"); st.stop()
        except: pass
    img = st.camera_input("Soru")
    if img:
        try:
            res_ai = MODEL.generate_content(contents=[{"role": "user", "parts": ["YKS Sorusu, çöz.", Image.open(img)]}])
            if res_ai and hasattr(res_ai, "text"):
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                vt_sorgu("UPDATE users SET ai_sayaci=ai_sayaci+1, son_islem_zamani=? WHERE username=?", (now_str, st.session_state.user), commit=True)
                st.markdown(res_ai.text)
        except: st.error("AI meşgul, kotanızdan düşülmedi.")

elif menu == "📊 Karargah":
    st.title(f"Hoş geldin, {st.session_state.user}!")
    st.info(f"Bugün senin {u_streak}. günün! İstikrarın daim olsun.")

elif menu == "🛠️ Admin" and st.session_state.role == "admin":
    v_key = st.text_input("🔒 Admin Key", type="password")
    if v_key == ADMIN_VERIFY_KEY:
        logs = vt_sorgu("SELECT * FROM system_logs ORDER BY id DESC LIMIT 20")
        st.dataframe(pd.DataFrame(logs))
