import streamlit as st
import psycopg2 
from psycopg2 import extras, pool
import google.generativeai as genai
from datetime import datetime, timedelta, date
import time, bcrypt, secrets, json, logging, requests, io
from PIL import Image
from gtts import gTTS
import pandas as pd

# --- AYARLAR VE BAĞLANTILAR ---
st.set_page_config(page_title="T-BOZKURT", layout="wide", page_icon="🐺")

@st.cache_resource
def vt_havuzu_baslat():
    return psycopg2.pool.SimpleConnectionPool(1, 15, st.secrets["DATABASE_URL"])

HAVUZ = vt_havuzu_baslat()

def vt(sorgu, parametre=(), kaydet=False):
    baglanti = None
    try:
        baglanti = HAVUZ.getconn()
        imlec = baglanti.cursor(cursor_factory=extras.DictCursor)
        imlec.execute(sorgu, parametre)
        sonuc = imlec.fetchall() if imlec.description else None
        if kaydet: baglanti.commit()
        return sonuc if sonuc is not None else (True if kaydet else [])
    except Exception as e:
        if baglanti and kaydet: baglanti.rollback()
        return False
    finally:
        if baglanti: HAVUZ.putconn(baglanti)

@st.cache_resource
def ai_baslat():
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    return genai.GenerativeModel("gemini-1.5-flash-latest", generation_config={"response_mime_type": "application/json"})

MODEL = ai_baslat()

# --- YARDIMCI FONKSİYONLAR ---
def seslendir(metin):
    try:
        tts = gTTS(text=metin, lang='tr')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp
    except: return None

def maliyet_kaydet(kullanici, tokens):
    gider = (tokens / 1000000) * 0.075
    vt("INSERT INTO cost_logs (username, tokens, cost) VALUES (%s, %s, %s)", (kullanici, tokens, gider), kaydet=True)

# --- 1. OTURUM VE GİRİŞ SİSTEMİ ---
if "kullanici" not in st.session_state:
    st.title("🐺 T-BOZKURT KARARGAHI")
    sekme1, sekme2 = st.tabs(["Giriş", "Kayıt"])
    with sekme1:
        u = st.text_input("Kullanıcı Adı").lower().strip()
        p = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap"):
            res = vt("SELECT password, role FROM users WHERE username=%s", (u,))
            if res and bcrypt.checkpw(p.encode(), res[0][0].encode()):
                st.session_state.kullanici, st.session_state.rol = u, res[0][1]
                st.rerun()
            else: st.error("Hatalı bilgiler!")
    st.stop()

# Veri Çekme ve Günlük Reset
veri = vt("SELECT * FROM users WHERE username=%s", (st.session_state.kullanici,))[0]
if veri['son_giris'] != date.today():
    yeni_seri = (veri['streak'] + 1) if veri['son_giris'] == date.today() - timedelta(days=1) else 1
    vt("UPDATE users SET ai_sayaci=0, son_giris=%s, streak=%s WHERE username=%s", (date.today(), yeni_seri, st.session_state.kullanici), kaydet=True)
    st.rerun()

# --- 2. MENÜ VE SIDEBAR ---
menu = st.sidebar.radio("MENÜ", ["📊 Çalışma Masası", "📸 Soru Çözdür", "🏆 Derece Yapanlar", "💎 Özel Üyelik", "🛠 Sistem Yönetimi"])

# --- 3. MODÜLLER ---

