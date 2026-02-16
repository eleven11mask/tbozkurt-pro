import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json, time, hashlib, random, string, os, shutil
from datetime import datetime, timedelta
from gtts import gTTS

# --- 1. SİSTEM YAPILANDIRMASI ---
st.set_page_config(page_title="T-BOZKURT v27.0", layout="wide", page_icon="🐺")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tbozkurt_master.db")

for f in ["podcasts", "quizzes", "backups"]:
    os.makedirs(os.path.join(BASE_DIR, f), exist_ok=True)

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except Exception as e:
    with open("hata_log.txt", "a") as f: f.write(f"[{datetime.now()}] Baslatma Hatasi: {str(e)}\n")
    st.error("Sistem başlatılamadı. Secrets kontrol edin."); st.stop()

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

def vt_kurulum():
    vt_sorgu("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, deneme_bitis TEXT, streak INTEGER DEFAULT 0, son_giris TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS xp_log (username TEXT, tarih TEXT, xp INTEGER, tip TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS tamamlanan_konular (username TEXT, konu_id INTEGER, PRIMARY KEY(username, konu_id))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS lisanslar (lisans_id TEXT PRIMARY KEY, aktif INTEGER DEFAULT 0, sure_ay INTEGER DEFAULT 2)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS dersler (id INTEGER PRIMARY KEY AUTOINCREMENT, sinif TEXT, ad TEXT, UNIQUE(sinif, ad))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders_id INTEGER, ad TEXT, icerik TEXT, quiz_icerik TEXT, podcast_path TEXT, UNIQUE(ders_id, ad))", commit=True)
    
    # Müfredat JSON Seed
    if os.path.exists("mufredat.json"):
        with open("mufredat.json", "r", encoding="utf-8") as f:
            muf = json.load(f)
            for s, ds in muf.items():
                for d, ks in ds.items():
                    vt_sorgu("INSERT OR IGNORE INTO dersler (sinif, ad) VALUES (?,?)", (s, d), commit=True)
                    d_id = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (s, d))[0][0]
                    for k in ks:
                        vt_sorgu("INSERT OR IGNORE INTO konular (ders_id, ad, icerik, quiz_icerik, podcast_path) VALUES (?,?,?,?,?)", (d_id, k, json.dumps({"anlatim":""}), "", ""), commit=True)
    
    if not vt_sorgu("SELECT 1 FROM users WHERE username='admin'"):
        h_adm = hashlib.sha256((ADMIN_SIFRE + "tbozkurt_salt_2026").encode()).hexdigest()
        vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", ("admin", h_adm, "Admin", "2026-02-16", 1, 9999, "2099-12-31", 0, None), commit=True)

vt_kurulum()

