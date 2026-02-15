import streamlit as st
import sqlite3
import google.generativeai as genai
import json
import time
import hashlib
from datetime import datetime
from gtts import gTTS
import os

# -------------------------------------------------
# 1️⃣ YAPILANDIRMA
# -------------------------------------------------
st.set_page_config(page_title="T-BOZKURT v6.8 FINAL", layout="wide", page_icon="🐺")

if not os.path.exists("podcasts"):
    os.makedirs("podcasts")

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except Exception as e:
    st.error(f"⚠️ Yapılandırma Hatası: {e}")
    st.stop()

# -------------------------------------------------
# 2️⃣ DATABASE MOTORU
# -------------------------------------------------
def get_connection():
    return sqlite3.connect('tbozkurt_v6.db', check_same_thread=False)

def vt_sorgu(sorgu, parametre=(), commit=False):
    conn = get_connection()
    c = conn.cursor()
    sonuc = []
    try:
        c.execute(sorgu, parametre)
        if commit:
            conn.commit()
        else:
            sonuc = c.fetchall()
    except Exception as e:
        if commit:
            conn.rollback()
        print("DB Hatası:", e)
    finally:
        conn.close()
    return sonuc

# -------------------------------------------------
# 3️⃣ SİSTEM KURULUMU
# -------------------------------------------------
def hash_pass(p):
    return hashlib.sha256((p + "tbozkurt_salt_2026").encode()).hexdigest()

def vt_kurulum():
    vt_sorgu("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS dersler (id INTEGER PRIMARY KEY AUTOINCREMENT, sinif TEXT, ad TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders_id INTEGER, ad TEXT, icerik TEXT, podcast_path TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS kurt_kampi (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, mesaj TEXT, tarih TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS tamamlanan_konular (username TEXT, konu_id INTEGER, PRIMARY KEY(username, konu_id))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS xp_log (username TEXT, tarih TEXT, xp INTEGER)", commit=True)

    # Admin garanti
    admin_var = vt_sorgu("SELECT 1 FROM users WHERE username='admin'")
    if not admin_var:
        vt_sorgu(
            "INSERT INTO users VALUES (?,?,?,?,?,?)",
            ("admin", hash_pass(ADMIN_SIFRE), "Admin", datetime.now().strftime("%Y-%m-%d"), 1, 9999),
            commit=True
        )

vt_kurulum()

# -------------------------------------------------
# 4️⃣ MÜFREDAT YÜKLEME
# -------------------------------------------------
def mufredat_yukle():
    mufredat = {
        "9. Sınıf": {
            "Matematik": ["Mantık", "Kümeler", "Fonksiyonlar"],
            "Fizik": ["Hareket", "Kuvvet"]
        },
        "10. Sınıf": {
            "Matematik": ["Permütasyon", "Trigonometri"]
        }
    }

    for sinif, dersler in mufredat.items():
        for ders, konular in dersler.items():
            ders_kontrol = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))
            if ders_kontrol:
                ders_id = ders_kontrol[0][0]
            else:
                vt_sorgu("INSERT INTO dersler (sinif, ad) VALUES (?,?)", (sinif, ders), commit=True)
                ders_id = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))[0][0]

            for konu in konular:
                varmi = vt_sorgu("SELECT 1 FROM konular WHERE ders_id=? AND ad=?", (ders_id, konu))
                if not varmi:
                    bos = json.dumps({"anlatim":"Henüz üretilmedi.","kavramlar":[],"ornekler":[]}, ensure_ascii=False)
                    vt_sorgu("INSERT INTO konular (ders_id, ad, icerik, podcast_path) VALUES (?,?,?,?)",
                             (ders_id, konu, bos, ""), commit=True)

# -------------------------------------------------
# 5️⃣ GİRİŞ SİSTEMİ
# -------------------------------------------------
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT Giriş")

    t1, t2 = st.tabs(["Giriş", "Kayıt"])

    with t1:
        with st.form("login"):
            u = st.text_input("Kullanıcı")
            p = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş"):
                res = vt_sorgu("SELECT password FROM users WHERE username=?", (u,))
                if (u=="admin" and p==ADMIN_SIFRE) or (res and res[0][0]==hash_pass(p)):
                    st.session_state.user = u
                    st.session_state.admin = (u=="admin")
                    st.rerun()
                else:
                    st.error("Hatalı giriş")

    with t2:
        with st.form("reg"):
            nu = st.text_input("Yeni Kullanıcı")
            np = st.text_input("Şifre", type="password")
            ns = st.selectbox("Sınıf", ["9. Sınıf","10. Sınıf","11. Sınıf","12. Sınıf"])
            if st.form_submit_button("Kayıt"):
                if not vt_sorgu("SELECT 1 FROM users WHERE username=?", (nu,)):
                    vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?)",
                             (nu, hash_pass(np), ns, datetime.now().strftime("%Y-%m-%d"), 0, 0),
                             commit=True)
                    st.success("Kayıt başarılı")
                    time.sleep(1)
                    st.rerun()

    st.stop()

