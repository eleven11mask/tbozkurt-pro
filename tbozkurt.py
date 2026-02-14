import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import json
import os
import time
import secrets
import string
import hashlib
from datetime import datetime, timedelta

# --- 1. YAPILANDIRMA VE GÜVENLİK ---
st.set_page_config(page_title="T-BOZKURT v2.9.2 PRO", layout="wide", page_icon="🐺")

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except:
    st.error("⚠️ Secrets ayarları eksik! GEMINI_KEY ve ADMIN_KEY tanımlanmalı.")

# --- 2. GÜÇLENDİRİLMİŞ VERİTABANI MOTORU ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    conn = sqlite3.connect('tbozkurt_pro.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute(sorgu, parametre)
        if commit: conn.commit()
        sonuc = c.fetchall()
        # SELECT sorgularında rowcount bazen -1 döner, bu durumda len(sonuc) kullanıyoruz.
        rowcount = c.rowcount if c.rowcount != -1 else len(sonuc)
        return sonuc, rowcount
    except Exception as e:
        if commit: conn.rollback()
        raise e
    finally:
        conn.close()

def vt_baslat():
    vt_sorgu('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders TEXT, sinif TEXT, konu_adi TEXT, icerik TEXT, ses_yolu TEXT)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS sorular (id INTEGER PRIMARY KEY AUTOINCREMENT, konu_id INTEGER, soru_metni TEXT, a TEXT, b TEXT, c TEXT, d TEXT, cevap TEXT)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS licenses (kod TEXT PRIMARY KEY, kullanildi INTEGER DEFAULT 0)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS test_sonuclari (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ders TEXT, dogru INTEGER, yanlis INTEGER, net REAL, tarih TEXT)''', commit=True)
    vt_sorgu("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_question ON sorular (konu_id, soru_metni)", commit=True)

vt_baslat()

# --- 3. YARDIMCI ARAÇLAR ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def lisans_uret_pro():
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(15))

def deneme_bilgisi(username):
    res, _ = vt_sorgu("SELECT kayit_tarihi, premium, xp FROM users WHERE username=?", (username,))
    if not res: return 0, 0, 0
    kayit_dt = datetime.strptime(res[0][0], "%Y-%m-%d %H:%M")
    kalan = 7 - (datetime.now() - kayit_dt).total_seconds() / 86400
    return max(0, int(kalan)), res[0][1], res[0][2]

