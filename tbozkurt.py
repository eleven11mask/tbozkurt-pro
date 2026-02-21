import streamlit as st
import psycopg2 
from psycopg2 import extras, pool
import google.generativeai as genai
from datetime import datetime, timedelta
import time, bcrypt, html, secrets, string, logging
from PIL import Image

# --- 1. SİSTEM ÇEKİRDEĞİ ---
st.set_page_config(page_title="T-BOZKURT", layout="wide", page_icon="🐺")
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(message)s')

@st.cache_resource
def init_model():
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    return genai.GenerativeModel("gemini-1.5-flash-latest")

MODEL = init_model()

@st.cache_resource
def init_db_pool():
    return psycopg2.pool.SimpleConnectionPool(1, 20, st.secrets["DATABASE_URL"])

db_p = init_db_pool()

def vt(s, p=(), commit=False):
    c = db_p.getconn()
    try:
        cur = c.cursor(cursor_factory=extras.DictCursor)
        cur.execute(s, p)
        if commit:
            affected = cur.rowcount
            c.commit()
            cur.close()
            return affected > 0
        res = cur.fetchall()
        cur.close()
        return res
    except Exception as e:
        logging.error(f"VT HATASI: {e}")
        return False if commit else []
    finally: db_p.putconn(c)

def generate_lic_id():
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(15))

# --- 2. GİRİŞ VE KAYIT ---
if "user" not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🐺 T-BOZKURT KARARGAHI</h1>", unsafe_allow_html=True)
    mod = st.segmented_control("Erişim", ["Giriş Yap", "Kayıt Ol"], default="Giriş Yap")
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        if mod == "Giriş Yap":
            with st.form("l_form"):
                u = st.text_input("Alfa Adı")
                p = st.text_input("Şifre", type="password")
                if st.form_submit_button("SİSTEME GİR", use_container_width=True):
                    res = vt("SELECT password, role FROM users WHERE username=%s", (u,))
                    if res and bcrypt.checkpw(p.encode(), res[0][0].encode()):
                        st.session_state.user, st.session_state.role = u, res[0][1]
                        vt("INSERT INTO analytics (username, event) VALUES (%s, 'login')", (u,), commit=True)
                        st.rerun()
                    else: st.error("Erişim Reddedildi!")
        else:
            with st.form("k_form"):
                nu = st.text_input("Yeni Alfa Adı")
                np = st.text_input("Şifre Belirle", type="password")
                if st.form_submit_button("KATIL", use_container_width=True):
                    if len(nu) >= 3 and not vt("SELECT 1 FROM users WHERE username=%s", (nu,)):
                        hp = bcrypt.hashpw(np.encode(), bcrypt.gensalt()).decode()
                        dbitis = (datetime.now() + timedelta(days=7)).date()
                        vt("""INSERT INTO users (username, password, premium_expiry, streak, xp, ai_sayaci, son_giris, role) 
                           VALUES (%s, %s, %s, 1, 0, 0, %s, 'user')""", (nu, hp, dbitis, str(datetime.now().date())), commit=True)
                        st.success("🐺 Kayıt Tamam! 7 Günlük Deneme Başladı.")
    st.stop()

# --- 3. VERİ ÇEKME VE ZIRHLI KONTROL ---
res_u = vt("SELECT * FROM users WHERE username=%s", (st.session_state.user,))
if not res_u: st.session_state.clear(); st.stop()
u_data = res_u[0]
today = datetime.now().date()

# 🛡️ KeyError Koruması (SQL'deki yeni sütunlarla tam uyumlu)
p_exp = u_data.get('premium_expiry')
u_xp = u_data.get('xp', 0)
u_ai_count = u_data.get('ai_sayaci', 0)
u_streak = u_data.get('streak', 1)
s_oid = u_data.get('shopify_order_id')

# Günlük Reset Mantığı
if u_data.get('son_giris') != str(today):
    n_streak = u_streak + 1 if u_data.get('son_giris') == str(today - timedelta(days=1)) else 1
    vt("UPDATE users SET ai_sayaci=0, son_giris=%s, streak=%s WHERE username=%s", (str(today), n_streak, st.session_state.user), commit=True)
    st.rerun()

