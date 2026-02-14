import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json
import time
import secrets
import string
import hashlib
from datetime import datetime

# --- 1. YAPILANDIRMA VE TAM MÜFREDAT ---
st.set_page_config(page_title="T-BOZKURT v3.5", layout="wide", page_icon="🐺")

# Müfredat (9-12 Tüm Temel Dersler ve Konular)
MUFREDAT = {
    "9. Sınıf": {
        "Matematik": ["Mantık", "Kümeler", "Üçgenler", "Veri"],
        "Türk Dili ve Edebiyatı": ["Hikaye", "Şiir", "Roman"],
        "Fizik": ["Hareket", "Enerji", "Isı ve Sıcaklık"],
        "Kimya": ["Atom ve Periyodik Sistem", "Kimya Bilimi"]
    },
    "10. Sınıf": {
        "Matematik": ["Fonksiyonlar", "Polinomlar", "Dörtgenler"],
        "Biyoloji": ["Hücre Bölünmeleri", "Kalıtım"],
        "Tarih": ["Osmanlı Kuruluş", "Selçuklu Dönemi"],
        "Coğrafya": ["İç Kuvvetler", "Dış Kuvvetler"]
    },
    "11. Sınıf": {
        "Matematik (AYT)": ["Trigonometri", "Analitik Geometri", "Limit"],
        "Fizik (AYT)": ["Vektörler", "Newton Yasaları", "Atışlar"],
        "Kimya (AYT)": ["Modern Atom Teorisi", "Gazlar", "Sıvı Çözeltiler"]
    },
    "12. Sınıf": {
        "Matematik (AYT)": ["Türev", "İntegral", "Logaritma"],
        "Edebiyat (AYT)": ["Cumhuriyet Dönemi", "Batı Etkisi"],
        "Biyoloji (AYT)": ["Genden Proteine", "Bitki Biyolojisi"]
    }
}

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except:
    st.error("⚠️ Secrets yapılandırması eksik!")

# --- 2. VERİTABANI MOTORU ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    conn = sqlite3.connect('tbozkurt_pro.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute(sorgu, parametre)
        if commit: conn.commit()
        sonuc = c.fetchall()
        return sonuc, (c.rowcount if c.rowcount != -1 else len(sonuc))
    except:
        if commit: conn.rollback()
        return [], 0
    finally:
        conn.close()

def vt_baslat():
    vt_sorgu('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders TEXT, sinif TEXT, konu_adi TEXT, icerik TEXT, ses_yolu TEXT)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS sorular (id INTEGER PRIMARY KEY AUTOINCREMENT, konu_id INTEGER, soru_metni TEXT, a TEXT, b TEXT, c TEXT, d TEXT, cevap TEXT, cozum TEXT)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS licenses (kod TEXT PRIMARY KEY, kullanildi INTEGER DEFAULT 0)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS test_sonuclari (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ders TEXT, dogru INTEGER, yanlis INTEGER, net REAL, tarih TEXT)''', commit=True)
    vt_sorgu("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_question ON sorular (konu_id, soru_metni)", commit=True)

vt_baslat()

# --- 3. YARDIMCI ARAÇLAR ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def deneme_bilgisi(u):
    res, _ = vt_sorgu("SELECT kayit_tarihi, premium, xp FROM users WHERE username=?", (u,))
    if not res: return 0, 0, 0
    dt = datetime.strptime(res[0][0], "%Y-%m-%d %H:%M")
    kalan = 7 - (datetime.now() - dt).total_seconds() / 86400
    return max(0, int(kalan)), res[0][1], res[0][2]

