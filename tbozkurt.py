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

# --- 1. SİSTEM YAPILANDIRMASI ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tbozkurt_final.db")

for f in ["podcasts", "quizzes"]:
    if not os.path.exists(os.path.join(BASE_DIR, f)): os.makedirs(os.path.join(BASE_DIR, f))

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except:
    st.error("⚠️ Secrets yapılandırması eksik!"); st.stop()

# --- 2. VERİTABANI VE TAM MÜFREDAT YÜKLEME ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    sonuc = []
    try:
        c.execute(sorgu, parametre)
        if commit: conn.commit()
        else: sonuc = c.fetchall()
    except Exception as e:
        if commit: conn.rollback()
        st.error(f"Sistem Hatası: {e}")
    finally: conn.close()
    return sonuc

def mufredat_enjekte_et():
    mufredat = {
        "9. Sınıf": {
            "Matematik": ["Mantık", "Kümeler", "Denklemler", "Üçgenler"],
            "Edebiyat": ["Giriş", "Hikaye", "Şiir", "Masal/Fabl"],
            "Fizik": ["Fizik Bilimine Giriş", "Madde ve Özellikleri", "Hareket ve Kuvvet"],
            "Kimya": ["Kimya Bilimi", "Atom ve Periyodik Sistem"],
            "Biyoloji": ["Hücre", "Canlılar Dünyası"]
        },
        "10. Sınıf": {
            "Matematik": ["Fonksiyonlar", "Polinomlar", "İkinci Dereceden Denklemler"],
            "Edebiyat": ["Halk Edebiyatı", "Divan Edebiyatı", "Roman"],
            "Fizik": ["Elektrik ve Manyetizma", "Basınç ve Kaldırma Kuvveti"],
            "Biyoloji": ["Kalıtım", "Ekosistem Ekolojisi"]
        },
        "11. Sınıf": {
            "Matematik": ["Trigonometri", "Analitik Geometri", "Fonksiyonlarda Uygulamalar"],
            "Fizik": ["Kuvvet ve Hareket", "Elektriksel Kuvvet ve Alan"],
            "Kimya": ["Modern Atom Teorisi", "Gazlar", "Sıvı Çözeltiler"]
        },
        "12. Sınıf": {
            "Matematik": ["Logaritma", "Diziler", "Trigonometri 2", "Limit", "Türev", "İntegral"],
            "Fizik": ["Çembersel Hareket", "Atom Fiziğine Giriş", "Modern Fizik"],
            "Biyoloji": ["Genden Proteine", "Fotosentez", "Bitki Biyolojisi"]
        }
    }
    for sinif, dersler in mufredat.items():
        for ders, konular in dersler.items():
            d_kontrol = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))
            if d_kontrol: d_id = d_kontrol[0][0]
            else:
                vt_sorgu("INSERT INTO dersler (sinif, ad) VALUES (?,?)", (sinif, ders), commit=True)
                d_id = vt_sorgu("SELECT id FROM dersler WHERE sinif=? AND ad=?", (sinif, ders))[0][0]
            for k in konular:
                if not vt_sorgu("SELECT 1 FROM konular WHERE ders_id=? AND ad=?", (d_id, k)):
                    vt_sorgu("INSERT INTO konular (ders_id, ad, icerik, quiz_icerik, podcast_path) VALUES (?,?,?,?,?)", 
                             (d_id, k, json.dumps({"anlatim": ""}), "", ""), commit=True)