is_prem = (st.session_state.role == 'admin') or (p_exp and today <= p_exp)
u_seviye = (u_xp // 100) + 1

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title(f"🎖️ {st.session_state.user}")
    st.metric("🔥 Seri", f"{u_streak} Gün")
    st.metric("🏆 Seviye", u_seviye)
    if is_prem: st.success(f"⭐ PREMİUM ({p_exp})")
    else: st.warning("⚠️ ÜCRETSİZ")
    menu = st.radio("OPERASYON", ["🏰 Karargah", "📸 Soru Çöz", "🛡️ Kurt Kampı", "💳 Lisans Aktif Et", "🛠️ Admin"])
    if st.button("🚪 Ayrıl"): st.session_state.clear(); st.rerun()

# --- 5. MODÜLLER ---

if menu == "🏰 Karargah":
    st.header("📚 Eğitim Üssü")
    res_m = vt("SELECT DISTINCT sinif FROM mufredat")
    s_list = [r[0] for r in res_m] if res_m else ["9","10","11","12"]
    s_sinif = st.selectbox("Sınıf", s_list)
    res_d = vt("SELECT DISTINCT ders FROM mufredat WHERE sinif=%s", (s_sinif,))
    d_list = [r[0] for r in res_d] if res_d else ["Ders Yok"]
    s_ders = st.selectbox("Ders", d_list)
    res_k = vt("SELECT id, konu FROM mufredat WHERE sinif=%s AND ders=%s", (s_sinif, s_ders))
    k_dict = {k['konu']: k['id'] for k in res_k}
    s_konu = st.selectbox("Konu", list(k_dict.keys()) if k_dict else ["Yok"])
    
    if st.button("Eğitimi Başlat") and k_dict:
        r_detay = vt("SELECT icerik, podcast_url FROM mufredat WHERE id=%s", (k_dict[s_konu],))
        if r_detay:
            t1, t2 = st.tabs(["📖 Notlar", "🎧 Podcast"])
            with t1: st.markdown(r_detay[0]['icerik'])
            with t2: 
                if r_detay[0]['podcast_url']: st.audio(r_detay[0]['podcast_url'])
                else: st.info("Podcast mühimmatı yolda.")

elif menu == "📸 Soru Çöz":
    max_h = 3 if not is_prem else 50
    if u_ai_count >= max_h: st.error("Mühimmat Bitti!"); st.stop()
    img = st.camera_input("Soru Çek")
    if img:
        if img.size > 10 * 1024 * 1024: st.error("Dosya çok büyük!"); st.stop()
        with st.spinner("AI Çözüyor..."):
            try:
                res = MODEL.generate_content(["YKS öğretmenisin. Bu soruyu adım adım Türkçe çöz.", Image.open(img)])
                if res and hasattr(res, 'text'):
                    st.markdown(res.text)
                    vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10 WHERE username=%s", (st.session_state.user,), commit=True)
                    st.toast("🎯 +10 XP!"); time.sleep(1); st.rerun()
            except Exception as e: st.error("AI Meşgul, sonra tekrar dene.")

elif menu == "🛡️ Kurt Kampı":
    st.header("⚔️ Sohbet Odaları")
    oda = st.segmented_control("Hat", ["BETA", "ALFA", "PREMIUM"], default="BETA")
    if oda == "ALFA" and u_seviye < 5: st.error("5. Seviye olmalısın!"); st.stop()
    if oda == "PREMIUM" and not is_prem: st.error("Premium olmalısın!"); st.stop()
    
    with st.container(height=300):
        msgs = vt("SELECT username, message, tarih FROM chat_rooms WHERE room=%s ORDER BY id DESC LIMIT 20", (oda,))
        for m in reversed(msgs):
            st.write(f"**{m[0]}:** {html.escape(m[1])} <small>{m[2]}</small>", unsafe_allow_html=True)
    
    with st.form("c_f", clear_on_submit=True):
        m_txt = st.text_input("Mesaj...")
        if st.form_submit_button("GÖNDER") and m_txt.strip():
            vt("INSERT INTO chat_rooms (username, message, room, tarih) VALUES (%s,%s,%s,%s)", 
               (st.session_state.user, m_txt, oda, datetime.now().strftime("%H:%M")), commit=True)
            vt("UPDATE users SET xp=xp+1 WHERE username=%s", (st.session_state.user,), commit=True)
            st.rerun()

elif menu == "💳 Lisans Aktif Et":
    st.header("🎖️ Lisans Aktivasyonu")
    if s_oid and is_prem: st.info(f"Aktif Lisans: {s_oid}")
    else:
        with st.form("lic_f"):
            oid = st.text_input("Shopify Sipariş No")
            if st.form_submit_button("GÖNDER") and oid.strip():
                if vt("UPDATE users SET shopify_order_id=%s WHERE username=%s", (oid, st.session_state.user), commit=True):
                    st.success("Talep alındı.")

elif menu == "🛠️ Admin":
    if st.session_state.role != 'admin': st.error("Yetkisiz!"); st.stop()
    t1, t2, t3 = st.tabs(["🎖️ Onay", "📦 Müfredat", "📊 Analiz"])
    with t1:
        target = st.text_input("Kullanıcı")
        days = st.number_input("Gün", min_value=1, value=30)
        if st.button("Onayla"):
            exp = datetime.now().date() + timedelta(days=days)
            if vt("UPDATE users SET premium_expiry=%s, shopify_order_id=NULL WHERE username=%s", (exp, target), commit=True):
                st.success(f"{target} artık Premium!")
    with t2:
        with st.form("m_i"):
            s, d, k = st.text_input("Sınıf"), st.text_input("Ders"), st.text_input("Konu")
            i, p = st.text_area("İçerik"), st.text_input("Podcast URL")
            if st.form_submit_button("KAYDET"):
                vt("INSERT INTO mufredat (sinif, ders, konu, icerik, podcast_url) VALUES (%s,%s,%s,%s,%s)", (s,d,k,i,p), commit=True)
                st.success("Eklendi.")
    with t3:
        st.table(vt("SELECT * FROM analytics ORDER BY id DESC LIMIT 10"))