# --- 4. OTURUM YÖNETİMİ ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Akademik Karargah")
    t_giris, t_kayit = st.tabs(["Karargaha Giriş", "7 Günlük Deneme Başlat"])
    
    with t_kayit:
        with st.form("kayit_formu"):
            u = st.text_input("Kullanıcı Adı")
            p = st.text_input("Şifre", type="password")
            s = st.selectbox("Sınıf", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
            if st.form_submit_button("Hesap Oluştur"):
                res, _ = vt_sorgu("SELECT * FROM users WHERE username=?", (u,))
                if res: st.error("Bu kullanıcı adı alınmış.")
                else:
                    vt_sorgu("INSERT INTO users (username, password, sinif, kayit_tarihi) VALUES (?,?,?,?)",
                             (u, hash_pass(p), s, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                    st.success("Kayıt başarılı! Giriş yapınız."); st.balloons()
    
    with t_giris:
        with st.form("giris_formu"):
            u_i = st.text_input("Kullanıcı Adı")
            p_i = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap"):
                d, _ = vt_sorgu("SELECT password FROM users WHERE username=?", (u_i,))
                if d and d[0][0] == hash_pass(p_i):
                    st.session_state.user = u_i
                    st.rerun()
                else: st.error("Kullanıcı adı veya şifre hatalı!")
    st.stop()

# --- 5. PANEL VE YETKİLENDİRME ---
u_name = st.session_state.user
kalan_gun, premium_mu, u_xp = deneme_bilgisi(u_name)

with st.sidebar:
    st.title(f"🐺 {u_name}")
    st.metric("🔥 Toplam XP", u_xp)
    if premium_mu: st.success("💎 PREMIUM ÜYELİK")
    else:
        st.warning(f"⏳ Deneme: {kalan_gun} Gün")
        l_kod = st.text_input("Lisans Kodu")
        if st.button("Sistemi Aktif Et"):
            res, _ = vt_sorgu("SELECT * FROM licenses WHERE kod=? AND kullanildi=0", (l_kod,))
            if res:
                vt_sorgu("UPDATE users SET premium=1 WHERE username=?", (u_name,), commit=True)
                vt_sorgu("UPDATE licenses SET kullanildi=1 WHERE kod=?", (l_kod,), commit=True)
                st.success("Premium aktif!"); st.rerun()
            else: st.error("Geçersiz kod!")
    if st.button("Oturumu Kapat"):
        del st.session_state.user
        st.rerun()
    st.divider()
    admin_sifre_giris = st.text_input("Yönetici Kilidi", type="password")
    is_admin = (admin_sifre_giris == ADMIN_SIFRE)

if kalan_gun <= 0 and not premium_mu:
    st.error("🛑 Deneme bitti! Lisans almalısınız."); st.stop()

# --- 6. ANA MODÜLLER ---
tab_secenekleri = ["📚 Ders Çalış", "📊 Analiz"]
if is_admin: tab_secenekleri.append("🛡️ Admin")
ana_tabs = st.tabs(tab_secenekleri)

with ana_tabs[0]:
    # HATANIN DÜZELTİLDİĞİ KRİTİK ALAN
    res_sinif, _ = vt_sorgu("SELECT sinif FROM users WHERE username=?", (u_name,))
    if res_sinif:
        sinif_bilgisi = res_sinif[0][0] # Saf metin olarak çekiyoruz
        ders_listesi, _ = vt_sorgu("SELECT DISTINCT ders FROM konular WHERE sinif=?", (sinif_bilgisi,))
        
        if ders_listesi:
            secilen_ders = st.selectbox("Ders", [d[0] for d in ders_listesi])
            konu_listesi, _ = vt_sorgu("SELECT id, konu_adi FROM konular WHERE ders=? AND sinif=?", (secilen_ders, sinif_bilgisi))
            
            if konu_listesi:
                secilen_konu_ad = st.selectbox("Konu", [k[1] for k in konu_listesi])
                k_id = [k[0] for k in konu_listesi if k[1] == secilen_konu_ad][0]
                k_detay, _ = vt_sorgu("SELECT icerik, ses_yolu FROM konular WHERE id=?", (k_id,))
                
                c1, c2, c3 = st.tabs(["📖 Anlatım", "🎧 Sesli", "📝 Test"])
                with c1: st.markdown(k_detay[0][0])
                with c2: 
                    if os.path.exists(k_detay[0][1]): st.audio(k_detay[0][1])
                    else: st.info("Ses kaydı yok.")
                with c3:
                    sorular, _ = vt_sorgu("SELECT * FROM sorular WHERE konu_id=? ORDER BY RANDOM() LIMIT 15", (k_id,))
                    if sorular:
                        with st.form(f"test_{k_id}"):
                            cevaplar = {}
                            for i, s in enumerate(sorular):
                                st.write(f"**{i+1}.** {s[2]}")
                                cevaplar[i] = st.radio(f"Seçenek {i}", ["a", "b", "c", "d"], horizontal=True, key=f"q_{s[0]}")
                            if st.form_submit_button("Bitir"):
                                d_sayisi = sum(1 for i, s in enumerate(sorular) if cevaplar[i] == s[7])
                                y_sayisi = len(sorular) - d_sayisi
                                net = d_sayisi - (y_sayisi * 0.25)
                                vt_sorgu("UPDATE users SET xp = xp + ? WHERE username=?", (d_sayisi*20, u_name), commit=True)
                                vt_sorgu("INSERT INTO test_sonuclari (username, ders, dogru, yanlis, net, tarih) VALUES (?,?,?,?,?,?)",
                                         (u_name, secilen_ders, d_sayisi, y_sayisi, net, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                                st.success(f"Net: {net} | +{d_sayisi*20} XP"); st.balloons()
                    else: st.info("Soru eklenmemiş.")
    else: st.info("Ders/Konu bulunamadı.")

with ana_tabs[1]:
    st.header("📊 Gelişim")
    veriler, _ = vt_sorgu("SELECT ders, dogru, yanlis, net, tarih FROM test_sonuclari WHERE username=?", (u_name,))
    if veriler:
        df = pd.DataFrame(veriler, columns=["Ders", "Doğru", "Yanlış", "Net", "Tarih"])
        st.dataframe(df, use_container_width=True)
        st.line_chart(df.set_index("Tarih")["Net"])

# --- 7. ADMIN PANELİ (YÜKSEK PERFORMANS) ---
if is_admin:
    with ana_tabs[-1]:
        st.header("🛡️ Yönetici Paneli")
        col_l, col_a = st.columns(2)
        with col_l:
            if st.button("10 Lisans Üret"):
                kodlar = [lisans_uret_pro() for _ in range(10)]
                for k in kodlar: vt_sorgu("INSERT INTO licenses (kod) VALUES (?)", (k,), commit=True)
                st.code("\n".join(kodlar))
        with col_a:
            st.subheader("🤖 Soru Fabrikası")
            a_s = st.selectbox("Sınıf", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
            a_d = st.text_input("Ders")
            a_k = st.text_input("Konu")
            a_n = st.number_input("Adet", 10, 200, 50)
            if st.button("🚀 Üret"):
                if not a_d or not a_k: st.error("Eksik bilgi!"); st.stop()
                k_kontrol, _ = vt_sorgu("SELECT id FROM konular WHERE ders=? AND sinif=? AND konu_adi=?", (a_d, a_s, a_k))
                if k_kontrol: kid = k_kontrol[0][0]
                else:
                    vt_sorgu("INSERT INTO konular (ders, sinif, konu_adi, icerik, ses_yolu) VALUES (?,?,?,?,?)", (a_d, a_s, a_k, f"{a_k} özeti.", ""), commit=True)
                    kid = vt_sorgu("SELECT id FROM konular WHERE ders=? AND sinif=? AND konu_adi=?", (a_d, a_s, a_k))[0][0]

                toplam, deneme, max_d, batch = 0, 0, a_n*2, 20
                pb = st.progress(0.0)
                while toplam < a_n and deneme < max_d:
                    deneme += 1
                    kalan = min(batch, a_n - toplam)
                    prompt = f"{a_s} {a_d} {a_k} için {kalan} soru üret. JSON format: [{{'soru': '...', 'a': '...', 'b': '...', 'c': '...', 'd': '...', 'cevap': 'a/b/c/d'}}]"
                    try:
                        res = MODEL.generate_content(prompt)
                        s_list = json.loads(res.text.replace("```json", "").replace("```", "").strip())
                        for s in s_list:
                            if s["cevap"].lower() in ["a", "b", "c", "d"]:
                                _, row = vt_sorgu("INSERT OR IGNORE INTO sorular (konu_id, soru_metni, a, b, c, d, cevap) VALUES (?,?,?,?,?,?,?)",
                                                  (kid, s["soru"], s["a"], s["b"], s["c"], s["d"], s["cevap"].lower()), commit=True)
                                if row > 0: toplam += 1
                        pb.progress(min(toplam/a_n, 1.0))
                        time.sleep(1.3)
                    except: continue
                st.success(f"✅ {toplam} soru eklendi!")