def vt_kurulum():
    vt_sorgu("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, deneme_bitis TEXT, lisans_id TEXT, son_giris TEXT, streak INTEGER DEFAULT 0)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS dersler (id INTEGER PRIMARY KEY AUTOINCREMENT, sinif TEXT, ad TEXT, UNIQUE(sinif, ad))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders_id INTEGER, ad TEXT, icerik TEXT, quiz_icerik TEXT, podcast_path TEXT, UNIQUE(ders_id, ad))", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS xp_log (username TEXT, tarih TEXT, xp INTEGER)", commit=True)
    vt_sorgu("CREATE TABLE IF NOT EXISTS tamamlanan_konular (username TEXT, konu_id INTEGER, PRIMARY KEY(username, konu_id))", commit=True)
    mufredat_enjekte_et()
    if not vt_sorgu("SELECT 1 FROM users WHERE username='admin'"):
        h_adm = hashlib.sha256((ADMIN_SIFRE + "tbozkurt_salt_2026").encode()).hexdigest()
        vt_sorgu("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)", ("admin", h_adm, "Admin", "2026-02-15", 1, 9999, "2099-12-31", "ADM-ALFA", None, 0), commit=True)

vt_kurulum()

# --- 3. GİRİŞ VE STREAK SİSTEMİ ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT")
    t1, t2 = st.tabs(["Giriş", "Kayıt"])
    with t1:
        u = st.text_input("Kullanıcı")
        p = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap"):
            h_p = hashlib.sha256((p + "tbozkurt_salt_2026").encode()).hexdigest()
            res = vt_sorgu("SELECT password FROM users WHERE username=?", (u,))
            if res and res[0][0] == h_p:
                st.session_state.user = u
                st.session_state.admin = (u == "admin")
                # Streak Güncelleme
                today = datetime.now().date()
                u_info = vt_sorgu("SELECT son_giris, streak FROM users WHERE username=?", (u,))
                if u_info[0][0]:
                    fark = (today - datetime.strptime(u_info[0][0], "%Y-%m-%d").date()).days
                    if fark == 1: vt_sorgu("UPDATE users SET streak=streak+1, son_giris=? WHERE username=?", (str(today), u), commit=True)
                    elif fark > 1: vt_sorgu("UPDATE users SET streak=1, son_giris=? WHERE username=?", (str(today), u), commit=True)
                else: vt_sorgu("UPDATE users SET streak=1, son_giris=? WHERE username=?", (str(today), u), commit=True)
                st.rerun()
    with t2:
        nu, np = st.text_input("Yeni Kullanıcı"), st.text_input("Yeni Şifre", type="password")
        ns = st.selectbox("Sınıf", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
        if st.button("Kayıt Ol"):
            h_np = hashlib.sha256((np + "tbozkurt_salt_2026").encode()).hexdigest()
            d_bit = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            vt_sorgu("INSERT INTO users (username, password, sinif, kayit_tarihi, deneme_bitis) VALUES (?,?,?,?,?)", (nu, h_np, ns, "2026-02-15", d_bit), commit=True)
            st.success("Kayıt başarılı!"); time.sleep(1)
    st.stop()

# --- 4. PANEL VE İLERLEME ---
u_data = vt_sorgu("SELECT xp, sinif, streak, premium, deneme_bitis FROM users WHERE username=?", (st.session_state.user,))[0]
u_xp, u_sinif, u_streak, u_pre, u_deneme = u_data

with st.sidebar:
    st.title(f"🐺 {st.session_state.user}")
    st.metric("XP Puanı", f"{u_xp}")
    st.metric("🔥 Seri", f"{u_streak} Gün")
    st.divider()
    st.subheader("🏆 Liderlik")
    for i, (un, ux) in enumerate(vt_sorgu("SELECT username, xp FROM users ORDER BY xp DESC LIMIT 5"), 1):
        st.write(f"{i}. {un} - {ux} XP")
    st.divider()
    menu = st.radio("Menü", ["📚 Dersler", "🛠️ Admin"] if st.session_state.admin else ["📚 Dersler"])
    if st.button("🚪 Çıkış"): st.session_state.clear(); st.rerun()

# --- 5. EĞİTİM MODÜLÜ ---
if menu == "📚 Dersler":
    # İlerleme Yüzdesi
    total_k = vt_sorgu("SELECT COUNT(*) FROM konular k JOIN dersler d ON k.ders_id=d.id WHERE d.sinif=?", (u_sinif,))[0][0]
    done_k = vt_sorgu("SELECT COUNT(*) FROM tamamlanan_konular WHERE username=?", (st.session_state.user,))[0][0]
    st.subheader(f"📊 {u_sinif} İlerleme: %{int((done_k/total_k)*100) if total_k > 0 else 0}")
    st.progress(done_k/total_k if total_k > 0 else 0.0)

    dersler = vt_sorgu("SELECT id, ad FROM dersler WHERE sinif=?", (u_sinif,))
    sec_d = st.selectbox("Ders Seç", [d[1] for d in dersler])
    d_id = [d[0] for d in dersler if d[1] == sec_d][0]
    
    konular = vt_sorgu("SELECT id, ad, icerik, quiz_icerik, podcast_path FROM konular WHERE ders_id=?", (d_id,))
    sec_k = st.selectbox("Konu Seç", [k[1] for k in konular])
    k_data = [k for k in konular if k[1] == sec_k][0]
    
    t1, t2, t3 = st.tabs(["📖 Anlatım", "🎧 Podcast", "⚔️ Quiz"])
    with t1:
        anlatim = json.loads(k_data[2]).get("anlatim", "")
        if anlatim: 
            st.write(anlatim)
            if st.button("✅ Konuyu Bitirdim (+5 XP)"):
                if not vt_sorgu("SELECT 1 FROM tamamlanan_konular WHERE username=? AND konu_id=?", (st.session_state.user, k_data[0])):
                    vt_sorgu("INSERT INTO tamamlanan_konular VALUES (?,?)", (st.session_state.user, k_data[0]), commit=True)
                    vt_sorgu("UPDATE users SET xp=xp+5 WHERE username=?", (st.session_state.user,), commit=True)
                    st.balloons(); st.rerun()
        else: st.info("Bu konu için içerik henüz üretilmedi.")
    with t2:
        if k_data[4] and os.path.exists(os.path.join(BASE_DIR, k_data[4])): st.audio(os.path.join(BASE_DIR, k_data[4]))
        else: st.warning("Podcast hazır değil.")
    with t3:
        if k_data[3]:
            quiz = json.loads(k_data[3])
            with st.form(f"quiz_{k_data[0]}"):
                score = 0
                for i, q in enumerate(quiz):
                    ans = st.radio(f"{i+1}. {q['soru']}", q['siklar'], key=f"q_{k_data[0]}_{i}")
                    if ans == q['dogru']: score += 1
                if st.form_submit_button("Testi Bitir"):
                    vt_sorgu("UPDATE users SET xp=xp+? WHERE username=?", (score*5, st.session_state.user), commit=True)
                    st.success(f"+{score*5} XP Kazandın!"); time.sleep(1); st.rerun()
        else: st.warning("Quiz hazır değil.")

# --- 6. ADMIN MOTORU ---
elif menu == "🛠️ Admin" and st.session_state.admin:
    st.subheader("🚀 AI İçerik Üretimi")
    s_sec = st.selectbox("Hedef Sınıf", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
    d_sec = st.selectbox("Hedef Ders", [d[1] for d in vt_sorgu("SELECT ad FROM dersler WHERE sinif=?", (s_sec,))])
    k_sec = st.selectbox("Hedef Konu", [k[1] for k in vt_sorgu("SELECT k.ad FROM konular k JOIN dersler d ON k.ders_id=d.id WHERE d.sinif=? AND d.ad=?", (s_sec, d_sec))])
    
    if st.button("Mühürle ve Yayınla"):
        with st.spinner("Kurtlar içeriği hazırlıyor..."):
            prompt = f"{s_sec} {d_sec} {k_sec} konusu için kapsamlı anlatım ve 3 soruluk quiz üret. Format JSON: {{'anlatim':'...', 'quiz':[{{'soru':'','siklar':['','','',''],'dogru':''}}]}}"
            res = MODEL.generate_content(prompt)
            try:
                data = json.loads(res.text.strip().replace("```json","").replace("```",""))
                p_path = f"podcasts/p_{int(time.time())}.mp3"
                gTTS(data["anlatim"][:500], lang="tr").save(os.path.join(BASE_DIR, p_path))
                k_id = vt_sorgu("SELECT k.id FROM konular k JOIN dersler d ON k.ders_id=d.id WHERE d.sinif=? AND d.ad=? AND k.ad=?", (s_sec, d_sec, k_sec))[0][0]
                vt_sorgu("UPDATE konular SET icerik=?, quiz_icerik=?, podcast_path=? WHERE id=?", 
                         (json.dumps({"anlatim":data["anlatim"]}, ensure_ascii=False), json.dumps(data["quiz"], ensure_ascii=False), p_path, k_id), commit=True)
                st.success("✅ İçerik başarıyla mühürlendi!"); st.rerun()
            except Exception as e: st.error(f"Hata: {e}")
