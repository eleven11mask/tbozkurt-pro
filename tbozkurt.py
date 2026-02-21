import streamlit as st
import psycopg2 
from psycopg2 import extras, pool
import google.generativeai as genai
from datetime import datetime, timedelta
import time, bcrypt, html, secrets, string, logging
from PIL import Image

# --- 1. SİSTEM ÇEKİRDEĞİ & LOGLAMA ---
st.set_page_config(page_title="T-BOZKURT", layout="wide", page_icon="🐺")

# Hataların sessizce yok olmaması için arka plan kayıt sistemi
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(message)s')

@st.cache_resource
def init_model():
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    return genai.GenerativeModel("gemini-1.5-flash-latest")

MODEL = init_model()

@st.cache_resource
def init_db_pool():
    # 20 kullanıcıya kadar eş zamanlı bağlantı havuzu
    return psycopg2.pool.SimpleConnectionPool(1, 20, st.secrets["DATABASE_URL"])

db_p = init_db_pool()

def vt(s, p=(), commit=False):
    """
    Zırhlı Veritabanı Motoru. 
    Rowcount kontrollü (işlem başarısını teyit eder) ve Loglamalıdır.
    """
    c = db_p.getconn()
    try:
        cur = c.cursor(cursor_factory=extras.DictCursor)
        cur.execute(s, p)
        if commit:
            affected = cur.rowcount
            c.commit()
            cur.close()
            return affected > 0 # İşlem gerçekten bir satırı etkiledi mi?
        res = cur.fetchall()
        cur.close()
        return res
    except Exception as e:
        logging.error(f"VT KRİTİK HATA: {e}")
        return False if commit else []
    finally: db_p.putconn(c)

