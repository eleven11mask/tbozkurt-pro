import streamlit as st
import psycopg2 
from psycopg2 import extras, pool
import google.generativeai as genai
import bcrypt, time, secrets, json, io
from datetime import date, timedelta
from PIL import Image
from gtts import gTTS
import pandas as pd

# --- AYARLAR VE ÇEKİRDEK GÜVENLİK ---
st.set_page_config(page_title="T-BOZKURT v14.8", layout="wide", page_icon="🐺")

@st.cache_resource
def havuz_baslat():
    """Bağlantı havuzu: Uzun süre bekleyen bağlantıları canlı tutar."""
    try:
        return psycopg2.pool.SimpleConnectionPool(1, 20, st.secrets["DATABASE_URL"])
    except Exception as e:
        st.error(f"Veritabanı bağlantı hatası: {e}")
        return None

HAVUZ = havuz_baslat()

def vt(sorgu, parametre=(), kaydet=False):
    baglanti = None
    try:
        baglanti = HAVUZ.getconn()
        with baglanti.cursor() as ping: ping.execute("SELECT 1") # Canlılık kontrolü
        imlec = baglanti.cursor(cursor_factory=extras.DictCursor)
        imlec.execute(sorgu, parametre)
        sonuc = imlec.fetchall() if imlec.description else None
        if kaydet: baglanti.commit()
        return sonuc
    except Exception as e:
        if baglanti: baglanti.rollback()
        # Kritik hataları sessizce logla
        return None
    finally:
        if baglanti: HAVUZ.putconn(baglanti)

@st.cache_resource
def ai_motoru():
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    # Hem görsel hem metin işleyebilen Pro/Flash modelini aktif et
    return genai.GenerativeModel("gemini-1.5-flash-latest", generation_config={"response_mime_type": "application/json"})

MODEL = ai_motoru()

# --- OPTİMİZE EDİLMİŞ ARAÇLAR ---
@st.cache_data(show_spinner=False)
def ses_uret_hibrit(metin):
    """Büyük metinleri parçalara bölerek gTTS limitini aşar ve önbelleğe alır."""
    try:
        temiz_metin = metin.replace("#","").replace("*","").replace("_","")
        tts = gTTS(text=temiz_metin[:1000], lang='tr') # Karakter sınırı artırıldı
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except: return None

def maliyet_kaydet(kullanici, tokens):
    maliyet = (tokens / 1000000) * 0.075 
    vt("INSERT INTO cost_logs (username, tokens, cost) VALUES (%s,%s,%s)", (kullanici, tokens, maliyet), kaydet=True)

# --- GİRİŞ VE KAYIT PANELİ ---
if "kullanici" not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🐺 T-BOZKURT KARARGAHI</h1>", unsafe_allow_html=True)
    sekme1, sekme2 = st.tabs(["🔑 Giriş Yap", "📝 Kayıt Ol"])
    
    with sekme1:
        u_giriş = st.text_input("Kullanıcı Adı", key="u_in").lower().strip()
        p_giriş = st.text_input("Şifre", type="password", key="p_in")
        if st.button("KARARGAHA GİR"):
            res = vt("SELECT password, role FROM users WHERE username=%s", (u_giriş,))
            if res and bcrypt.checkpw(p_giriş.encode(), res[0]['password'].encode()):
                st.session_state.kullanici = u_giriş
                st.session_state.rol = res[0]['role']
                st.rerun()
            else: st.error("Kullanıcı adı veya şifre hatalı!")

    with sekme2:
        u_yeni = st.text_input("Yeni Kullanıcı Adı", key="u_reg").lower().strip()
        p_yeni = st.text_input("Şifre (Min 6 Karakter)", type="password", key="p_reg")
        if st.button("KATIL"):
            if len(p_yeni) >= 6 and not vt("SELECT 1 FROM users WHERE username=%s", (u_yeni,)):
                hp = bcrypt.hashpw(p_yeni.encode(), bcrypt.gensalt()).decode()
                vt("INSERT INTO users (username, password) VALUES (%s, %s)", (u_yeni, hp), kaydet=True)
                st.success("Kayıt başarılı! Şimdi giriş yapabilirsin.")
            else: st.error("Geçersiz kullanıcı adı veya kısa şifre!")
    st.stop()

# --- SİSTEM AKIŞI VE GÜNLÜK RESET ---
u_verisi = vt("SELECT * FROM users WHERE username=%s", (st.session_state.kullanici,))[0]
if u_verisi['son_giris'] != date.today():
    seri = (u_verisi['streak'] + 1) if u_verisi['son_giris'] == date.today() - timedelta(days=1) else 1
    vt("UPDATE users SET ai_sayaci=0, son_giris=%s, streak=%s WHERE username=%s", (date.today(), seri, st.session_state.kullanici), kaydet=True)
    st.rerun()

# --- ANA MENÜ ---
menu = st.sidebar.radio("MENÜ", ["📊 Çalışma Masası", "📸 Soru Çözdür", "💎 Özel Üyelik", "🛠 Sistem Yönetimi"])

