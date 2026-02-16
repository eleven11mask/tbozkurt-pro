import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json, time, hashlib, random, string, os, shutil
from datetime import datetime, timedelta
from gtts import gTTS

# --- 1. SİSTEM YAPILANDIRMASI ---
st.set_page_config(page_title="T-BOZKURT v26.0", layout="wide", page_icon="🐺")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tbozkurt_final.db")

for f in ["podcasts", "quizzes", "backups"]:
    os.makedirs(os.path.join(BASE_DIR, f), exist_ok=True)

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except Exception as e:
    with open("hata_log.txt", "a") as f:
        f.write(f"[{datetime.now()}] Baslatma Hatasi: {str(e)}\n")
    st.error("Sistem başlatılamadı."); st.stop()

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

# --- 3. MÜFREDAT SEED (JSON TABANLI) ---
def mufredat_enjekte_et():
    json_path = os.path.join(BASE_DIR, "mufredat.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            mufredat = json.load(f)
        for sinif, dersler in mufredat.items():
            for ders, konular in dersler.items():
                d_res = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))
                d_id = d_res[0][0] if d_res else vt_sorgu("INSERT INTO dersler (sinif, ad) VALUES (?,?)", (sinif, ders), commit=True) or vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))[0][0]
                for konu in konular:
                    if not vt_sorgu("SELECT 1 FROM konular WHERE ders_id=? AND ad=?", (d_id, konu)):
                        vt_sorgu("INSERT INTO konular (ders_id, ad, icerik, quiz_icerik, podcast_path) VALUES (?,?,?,?,?)", (d_id, konu, json.dumps({"anlatim":""}), "", ""), commit=True)

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

