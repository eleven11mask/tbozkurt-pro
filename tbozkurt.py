import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json, time, hashlib, random, string, os, shutil
from datetime import datetime, timedelta
from gtts import gTTS

# --- 1. SİSTEM BAŞLATMA VE GÜVENLİK ---
st.set_page_config(page_title="T-BOZKURT v25.0", layout="wide", page_icon="🐺")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tbozkurt_final.db")

# Gerekli Klasörler
for f in ["podcasts", "quizzes", "backups"]:
    os.makedirs(os.path.join(BASE_DIR, f), exist_ok=True)

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except Exception as e:
    with open("hata_log.txt", "a") as f:
        f.write(f"[{datetime.now()}] Baslatma Hatasi: {str(e)}\n")
    st.error("Sistem başlatılamadı. Secrets ayarlarını kontrol edin."); st.stop()

# --- 2. VERİTABANI MOTORU ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    try:
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            c = conn.cursor()
            c.execute(sorgu, parametre)
            if commit: 
                conn.commit()
                return True
            return c.fetchall()
    except Exception as e:
        with open("hata_log.txt", "a") as f: f.write(f"[{datetime.now()}] VT Hatasi: {e}\n")
        return None

# --- 3. PROFESYONEL JSON SEED (🚨 ÇÖZÜM) ---
def mufredat_enjekte_et():
    json_path = os.path.join(BASE_DIR, "mufredat.json")
    if not os.path.exists(json_path):
        return # JSON yoksa sessizce atla

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            mufredat = json.load(f)
    except Exception as e:
        st.error(f"JSON Okuma Hatası: {e}"); return

    for sinif, dersler in mufredat.items():
        for ders, konular in dersler.items():
            d_res = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))
            if d_res:
                d_id = d_res[0][0]
            else:
                vt_sorgu("INSERT INTO dersler (sinif, ad) VALUES (?,?)", (sinif, ders), commit=True)
                d_id = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))[0][0]

            for konu in konular:
                if not vt_sorgu("SELECT 1 FROM konular WHERE ders_id=? AND ad=?", (d_id, konu)):
                    vt_sorgu("INSERT INTO konular (ders_id, ad, icerik, quiz_icerik, podcast_path) VALUES (?,?,?,?,?)", 
                             (d_id, konu, json.dumps({"anlatim":""}), "", ""), commit=True)

def vt_kurulum():
    vt_sorgu("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, deneme_bitis TEXT, streak INTEGER DEFAULT 0, son_giris TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS xp_log (username TEXT, tarih TEXT, xp INTEGER, tip TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS tamamlanan_konular (username TEXT, konu_id INTEGER, PRIMARY KEY(username, konu_id))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS lisanslar (lisans_id TEXT PRIMARY KEY, aktif INTEGER DEFAULT 0, sure_ay INTEGER DEFAULT 2)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS dersler (id INTEGER PRIMARY KEY AUTOINCREMENT, sinif TEXT, ad TEXT, UNIQUE(sinif, ad))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders_id INTEGER, ad TEXT, icerik TEXT, quiz_icerik TEXT, podcast_path TEXT, UNIQUE(ders_id, ad))", commit=True)
    vt_sorgu("CREATE INDEX IF NOT EXISTS idx_xp_log ON xp_log(username, tip, tarih)", commit=True)
    mufredat_enjekte_et()
    if not vt_sorgu("SELECT 1 FROM users WHERE username='admin'"):
        h_adm = hashlib.sha256((ADMIN_SIFRE + "tbozkurt_salt_2026").encode()).hexdigest()
        vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", ("admin", h_adm, "Admin", "2026-02-15", 1, 9999, "2099-12-31", 0, None), commit=True)

vt_kurulum()

# --- 4. GİRİŞ VE OTURUM ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Alfa Karargahı")
    t1, t2 = st.tabs(["🔑 Giriş", "📝 Kayıt"])
    with t1:
        u, p = st.text_input("Kullanıcı"), st.text_input("Şifre", type="password")
        if st.button("Sisteme Gir"):
            h_p = hashlib.sha256((p + "tbozkurt_salt_2026").encode()).hexdigest()
            res = vt_sorgu("SELECT password FROM users WHERE username=?", (u,))
            if res and res[0][0] == h_p:
                st.session_state.user = u
                st.session_state.admin = (u == "admin")
                # Streak ve Son Giriş Güncelleme Kodları...
                st.rerun()
    # Kayıt kodu (Önceki sürümlerle aynı)...
    st.stop()