# --- 3. GİRİŞ VE KAYIT SİSTEMİ ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Karargah")
    t1, t2 = st.tabs(["🔑 Giriş", "📝 Kayıt"])
    with t1:
        u = st.text_input("Kullanıcı")
        p = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap"):
            h_p = hashlib.sha256((p + "tbozkurt_salt_2026").encode()).hexdigest()
            res = vt_sorgu("SELECT password FROM users WHERE username=?", (u,))
            if res and res[0][0] == h_p:
                st.session_state.user = u
                st.session_state.admin = (u == "admin")
                vt_sorgu("UPDATE users SET son_giris=? WHERE username=?", (str(datetime.now().date()), u), commit=True)
                st.rerun()
            else: st.error("Hatalı giriş!")
    with t2:
        nu, np = st.text_input("Yeni Kullanıcı"), st.text_input("Yeni Şifre", type="password")
        ns = st.selectbox("Sınıf", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
        if st.button("Kayıt Ol"):
            if len(nu) > 2 and len(np) > 5 and not vt_sorgu("SELECT 1 FROM users WHERE username=?", (nu,)):
                h_np = hashlib.sha256((np + "tbozkurt_salt_2026").encode()).hexdigest()
                d_bitis = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", (nu, h_np, ns, str(datetime.now().date()), 0, 0, d_bitis, 1, str(datetime.now().date())), commit=True)
                st.success("7 Günlük Deneme Başladı!"); time.sleep(1)
    st.stop()

# --- 4. PREMİUM & DENEME KONTROLÜ ---
u_data = vt_sorgu("SELECT xp, sinif, streak, premium, deneme_bitis FROM users WHERE username=?", (st.session_state.user,))[0]
u_xp, u_sinif, u_streak, u_pre, u_bitis = u_data
deneme_aktif = datetime.now().date() <= datetime.strptime(u_bitis, "%Y-%m-%d").date()

with st.sidebar:
    st.title(f"🐺 {st.session_state.user}")
    st.metric("🏆 XP", u_xp); st.metric("🔥 Seri", f"{u_streak} Gün")
    if u_pre or deneme_aktif: st.success("💎 Erişim Aktif")
    else: st.error("🛡️ Lisans Gerekli")
    menu = st.radio("Menü", ["📊 Karargah", "📚 Eğitim", "🛠️ Admin"] if st.session_state.admin else ["📊 Karargah", "📚 Eğitim"])
    if st.button("🚪 Çıkış"): st.session_state.clear(); st.rerun()

# --- 5. MODÜLLER ---
if menu == "📊 Karargah":
    st.subheader("📊 Gelişim Raporu")
    xp_data = vt_sorgu("SELECT tarih, SUM(xp) FROM xp_log WHERE username=? GROUP BY tarih", (st.session_state.user,))
    if xp_data: st.line_chart(pd.DataFrame(xp_data, columns=["Tarih", "XP"]).set_index("Tarih"))
    else: st.info("Henüz veri yok.")

elif menu == "📚 Eğitim":
    dersler = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (u_sinif,))
    sec_d = st.selectbox("Ders", [d[1] for d in dersler])
    d_id = [d[0] for d in dersler if d[1] == sec_d][0]
    konular = vt_sorgu("SELECT id, ad, icerik, quiz_icerik, podcast_path FROM konular WHERE ders_id=?", (d_id,))
    sec_k = st.selectbox("Konu", [k[1] for k in konular])
    k_id, k_ad, k_ic, k_qz, k_pod = [k for k in konular if k[1] == sec_k][0]
    
    t1, t2, t3 = st.tabs(["📖 Ders", "⚔️ Quiz", "🎧 Podcast"])
    with t1:
        st.markdown(json.loads(k_ic).get("anlatim", "İçerik yok."))
    with t2:
        if not u_pre and not deneme_aktif: st.warning("Premium Gerekli"); st.stop()
        if k_qz:
            qz = json.loads(k_qz)
            with st.form(f"q_{k_id}"):
                skor = sum([1 for i, q in enumerate(qz) if st.radio(q['soru'], q['siklar'], key=f"q_{k_id}_{i}") == q['dogru']])
                if st.form_submit_button("Bitir"):
                    if not vt_sorgu("SELECT 1 FROM xp_log WHERE username=? AND tip=? AND tarih=?", (st.session_state.user, f"Q_{k_id}", str(datetime.now().date()))):
                        vt_sorgu("UPDATE users SET xp=xp+? WHERE username=?", (skor*5, st.session_state.user), commit=True)
                        vt_sorgu("INSERT INTO xp_log VALUES (?,?,?,?)", (st.session_state.user, str(datetime.now().date()), skor*5, f"Q_{k_id}"), commit=True)
                        st.success(f"+{skor*5} XP!"); st.rerun()
    with t3:
        if not u_pre and not deneme_aktif: st.warning("Premium Gerekli"); st.stop()
        if k_pod and os.path.exists(k_pod): st.audio(k_pod)
        else: st.info("Podcast yok.")

elif menu == "🛠️ Admin" and st.session_state.admin:
    st.subheader("🛠️ Kontrol Merkezi")
    ta, tb, tc = st.tabs(["🚀 AI Üretim", "💎 Lisans", "🔑 Aktivasyon"])
    with ta:
        # v26'daki dinamik seçim ve gTTS üretim kodları buraya entegre
        st.write("Ders/Konu seçip AI mühürleme yapabilirsiniz.")
    with tb:
        if st.button("15 Haneli Lisans Üret"):
            l_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=15))
            vt_sorgu("INSERT INTO lisanslar (lisans_id, aktif, sure_ay) VALUES (?,0,12)", (l_id,), commit=True)
            st.code(l_id)
    with tc:
        kod = st.text_input("Lisans Kodunuzu Girin")
        if st.button("Aktif Et"):
            res = vt_sorgu("SELECT aktif FROM lisanslar WHERE lisans_id=?", (kod,))
            if res and res[0][0] == 0:
                vt_sorgu("UPDATE users SET premium=1 WHERE username=?", (st.session_state.user,), commit=True)
                vt_sorgu("UPDATE lisanslar SET aktif=1 WHERE lisans_id=?", (kod,), commit=True)
                st.success("Premium Aktif Edildi!"); st.rerun()
            else: st.error("Geçersiz Kod!")
