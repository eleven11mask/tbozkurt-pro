import streamlit as st
import psycopg2 
from psycopg2 import extras, pool
import google.generativeai as genai
from datetime import datetime, timedelta
from PIL import Image
import time, bcrypt

# --- 1. SİSTEM YAPILANDIRMASI (HIZLANDIRILMIŞ) ---
st.set_page_config(page_title="T-BOZKURT", layout="wide", page_icon="🐺")

@st.cache_resource
def init_model():
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    return genai.GenerativeModel("gemini-1.5-flash-latest")

MODEL = init_model()

@st.cache_resource
def init_db_pool():
    # Bağlantı sayısını optimize ettik
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
        st.error(f"Sistem Hatası: {e}")
        return False if commit else []
    finally: db_p.putconn(c)

def log_event(u, event):
    vt("INSERT INTO analytics (username, event) VALUES (%s, %s)", (u, event), commit=True)

# --- 2. GİRİŞ & KAYIT EKRANI (DÜZELTİLMİŞ & HIZLI) ---
if "user" not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🐺 T-BOZKURT KARARGAHI</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_secim = st.segmented_control("İşlem Seçin", ["🔑 Giriş Yap", "📝 Nefer Kaydı"], default="🔑 Giriş Yap")
        
        if tab_secim == "🔑 Giriş Yap":
            with st.form("login_form", clear_on_submit=False):
                u = st.text_input("Alfa Adı")
                p = st.text_input("Şifre", type="password")
                submit = st.form_submit_button("KARARGAHA GİR", use_container_width=True)
                
                if submit:
                    res = vt("SELECT password, role FROM users WHERE username=%s", (u,))
                    if res and bcrypt.checkpw(p.encode(), res[0][0].encode()):
                        st.session_state.user, st.session_state.role = u, res[0][1]
                        # Hız için bu fonksiyonu login sonrası çalıştırıyoruz
                        today = str(datetime.now().date())
                        vt("UPDATE users SET son_giris=%s WHERE username=%s", (today, u), commit=True)
                        log_event(u, "login")
                        st.success("Giriş yapıldı! Aktarılıyorsunuz...")
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error("Alfa adı veya şifre hatalı!")

        else:
            with st.form("register_form", clear_on_submit=True):
                nu = st.text_input("Yeni Alfa Adı (3-20 Karakter)")
                np = st.text_input("Güçlü Bir Şifre", type="password")
                submit_reg = st.form_submit_button("KARARGAHA KATIL", use_container_width=True)
                
                if submit_reg:
                    if 3 <= len(nu) <= 20:
                        if not vt("SELECT 1 FROM users WHERE username=%s", (nu,)):
                            hp = bcrypt.hashpw(np.encode(), bcrypt.gensalt()).decode()
                            d_bitis = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                            vt("INSERT INTO users (username, password, deneme_bitis, deneme_kullanildi, streak, xp) VALUES (%s,%s,%s,TRUE,1,0)", 
                               (nu, hp, d_bitis), commit=True)
                            st.success("🐺 Kayıt Başarılı! Giriş sekmesine geçebilirsiniz.")
                            log_event(nu, "register")
                        else: st.error("Bu alfa adı zaten alınmış!")
                    else: st.error("İsim uzunluğu uygun değil!")
    st.stop()

# --- 3. ANA SİSTEM (YAVAŞLIK ÖNLENMİŞ) ---
@st.cache_data(ttl=300) # Liderlik tablosunu 5 dakika bellekte tutar, sistemi hızlandırır
def get_liderler():
    return vt("SELECT username, xp FROM users ORDER BY xp DESC LIMIT 5")

# Kullanıcı verilerini çek
user_data = vt("SELECT streak, xp, ai_sayaci, deneme_bitis, son_ai_zamani FROM users WHERE username=%s", (st.session_state.user,))
if not user_data: st.session_state.clear(); st.stop()

u_streak, u_xp, u_ai, u_bitis, u_ai_zaman = user_data[0]
bitis_tarih = datetime.strptime(u_bitis, "%Y-%m-%d").date()
is_active = datetime.now().date() <= bitis_tarih
k_tipi = st.session_state.role if st.session_state.role == "admin" else ("premium" if is_active else "free")

# --- 4. SIDEBAR & NAVİGASYON ---
menu_items = ["📊 Karargah", "📸 Soru Çöz", "📚 Müfredat", "💬 Sohbet"]
if st.session_state.role == "admin": menu_items.append("🛠️ Admin Paneli")

with st.sidebar:
    st.title(f"🎖️ {st.session_state.user}")
    if k_tipi != "free": st.success("⭐ PREMİUM")
    st.metric("Tecrübe", f"{u_xp} XP")
    menu = st.radio("OPERASYON", menu_items)
    if st.button("🚪 Çıkış"): st.session_state.clear(); st.rerun()

# --- 5. MODÜLLER (BOZULMADAN HIZLANDIRILDI) ---
if menu == "📊 Karargah":
    st.header("🐺 Karargah Genel Durumu")
    c1, c2 = st.columns(2)
    c1.metric("İstikrar", f"{u_streak} Gün")
    c2.metric("Sınıf", (u_xp // 100) + 1, "Seviye")
    
    st.subheader("🏆 En Güçlü Bozkurtlar")
    for i, l in enumerate(get_liderler(), 1):
        st.write(f"**{i}. {l[0]}** — {l[1]} XP")

elif menu == "📸 Soru Çöz":
    max_hak = 3 if k_tipi == "free" else (999 if k_tipi == "admin" else 50)
    if u_ai >= max_hak: st.error("Mühimmat doldu!"); st.stop()
    
    img = st.camera_input("Soru Gönder")
    if img:
        with st.spinner("AI Çözüyor..."):
            res = MODEL.generate_content(["YKS sorusu çöz.", Image.open(img)])
            if res:
                st.markdown(res.text)
                vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10, son_ai_zamani=%s WHERE username=%s", (datetime.now(), st.session_state.user), commit=True)

# ... (Müfredat, Sohbet ve Admin modülleri v1.2'deki gibi devam eder)
