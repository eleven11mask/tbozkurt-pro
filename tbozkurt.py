import streamlit as st
import psycopg2 
from psycopg2 import extras
import google.generativeai as genai
import json, time, hashlib, os, re
try:
    import bcrypt
except ImportError:
    st.error("🚨 'bcrypt' kütüphanesi eksik! 'pip install bcrypt' yapmalısın."); st.stop()
from datetime import datetime, timedelta
from PIL import Image

# --- 1. YAPILANDIRMA ---
st.set_page_config(page_title="T-BOZKURT", layout="wide", page_icon="🐺")

AI_KOTALARI = {"free": 2, "premium": 35, "admin": 999}
RATE_LIMITS = {"free": 15, "premium": 5, "admin": 0}
SALT_OLD = "v57_ultra_secure_salt_2026"

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
    ADMIN_VERIFY_KEY = st.secrets.get("ADMIN_VERIFY_KEY", "KIZILELMA_2026")
    DB_URL = st.secrets["DATABASE_URL"]
except Exception:
    st.error("⚠️ Secrets (DATABASE_URL, GEMINI_KEY vb.) eksik veya hatalı!"); st.stop()

# --- 2. POSTGRESQL MOTORU ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=extras.DictCursor)
        cur.execute(sorgu, parametre)
        if commit:
            conn.commit()
            res = True
        else:
            res = cur.fetchall()
        cur.close()
        conn.close()
        return res if res else []
    except Exception as e:
        return False if commit else []

def log_ekle(u, islem, detay):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vt_sorgu("INSERT INTO system_logs (username, islem, detay, tarih) VALUES (%s,%s,%s,%s)", (u, islem, detay, now), commit=True)

def vt_kurulum():
    # Kullanıcı tablosu
    vt_sorgu("""CREATE TABLE IF NOT EXISTS users (
        username VARCHAR PRIMARY KEY, password VARCHAR, sinif VARCHAR, role VARCHAR DEFAULT 'user',
        kayit_tarihi VARCHAR, xp INTEGER DEFAULT 0, deneme_bitis VARCHAR, streak INTEGER DEFAULT 0, 
        son_giris VARCHAR, rozetler VARCHAR DEFAULT '[]', son_islem_zamani VARCHAR DEFAULT '', 
        ai_sayaci INTEGER DEFAULT 0, aktif INTEGER DEFAULT 1,
        hatali_giris INTEGER DEFAULT 0, kilit_suresi VARCHAR)""", commit=True)
    
    # Log tablosu
    vt_sorgu("""CREATE TABLE IF NOT EXISTS system_logs (
        id SERIAL PRIMARY KEY, username VARCHAR, islem VARCHAR, detay TEXT, tarih VARCHAR)""", commit=True)
    
    # Admin kontrolü
    if not vt_sorgu("SELECT 1 FROM users WHERE username='t_admin'"):
        h_adm = bcrypt.hashpw(ADMIN_SIFRE.encode(), bcrypt.gensalt()).decode()
        vt_sorgu("INSERT INTO users (username, password, role, aktif, deneme_bitis) VALUES (%s,%s,%s,%s,%s)", 
                 ("t_admin", h_adm, "admin", 1, "2099-12-31"), commit=True)

vt_kurulum()

# --- 3. SİSTEM FONKSİYONLARI ---
def sifre_dogrula(u, p, stored_hash):
    if stored_hash.startswith("$2b$"):
        return bcrypt.checkpw(p.encode(), stored_hash.encode())
    return hashlib.sha256((u + p + SALT_OLD).encode()).hexdigest() == stored_hash

