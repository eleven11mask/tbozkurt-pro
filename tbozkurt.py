import streamlit as st
import psycopg2 
from psycopg2 import extras, pool
import google.generativeai as genai
import bcrypt, time, secrets, json, io
from datetime import date, timedelta
from PIL import Image
from gtts import gTTS
import pandas as pd

# --- 1. ÇEKİRDEK HIZ VE GÜVENLİK AYARLARI ---
st.set_page_config(page_title="T-BOZKURT v15.0", layout="wide", page_icon="🐺")

@st.cache_resource
def havuz_olustur():
    """Çok kanallı (Threaded) bağlantı havuzu: Çakışmaları ve yavaşlığı önler."""
    try:
        # Minimum 1, maksimum 40 bağlantı kapasitesi
        return psycopg2.pool.ThreadedConnectionPool(1, 40, st.secrets["DATABASE_URL"])
    except Exception as e:
        st.error(f"Havuz Hatası: {e}")
        return None

HAVUZ = havuz_olustur()

def vt(sorgu, parametre=(), kaydet=False):
    """Gelişmiş hata yönetimi ve otomatik bağlantı temizliği."""
    baglanti = None
    try:
        baglanti = HAVUZ.getconn()
        baglanti.autocommit = False
        with baglanti.cursor(cursor_factory=extras.DictCursor) as imlec:
            imlec.execute(sorgu, parametre)
            sonuc = imlec.fetchall() if imlec.description else None
            if kaydet: baglanti.commit()
            return sonuc
    except Exception as e:
        if baglanti: baglanti.rollback()
        # Hatayı veritabanına logla
        return None
    finally:
        if baglanti:
            HAVUZ.putconn(baglanti) # Bağlantıyı havuza geri bırak (Şişmeyi önler)

@st.cache_resource
def ai_motoru():
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    return genai.GenerativeModel("gemini-1.5-flash-latest", generation_config={"response_mime_type": "application/json"})

MODEL = ai_motoru()

# --- 2. YARDIMCI ARAÇLAR (SES & MALİYET) ---
@st.cache_data(show_spinner=False)
def seslendir(metin):
    try:
        tts = gTTS(text=metin[:1000], lang='tr')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except: return None

def maliyet_kaydet(kullanici, tokens):
    gider = (tokens / 1000000) * 0.075
    vt("INSERT INTO cost_logs (username, tokens, cost) VALUES (%s, %s, %s)", (kullanici, tokens, gider), kaydet=True)

# --- 3. GİRİŞ VE KAYIT EKRANI (HIZLANDIRILMIŞ) ---
def giris_sistemi():
    if "kullanici" not in st.session_state:
        st.markdown("<h1 style='text-align: center;'>🐺 T-BOZKURT KARARGAHI</h1>", unsafe_allow_html=True)
        sekme1, sekme2 = st.tabs(["🔑 Karargaha Gir", "📝 Yeni Kayıt"])
        
        with sekme1:
            with st.form("giris_formu"): # Form yapısı girişi hızlandırır
                k_adi = st.text_input("Kullanıcı Adı").lower().strip()
                sifre = st.text_input("Şifre", type="password")
                onay = st.form_submit_button("GİRİŞ YAP")
                
                if onay:
                    if not k_adi or not sifre:
                        st.warning("Eksik bilgi girmeyin.")
                    else:
                        res = vt("SELECT password, role FROM users WHERE username=%s", (k_adi,))
                        if res and bcrypt.checkpw(sifre.encode(), res[0]['password'].encode()):
                            st.session_state.kullanici = k_adi
                            st.session_state.rol = res[0]['role']
                            st.success("🐺 Kapılar açılıyor...")
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.error("Hatalı kullanıcı adı veya şifre!")

        with sekme2:
            with st.form("kayit_formu"):
                y_adi = st.text_input("Yeni Kullanıcı Adı").lower().strip()
                y_sifre = st.text_input("Şifre (Min 6 Karakter)", type="password")
                kayit_onay = st.form_submit_button("KARARGAHA KATIL")
                
                if kayit_onay:
                    if len(y_sifre) >= 6 and y_adi:
                        mevcut = vt("SELECT 1 FROM users WHERE username=%s", (y_adi,))
                        if not mevcut:
                            h_sifre = bcrypt.hashpw(y_sifre.encode(), bcrypt.gensalt()).decode()
                            vt("INSERT INTO users (username, password, role) VALUES (%s, %s, 'user')", (y_adi, h_sifre), kaydet=True)
                            st.success("🐺 Kayıt başarılı! Şimdi giriş yapabilirsin.")
                        else: st.error("Bu kullanıcı adı zaten alınmış!")
                    else: st.warning("Geçerli bilgiler giriniz!")
        st.stop()