# --- 4. GİRİŞ, KAYIT VE 7 GÜNLÜK DENEME (🚨 GERİ GELDİ) ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Karargah")
    t1, t2 = st.tabs(["🔑 Giriş", "📝 Kayıt"])
    with t1:
        u, p = st.text_input("Kullanıcı"), st.text_input("Şifre", type="password")
        if st.button("Giriş Yap"):
            h_p = hashlib.sha256((p + "tbozkurt_salt_2026").encode()).hexdigest()
            res = vt_sorgu("SELECT password FROM users WHERE username=?", (u,))
            if res and res[0][0] == h_p:
                st.session_state.user = u
                st.session_state.admin = (u == "admin")
                # 🔥 Streak ve Son Giris Motoru (v19'daki gibi)
                bugun = datetime.now().date()
                u_info = vt_sorgu("SELECT son_giris, streak FROM users WHERE username=?", (u,))[0]
                if u_info[0]:
                    son_t = datetime.strptime(u_info[0], "%Y-%m-%d").date()
                    fark = (bugun - son_t).days
                    if fark == 1: vt_sorgu("UPDATE users SET streak=streak+1, son_giris=? WHERE username=?", (str(bugun), u), commit=True)
                    elif fark > 1: vt_sorgu("UPDATE users SET streak=1, son_giris=? WHERE username=?", (str(bugun), u), commit=True)
                else: vt_sorgu("UPDATE users SET streak=1, son_giris=? WHERE username=?", (str(bugun), u), commit=True)
                st.rerun()
    with t2:
        nu, np = st.text_input("Kullanıcı Adı"), st.text_input("Şifre ", type="password")
        ns = st.selectbox("Sınıf ", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
        if st.button("Kayıt Ol ve 7 Gün Deneme Kazan"):
            if len(nu) > 2 and len(np) > 5 and not vt_sorgu("SELECT 1 FROM users WHERE username=?", (nu,)):
                h_np = hashlib.sha256((np + "tbozkurt_salt_2026").encode()).hexdigest()
                # 🚨 7 GÜNLÜK DENEME HESAPLAMA
                deneme_sonu = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", (nu, h_np, ns, str(datetime.now().date()), 0, 0, deneme_sonu, 0, None), commit=True)
                st.success("🐺 Kayıt Başarılı! 7 Günlük Deneme Tanımlandı."); time.sleep(1)
    st.stop()

# --- 5. SIDEBAR VE PREMIUM DURUM KONTROLÜ ---
u_data = vt_sorgu("SELECT xp, sinif, streak, premium, deneme_bitis FROM users WHERE username=?", (st.session_state.user,))[0]
u_xp, u_sinif, u_streak, u_pre, u_bitis = u_data

# Deneme Süresi Kontrolü (🚨 Otomatik Premium Düşürme)
is_trial_active = False
if not st.session_state.admin:
    bugun = datetime.now().date()
    bitis_tarihi = datetime.strptime(u_bitis, "%Y-%m-%d").date()
    if bugun <= bitis_tarihi:
        is_trial_active = True # Deneme süresi içinde her yer açık

with st.sidebar:
    st.title(f"🐺 {st.session_state.user}")
    st.metric("🔥 Seri", f"{u_streak} Gün")
    st.metric("🏆 XP", u_xp)
    if u_pre or is_trial_active: st.success("💎 Premium / Deneme Aktif")
    else: st.error("🛡️ Süre Doldu! Lisans Gerekiyor")
    
    st.divider()
    menu = st.radio("Menü", ["📊 Karargah", "📚 Eğitim", "🛠️ Admin"] if st.session_state.admin else ["📊 Karargah", "📚 Eğitim"])
    if st.button("🚪 Ayrıl"): st.session_state.clear(); st.rerun()

# --- 6. KARARGAH (DASHBOARD) ---
if menu == "📊 Karargah":
    st.subheader("📊 Alfa Gelişim Analizi")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Tamamlanan Konu", vt_sorgu("SELECT COUNT(*) FROM tamamlanan_konular WHERE username=?", (st.session_state.user,))[0][0])
    with c2:
        st.metric("Kalan Deneme", f"{(datetime.strptime(u_bitis, '%Y-%m-%d').date() - datetime.now().date()).days} Gün")
    
    xp_log = vt_sorgu("SELECT tarih, SUM(xp) FROM xp_log WHERE username=? GROUP BY tarih", (st.session_state.user,))
    if xp_log:
        df = pd.DataFrame(xp_log, columns=["Tarih", "XP"])
        st.line_chart(df.set_index("Tarih"))

# --- 7. EĞİTİM MODÜLÜ (🚨 TÜM ÖZELLİKLER AKTİF) ---
elif menu == "📚 Eğitim":
    dersler = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (u_sinif,))
    sec_d = st.selectbox("Ders", [d[1] for d in dersler])
    d_id = [d[0] for d in dersler if d[1] == sec_d][0]
    konular = vt_sorgu("SELECT id, ad, icerik, quiz_icerik, podcast_path FROM konular WHERE ders_id=?", (d_id,))
    
    if konular:
        sec_k = st.selectbox("Konu", [k[1] for k in konular])
        k_id, k_ad, k_ic, k_qz, k_pod = [k for k in konular if k[1] == sec_k][0]
        
        t1, t2, t3 = st.tabs(["📖 Ders Anlatımı", "⚔️ Bilgi Savaşı (Quiz)", "🎧 Podcast"])
        
        with t1:
            st.markdown(json.loads(k_ic).get("anlatim", "Mühürlenmemiş."))
            if st.button("✅ Konuyu Bitir (+10 XP)"):
                if not vt_sorgu("SELECT 1 FROM tamamlanan_konular WHERE username=? AND konu_id=?", (st.session_state.user, k_id)):
                    vt_sorgu("UPDATE users SET xp=xp+10 WHERE username=?", (st.session_state.user,), commit=True)
                    vt_sorgu("INSERT INTO tamamlanan_konular VALUES (?,?)", (st.session_state.user, k_id), commit=True)
                    st.success("Tebrikler!"); st.rerun()
        
        with t2:
            if not u_pre and not is_trial_active:
                st.warning("Bu özellik Premium lisans gerektirir."); st.stop()
            if k_qz:
                quiz = json.loads(k_qz)
                with st.form(f"quiz_{k_id}"):
                    score = sum([1 for i, q in enumerate(quiz) if st.radio(q['soru'], q['siklar'], key=f"q_{k_id}_{i}") == q['dogru']])
                    if st.form_submit_button("Savaşı Tamamla"):
                        if not vt_sorgu("SELECT 1 FROM xp_log WHERE username=? AND tip=? AND tarih=?", (st.session_state.user, f"QUIZ_{k_id}", str(datetime.now().date()))):
                            vt_sorgu("UPDATE users SET xp=xp+? WHERE username=?", (score*5, st.session_state.user), commit=True)
                            vt_sorgu("INSERT INTO xp_log VALUES (?,?,?,?)", (st.session_state.user, str(datetime.now().date()), score*5, f"QUIZ_{k_id}"), commit=True)
                            st.success(f"⚔️ +{score*5} XP Kazandın!"); st.rerun()
            else: st.info("Quiz hazırlanıyor...")

        with t3:
            if not u_pre and not is_trial_active:
                st.warning("Bu özellik Premium lisans gerektirir."); st.stop()
            if k_pod and os.path.exists(os.path.join(BASE_DIR, k_pod)): st.audio(os.path.join(BASE_DIR, k_pod))
            else: st.info("Podcast hazırlanıyor...")