def sistem_kontrol(u):
    today = str(datetime.now().date())
    res = vt_sorgu("SELECT son_giris, streak FROM users WHERE username=%s", (u,))
    if res and res[0]['son_giris'] != today:
        vt_sorgu("UPDATE users SET ai_sayaci=0, son_giris=%s WHERE username=%s", (today, u), commit=True)
        try:
            if res[0]['son_giris']:
                fark = (datetime.now().date() - datetime.strptime(res[0]['son_giris'], "%Y-%m-%d").date()).days
                yeni = res[0]['streak'] + 1 if fark == 1 else 1
            else: yeni = 1
            vt_sorgu("UPDATE users SET streak=%s WHERE username=%s", (yeni, u), commit=True)
        except: pass

# --- 4. GİRİŞ / KAYIT EKRANI ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Karargah")
    t1, t2 = st.tabs(["🔑 Giriş", "📝 Nefer Kaydı"])
    
    with t1:
        u = st.text_input("Alfa Adı", key="login_u")
        p = st.text_input("Şifre", type="password", key="login_p")
        if st.button("Sisteme Gir", key="login_btn"):
            u_info = vt_sorgu("SELECT password, hatali_giris, kilit_suresi, aktif, role FROM users WHERE username=%s", (u,))
            if u_info:
                pw, h_giris, kilit, aktif, u_role = u_info[0]
                if kilit and datetime.now() < datetime.strptime(kilit, "%Y-%m-%d %H:%M:%S"):
                    st.error(f"🔒 Hesap kilitlendi! Açılış: {kilit}"); st.stop()
                
                if sifre_dogrula(u, p, pw):
                    vt_sorgu("UPDATE users SET hatali_giris=0, kilit_suresi=NULL WHERE username=%s", (u,), commit=True)
                    st.session_state.user = u
                    st.session_state.role = u_role
                    log_ekle(u, "GIRIS", "Başarılı giriş.")
                    sistem_kontrol(u); st.rerun()
                else:
                    yeni_h = h_giris + 1
                    if yeni_h >= 5:
                        k_vakti = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
                        vt_sorgu("UPDATE users SET hatali_giris=0, kilit_suresi=%s WHERE username=%s", (k_vakti, u), commit=True)
                        log_ekle(u, "GUVENLIK", "Hesap kilitlendi (5 hatalı deneme)")
                    else:
                        vt_sorgu("UPDATE users SET hatali_giris=%s WHERE username=%s", (yeni_h, u), commit=True)
                    st.error(f"Hatalı şifre! (Kalan Hak: {5-yeni_h})")
            else: st.error("Kullanıcı bulunamadı.")
            
    with t2:
        nu = st.text_input("Yeni Alfa Adı", key="reg_u")
        np = st.text_input("Şifre (Min 6 Karakter)", type="password", key="reg_p")
        if st.button("Kaydol", key="reg_btn"):
            if len(np) < 6: st.warning("Şifre çok kısa!")
            elif vt_sorgu("SELECT 1 FROM users WHERE username=%s", (nu,)): st.error("Bu ad alınmış.")
            else:
                h_np = bcrypt.hashpw(np.encode(), bcrypt.gensalt()).decode()
                vt_sorgu("INSERT INTO users (username, password, kayit_tarihi, streak) VALUES (%s,%s,%s,%s)", 
                         (nu, h_np, str(datetime.now().date()), 1), commit=True)
                log_ekle(nu, "KAYIT", "Yeni nefer katıldı.")
                st.success("Kayıt başarılı! Giriş yapabilirsin.")
    st.stop()

# --- 5. ANA EKRAN VERİLERİ ---
res = vt_sorgu("SELECT xp, deneme_bitis, ai_sayaci, son_islem_zamani, streak FROM users WHERE username=%s", (st.session_state.user,))
if not res:
    st.error("Oturum hatası.")
    st.session_state.clear(); st.rerun()

u_xp, u_bitis, u_ai_kota, u_son_islem, u_streak = res[0]

# Rütbe ve Kota Kontrolü
premium = False
if u_bitis:
    try: premium = datetime.now().date() <= datetime.strptime(u_bitis, "%Y-%m-%d").date()
    except: pass

