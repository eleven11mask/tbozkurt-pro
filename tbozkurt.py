import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json
import time
import hashlib
from datetime import datetime, timedelta
from gtts import gTTS
import os

# --- 1. AYARLAR VE DİZİN ---
st.set_page_config(page_title="T-BOZKURT v7.5 MASTER", layout="wide", page_icon="🐺")

if not os.path.exists("podcasts"):
    os.makedirs("podcasts")

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except Exception as e:
    st.error(f"⚠️ Yapılandırma Hatası: {e}"); st.stop()

# --- 2. VERİTABANI MOTORU (Cloud Stabil) ---
def get_connection():
    return sqlite3.connect('tbozkurt_master.db', check_same_thread=False)

def vt_sorgu(sorgu, parametre=(), commit=False):
    conn = get_connection()
    c = conn.cursor()
    sonuc = []
    try:
        c.execute(sorgu, parametre)
        if commit: conn.commit()
        else: sonuc = c.fetchall()
    except Exception as e:
        if commit: conn.rollback()
        print(f"🚨 DB Hatası: {e}")
    finally: conn.close()
    return sonuc

# --- 3. SİSTEM KURULUMU & MÜFREDAT MOTORU ---
def hash_pass(p):
    return hashlib.sha256((p + "tbozkurt_salt_2026").encode()).hexdigest()

def vt_kurulum():
    vt_sorgu("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, deneme_bitis TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS dersler (id INTEGER PRIMARY KEY AUTOINCREMENT, sinif TEXT, ad TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders_id INTEGER, ad TEXT, icerik TEXT, podcast_path TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS tamamlanan_konular (username TEXT, konu_id INTEGER, PRIMARY KEY(username, konu_id))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS xp_log (username TEXT, tarih TEXT, xp INTEGER)", commit=True)
    
    if not vt_sorgu("SELECT 1 FROM users WHERE username='admin'"):
        vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?)", 
                 ("admin", hash_pass(ADMIN_SIFRE), "Admin", "2026-01-01", 1, 9999, "2099-12-31"), commit=True)

def mufredat_yukle():
    mufredat = {
        "9. Sınıf": {
            "Matematik": ["Mantık", "Kümeler", "Denklemler ve Eşitsizlikler", "Üslü ve Köklü İfadeler", "Oran ve Orantı", "Problemler", "Üçgenler", "Veri"],
            "Fizik": ["Fizik Bilimine Giriş", "Madde ve Özellikleri", "Hareket ve Kuvvet", "Enerji", "Isı ve Sıcaklık", "Elektrostatik"],
            "Kimya": ["Kimya Bilimi", "Atom ve Periyodik Sistem", "Kimyasal Türler Arası Etkileşimler", "Maddenin Halleri", "Doğa ve Kimya"],
            "Biyoloji": ["Yaşam Bilimi Biyoloji", "Hücre", "Canlılar Dünyası"]
        },
        "10. Sınıf": {
            "Matematik": ["Sayma ve Olasılık", "Fonksiyonlar", "Polinomlar", "İkinci Dereceden Denklemler", "Dörtgenler ve Çokgenler", "Uzay Geometri"],
            "Fizik": ["Elektrik ve Manyetizma", "Basınç ve Kaldırma Kuvveti", "Dalgalar", "Optik"],
            "Kimya": ["Kimyanın Temel Kanunları", "Karışımlar", "Asitler, Bazlar ve Tuzlar", "Kimya Her Yerde"],
            "Biyoloji": ["Hücre Bölünmeleri", "Kalıtımın Genel İlkeleri", "Ekosistem Ekolojisi"]
        },
        "11. Sınıf": {
            "Matematik": ["Trigonometri", "Analitik Geometri", "Fonksiyonlarda Uygulamalar", "Denklem ve Eşitsizlik Sistemleri", "Çember ve Daire", "Olasılık"],
            "Fizik": ["Kuvvet ve Hareket", "Elektrik ve Manyetizma"],
            "Kimya": ["Modern Atom Teorisi", "Gazlar", "Sıvı Çözeltiler", "Kimyasal Tepkimelerde Enerji", "Hız", "Denge"],
            "Biyoloji": ["İnsan Fizyolojisi (Sistemler)", "Komünite ve Popülasyon Ekolojisi"]
        },
        "12. Sınıf": {
            "Matematik": ["Logaritma", "Diziler", "Limit ve Süreklilik", "Türev", "İntegral", "Çemberin Analitiği"],
            "Fizik": ["Çembersel Hareket", "Dalga Mekaniği", "Atom Fiziğine Giriş", "Modern Fizik"],
            "Kimya": ["Kimya ve Elektrik", "Karbon Kimyasına Giriş", "Organik Bileşikler"],
            "Biyoloji": ["Genden Proteine", "Canlılarda Enerji Dönüşümleri", "Bitki Biyolojisi"]
        }
    }
    for sinif, dersler in mufredat.items():
        for ders, konular in dersler.items():
            dk = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))
            d_id = dk[0][0] if dk else vt_sorgu("INSERT INTO dersler (sinif, ad) VALUES (?,?)", (sinif, ders), commit=True) or vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))[0][0]
            for konu in konular:
                if not vt_sorgu("SELECT 1 FROM konular WHERE ders_id=? AND ad=?", (d_id, konu)):
                    bos = json.dumps({"anlatim":"İçerik henüz mühürlenmedi.","kavramlar":[],"ornekler":[]}, ensure_ascii=False)
                    vt_sorgu("INSERT INTO konular (ders_id, ad, icerik, podcast_path) VALUES (?,?,?,?)", (d_id, konu, bos, ""), commit=True)

