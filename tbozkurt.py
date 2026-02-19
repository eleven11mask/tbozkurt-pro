import streamlit as st
import psycopg2 
from psycopg2 import extras, pool
import google.generativeai as genai
from datetime import datetime, timedelta
from PIL import Image
import time, bcrypt, html

# --- 1. ÇEKİRDEK YAPILANDIRMA ---
st.set_page_config(page_title="T-BOZKURT", layout="wide", page_icon="🐺")

@st.cache_resource
def init_model():
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    return genai.GenerativeModel("gemini-1.5-flash-latest")

MODEL = init_model()

@st.cache_resource
def init_db_pool():
    return psycopg2.pool.SimpleConnectionPool(1, 15, st.secrets["DATABASE_URL"])

db_p = init_db_pool()

def vt(s, p=(), commit=False):
    c = db_p.getconn()
    try:
        cur = c.cursor(cursor_factory=extras.DictCursor)
        cur.execute(s, p)
        res = True if commit else cur.fetchall()
        if commit: c.commit()
        cur.close()
        return res
    except Exception as e:
        print(f"VT Hatası: {e}")
        return False if commit else []
    finally: db_p.putconn(c)

def log_event(u, ev):
    vt("INSERT INTO analytics (username, event) VALUES (%s, %s)", (u, ev), commit=True)

# --- 2. KİMLİK DOĞRULAMA ---
if "user" not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🐺 T-BOZKURT KARARGAHI</h1>", unsafe_allow_html=True)
    mod = st.segmented_control("Harekât", ["Giriş Yap", "Kayıt Ol"], default="Giriş Yap")
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        if mod == "Giriş Yap":
            with st.form("l_form"):
                u = st.text_input("Alfa Adı")
                p = st.text_input("Şifre", type="password")
                if st.form_submit_button("BAĞLAN", use_container_width=True):
                    res = vt("SELECT password, role FROM users WHERE username=%s", (u,))
                    if res and bcrypt.checkpw(p.encode(), res[0][0].encode()):
                        st.session_state.user, st.session_state.role = u, res[0][1]
                        log_event(u, "login"); st.rerun()
                    else: st.error("Hatalı Kimlik!")
        else:
            with st.form("k_form"):
                nu = st.text_input("Yeni Alfa Adı")
                np = st.text_input("Şifre Belirle", type="password")
                if st.form_submit_button("KATIL", use_container_width=True):
                    if len(nu) >= 3 and not vt("SELECT 1 FROM users WHERE username=%s", (nu,)):
                        hp = bcrypt.hashpw(np.encode(), bcrypt.gensalt()).decode()
                        dbitis = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                        vt("""INSERT INTO users (username, password, deneme_bitis, deneme_kullanildi, streak, xp, ai_sayaci, son_giris) 
                           VALUES (%s, %s, %s, TRUE, 1, 0, 0, %s)""", (nu, hp, dbitis, str(datetime.now().date())), commit=True)
                        log_event(nu, "register"); st.success("Hoş geldin nefer!")
                    else: st.error("Geçersiz ad veya kullanımda.")
    st.stop()

# --- 3. VERİ KONTROLÜ & RESET ---
res_u = vt("SELECT * FROM users WHERE username=%s", (st.session_state.user,))
if not res_u: st.session_state.clear(); st.stop()

u_data = res_u[0]
today = str(datetime.now().date())

if u_data['son_giris'] != today:
    n_streak = u_data['streak'] + 1 if u_data['son_giris'] == str(datetime.now().date() - timedelta(days=1)) else 1
    vt("UPDATE users SET ai_sayaci=0, son_giris=%s, streak=%s WHERE username=%s", (today, n_streak, st.session_state.user), commit=True)
    st.rerun()

try:
    is_prem = st.session_state.role == 'admin' or (u_data['deneme_bitis'] and datetime.now().date() <= datetime.strptime(u_data['deneme_bitis'], "%Y-%m-%d").date())
except: is_prem = False

