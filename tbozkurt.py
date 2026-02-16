import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json, time, hashlib, random, string, os
from datetime import datetime, timedelta

# --- 1. SİSTEM YAPILANDIRMASI ---
st.set_page_config(page_title="T-BOZKURT v34.0", layout="wide", page_icon="🐺")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tbozkurt_master.db")

for f in ["podcasts", "quizzes", "backups"]:
    os.makedirs(os.path.join(BASE_DIR, f), exist_ok=True)

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except Exception as e:
    st.error("⚠️ Secrets (Sırlar) yapılandırması eksik! Lütfen GEMINI_KEY ve ADMIN_KEY'i ekleyin.")
    st.stop()

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
        with open("hata_log.txt", "a") as f: f.write(f"[{datetime.now()}] VT Hatası: {e}\n")
        return None

def mufredat_enjekte_et():
    json_path = os.path.join(BASE_DIR, "mufredat.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                muf = json.load(f)
                for s, ds in muf.items():
                    for d, ks in ds.items():
                        vt_sorgu("INSERT OR IGNORE INTO dersler (sinif, ad) VALUES (?,?)", (s, d), commit=True)
                        d_res = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (s, d))
                        if d_res:
                            d_id = d_res[0][0]
                            for k in ks:
                                vt_sorgu("INSERT OR IGNORE INTO konular (ders_id, ad, icerik, quiz_icerik, podcast_path) VALUES (?,?,?,?,?)", 
                                         (d_id, k, json.dumps({"anlatim":""}), "", ""), commit=True)
            except: pass

def vt_kurulum():
    vt_sorgu("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, deneme_bitis TEXT, streak INTEGER DEFAULT 0, son_giris TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS xp_log (username TEXT, tarih TEXT, xp INTEGER, tip TEXT)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS tamamlanan_konular (username TEXT, konu_id INTEGER, PRIMARY KEY(username, konu_id))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS lisanslar (lisans_id TEXT PRIMARY KEY, aktif INTEGER DEFAULT 0, sure_ay INTEGER DEFAULT 12)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS dersler (id INTEGER PRIMARY KEY AUTOINCREMENT, sinif TEXT, ad TEXT, UNIQUE(sinif, ad))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders_id INTEGER, ad TEXT, icerik TEXT, quiz_icerik TEXT, podcast_path TEXT, UNIQUE(ders_id, ad))", commit=True)
    mufredat_enjekte_et()
    if not vt_sorgu("SELECT 1 FROM users WHERE username='admin'"):
        h_adm = hashlib.sha256((ADMIN_SIFRE + "tbozkurt_salt_2026").encode()).hexdigest()
        vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", ("admin", h_adm, "Admin", "2026-02-16", 1, 9999, "2099-12-31", 0, None), commit=True)

vt_kurulum()