vt_kurulum()

# --- 4. GİRİŞ VE 7 GÜNLÜK DENEME ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT Karargah")
    t1, t2 = st.tabs(["🔐 Giriş", "🚀 7 Günlük Ücretsiz Deneme Başlat"])
    with t1:
        with st.form("l"):
            u, p = st.text_input("Kullanıcı Adı"), st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap"):
                res = vt_sorgu("SELECT password FROM users WHERE username=?", (u,))
                if (u=="admin" and p==ADMIN_SIFRE) or (res and res[0][0]==hash_pass(p)):
                    st.session_state.user, st.session_state.admin = u, (u=="admin")
                    st.rerun()
                else: st.error("Hatalı Giriş!")
    with t2:
        with st.form("r"):
            nu, np = st.text_input("Yeni Kullanıcı"), st.text_input("Yeni Şifre", type="password")
            ns = st.selectbox("Sınıf", ["9. Sınıf","10. Sınıf","11. Sınıf","12. Sınıf"])
            if st.form_submit_button("Ücretsiz Denemeyi Başlat"):
                if nu.strip() and np.strip():
                    if not vt_sorgu("SELECT 1 FROM users WHERE username=?", (nu,)):
                        bitis = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                        vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?)", (nu, hash_pass(np), ns, datetime.now().strftime("%Y-%m-%d"), 0, 0, bitis), commit=True)
                        st.success(f"🐺 Hoş geldin! Deneme Bitiş: {bitis}"); time.sleep(1); st.rerun()
                    else: st.error("Kullanıcı adı alınmış.")
    st.stop()

# --- 5. PANEL VERİLERİ ---
u_name = st.session_state.user
is_admin = st.session_state.get("admin", False)
u_data = vt_sorgu("SELECT premium, xp, sinif, deneme_bitis FROM users WHERE username=?", (u_name,))
db_pre, u_xp, u_sinif, d_bitis = u_data[0]
is_pre = 1 if (is_admin or db_pre == 1 or d_bitis >= datetime.now().strftime("%Y-%m-%d")) else 0

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title(f"🐺 {u_name}")
    st.metric("🔥 XP", u_xp)
    if is_pre and not is_admin and db_pre == 0:
        st.caption(f"⏳ Deneme Bitiş: {d_bitis}")
    elif not is_pre:
        st.warning("💎 Deneme Bitti!")
        if st.button("Premium Al"): vt_sorgu("UPDATE users SET premium=1 WHERE username=?", (u_name,), commit=True); st.rerun()
    
    menu = st.radio("Menü", ["📚 Dersler", "🛠️ Yönetici"] if is_admin else ["📚 Dersler"])
    if st.button("🚪 Çıkış"): st.session_state.clear(); st.rerun()