k_tipi = st.session_state.role if st.session_state.role == 'admin' else ('premium' if is_prem else 'free')
u_seviye = (u_data['xp'] // 100) + 1

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title(f"🎖️ {st.session_state.user}")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Seri", f"{u_data['streak']} Gün")
    c2.metric("🏆 Seviye", u_seviye)
    st.progress(min((u_data['xp'] % 100) / 100, 1.0), text=f"İlerleme: {u_data['xp'] % 100}/100")
    
    if u_data['streak'] >= 3: st.success("🎖️ İstikrarlı Kurt")
    if k_tipi != 'free': st.success("⭐ PREMİUM: Hızlı Hat")
    else: st.info("💡 Premium ile limitleri kaldır!")

    menus = ["🏰 Karargah", "📸 Soru Çöz"]
    if st.session_state.role == "admin": menus.append("🛠️ Admin")
    menu = st.radio("OPERASYON", menus)
    if st.button("🚪 Ayrıl"): st.session_state.clear(); st.rerun()

# --- 5. MODÜLLER ---
if menu == "🏰 Karargah":
    st.header("🛡️ Harekat Merkezi")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🟢 BETA (1-5)", use_container_width=True): st.session_state.oda = "BETA"
    with col2:
        if u_seviye > 5 or st.session_state.role == 'admin':
            if st.button("🔴 ALFA (5+)", use_container_width=True): st.session_state.oda = "ALFA"
        else: st.info("🔒 Seviye 5+")
    with col3:
        if k_tipi != 'free':
            if st.button("💎 ÖZEL SUNUCU", use_container_width=True): st.session_state.oda = "PREMIUM"
        else: st.warning("🔒 Lisans Gerekli")

    if "oda" in st.session_state:
        st.markdown(f"**📡 {st.session_state.oda} Hattı**")
        r_chat = vt("SELECT son_chat_zamani FROM users WHERE username=%s", (st.session_state.user,))
        check_chat = r_chat[0][0] if r_chat else None
        
        with st.container(height=250):
            msgs = vt("SELECT username, message, tarih FROM chat_rooms WHERE room=%s ORDER BY id DESC LIMIT 15", (st.session_state.oda,))
            for m in reversed(msgs):
                st.write(f"**{m[0]}:** {html.escape(m[1])} <small style='color:gray;'>{m[2]}</small>", unsafe_allow_html=True)
        
        with st.form("chat_form", clear_on_submit=True):
            msg = st.text_input("Mesaj...")
            if st.form_submit_button("GÖNDER"):
                if check_chat and (datetime.now() - check_chat).total_seconds() < 3:
                    st.toast("⚠️ Bekleyiniz (3sn)")
                elif msg.strip():
                    vt("INSERT INTO chat_rooms (username, message, room, tarih) VALUES (%s,%s,%s,%s)", 
                       (st.session_state.user, msg, st.session_state.oda, datetime.now().strftime("%H:%M")), commit=True)
                    vt("UPDATE users SET son_chat_zamani=%s, xp=xp+1 WHERE username=%s", (datetime.now(), st.session_state.user), commit=True)
                    st.toast("💬 +1 XP"); time.sleep(0.3); st.rerun()

    st.divider()
    st.subheader("📚 Eğitim Cephaneliği")
    d_list = vt("SELECT DISTINCT ders FROM mufredat")
    sec_d = st.selectbox("Ders", [d[0] for d in d_list] if d_list else ["Yok"])
    k_list = vt("SELECT id, konu FROM mufredat WHERE ders=%s", (sec_d,))
    k_dict = {k['konu']: k['id'] for k in k_list}
    sec_k = st.selectbox("Konu", list(k_dict.keys()) if k_dict else ["Yok"])
    
    if st.button("Eğitimi Başlat") and k_dict:
        # 1️⃣ Production Korumalı Veri Çekme
        r_detay = vt("SELECT icerik, podcast_url FROM mufredat WHERE id=%s", (k_dict[sec_k],))
        if r_detay:
            detay = r_detay[0]
            t1, t2 = st.tabs(["📖 Notlar", "🎧 Podcast"])
            with t1: st.markdown(detay['icerik'])
            with t2:
                if detay['podcast_url']: st.audio(detay['podcast_url'])
                else: st.info("Podcast yakında.")
        else: st.error("Hata: İçerik Karargahta bulunamadı!")

elif menu == "📸 Soru Çöz":
    r_ai = vt("SELECT ai_sayaci FROM users WHERE username=%s", (st.session_state.user,))
    curr_ai = r_ai[0][0] if r_ai else 999
    max_h = 3 if k_tipi == 'free' else (999 if k_tipi == 'admin' else 50)
    
    if curr_ai >= max_h: st.error(f"❌ Limit Doldu ({max_h}/{max_h})"); st.stop()
    
    img = st.camera_input("Soru Çek")
    if img:
        with st.spinner("AI Analiz Ediyor..."):
            res = MODEL.generate_content(["Sen bir YKS öğretmenisin. Soruyu Türkçe ve adım adım çöz.", Image.open(img)])
            if res:
                st.markdown(res.text)
                vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10 WHERE username=%s", (st.session_state.user,), commit=True)
                log_event(st.session_state.user, "ai_solve")
                st.toast("🎯 +10 XP!"); time.sleep(1); st.rerun()

elif menu == "🛠️ Admin":
    st.title("🔑 Analiz")
    st.table(vt("SELECT username, event, tarih FROM analytics ORDER BY id DESC LIMIT 15"))