# --- 3. OTURUM VE STREAK ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Karargah")
    t1, t2 = st.tabs(["🔑 Giriş Yap", "📝 Kayıt Ol"])
    with t1:
        u = st.text_input("Kullanıcı Adı")
        p = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap", use_container_width=True):
            h_p = hashlib.sha256((p + "tbozkurt_salt_2026").encode()).hexdigest()
            res = vt_sorgu("SELECT password FROM users WHERE username=?", (u,))
            if not res: st.error("❌ Kullanıcı bulunamadı!")
            elif res[0][0] == h_p:
                today = datetime.now().date()
                last_data = vt_sorgu("SELECT son_giris, streak FROM users WHERE username=?", (u,))
                if last_data:
                    son, eski_streak = last_data[0]
                    if son and son.strip() != "":
                        son_tarih = datetime.strptime(son, "%Y-%m-%d").date()
                        if son_tarih == today - timedelta(days=1): yeni_streak = eski_streak + 1
                        elif son_tarih == today: yeni_streak = eski_streak
                        else: yeni_streak = 1
                    else: yeni_streak = 1
                    vt_sorgu("UPDATE users SET streak=?, son_giris=? WHERE username=?", (yeni_streak, str(today), u), commit=True)
                st.session_state.user = u
                st.session_state.admin = (u == "admin")
                st.rerun()
            else: st.error("❌ Hatalı şifre!")
    with t2:
        nu, np = st.text_input("Yeni Kullanıcı"), st.text_input("Yeni Şifre", type="password")
        ns = st.selectbox("Sınıfınız", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
        if st.button("Kaydı Tamamla"):
            if len(nu) > 2 and len(np) > 5 and not vt_sorgu("SELECT 1 FROM users WHERE username=?", (nu,)):
                h_np = hashlib.sha256((np + "tbozkurt_salt_2026").encode()).hexdigest()
                d_bitis = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", (nu, h_np, ns, str(datetime.now().date()), 0, 0, d_bitis, 1, str(datetime.now().date())), commit=True)
                st.success("🐺 Kayıt Başarılı! 7 Günlük Deneme Başladı."); time.sleep(1); st.rerun()
    st.stop()

# --- 4. PREMİUM & VERİ KONTROLÜ ---
res_data = vt_sorgu("SELECT xp, sinif, streak, premium, deneme_bitis FROM users WHERE username=?", (st.session_state.user,))
if not res_data: st.session_state.clear(); st.rerun()
u_xp, u_sinif, u_streak, u_pre, u_bitis = res_data[0]

premium_aktif = False
if u_bitis:
    try:
        premium_aktif = datetime.now().date() <= datetime.strptime(u_bitis, "%Y-%m-%d").date()
    except: premium_aktif = False

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title(f"🐺 {st.session_state.user}")
    st.metric("🏆 XP", u_xp)
    st.metric("🔥 Seri", f"{u_streak} Gün")
    if premium_aktif: st.success("💎 Erişim Aktif")
    else: st.warning("🛡️ Lisans Gerekli")
    
    menu = st.radio("Operasyon Merkezi", ["📊 Karargah", "📚 Eğitim", "🛠️ Admin"] if st.session_state.admin else ["📊 Karargah", "📚 Eğitim"])
    
    st.divider()
    st.subheader("💎 Lisans Aktifleştir")
    kod = st.text_input("15 Haneli Kod", key="lic_input")
    if st.button("Kodu Aktifleştir"):
        l_res = vt_sorgu("SELECT sure_ay FROM lisanslar WHERE lisans_id=? AND aktif=0", (kod,))
        if l_res and len(l_res) > 0:
            sure = l_res[0][0]
            yeni_bitis = (datetime.now() + timedelta(days=30*sure)).strftime("%Y-%m-%d")
            vt_sorgu("UPDATE users SET premium=1, deneme_bitis=? WHERE username=?", (yeni_bitis, st.session_state.user), commit=True)
            vt_sorgu("UPDATE lisanslar SET aktif=1 WHERE lisans_id=?", (kod,), commit=True)
            st.success(f"🚀 {sure} Aylık Premium Aktif Edildi!"); time.sleep(1); st.rerun()
        else: st.error("❌ Geçersiz Kod!")
    
    if st.button("🚪 Ayrıl"): st.session_state.clear(); st.rerun()

# --- 6. MODÜLLER ---
if menu == "📊 Karargah":
    st.subheader("📊 Analitik Gelişim")
    xp_log = vt_sorgu("SELECT tarih, SUM(xp) FROM xp_log WHERE username=? GROUP BY tarih ORDER BY tarih ASC", (st.session_state.user,))
    if xp_log:
        df = pd.DataFrame(xp_log, columns=["Tarih", "Kazanılan XP"])
        st.line_chart(df.set_index("Tarih"))
    else: st.info("Savaşa başla ve ilk XP'ni kazan!")

elif menu == "📚 Eğitim":
    dersler = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (u_sinif,))
    if not dersler: st.warning("⚠️ Müfredat henüz yüklenmemiş."); st.stop()
    
    sec_d = st.selectbox("Ders Seç", [d[1] for d in dersler])
    d_id = [d[0] for d in dersler if d[1] == sec_d][0]
    konular = vt_sorgu("SELECT id, ad, icerik, quiz_icerik, podcast_path FROM konular WHERE ders_id=?", (d_id,))
    
    if konular:
        sec_k = st.selectbox("Konu Seç", [k[1] for k in konular])
        k_id, k_ad, k_ic, k_qz, k_pod = [k for k in konular if k[1] == sec_k][0]
        
        t1, t2, t3 = st.tabs(["📖 Ders", "⚔️ Quiz", "🎧 Podcast"])
        with t1:
            st.markdown(json.loads(k_ic).get("anlatim", "İçerik hazırlanıyor..."))
            if st.button("✅ Konuyu Bitir (+10 XP)"):
                if not vt_sorgu("SELECT 1 FROM tamamlanan_konular WHERE username=? AND konu_id=?", (st.session_state.user, k_id)):
                    vt_sorgu("UPDATE users SET xp=xp+10 WHERE username=?", (st.session_state.user,), commit=True)
                    vt_sorgu("INSERT INTO xp_log VALUES (?,?,?,?)", (st.session_state.user, str(datetime.now().date()), 10, "konu"), commit=True)
                    vt_sorgu("INSERT INTO tamamlanan_konular VALUES (?,?)", (st.session_state.user, k_id), commit=True)
                    st.success("Tebrikler!"); time.sleep(1); st.rerun()
        
        with t2:
            if not premium_aktif: st.error("🛡️ Premium Gerekli"); st.stop()
            if k_qz:
                qz = json.loads(k_qz)
                with st.form(f"quiz_{k_id}"):
                    cevaplar = [st.radio(q['soru'], q['siklar'], key=f"q_{k_id}_{i}") for i, q in enumerate(qz)]
                    if st.form_submit_button("Savaşı Bitir"):
                        skor = sum([1 for i, c in enumerate(cevaplar) if c == qz[i]['dogru']])
                        vt_sorgu("UPDATE users SET xp=xp+? WHERE username=?", (skor*5, st.session_state.user), commit=True)
                        vt_sorgu("INSERT INTO xp_log VALUES (?,?,?,?)", (st.session_state.user, str(datetime.now().date()), skor*5, "quiz"), commit=True)
                        st.success(f"⚔️ +{skor*5} XP!"); time.sleep(1); st.rerun()

elif menu == "🛠️ Admin" and st.session_state.admin:
    st.subheader("🛠️ Karargah Kontrol")
    ay = st.slider("Lisans Süresi (Ay)", 1, 24, 12)
    if st.button("15 Haneli Lisans Üret"):
        l_id = ''.join(random.choices(string.ascii_uppercase + string.digits + string.ascii_lowercase, k=15))
        vt_sorgu("INSERT INTO lisanslar (lisans_id, aktif, sure_ay) VALUES (?,0,?)", (l_id, ay), commit=True)
        st.code(l_id)