# --- 4. ANA PROGRAM AKIŞI ---
giris_sistemi()
u_info = vt("SELECT * FROM users WHERE username=%s", (st.session_state.kullanici,))[0]

# Günlük Hak Resetleme
if u_info['son_giris'] != date.today():
    yeni_seri = (u_info['streak'] + 1) if u_info['son_giris'] == date.today() - timedelta(days=1) else 1
    vt("UPDATE users SET ai_sayaci=0, son_giris=%s, streak=%s WHERE username=%s", (date.today(), yeni_seri, st.session_state.kullanici), kaydet=True)
    st.rerun()

# Menü
menu = st.sidebar.radio("🐺 T-BOZKURT MENÜ", ["📊 Çalışma Masası", "📸 Soru Çözdür", "💎 Özel Üyelik", "🛠 Sistem Yönetimi"])

if menu == "📊 Çalışma Masası":
    st.title(f"Hoş geldin, {st.session_state.kullanici.upper()}!")
    c1, c2, c3 = st.columns(3)
    c1.metric("Çalışma Serisi", f"{u_info['streak']} Gün")
    c2.metric("Toplam Puan", u_info['xp'])
    sinir = 300 if st.session_state.rol != 'user' else (5 + (u_info['xp'] // 100))
    c3.metric("Kalan Hakkın", f"{max(0, sinir - u_info['ai_sayaci'])}")

elif menu == "📸 Soru Çözdür":
    st.header("📸 Akıllı Soru Çözüm Merkezi")
    f = st.camera_input("Soruyu Çek")
    if not f: f = st.file_uploader("Veya Yükle", type=['jpg','png','jpeg'])

    if f:
        img = Image.open(f).convert("RGB")
        img.thumbnail((1024, 1024))
        
        with st.spinner("🐺 Bozkurt analiz ediyor..."):
            # Adım 1: OCR
            p1 = "Görseldeki soruyu metne dök ve ders/konu saptanmasını yap. JSON: {metin, ders, konu}"
            r1 = MODEL.generate_content([p1, img])
            v1 = json.loads(r1.text)
            maliyet_kaydet(st.session_state.kullanici, r1.usage_metadata.total_token_count)
            
            # Adım 2: Hibrit Hafıza
            hafiza = vt("SELECT icerik, kurt_notu FROM topic_contents WHERE ders=%s AND konu=%s", (v1['ders'], v1['konu']))
            
            if hafiza:
                cozum, knotu, kaynak = hafiza[0]['icerik'], hafiza[0]['kurt_notu'], "Hafıza"
            else:
                p2 = f"{v1['ders']} - {v1['konu']} anlatımı JSON: {{cozum, kurt_notu}}"
                r2 = MODEL.generate_content([p2, v1['metin']])
                v2 = json.loads(r2.text)
                cozum, knotu, kaynak = v2['cozum'], v2['kurt_notu'], "Yapay Zeka"
                
                vt("""
                    INSERT INTO topic_contents (ders, konu, icerik, kurt_notu) VALUES (%s,%s,%s,%s)
                    ON CONFLICT (ders, konu) DO UPDATE SET icerik=EXCLUDED.icerik, kurt_notu=EXCLUDED.kurt_notu
                """, (v1['ders'], v1['konu'], cozum, knotu), kaydet=True)
                maliyet_kaydet(st.session_state.kullanici, r2.usage_metadata.total_token_count)
                vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10 WHERE username=%s", (st.session_state.kullanici,), kaydet=True)

            st.success(f"📌 {v1['ders']} | {v1['konu']} ({kaynak})")
            st.markdown(cozum)
            st.info(f"🐺 Kurt Notu: {knotu}")

elif menu == "🛠 Sistem Yönetimi":
    if st.session_state.rol == 'admin':
        st.subheader("💰 Maliyet ve Harcama Analizi")
        m_data = vt("SELECT date(tarih) as d, sum(cost) as m FROM cost_logs GROUP BY d ORDER BY d LIMIT 7")
        if m_data:
            df = pd.DataFrame(m_data, columns=['Gün', 'Maliyet'])
            st.area_chart(df.set_index('Gün'))
        
        if st.button("✨ 15 Haneli Lisans Kodu Üret"):
            l_kod = f"TB-{secrets.token_urlsafe(11)[:15].upper()}"
            vt("INSERT INTO license_codes (code) VALUES (%s)", (l_kod,), kaydet=True)
            st.code(l_kod)

st.sidebar.markdown("---")
st.sidebar.caption("T-BOZKURT v15.0 | 2026")