k_tipi = st.session_state.role if st.session_state.role == "admin" else ("premium" if premium else "free")
max_kota, limit_sn = AI_KOTALARI.get(k_tipi, 2), RATE_LIMITS.get(k_tipi, 15)

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title(f"🎖️ {st.session_state.user}")
    st.metric("🤖 AI Günlük Kota", f"{u_ai_kota}/{max_kota}")
    st.divider()
    menu = st.radio("Operasyon", ["📊 Karargah", "📸 Soru Çöz", "🛠️ Admin"], key="main_menu")
    if st.button("🚪 Güvenli Çıkış", key="logout_btn"):
        log_ekle(st.session_state.user, "CIKIS", "Çıkış yapıldı.")
        st.session_state.clear(); st.rerun()

# --- 7. MODÜLLER ---

if menu == "📸 Soru Çöz":
    if u_ai_kota >= max_kota: st.warning("Günlük AI limitin doldu! Yarına kadar dinlen."); st.stop()
    
    if u_son_islem:
        try:
            fark = (datetime.now() - datetime.strptime(u_son_islem, "%Y-%m-%d %H:%M:%S")).total_seconds()
            if fark < limit_sn: st.warning(f"🕒 Hızlı gidiyorsun! {int(limit_sn-fark)} saniye sonra tekrar dene."); st.stop()
        except: pass

    img = st.camera_input("Soruyu Karargaha Gönder", key="cam_input")
    if img:
        with st.spinner("AI Soruyu Analiz Ediyor..."):
            try:
                res_ai = MODEL.generate_content(contents=[{"role": "user", "parts": ["YKS Sorusu, adım adım Türkçe çöz.", Image.open(img)]}])
                if res_ai and hasattr(res_ai, "text"):
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    vt_sorgu("UPDATE users SET ai_sayaci=ai_sayaci+1, son_islem_zamani=%s WHERE username=%s", (now_str, st.session_state.user), commit=True)
                    log_ekle(st.session_state.user, "AI_COZUM", "Soru başarıyla çözüldü.")
                    st.markdown(res_ai.text)
                else: raise Exception("Boş yanıt")
            except Exception as e:
                log_ekle(st.session_state.user, "AI_HATA", str(e)[:100])
                st.error("AI şu an meşgul, kotandan düşülmedi. Tekrar dene!")

elif menu == "📊 Karargah":
    st.title(f"🐺 Hoş geldin, {st.session_state.user}!")
    st.info(f"YKS Yolculuğunda **{u_streak}.** günündesin! Bozkurtlar pes etmez.")

elif menu == "🛠️ Admin" and st.session_state.role == "admin":
    v_key = st.text_input("🔒 Admin Doğrulama Anahtarı", type="password", key="adm_v_key")
    if v_key == ADMIN_VERIFY_KEY:
        t1, t2 = st.tabs(["👥 Neferler", "📜 Kayıtlar"])
        with t1:
            search = st.text_input("Nefer Ara (Alfa Adı)", key="adm_search")
            u_data = vt_sorgu("SELECT username, xp, ai_sayaci, aktif FROM users WHERE username LIKE %s", (f"%{search}%",))
            st.table(pd.DataFrame(u_data, columns=["Alfa", "XP", "AI Kullanım", "Durum"]))
        with t2:
            if st.button("🗑️ Eski Kayıtları Temizle", key="clear_logs"):
                vt_sorgu("DELETE FROM system_logs WHERE id NOT IN (SELECT id FROM system_logs ORDER BY id DESC LIMIT 100)", commit=True)
                st.success("Son 100 kayıt hariç tüm loglar temizlendi.")
            logs = vt_sorgu("SELECT * FROM system_logs ORDER BY id DESC LIMIT 100")
            st.dataframe(pd.DataFrame(logs, columns=["ID", "Alfa", "İşlem", "Detay", "Tarih"]))
    else: st.info("Admin erişimi için anahtar giriniz.")