# --- 4. OTURUM VE PANEL ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT")
    tab1, tab2 = st.tabs(["Giriş", "Kayıt"])
    with tab1:
        with st.form("g"):
            ui, pi = st.text_input("Kullanıcı Adı"), st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş"):
                d, _ = vt_sorgu("SELECT password FROM users WHERE username=?", (ui,))
                if d and d[0][0] == hash_pass(pi): st.session_state.user = ui; st.rerun()
                else: st.error("Hatalı!")
    with tab2:
        with st.form("k"):
            u, p, s = st.text_input("Kullanıcı Adı"), st.text_input("Şifre", type="password"), st.selectbox("Sınıf", list(MUFREDAT.keys()))
            if st.form_submit_button("Katıl"):
                res, _ = vt_sorgu("SELECT * FROM users WHERE username=?", (u,))
                if res: st.error("Alınmış.")
                else:
                    vt_sorgu("INSERT INTO users (username, password, sinif, kayit_tarihi) VALUES (?,?,?,?)", (u, hash_pass(p), s, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                    st.success("Başarılı!"); st.balloons()
    st.stop()

u_name = st.session_state.user
k_gun, is_pre, u_xp = deneme_bilgisi(u_name)

with st.sidebar:
    st.title(f"🐺 {u_name}")
    st.metric("🔥 Toplam XP", u_xp)
    if not is_pre:
        st.warning(f"⏳ Deneme: {k_gun} Gün")
        lkod = st.text_input("Lisans Kodu")
        if st.button("Aktif Et"):
            res, _ = vt_sorgu("SELECT * FROM licenses WHERE kod=? AND kullanildi=0", (lkod,))
            if res:
                vt_sorgu("UPDATE users SET premium=1 WHERE username=?", (u_name,), commit=True)
                vt_sorgu("UPDATE licenses SET kullanildi=1 WHERE kod=?", (lkod,), commit=True)
                st.success("Premium!"); st.rerun()
    else: st.success("💎 PREMIUM")
    if st.button("Çıkış"): del st.session_state.user; st.rerun()
    is_admin = (st.text_input("Admin", type="password") == ADMIN_SIFRE)

if k_gun <= 0 and not is_pre: st.error("Süre bitti!"); st.stop()

# --- 5. MODÜLLER ---
tabs = st.tabs(["📚 Ders Çalış", "📊 Analiz", "🛠️ Admin"] if is_admin else ["📚 Ders Çalış", "📊 Analiz"])

with tabs[0]:
    rs, _ = vt_sorgu("SELECT sinif FROM users WHERE username=?", (u_name,))
    if rs:
        s_bilgi = rs[0][0]
        dl, _ = vt_sorgu("SELECT DISTINCT ders FROM konular WHERE sinif=?", (s_bilgi,))
        if dl:
            s_ders = st.selectbox("Ders", [d[0] for d in dl])
            kl, _ = vt_sorgu("SELECT id, konu_adi FROM konular WHERE ders=? AND sinif=?", (s_ders, s_bilgi))
            if kl:
                sk_ad = st.selectbox("Konu", [k[1] for k in kl])
                kid = [k[0] for k in kl if k[1] == sk_ad][0]
                
                c1, c2 = st.tabs(["📖 Konu Anlatımı", "📝 Test Çöz"])
                with c1:
                    detay, _ = vt_sorgu("SELECT icerik FROM konular WHERE id=?", (kid,))
                    st.markdown(detay[0][0])
                with c2:
                    sorular, _ = vt_sorgu("SELECT * FROM sorular WHERE konu_id=? ORDER BY RANDOM() LIMIT 15", (kid,))
                    if sorular:
                        with st.form(f"t_{kid}"):
                            cevaplar = {}
                            for i, s in enumerate(sorular):
                                st.info(f"**Soru {i+1}:** {s[2]}")
                                cevaplar[i] = st.radio(f"Seçenekler {i}", [f"A) {s[3]}", f"B) {s[4]}", f"C) {s[5]}", f"D) {s[6]}"], key=f"s_{s[0]}")
                            if st.form_submit_button("Testi Tamamla"):
                                ds = sum(1 for i, s in enumerate(sorular) if cevaplar[i].startswith(s[7].upper()))
                                n = ds - ((len(sorular)-ds)*0.25)
                                vt_sorgu("UPDATE users SET xp = xp + ? WHERE username=?", (ds*20, u_name), commit=True)
                                vt_sorgu("INSERT INTO test_sonuclari (username, ders, dogru, yanlis, net, tarih) VALUES (?,?,?,?,?,?)", (u_name, s_ders, ds, len(sorular)-ds, n, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                                
                                # Görsel Kart Görünümü
                                st.success(f"🎯 Test Tamamlandı! Net: {n}")
                                for i, s in enumerate(sorular):
                                    with st.expander(f"Soru {i+1} Analizi"):
                                        st.write(f"Senin Cevabın: {cevaplar[i]}")
                                        st.write(f"Doğru Cevap: **{s[7].upper()}**")
                                        st.markdown(f"**💡 Çözüm:** {s[8]}")
                                st.balloons()
                    else: st.info("Soru yok.")

with tabs[1]:
    v, _ = vt_sorgu("SELECT ders, net, tarih FROM test_sonuclari WHERE username=?", (u_name,))
    if v:
        df = pd.DataFrame(v, columns=["Ders", "Net", "Tarih"])
        st.line_chart(df.set_index("Tarih")["Net"])
        st.dataframe(df.tail(10), use_container_width=True)

# --- 6. ADMIN (HIZLANDIRILMIŞ DİNAMİK BATCH) ---
if is_admin:
    with tabs[-1]:
        st.subheader("🛡️ Yönetim Merkezi")
        if st.button("📌 Müfredatı Güncelle (9-12)"):
            c = 0
            for snf, drsler in MUFREDAT.items():
                for drs, knlar in drsler.items():
                    for kn in knlar:
                        ex, _ = vt_sorgu("SELECT id FROM konular WHERE ders=? AND sinif=? AND konu_adi=?", (drs, snf, kn))
                        if not ex:
                            vt_sorgu("INSERT INTO konular (ders, sinif, konu_adi, icerik) VALUES (?,?,?,?)", (drs, snf, kn, f"{kn} hakkında akademik notlar..."), commit=True)
                            c += 1
            st.success(f"{c} Konu eklendi.")

        st.divider()
        st.subheader("🤖 Dinamik Soru Fabrikası")
        fs = st.selectbox("Sınıf", list(MUFREDAT.keys()))
        dl_a, _ = vt_sorgu("SELECT DISTINCT ders FROM konular WHERE sinif=?", (fs,))
        fd = st.selectbox("Ders", [d[0] for d in dl_a] if dl_a else ["Boş"])
        kl_a, _ = vt_sorgu("SELECT id, konu_adi FROM konular WHERE ders=? AND sinif=?", (fd, fs))
        fk_ad = st.selectbox("Konu", [k[1] for k in kl_a] if kl_a else ["Boş"])
        
        # Dinamik Batch Ayarı
        batch_hizi = st.select_slider("Üretim Hızı (Batch)", options=[3, 5, 8, 10], value=5)
        fn = st.number_input("Hedef Soru Sayısı", 5, 200, 20)
        
        if st.button("🚀 Akıllı Üretimi Başlat"):
            f_kid = [k[0] for k in kl_a if k[1] == fk_ad][0]
            toplam, deneme, max_d = 0, 0, fn*3
            pb = st.progress(0.0)
            status = st.empty()
            
            while toplam < fn and deneme < max_d:
                deneme += 1
                kalan = min(batch_hizi, fn - toplam)
                status.info(f"⏳ İlerleme: {toplam}/{fn} | AI Sınıf: {fs}")
                
                prompt = f"""
                GÖREV: {fs} {fd} - {fk_ad} konusu için {kalan} adet YKS tarzı soru üret.
                JSON FORMAT: [{{'soru': '..', 'a': '..', 'b': '..', 'c': '..', 'd': '..', 'cevap': 'a', 'cozum': '..'}}]
                KURAL: Soru metninde çift tırnak (") kullanma.
                """
                try:
                    res = MODEL.generate_content(prompt)
                    raw = res.text.strip()
                    if "```" in raw: raw = raw.split("```")[1].replace("json", "")
                    
                    s_list = json.loads(raw)
                    for s in s_list:
                        _, row = vt_sorgu("INSERT OR IGNORE INTO sorular (konu_id, soru_metni, a, b, c, d, cevap, cozum) VALUES (?,?,?,?,?,?,?,?)", 
                                         (f_kid, s["soru"], s["a"], s["b"], s["c"], s["d"], s["cevap"].lower(), s["cozum"]), commit=True)
                        if row > 0: toplam += 1
                    pb.progress(min(toplam/fn, 1.0))
                    time.sleep(1.5) # API Güvenlik Beklemesi
                except:
                    time.sleep(2)
            status.success(f"✅ İşlem bitti! {toplam} yeni soru mühürlendi.")