def generate_lic_id():
    """15 haneli, tahmin edilemez kripto lisans ID üretici"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(15))

# --- 2. KİMLİK DOĞRULAMA (GİRİŞ/KAYIT) ---
if "user" not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🐺 T-BOZKURT KARARGAHI</h1>", unsafe_allow_html=True)
    mod = st.segmented_control("Erişim Hattı", ["Giriş Yap", "Kayıt Ol"], default="Giriş Yap")
    
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
                        # Kayıt anında 7 günlük deneme tanımlanır
                        vt("""INSERT INTO users (username, password, premium_expiry, shopify_order_id, streak, xp, ai_sayaci, son_giris) 
                           VALUES (%s, %s, %s, NULL, 1, 0, 0, %s)""", (nu, hp, dbitis, str(datetime.now().date())), commit=True)
                        st.success("🐺 Kayıt Başarılı! 7 Günlük Deneme Aktif.")
    st.stop()

# --- 3. PREMİUM DURUMU & GÜNLÜK RESET ---
res_u = vt("SELECT * FROM users WHERE username=%s", (st.session_state.user,))
if not res_u: st.session_state.clear(); st.stop()
u_data = res_u[0]
today = datetime.now().date()

# Günlük AI Sayacı ve Streak Kontrolü
if u_data['son_giris'] != str(today):
    n_streak = u_data['streak'] + 1 if u_data['son_giris'] == str(today - timedelta(days=1)) else 1
    vt("UPDATE users SET ai_sayaci=0, son_giris=%s, streak=%s WHERE username=%s", (str(today), n_streak, st.session_state.user), commit=True)
    st.rerun()

# Premium Yetki Kontrolü (Server-side)
is_prem = (st.session_state.role == 'admin') or (u_data['premium_expiry'] and today <= u_data['premium_expiry'])
k_tipi = st.session_state.role if st.session_state.role == 'admin' else ('premium' if is_prem else 'free')
u_seviye = (u_data['xp'] // 100) + 1

# --- 4. SIDEBAR (KOMUTA MERKEZİ) ---
with st.sidebar:
    st.title(f"🎖️ {st.session_state.user}")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Seri", f"{u_data['streak']} Gün")
    c2.metric("🏆 Seviye", u_seviye)
    st.progress(min((u_data['xp'] % 100) / 100, 1.0))
    
    if is_prem: st.success(f"⭐ PREMİUM ({u_data['premium_expiry']})")
    else: st.warning("⚠️ ÜCRETSİZ HESAP")

    menu = st.radio("OPERASYON", ["🏰 Karargah", "📸 Soru Çöz", "🛡️ Kurt Kampı", "💳 Lisans Aktif Et", "🛠️ Admin"])
    if st.button("🚪 Ayrıl"): st.session_state.clear(); st.rerun()

# --- 5. OPERASYONEL MODÜLLER ---

# --- A. KARARGAH (EĞİTİM & MÜFREDAT) ---
if menu == "🏰 Karargah":
    st.header("📚 Eğitim Üssü")
    res_m = vt("SELECT DISTINCT sinif FROM mufredat")
    s_list = [r[0] for r in res_m] if res_m else ["9","10","11","12"]
    
    col1, col2 = st.columns(2)
    with col1: s_sinif = st.selectbox("Sınıf", s_list)
    with col2:
        res_d = vt("SELECT DISTINCT ders FROM mufredat WHERE sinif=%s", (s_sinif,))
        d_list = [r[0] for r in res_d] if res_d else ["Ders Yok"]
        s_ders = st.selectbox("Ders", d_list)
    
    res_k = vt("SELECT id, konu FROM mufredat WHERE sinif=%s AND ders=%s", (s_sinif, s_ders))
    k_dict = {k['konu']: k['id'] for k in res_k}
    s_konu = st.selectbox("Konu", list(k_dict.keys()) if k_dict else ["Yok"])
    
    if st.button("Eğitimi Başlat") and k_dict:
        r_detay = vt("SELECT icerik, podcast_url FROM mufredat WHERE id=%s", (k_dict[s_konu],))
        if r_detay:
            detay = r_detay[0]
            st.divider()
            t1, t2 = st.tabs(["📖 Ders Notları", "🎧 Podcast"])
            with t1: st.markdown(detay['icerik'])
            with t2:
                if detay['podcast_url']: st.audio(detay['podcast_url'])
                else: st.info("Bu konu için podcast mühimmatı yolda.")

# --- B. LİSANS AKTİF ET (SHOPIFY ENTEGRASYON) ---
elif menu == "💳 Lisans Aktif Et":
    st.header("🎖️ Premium Aktivasyon")
    
    allow_req = False
    if u_data['shopify_order_id'] and is_prem:
        st.info(f"Mevcut Lisansınız Aktif: {u_data['shopify_order_id']}.")
    elif u_data['shopify_order_id'] and not is_prem:
        st.warning("Eski lisans süreniz dolmuş. Yeni bir sipariş numarası girebilirsiniz.")
        allow_req = True
    else:
        allow_req = True

    if allow_req:
        with st.form("lic_f"):
            oid = st.text_input("Shopify Sipariş No (Örn: #1024)")
            if st.form_submit_button("LİSANS TALEBİ GÖNDER"):
                if oid.strip():
                    if vt("UPDATE users SET shopify_order_id=%s WHERE username=%s", (oid, st.session_state.user), commit=True):
                        vt("INSERT INTO analytics (username, event) VALUES (%s, %s)", (st.session_state.user, f"lic_req: {oid}"), commit=True)
                        st.success("Talebiniz Admin onayına iletildi."); time.sleep(1); st.rerun()
                else: st.error("Sipariş No boş bırakılamaz!")

# --- C. KURT KAMPI (YETKİ KONTROLLÜ CHAT) ---
elif menu == "🛡️ Kurt Kampı":
    st.header("⚔️ Kurt Kampı Sohbet")
    oda = st.segmented_control("Hat Seç", ["BETA", "ALFA", "PREMIUM"], default="BETA")
    
    # Oda Yetki Kontrolleri
    if oda == "ALFA" and u_seviye < 5 and st.session_state.role != "admin":
        st.error("🔴 ALFA Hattı için en az 5. Seviye olmalısın!"); st.stop()
    if oda == "PREMIUM" and not is_prem:
        st.error("💎 ÖZEL HAT sadece Premium neferler içindir!"); st.stop()

    with st.container(height=300):
        msgs = vt("SELECT username, message, tarih FROM chat_rooms WHERE room=%s ORDER BY id DESC LIMIT 20", (oda,))
        for m in reversed(msgs):
            st.write(f"**{m[0]}:** {html.escape(m[1])} <small style='color:gray;'>{m[2]}</small>", unsafe_allow_html=True)
    
    with st.form("c_f", clear_on_submit=True):
        m_txt = st.text_input("Mesaj...")
        if st.form_submit_button("GÖNDER"):
            if m_txt.strip():
                vt("INSERT INTO chat_rooms (username, message, room, tarih) VALUES (%s,%s,%s,%s)", 
                   (st.session_state.user, m_txt, oda, datetime.now().strftime("%H:%M")), commit=True)
                vt("UPDATE users SET xp=xp+1 WHERE username=%s", (st.session_state.user,), commit=True)
                st.rerun()

# --- D. SORU ÇÖZ (ZIRHLI AI MOTORU) ---
elif menu == "📸 Soru Çöz":
    r_ai = vt("SELECT ai_sayaci FROM users WHERE username=%s", (st.session_state.user,))
    curr_ai = r_ai[0][0] if r_ai else 999
    max_h = 3 if k_tipi == 'free' else (999 if k_tipi == 'admin' else 50)
    
    if curr_ai >= max_h: st.error("Günlük Mühimmat Bitti!"); st.stop()
    
    img = st.camera_input("Soru Çek")
    if img:
        # DoS Koruması: Max 10MB
        if img.size > 10 * 1024 * 1024:
            st.error("Görsel çok büyük! (Maksimum 10MB)"); st.stop()

        with st.spinner("AI Karargahtan Bilgi Çekiyor..."):
            try:
                res = MODEL.generate_content(["Sen bir YKS öğretmenisin. Bu soruyu Türkçe, adım adım ve net şekilde çöz.", Image.open(img)])
                if res and hasattr(res, "text") and res.text:
                    st.markdown(res.text)
                    # Sadece başarılı çözümde kota düşer ve XP artar
                    vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10 WHERE username=%s", (st.session_state.user,), commit=True)
                    st.toast("🎯 +10 XP Kazanıldı!"); time.sleep(1); st.rerun()
                else: st.error("AI şu an yanıt veremiyor.")
            except Exception as e:
                logging.error(f"AI API HATASI: {e}")
                st.error("AI servisi şu an meşgul. Lütfen 1 dakika sonra tekrar deneyin.")

# --- E. ADMIN PANELI (STRATEJİK YÖNETİM) ---
elif menu == "🛠️ Admin":
    if st.session_state.role != "admin": st.error("Yetkisiz Erişim!"); st.stop()
    t1, t2, t3, t4 = st.tabs(["🎖️ Lisans Onay", "🔑 ID Üret", "📦 Müfredat Girişi", "📊 Analiz"])
    
    with t1:
        st.subheader("Kullanıcı Yetkilendirme")
        with st.form("p_f"):
            target = st.text_input("Hedef Kullanıcı Adı")
            days = st.number_input("Verilecek Gün Sayısı", min_value=1, value=30)
            if st.form_submit_button("PREMIUM YETKİSİ VER / ONAYLA"):
                if vt("SELECT 1 FROM users WHERE username=%s", (target,)):
                    exp = datetime.now().date() + timedelta(days=days)
                    if vt("UPDATE users SET premium_expiry=%s, shopify_order_id=NULL WHERE username=%s", (exp, target), commit=True):
                        st.success(f"{target} kullanıcısı {exp} tarihine kadar Premium yapıldı.")
                else: st.error("Böyle bir nefer bulunamadı!")

    with t2:
        st.subheader("Kripto Lisans ID Üretici")
        if st.button("15 HANELİ GÜVENLİ ID ÜRET"):
            st.code(generate_lic_id(), language="text")

    with t3:
        st.subheader("Manuel Müfredat Girişi")
        with st.form("m_f"):
            s, d, k = st.text_input("Sınıf (9-12)"), st.text_input("Ders Adı"), st.text_input("Konu Adı")
            i = st.text_area("Konu Anlatımı (Markdown Destekli)")
            p = st.text_input("Podcast URL")
            if st.form_submit_button("KARARGAHA KAYDET"):
                if vt("INSERT INTO mufredat (sinif, ders, konu, icerik, podcast_url) VALUES (%s,%s,%s,%s,%s)", (s,d,k,i,p), commit=True):
                    st.success("Mühimmat sisteme başarıyla yüklendi!")

    with t4:
        st.subheader("Sistem Hareket Logları")
        st.table(vt("SELECT id, username, event, tarih FROM analytics ORDER BY id DESC LIMIT 20"))
