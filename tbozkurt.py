import streamlit as st
import psycopg2 
from psycopg2 import extras, pool
import google.generativeai as genai
from datetime import datetime, timedelta
from PIL import Image
import time, bcrypt

# --- 1. SİSTEM YAPILANDIRMASI ---
st.set_page_config(page_title="T-BOZKURT", layout="wide", page_icon="🐺")

@st.cache_resource
def init_model():
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    return genai.GenerativeModel("gemini-1.5-flash-latest")

MODEL = init_model()

@st.cache_resource
def init_db_pool():
    # Supabase Free Plan dostu: 20 Connection
    return psycopg2.pool.SimpleConnectionPool(1, 20, st.secrets["DATABASE_URL"])

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
        print(f"🔴 KRİTİK HATA: {e}")
        return False if commit else []
    finally: db_p.putconn(c)

def log_event(u, event):
    vt("INSERT INTO analytics (username, event) VALUES (%s, %s)", (u, event), commit=True)

# --- 2. MOTORLAR & GÜVENLİK ---
def seviye_hesapla(xp): return (xp // 100) + 1
def kurt_sinifi(streak):
    if streak < 15: return "Yavru Kurt"
    elif streak < 60: return "Savaş Kurdu"
    else: return "Alfa Kurt"

def streak_ve_kota_guncelle(u):
    today = str(datetime.now().date())
    res = vt("SELECT son_giris FROM users WHERE username=%s", (u,))
    if res and res[0][0] != today:
        # Günlük Sayaçları Sıfırla
        vt("UPDATE users SET ai_sayaci=0, gunluk_chat_xp=0, son_giris=%s WHERE username=%s", (today, u), commit=True)
        # İstikrar (Streak) Mekanizması
        last_entry = res[0][0]
        if last_entry == str(datetime.now().date() - timedelta(days=1)):
            vt("UPDATE users SET streak=streak+1 WHERE username=%s", (u,), commit=True)
        else:
            vt("UPDATE users SET streak=1 WHERE username=%s", (u,), commit=True)

# --- 3. OTURUM YÖNETİMİ ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Karargah")
    t1, t2 = st.tabs(["🔑 Giriş Yap", "📝 Nefer Kaydı"])
    with t2:
        nu = st.text_input("Alfa Adı (3-20 Karakter)")
        np = st.text_input("Şifre", type="password")
        if st.button("KARARGAHA KATIL"):
            if 3 <= len(nu) <= 20:
                if not vt("SELECT 1 FROM users WHERE username=%s", (nu,)):
                    hp = bcrypt.hashpw(np.encode(), bcrypt.gensalt()).decode()
                    d_bitis = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                    vt("INSERT INTO users (username, password, deneme_bitis, deneme_kullanildi) VALUES (%s,%s,%s,TRUE)", (nu, hp, d_bitis), commit=True)
                    st.success("🐺 Kayıt Başarılı! 7 Günlük Deneme Başladı."); log_event(nu, "register")
                else: st.error("Bu isim karargahta mevcut.")
            else: st.error("İsim 3-20 karakter olmalı.")
    with t1:
        u = st.text_input("Alfa Adı", key="l_u")
        p = st.text_input("Şifre", type="password", key="l_p")
        if st.button("GİRİŞ YAP"):
            res = vt("SELECT password, role FROM users WHERE username=%s", (u,))
            if res and bcrypt.checkpw(p.encode(), res[0][0].encode()):
                st.session_state.user, st.session_state.role = u, res[0][1]
                streak_ve_kota_guncelle(u); log_event(u, "login"); st.rerun()
            else: st.error("Erişim Reddedildi.")
    st.stop()

# --- 4. VERİ KONTROLÜ & PLAN BELİRLEME ---
user_data = vt("SELECT streak, xp, ai_sayaci, deneme_bitis, son_ai_zamani, son_chat_zamani, gunluk_chat_xp FROM users WHERE username=%s", (st.session_state.user,))
if not user_data:
    st.session_state.clear(); st.stop()

u_streak, u_xp, u_ai, u_bitis, u_ai_zaman, u_chat_zaman, u_chat_xp = user_data[0]

# Deneme Süresi Kontrolü
try:
    bitis_tarih = datetime.strptime(u_bitis, "%Y-%m-%d").date()
    is_active = datetime.now().date() <= bitis_tarih
except:
    is_active = False

k_tipi = st.session_state.role if st.session_state.role == "admin" else ("premium" if is_active else "free")

# --- 5. NAVİGASYON & SİDEBAR ---
menu_items = ["📊 Karargah", "📸 Soru Çöz", "📚 Müfredat", "💬 Sohbet"]
if st.session_state.role == "admin": menu_items.append("🛠️ Admin Paneli")

with st.sidebar:
    st.title(f"🎖️ {st.session_state.user}")
    if k_tipi != "free": 
        st.success("⭐ PREMİUM AKTİF")
    elif u_bitis: # 3️⃣ Satış Psikolojisi: Deneme Bitiş Mesajı
        st.info("💡 Deneme süren doldu. Karargah mühimmatı için Premium'a geç!")
        
    st.caption(f"{kurt_sinifi(u_streak)} | Seviye {seviye_hesapla(u_xp)}")
    st.progress(min((u_xp % 100) / 100, 1.0), text=f"Seviye XP: {u_xp % 100}")
    menu = st.radio("OPERASYON SEÇ", menu_items)
    if st.button("🚪 Çıkış"): st.session_state.clear(); st.rerun()

# --- 6. MODÜLLER ---

if menu == "📊 Karargah":
    st.header("🐺 Karargah Genel Durumu")
    c1, c2 = st.columns(2)
    c1.metric("İstikrar", f"{u_streak} Gün")
    c2.metric("Toplam Tecrübe (XP)", u_xp)
    st.divider()
    st.subheader("🏆 En Güçlü 5 Bozkurt")
    for i, l in enumerate(vt("SELECT username, xp FROM users ORDER BY xp DESC LIMIT 5"), 1):
        st.write(f"**{i}. {l[0]}** — {l[1]} XP")

elif menu == "📸 Soru Çöz":
    max_hak = 3 if k_tipi == "free" else (999 if k_tipi == "admin" else 50)
    if u_ai >= max_hak:
        st.error(f"❌ Günlük {max_hak} soru limitin doldu!"); st.stop()
    
    img = st.camera_input("Soruyu Karargaha Gönder")
    if img:
        with st.spinner("AI Strateji Geliştiriyor..."):
            res = MODEL.generate_content(["YKS sorusu, adım adım Türkçe çöz.", Image.open(img)])
            if res and res.text:
                st.markdown(res.text)
                # 1️⃣ TIMESTAMP Güvenliği (Direkt Python objesi olarak gönderilir)
                now_ts = datetime.now() 
                vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10, son_ai_zamani=%s WHERE username=%s", (now_ts, st.session_state.user), commit=True)
                log_event(st.session_state.user, "ai_solve")

elif menu == "📚 Müfredat":
    st.subheader("📖 Müfredat Notları")
    ders_list = vt("SELECT DISTINCT ders FROM mufredat")
    sec_ders = st.selectbox("Ders Seç", [d[0] for d in ders_list] if ders_list else ["Veri Yok"])
    
    konu_list = vt("SELECT id, konu FROM mufredat WHERE ders=%s", (sec_ders,))
    konu_dict = {k[1]: k[0] for k in konu_list} if konu_list else {}
    
    sec_konu_ad = st.selectbox("Konu Seç", list(konu_dict.keys()) if konu_dict else ["Veri Yok"])
    if st.button("İçeriği Oku") and konu_dict:
        konu_id = konu_dict[sec_konu_ad]
        icerik = vt("SELECT icerik FROM mufredat WHERE id=%s", (konu_id,))
        # 2️⃣ Boş Müfredat İçerik Koruması
        if icerik and icerik[0][0]:
            st.markdown(icerik[0][0])
        else:
            st.warning("Bu konuya ait içerik henüz girilmemiş.")

elif menu == "🛠️ Admin Paneli":
    st.header("🔑 Karargah Yönetimi")
    t_a1, t_a2 = st.tabs(["📈 Analitik", "➕ Müfredat Ekle"])
    with t_a1:
        st.subheader("Son Hareketler")
        st.table(vt("SELECT username, event, tarih FROM analytics ORDER BY tarih DESC LIMIT 20"))
    with t_a2:
        d_ad = st.text_input("Ders"); k_ad = st.text_input("Konu"); icrk = st.text_area("İçerik (Markdown)")
        if st.button("Sisteme İşle"):
            vt("INSERT INTO mufredat (ders, konu, icerik, ekleyen) VALUES (%s,%s,%s,%s)", (d_ad, k_ad, icrk, st.session_state.user), commit=True)
            st.success("Müfredat Karargah'a eklendi.")

st.markdown("---")
st.caption(f"T-BOZKURT v1.2 | Karargah Yazılımı | Plan: {k_tipi.upper()}")
