import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json, time, hashlib, random, string, os
from datetime import datetime, timedelta

# --- 1. YAPILANDIRMA ---
st.set_page_config(page_title="T-BOZKURT v35.1", layout="wide", page_icon="🐺")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tbozkurt_master.db")

for f in ["podcasts", "quizzes", "backups"]:
    os.makedirs(os.path.join(BASE_DIR, f), exist_ok=True)

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except Exception as e:
    st.error("⚠️ Secrets.toml yapılandırması eksik! Lütfen GEMINI_KEY ve ADMIN_KEY ekleyin."); st.stop()

# --- 2. AI İÇERİK MOTORU ---
def ai_icerik_uret(ders_adi, konu_adi, tip="ders"):
    prompt = f"YKS uzmanı olarak {ders_adi} - {konu_adi} için "
    if tip == "ders":
        prompt += "detaylı Markdown konu anlatımı hazırla."
    else:
        prompt += "5 soruluk JSON test hazırla: [{'soru':'..','siklar':['A','B','C','D'],'dogru':'A'}]"
    try:
        response = MODEL.generate_content(prompt)
        return response.text.replace("```json", "").replace("```", "").strip()
    except: return ""

# --- 3. VERİTABANI VE ÇEKİRDEK ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    try:
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            c = conn.cursor()
            c.execute(sorgu, parametre)
            if commit: conn.commit(); return True
            return c.fetchall()
    except: return None

def vt_kurulum():
    vt_sorgu("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, deneme_bitis TEXT, streak INTEGER DEFAULT 0, son_giris TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS xp_log (username TEXT, tarih TEXT, xp INTEGER, tip TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS tamamlanan_konular (username TEXT, konu_id INTEGER, PRIMARY KEY(username, konu_id))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS lisanslar (lisans_id TEXT PRIMARY KEY, aktif INTEGER DEFAULT 0, sure_ay INTEGER DEFAULT 12)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS dersler (id INTEGER PRIMARY KEY AUTOINCREMENT, sinif TEXT, ad TEXT, UNIQUE(sinif, ad))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders_id INTEGER, ad TEXT, icerik TEXT, quiz_icerik TEXT, podcast_path TEXT, UNIQUE(ders_id, ad))", commit=True)
    if not vt_sorgu("SELECT 1 FROM dersler"):
        for s in ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"]:
            for d in ["Matematik", "Türkçe", "Fizik", "Kimya", "Biyoloji"]:
                vt_sorgu("INSERT INTO dersler (sinif, ad) VALUES (?,?)", (s, d), commit=True)
    if not vt_sorgu("SELECT 1 FROM users WHERE username='admin'"):
        h_adm = hashlib.sha256((ADMIN_SIFRE + "tbozkurt_salt_2026").encode()).hexdigest()
        vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", ("admin", h_adm, "Admin", "2026-02-18", 1, 9999, "2099-12-31", 0, None), commit=True)

vt_kurulum()