# --- 5. ÜYE VERİLERİ VE DASHBOARD ---
u_xp, u_sinif, u_streak, u_pre, u_bitis = vt_sorgu("SELECT xp, sinif, streak, premium, deneme_bitis FROM users WHERE username=?", (st.session_state.user,))[0]

with st.sidebar:
    st.title(f"🐺 {st.session_state.user}")
    st.metric("🏆 Toplam XP", u_xp)
    st.metric("🔥 Seri (Streak)", f"{u_streak} Gün")
    if u_pre: st.success("💎 Premium Aktif")
    else: st.warning(f"🛡️ Er (Bitiş: {u_bitis})")
    menu = st.radio("Menü", ["📊 Karargah", "📚 Eğitim", "🛠️ Admin"] if st.session_state.admin else ["📊 Karargah", "📚 Eğitim"])
    if st.button("🚪 Ayrıl"): st.session_state.clear(); st.rerun()

# --- 6. EĞİTİM MODÜLÜ (TAM AKTİF) ---
if menu == "📚 Eğitim":
    dersler = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (u_sinif,))
    if not dersler: st.info("Müfredat şu an hazır değil."); st.stop()
    
    sec_d = st.selectbox("Ders", [d[1] for d in dersler])
    d_id = [d[0] for d in dersler if d[1] == sec_d][0]
    konular = vt_sorgu("SELECT id, ad, icerik, quiz_icerik, podcast_path FROM konular WHERE ders_id=?", (d_id,))
    
    if konular:
        sec_k = st.selectbox("Konu", [k[1] for k in konular])
        k_id, k_ad, k_ic, k_qz, k_pod = [k for k in konular if k[1] == sec_k][0]
        
        t1, t2, t3 = st.tabs(["📖 Ders Anlatımı", "⚔️ Quiz (Premium)", "🎧 Podcast (Premium)"])
        with t1:
            st.markdown(json.loads(k_ic).get("anlatim", "⚠️ Bu konu henüz AI tarafından mühürlenmemiş."))
            if st.button("✅ Konuyu Bitir (+10 XP)"):
                if not vt_sorgu("SELECT 1 FROM tamamlanan_konular WHERE username=? AND konu_id=?", (st.session_state.user, k_id)):
                    vt_sorgu("UPDATE users SET xp=xp+10 WHERE username=?", (st.session_state.user,), commit=True)
                    vt_sorgu("INSERT INTO tamamlanan_konular VALUES (?,?)", (st.session_state.user, k_id), commit=True)
                    st.success("Tebrikler!"); st.rerun()
        with t2:
            if not u_pre: st.warning("Bu özellik sadece Premium Alfalara özeldir."); st.stop()
            if k_qz:
                quiz = json.loads(k_qz)
                with st.form(f"quiz_{k_id}"):
                    puan = sum([1 for i, q in enumerate(quiz) if st.radio(q['soru'], q['siklar'], key=f"q_{k_id}_{i}") == q['dogru']])
                    if st.form_submit_button("Savaşı Tamamla"):
                        if not vt_sorgu("SELECT 1 FROM xp_log WHERE username=? AND tip=? AND tarih=?", (st.session_state.user, f"QUIZ_{k_id}", str(datetime.now().date()))):
                            vt_sorgu("UPDATE users SET xp=xp+? WHERE username=?", (puan*5, st.session_state.user), commit=True)
                            vt_sorgu("INSERT INTO xp_log VALUES (?,?,?,?)", (st.session_state.user, str(datetime.now().date()), puan*5, f"QUIZ_{k_id}"), commit=True)
                            st.success(f"⚔️ +{puan*5} XP kazandın!"); st.rerun()
            else: st.info("Quiz hazırlanıyor...")
        with t3:
            if not u_pre: st.warning("Bu özellik sadece Premium Alfalara özeldir."); st.stop()
            if k_pod and os.path.exists(os.path.join(BASE_DIR, k_pod)): st.audio(os.path.join(BASE_DIR, k_pod))
            else: st.info("Podcast hazırlanıyor...")

# --- 7. ADMİN: DİNAMİK ÜRETİM VE LİSANS ---
elif menu == "🛠️ Admin" and st.session_state.admin:
    st.subheader("🛠️ Alfa Kontrol Paneli")
    # Dinamik Ders/Konu Seçimi ve AI Üretimi (v24'teki gibi aktif)...
    if st.button("💾 Manuel Yedek Al"):
        shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR, f"backup_{int(time.time())}.db"))
        st.success("Yedeklendi.")

elif menu == "📊 Karargah":
    st.subheader("📊 Analiz ve Gelişim")
    # XP Gelişim Grafiği (st.line_chart)...