if menu == "📊 Çalışma Masası":
    st.header(f"Selam {st.session_state.kullanici.upper()}! 🐺")
    k1, k2, k3 = st.columns(3)
    k1.metric("Seri (Gün)", veri['streak'])
    k2.metric("Toplam Puan", veri['xp'])
    limit = 300 if st.session_state.rol != 'user' else (5 + (veri['xp'] // 100))
    k3.metric("Kalan Hakkın", f"{limit - veri['ai_sayaci']}")

elif menu == "📸 Soru Çözdür":
    st.subheader("Soru Çözüm ve Konu Anlatımı")
    sekme_f, sekme_m = st.tabs(["📸 Fotoğraf", "✍️ Metin"])
    input_verisi = None
    
    with sekme_f: 
        f = st.camera_input("Soru Çek")
        if f: input_verisi = Image.open(f)
    with sekme_m: 
        m = st.text_area("Soruyu buraya yaz...")
        if st.button("Çözüm Al"): input_verisi = m

    if input_verisi:
        with st.spinner("🐺 Bozkurt Hafızayı ve Yapay Zekayı Sorguluyor..."):
            # 🟢 ADIM 1: OCR ve Konu Saptama
            saptama_p = "Sorunun dersini ve konusunu saptayıp JSON döndür: {metin, ders, konu}"
            sap_cevap = MODEL.generate_content([saptama_p, input_verisi])
            sap_json = json.loads(sap_cevap.text)
            
            # 🟢 ADIM 2: Hibrit Hafıza Kontrolü
            hafiza = vt("SELECT icerik, kurt_notu FROM topic_contents WHERE ders=%s AND konu=%s", (sap_json['ders'], sap_json['konu']))
            
            if hafiza:
                final_cozum, final_not, kaynak = hafiza[0]['icerik'], hafiza[0]['kurt_notu'], "Hafıza"
                vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+5 WHERE username=%s", (st.session_state.kullanici,), kaydet=True)
            else:
                # Atomik İşlem: Hak düş
                hak_check = vt("UPDATE users SET ai_sayaci=ai_sayaci+1, xp=xp+10 WHERE username=%s RETURNING id", (st.session_state.kullanici,), kaydet=True)
                if hak_check:
                    try:
                        ai_p = f"{sap_json['ders']} dersi {sap_json['konu']} konusu anlatımı JSON: {{cozum, kurt_notu}}"
                        ai_cevap = MODEL.generate_content([ai_p, input_verisi])
                        ai_json = json.loads(ai_cevap.text)
                        final_cozum, final_not, kaynak = ai_json['cozum'], ai_json['kurt_notu'], "Yapay Zeka"
                        
                        # Hafızaya Kaydet
                        vt("INSERT INTO topic_contents (ders, konu, icerik, kurt_notu) VALUES (%s,%s,%s,%s)", 
                           (sap_json['ders'], sap_json['konu'], final_cozum, final_not), kaydet=True)
                        maliyet_kaydet(st.session_state.kullanici, ai_cevap.usage_metadata.total_token_count)
                    except:
                        vt("UPDATE users SET ai_sayaci=ai_sayaci-1, xp=xp-10 WHERE username=%s", (st.session_state.kullanici,), kaydet=True)
                        st.error("Çözüm sırasında hata oluştu!"); st.stop()

            # 🟢 ADIM 3: Sonuç Gösterimi
            st.success(f"📌 {sap_json['ders']} | {sap_json['konu']} ({kaynak})")
            st.markdown(final_cozum)
            st.info(f"🐺 Kurt Notu: {final_not}")
            
            c1, c2 = st.columns(2)
            if c1.button("🔊 Çözümü Dinle"):
                s = seslendir(final_cozum.replace("*","").replace("#",""))
                if s: st.audio(s)
            if c2.button("🐺 Kurt Notunu Dinle"):
                s = seslendir(final_not)
                if s: st.audio(s)

elif menu == "🛠 Sistem Yönetimi":
    if st.session_state.rol != 'admin': st.warning("Yetkiniz yok!"); st.stop()
    
    st.subheader("🛠 Admin Kontrol Paneli")
    tab1, tab2, tab3 = st.tabs(["📊 Maliyet & Hata", "📝 Konu Düzenle", "💎 Lisans Üret"])
    
    with tab1:
        maliyet = vt("SELECT SUM(cost) FROM cost_logs")[0][0] or 0
        st.metric("Toplam Yapay Zeka Harcaması", f"${maliyet:.4f}")
        hatalar = vt("SELECT * FROM alarm_kayitlari ORDER BY tarih DESC LIMIT 5")
        st.write("Son Hata Kayıtları:", hatalar)
        
    with tab2:
        st.write("Hafızadaki Konuları Güncelle")
        konular = vt("SELECT id, ders, konu FROM topic_contents")
        if konular:
            sec = st.selectbox("Düzenlenecek Konu", [f"{k['id']} | {k['ders']} - {k['konu']}" for k in konular])
            sec_id = sec.split(" | ")[0]
            mevcut = vt("SELECT * FROM topic_contents WHERE id=%s", (sec_id,))[0]
            n_icerik = st.text_area("İçerik", value=mevcut['icerik'], height=200)
            n_not = st.text_input("Kurt Notu", value=mevcut['kurt_notu'])
            if st.button("Güncelle"):
                vt("UPDATE topic_contents SET icerik=%s, kurt_notu=%s WHERE id=%s", (n_icerik, n_not, sec_id), kaydet=True)
                st.success("Hafıza güncellendi!")

    with tab3:
        if st.button("15 Haneli Lisans Üret"):
            kod = f"TB-{secrets.token_urlsafe(11)[:15].upper()}"
            vt("INSERT INTO license_codes (code) VALUES (%s)", (kod,), kaydet=True)
            st.code(kod)