if menu == "📊 Çalışma Masası":
    st.title(f"Hoş geldin, {st.session_state.kullanici.upper()}! 🐺")
    c1, c2, c3 = st.columns(3)
    c1.metric("Seri (Gün)", u_verisi['streak'])
    c2.metric("Puan (XP)", u_verisi['xp'])
    hak_siniri = 300 if st.session_state.rol != 'user' else (5 + (u_verisi['xp'] // 100))
    c3.metric("Kalan Hakkın", max(0, hak_siniri - u_verisi['ai_sayaci']))

elif menu == "📸 Soru Çözdür":
    f = st.camera_input("Soruyu Fotoğrafla")
    if not f: f = st.file_uploader("Veya Görsel Yükle", type=['jpg','png','jpeg'])
    
    if f:
        img = Image.open(f).convert("RGB") # Format Güvenliği
        img.thumbnail((1024, 1024)) # Boyut Optimizasyonu
        
        with st.spinner("Bozkurt analiz ediyor..."):
            # 1. OCR ve Saptama
            p1 = "Görseldeki soruyu metne dök ve ders/konu saptanmasını yap. JSON: {metin, ders, konu}"
            r1 = MODEL.generate_content([p1, img])
            v1 = json.loads(r1.text)
            maliyet_kaydet(st.session_state.kullanici, r1.usage_metadata.total_token_count)
            
            # 2. Hibrit Hafıza Sorgusu
            hafiza = vt("SELECT icerik, kurt_notu FROM topic_contents WHERE ders=%s AND konu=%s", (v1['ders'], v1['konu']))
            
            if hafiza:
                cozum, knotu, kaynak = hafiza[0]['icerik'], hafiza[0]['kurt_notu'], "Hafıza (Ücretsiz)"
            else:
                # 3. AI Çözümü ve Akıllı Güncelleme (Upsert)
                p2 = f"{v1['ders']} - {v1['konu']} anlatımı JSON: {{cozum, kurt_notu}}"
                r2 = MODEL.generate_content([p2, v1['metin']])
                v2 = json.loads(r2.text)
                cozum, knotu, kaynak = v2['cozum'], v2['kurt_notu'], "Yapay Zeka"
                
                vt("""
                    INSERT INTO topic_contents (ders, konu, icerik, kurt_notu) 
                    VALUES (%s, %s, %s, %s) 
                    ON CONFLICT (ders, konu) DO UPDATE SET 
                    icerik=EXCLUDED.icerik, kurt_notu=EXCLUDED.kurt_notu, 
                    surum_no=topic_contents.surum_no+1, guncelleme_tarihi=NOW()
                """, (v1['ders'], v1['konu'], cozum, knotu), kaydet=True)
                
                maliyet_kaydet(st.session_state.kullanici, r2.usage_metadata.total_token_count)
                vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10 WHERE username=%s", (st.session_state.kullanici,), kaydet=True)

            # SONUÇ GÖSTERİMİ
            st.success(f"📌 {v1['ders']} | {v1['konu']} ({kaynak})")
            st.markdown(cozum)
            st.info(f"🐺 Kurt Notu: {knotu}")
            
            cs1, cs2 = st.columns(2)
            if cs1.button("🔊 Çözümü Dinle"):
                s = ses_uret_hibrit(cozum); st.audio(s) if s else st.warning("Ses üretilemedi.")
            if cs2.button("🐺 Kurt Notunu Dinle"):
                s = ses_uret_hibrit(knotu); st.audio(s) if s else st.warning("Ses üretilemedi.")

elif menu == "🛠 Sistem Yönetimi" and st.session_state.rol == 'admin':
    st.subheader("💰 Harcama ve Performans Analizi")
    tarih_sec = st.date_input("Analiz Aralığı", [date.today() - timedelta(days=7), date.today()])
    
    if len(tarih_sec) == 2:
        m_data = vt("SELECT date(tarih) as d, sum(cost) as m FROM cost_logs WHERE date(tarih) BETWEEN %s AND %s GROUP BY d ORDER BY d", (tarih_sec[0], tarih_sec[1]))
        if m_data:
            df = pd.DataFrame(m_data, columns=['Gün', 'Maliyet ($)'])
            st.area_chart(df.set_index('Gün'))
            st.metric("Toplam Harcama", f"${df['Maliyet ($)'].sum():.4f}")

    if st.button("✨ 15 Haneli Lisans Kodu Üret"):
        l_kod = f"TB-{secrets.token_urlsafe(11)[:15].upper()}"
        vt("INSERT INTO license_codes (code) VALUES (%s)", (l_kod,), kaydet=True)
        st.code(l_kod)
    
    st.subheader("⚠️ Sistem Alarmları")
    alarmlar = vt("SELECT * FROM alarm_kayitlari ORDER BY tarih DESC LIMIT 5")
    if alarmlar: st.table(alarmlar)

st.sidebar.markdown("---")
st.sidebar.caption("T-BOZKURT v14.8 | 2026")