# --- 8. ADMİN: AI ÜRETİM VE LİSANS (🚨 Geliştirilmiş) ---
elif menu == "🛠️ Admin" and st.session_state.admin:
    st.subheader("🛠️ Alfa Üretim ve Lisans")
    ta, tb = st.tabs(["🚀 AI İçerik Üretimi", "💎 Lisans Üret"])
    
    with ta:
        s_s = st.selectbox("Sınıf Seç", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
        d_l = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (s_s,))
        d_id = st.selectbox("Ders Seç", [d[1] for d in d_l])
        cur_d_id = [d[0] for d in d_l if d[1] == d_id][0]
        k_l = vt_sorgu("SELECT id, ad FROM konular WHERE ders_id=?", (cur_d_id,))
        k_id = st.selectbox("Konu Seç", [k[1] for k in k_l])
        cur_k_id = [k[0] for k in k_l if k[1] == k_id][0]

        if st.button("AI İle Mühürle"):
            with st.spinner("AI ve Podcast Hazırlanıyor..."):
                prompt = f"SADECE JSON: {{'anlatim':'markdown...','quiz':[{{'soru':'','siklar':[],'dogru':''}}]}} Konu: {s_s} {d_id} {k_id}"
                try:
                    res = MODEL.generate_content(prompt).text.strip()
                    if "```json" in res: res = res.split("```json")[1].split("```")[0]
                    data = json.loads(res)
                    p_path = f"podcasts/pod_{cur_k_id}.mp3"
                    gTTS(text=data['anlatim'][:800], lang='tr').save(os.path.join(BASE_DIR, p_path))
                    vt_sorgu("UPDATE konular SET icerik=?, quiz_icerik=?, podcast_path=? WHERE id=?", 
                             (json.dumps({"anlatim":data["anlatim"]}, ensure_ascii=False), 
                              json.dumps(data["quiz"], ensure_ascii=False), p_path, cur_k_id), commit=True)
                    st.success("Başarıyla Mühürlendi!"); st.rerun()
                except Exception as e: st.error(f"Hata: {e}")

    with tb:
        # 🚨 LİSANS ÜRETME (Özel ID formatı: 15 haneli, karmaşık)
        if st.button("15 Haneli Lisans Üret"):
            l_id = ''.join(random.choices(string.ascii_uppercase + string.digits + string.ascii_lowercase, k=15))
            vt_sorgu("INSERT INTO lisanslar (lisans_id, aktif, sure_ay) VALUES (?,?,?)", (l_id, 0, 12), commit=True)
            st.code(f"Üretilen Lisans: {l_id}")