# -------------------------------------------------
# 6️⃣ ANA PANEL
# -------------------------------------------------
u_name = st.session_state.user
is_admin = st.session_state.get("admin", False)

u_query = vt_sorgu("SELECT premium,xp,sinif FROM users WHERE username=?", (u_name,))
is_pre, u_xp, u_sinif = (1,9999,"Admin") if is_admin else u_query[0]

with st.sidebar:
    st.title(f"🐺 {u_name}")
    st.metric("XP", u_xp)
    menu = st.radio("Menü", ["📚 Ders","🛠️ Yönetici"] if is_admin else ["📚 Ders"])
    if st.button("Çıkış"):
        st.session_state.clear()
        st.rerun()

# -------------------------------------------------
# 7️⃣ DERS PANELİ
# -------------------------------------------------
if menu=="📚 Ders":
    dersler = vt_sorgu("SELECT id,ad FROM dersler WHERE sinif=?", (u_sinif,))
    if not dersler:
        st.warning("İçerik yok")
    else:
        d_map = {d[1]:d[0] for d in dersler}
        sec_d = st.selectbox("Ders", list(d_map.keys()))
        konular = vt_sorgu("SELECT id,ad,icerik,podcast_path FROM konular WHERE ders_id=?", (d_map[sec_d],))
        if konular:
            k_map = {k[1]:k for k in konular}
            sec_k = st.selectbox("Konu", list(k_map.keys()))
            konu = k_map[sec_k]

            data = json.loads(konu[2])
            st.write(data["anlatim"])

            for k in data["kavramlar"]:
                st.success(k)

            for o in data["ornekler"]:
                st.info(o)

            if konu[3] and os.path.exists(konu[3]):
                st.audio(konu[3])

# -------------------------------------------------
# 8️⃣ YÖNETİCİ PANELİ
# -------------------------------------------------
if menu=="🛠️ Yönetici" and is_admin:

    if st.button("📚 Müfredatı Yükle"):
        mufredat_yukle()
        st.success("Yüklendi")

    s_sec = st.selectbox("Sınıf", ["9. Sınıf","10. Sınıf","11. Sınıf","12. Sınıf"])
    dersler = vt_sorgu("SELECT id,ad FROM dersler WHERE sinif=?", (s_sec,))
    if dersler:
        d_map = {d[1]:d[0] for d in dersler}
        sec_d_ad = st.selectbox("Ders Seç", list(d_map.keys()))
        konular = vt_sorgu("SELECT id,ad FROM konular WHERE ders_id=?", (d_map[sec_d_ad],))
        if konular:
            k_map = {k[1]:k[0] for k in konular}
            sec_k_ad = st.selectbox("Konu Seç", list(k_map.keys()))

            if st.button("🚀 AI Üret"):
                with st.spinner("Üretiliyor..."):
                    prompt = f"{s_sec} {sec_d_ad} {sec_k_ad} için JSON üret. SADECE JSON."
                    res = MODEL.generate_content(prompt)
                    raw = res.text.strip().replace("```json","").replace("```","").strip()

                    try:
                        data = json.loads(raw)
                        if not all(k in data for k in ["anlatim","kavramlar","ornekler"]):
                            st.error("Eksik JSON")
                            st.stop()
                    except:
                        st.error("JSON hatası")
                        st.stop()

                    podcast_path = f"podcasts/{sec_k_ad}.mp3"
                    tts = gTTS(data["anlatim"], lang="tr")
                    tts.save(podcast_path)

                    vt_sorgu("UPDATE konular SET icerik=?, podcast_path=? WHERE id=?",
                             (json.dumps(data,ensure_ascii=False), podcast_path, k_map[sec_k_ad]),
                             commit=True)

                    st.success("Tamamlandı")
                    time.sleep(1)
                    st.rerun()