# --- 4. GİRİŞ VE 7 GÜNLÜK KAYIT SİSTEMİ ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT Karargahı")
    t1, t2 = st.tabs(["🔑 Giriş Yap", "📝 7 Gün Ücretsiz Kaydol"])
    with t1:
        u = st.text_input("Kullanıcı")
        p = st.text_input("Şifre", type="password")
        if st.button("Giriş"):
            h_p = hashlib.sha256((p + "tbozkurt_salt_2026").encode()).hexdigest()
            res = vt_sorgu("SELECT password FROM users WHERE username=?", (u,))
            if res and res[0][0] == h_p:
                st.session_state.user, st.session_state.admin = u, (u == "admin"); st.rerun()
            else: st.error("Hata!")
    with t2:
        st.info("🐺 Yeni Alfalara özel 7 gün tam erişim hediye!")
        nu = st.text_input("Yeni Alfa Adı")
        np = st.text_input("Şifre Belirle", type="password", key="reg")
        ns = st.selectbox("Sınıfın", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
        if st.button("Ücretsiz Denemeyi Başlat"):
            if nu and len(np) > 5:
                h_np = hashlib.sha256((np + "tbozkurt_salt_2026").encode()).hexdigest()
                trial_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                vt_sorgu("INSERT INTO users (username, password, sinif, kayit_tarihi, deneme_bitis, streak, son_giris) VALUES (?,?,?,?,?,?,?)", 
                         (nu, h_np, ns, str(datetime.now().date()), trial_date, 1, str(datetime.now().date())), commit=True)
                st.success(f"🐺 Hoş geldin {nu}! 7 günlük süren başladı."); time.sleep(1); st.rerun()
    st.stop()

# --- 5. PANEL VE KONTROLLER ---
res_data = vt_sorgu("SELECT xp, sinif, streak, deneme_bitis FROM users WHERE username=?", (st.session_state.user,))
u_xp, u_sinif, u_streak, u_bitis = res_data[0]
premium_aktif = datetime.now().date() <= datetime.strptime(u_bitis, "%Y-%m-%d").date() if u_bitis else False

with st.sidebar:
    st.title(f"🐺 {st.session_state.user}")
    st.metric("🏆 XP", u_xp); st.metric("🔥 Seri", f"{u_streak} Gün")
    menu = st.radio("Menü", ["📊 Karargah", "📚 Eğitim", "🛠️ Admin"])
    if st.button("🚪 Çıkış"): st.session_state.clear(); st.rerun()

# --- 6. EĞİTİM VE AI ---
if menu == "📚 Eğitim":
    dersler = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (u_sinif,))
    sec_d = st.selectbox("Ders", [d[1] for d in dersler])
    d_id = [d[0] for d in dersler if d[1] == sec_d][0]
    konu_adi = st.text_input("Çalışmak istediğin konuyu yaz:")
    if konu_adi:
        vt_sorgu("INSERT OR IGNORE INTO konular (ders_id, ad) VALUES (?,?)", (d_id, konu_adi), commit=True)
        k_res = vt_sorgu("SELECT id, icerik, quiz_icerik FROM konular WHERE ders_id=? AND ad=?", (d_id, konu_adi))[0]
        k_id, k_ic, k_qz = k_res
        t1, t2 = st.tabs(["📖 Ders", "⚔️ Quiz"])
        with t1:
            if not k_ic:
                with st.spinner("AI Hazırlıyor..."):
                    yeni = ai_icerik_uret(sec_d, konu_adi, "ders")
                    vt_sorgu("UPDATE konular SET icerik=? WHERE id=?", (json.dumps({"anlatim": yeni}), k_id), commit=True); st.rerun()
            st.markdown(json.loads(k_ic)["anlatim"])
        with t2:
            if not premium_aktif: st.error("🛡️ Premium Gerekli"); st.stop()
            if not k_qz:
                with st.spinner("Sorular Hazırlanıyor..."):
                    yeni = ai_icerik_uret(sec_d, konu_adi, "quiz")
                    vt_sorgu("UPDATE konular SET quiz_icerik=? WHERE id=?", (yeni, k_id), commit=True); st.rerun()
            try:
                qz = json.loads(k_qz)
                with st.form("q"):
                    cev = [st.radio(q['soru'], q['siklar'], key=f"q_{i}") for i, q in enumerate(qz)]
                    if st.form_submit_button("Bitir"):
                        skor = sum([1 for i, c in enumerate(cev) if c == qz[i]['dogru']])
                        vt_sorgu("UPDATE users SET xp=xp+? WHERE username=?", (skor*5, st.session_state.user), commit=True); st.rerun()
            except: st.error("Hata!")

elif menu == "🛠️ Admin" and st.session_state.admin:
    if st.button("12 Aylık Lisans Üret"):
        l_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=15))
        vt_sorgu("INSERT INTO lisanslar (lisans_id, aktif, sure_ay) VALUES (?,0,12)", (l_id,), commit=True)
        st.code(l_id)