# --- 7. DERS ÇALIŞMA ---
if menu == "📚 Dersler":
    dersler = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (u_sinif,))
    if not dersler: st.info("Lütfen müfredatı yükleyin.")
    else:
        d_m = {d[1]:d[0] for d in dersler}
        sec_d = st.selectbox("Ders", list(d_m.keys()))
        konular = vt_sorgu("SELECT id, ad, icerik, podcast_path FROM konular WHERE ders_id=?", (d_m[sec_d],))
        if konular:
            k_m = {k[1]:k for k in konular}
            sec_k = st.selectbox("Konu", list(k_m.keys()))
            konu = k_m[sec_k]
            
            if not is_admin and not vt_sorgu("SELECT 1 FROM tamamlanan_konular WHERE username=? AND konu_id=?", (u_name, konu[0])):
                if st.button("✅ Bitirdim (+5 XP)"):
                    bugun = datetime.now().strftime("%Y-%m-%d")
                    gunluk = vt_sorgu("SELECT SUM(xp) FROM xp_log WHERE username=? AND tarih=?", (u_name, bugun))[0][0] or 0
                    if gunluk < 20:
                        vt_sorgu("UPDATE users SET xp=xp+5 WHERE username=?", (u_name,), commit=True)
                        vt_sorgu("INSERT INTO xp_log VALUES (?,?,5)", (u_name, bugun), commit=True)
                        vt_sorgu("INSERT INTO tamamlanan_konular VALUES (?,?)", (u_name, konu[0]), commit=True)
                        st.balloons(); st.rerun()
                    else: st.warning("Günlük limit doldu!")

            data = json.loads(konu[2])
            t1, t2, t3 = st.tabs(["📖 Anlatım", "🧠 Kavramlar", "🎧 Podcast"])
            with t1:
                st.write(data["anlatim"])
                for o in data["ornekler"]: st.info(f"🔹 {o}")
            with t2:
                for k in data["kavramlar"]: st.success(f"📌 {k}")
            with t3:
                if konu[3] and os.path.exists(konu[3]): st.audio(konu[3])
                else: st.info("Podcast henüz üretilmedi.")

# --- 8. YÖNETİCİ ---
elif menu == "🛠️ Yönetici" and is_admin:
    st.subheader("🛠️ Karargah Kontrol")
    if st.button("📚 Tüm Müfredatı Mühürle (Şablon Yükle)"):
        mufredat_yukle(); st.success("Müfredat kuruldu!"); st.rerun()

    s_sec = st.selectbox("Sınıf Seç", ["9. Sınıf","10. Sınıf","11. Sınıf","12. Sınıf"])
    dersler_db = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (s_sec,))
    if dersler_db:
        d_map = {d[1]:d[0] for d in dersler_db}
        sec_d_ad = st.selectbox("Ders Seç", list(d_map.keys()))
        konular_db = vt_sorgu("SELECT id, ad FROM konular WHERE ders_id=?", (d_map[sec_d_ad],))
        if konular_db:
            k_map = {k[1]:k[0] for k in konular_db}
            sec_k_ad = st.selectbox("Konu Seç", list(k_map.keys()))
            if st.button("🚀 AI Üret ve Podcast Kaydet"):
                with st.spinner("AI Karargahı çalışıyor..."):
                    try:
                        p = f"{s_sec} {sec_d_ad} {sec_k_ad} için JSON üret: {{'anlatim':'','kavramlar':[],'ornekler':[]}}. SADECE JSON."
                        res = MODEL.generate_content(p)
                        raw = res.text.strip().replace("```json","").replace("```","").strip()
                        data = json.loads(raw)
                        path = f"podcasts/{hashlib.md5(sec_k_ad.encode()).hexdigest()}.mp3"
                        gTTS(data["anlatim"][:1000], lang="tr").save(path)
                        vt_sorgu("UPDATE konular SET icerik=?, podcast_path=? WHERE id=?", (json.dumps(data, ensure_ascii=False), path, k_map[sec_k_ad]), commit=True)
                        st.success("Mühürlendi!"); st.rerun()
                    except Exception as e: st.error(f"Hata: {e}")

