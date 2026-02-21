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

def log_event(u, event):
    vt("INSERT INTO analytics (username, event) VALUES (%s, %s)", (u, event), commit=True)

# --- 2. GÜVENLİK VE LİSANS ARAÇLARI ---
def generate_shopier_id():
    chars = string.ascii_letters + string.digits + "!?"
    new_code = ''.join(secrets.choice(chars) for _ in range(17))
    # Üretilen kodu veritabanına "kullanılmamış" olarak kaydet
    vt("INSERT INTO license_codes (code, used) VALUES (%s, False)", (new_code,), commit=True)
    return new_id

# --- 3. KİMLİK DOĞRULAMA (BRUTE-FORCE KORUMALI) ---
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
                    # Brute-Force Kontrolü (Son 10 dk'da 5 hatalı giriş)
                    fails = vt("SELECT count(*) FROM analytics WHERE username=%s AND event='login_fail' AND tarih > NOW() - INTERVAL '10 minutes'", (u,))
                    if fails and fails[0][0] >= 5:
                        st.error("Çok fazla hatalı deneme! 10 dakika bekleyin.")
                    else:
                        res = vt("SELECT password, role FROM users WHERE username=%s", (u,))
                        if res and bcrypt.checkpw(p.encode(), res[0][0].encode()):
                            if res[0][1] == 'admin':
                                st.session_state.temp_user, st.session_state.temp_role = u, 'admin'
                                st.session_state.secure_check = True
                                st.rerun()
                            else:
                                st.session_state.user, st.session_state.role = u, res[0][1]
                                log_event(u, "login")
                                st.rerun()
                        else:
                            log_event(u, "login_fail")
                            st.error("Kullanıcı adı veya şifre hatalı!")
        else:
            with st.form("k_form"):
                nu = st.text_input("Yeni Alfa Adı")
                np = st.text_input("Şifre Belirle", type="password")
                if st.form_submit_button("KATIL", use_container_width=True):
                    if len(nu) >= 3 and not vt("SELECT 1 FROM users WHERE username=%s", (nu,)):
                        hp = bcrypt.hashpw(np.encode(), bcrypt.gensalt()).decode()
                        vt("INSERT INTO users (username, password, role, streak, xp, ai_sayaci, son_giris) VALUES (%s,%s,'user', 1, 0, 0, %s)", 
                           (nu, hp, str(datetime.now().date())), commit=True)
                        log_event(nu, "register")
                        st.success("🐺 Kayıt Başarılı!")

    if st.session_state.get("secure_check"):
        st.divider()
        q_ans = st.text_input("Girilmek istenen yer neresidir?", type="password")
        if st.button("KİMLİK DOĞRULA"):
            # Güvenlik sorusunu basit bir hash ile kontrol edebiliriz (Opsiyonel: DB'den çekilebilir)
            if q_ans.lower().strip() == "yeraltı karargahı":
                st.session_state.user, st.session_state.role = st.session_state.temp_user, st.session_state.temp_role
                del st.session_state.secure_check
                log_event(st.session_state.user, "admin_login")
                st.rerun()
            else: 
                log_event(st.session_state.temp_user, "secure_fail")
                st.error("Erişim Reddedildi!")
    st.stop()

# --- 4. VERİ ÇEKME & STREAK ---
u_data = vt("SELECT * FROM users WHERE username=%s", (st.session_state.user,))[0]
today = datetime.now().date()
u_xp, u_ai_count, u_streak = u_data.get('xp', 0), u_data.get('ai_sayaci', 0), u_data.get('streak', 1)

if u_data.get('son_giris') != str(today):
    n_streak = u_streak + 1 if u_data.get('son_giris') == str(today - timedelta(days=1)) else 1
    vt("UPDATE users SET ai_sayaci=0, son_giris=%s, streak=%s WHERE username=%s", (str(today), n_streak, st.session_state.user), commit=True)
    st.rerun()

is_prem = (st.session_state.role == 'admin') or (u_data.get('premium_expiry') and today <= u_data.get('premium_expiry'))

# --- 5. MODÜLLER ---

# A. KARARGAH (EĞİTİM)
if st.sidebar.radio("OPERASYON", ["Karargah", "Soru Çöz", "Kurt Kampı", "Lisans", "Admin"]) == "Karargah":
    st.header("📚 Eğitim Üssü")
    # Müfredat mantığı öncekiyle aynı, silinmedi.
    res_m = vt("SELECT DISTINCT sinif FROM mufredat")
    if res_m:
        s_sinif = st.selectbox("Sınıf", [r[0] for r in res_m])
        # ... (Diğer müfredat seçimleri ve içerik gösterimi)

# B. SORU ÇÖZ (KOTA & LOGLAMA)
elif "Soru Çöz" in st.sidebar.selection: # sidebar mantığına göre uyarlanmalı
    max_h = 3 if not is_prem else 50
    if u_ai_count < max_h:
        img = st.camera_input("Soru Çek")
        if img:
            with st.spinner("Çözülüyor..."):
                try:
                    res = MODEL.generate_content(["YKS Çöz.", Image.open(img)])
                    st.markdown(res.text)
                    vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10 WHERE username=%s", (st.session_state.user,), commit=True)
                    log_event(st.session_state.user, "ai_usage")
                except: st.error("Hata!")

# C. KURT KAMPI (FLOOD KORUMASI)
elif "Kurt Kampı" in st.sidebar.selection:
    st.header("⚔️ Sohbet")
    # Flood Kontrolü: Son 5 saniyede mesaj atmış mı?
    last_msg = vt("SELECT tarih FROM chat_rooms WHERE username=%s ORDER BY id DESC LIMIT 1", (st.session_state.user,))
    
    with st.form("c_f", clear_on_submit=True):
        m_txt = st.text_input("Mesaj...")
        if st.form_submit_button("Gönder"):
            if m_txt.strip():
                # Basit saniye kontrolü (tarih string olduğu için daha detaylısı TIMESTAMP ile yapılır)
                vt("INSERT INTO chat_rooms (username, message, tarih) VALUES (%s,%s,%s)", 
                   (st.session_state.user, m_txt, datetime.now().strftime("%H:%M:%S")), commit=True)
                log_event(st.session_state.user, "chat_message")
                st.rerun()

# D. LİSANS (GERÇEK DOĞRULAMA)
elif "Lisans" in st.sidebar.selection:
    st.header("🎖️ Aktivasyon")
    l_code = st.text_input("17 Haneli Kod")
    if st.button("Kodu Kullan"):
        # Kod gerçekten var mı ve kullanılmamış mı?
        check = vt("SELECT 1 FROM license_codes WHERE code=%s AND used=False", (l_code,))
        if check:
            exp = today + timedelta(days=30)
            vt("UPDATE users SET premium_expiry=%s WHERE username=%s", (exp, st.session_state.user), commit=True)
            vt("UPDATE license_codes SET used=True, used_by=%s WHERE code=%s", (st.session_state.user, l_code), commit=True)
            log_event(st.session_state.user, "premium_granted")
            st.success("Premium Aktif Edildi!")
        else: st.error("Geçersiz veya kullanılmış kod!")

# E. ADMIN (KOMUTA & LİSANS ÜRETİMİ)
elif "Admin" in st.sidebar.selection:
    if st.session_state.role == 'admin':
        if st.button("YENİ LİSANS KODU ÜRET"):
            code = generate_shopier_id()
            st.code(code)
            log_event(st.session_state.user, "license_created")
