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
st.set_page_config(page_title="T-BOZKURT v2.9 PRO", layout="wide", page_icon="🐺")

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except:
    st.error("⚠️ Secrets ayarları eksik! GEMINI_KEY ve ADMIN_KEY tanımlanmalı.")

# --- 2. OPTİMİZE EDİLMİŞ VERİTABANI MOTORU ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    conn = sqlite3.connect('tbozkurt_pro.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute(sorgu, parametre)
        if commit: conn.commit()
        sonuc = c.fetchall()
        rowcount = c.rowcount # v2.9: Etkilenen satır sayısı (Performans için kritik)
        return sonuc, rowcount
    finally:
        conn.close()

def vt_baslat():
    # Tablo Kurulumları
    vt_sorgu('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, sinif TEXT, kayit_tarihi TEXT, premium INTEGER DEFAULT 0, xp INTEGER DEFAULT 0)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS konular (id INTEGER PRIMARY KEY AUTOINCREMENT, ders TEXT, sinif TEXT, konu_adi TEXT, icerik TEXT, ses_yolu TEXT)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS sorular (id INTEGER PRIMARY KEY AUTOINCREMENT, konu_id INTEGER, soru_metni TEXT, a TEXT, b TEXT, c TEXT, d TEXT, cevap TEXT)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS licenses (kod TEXT PRIMARY KEY, kullanildi INTEGER DEFAULT 0)''', commit=True)
    vt_sorgu('''CREATE TABLE IF NOT EXISTS test_sonuclari (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ders TEXT, dogru INTEGER, yanlis INTEGER, net REAL, tarih TEXT)''', commit=True)
    # Mükerrer soru engelleme indeksi
    vt_sorgu("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_question ON sorular (konu_id, soru_metni)", commit=True)

vt_baslat()

# --- 3. YARDIMCI ARAÇLAR ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def lisans_uret_pro():
    # 15 Karakterli, tahmin edilemez lisans yapısı
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
                    st.success("Kayıt başarılı! Giriş sekmesine geçiniz."); st.balloons()
    
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
    
    if premium_mu:
        st.success("💎 PREMIUM ÜYELİK")
    else:
        st.warning(f"⏳ Deneme Süresi: {kalan_gun} Gün")
        l_kod = st.text_input("Lisans Kodunu Onayla")
        if st.button("Sistemi Aktif Et"):
            res, _ = vt_sorgu("SELECT * FROM licenses WHERE kod=? AND kullanildi=0", (l_kod,))
            if res:
                vt_sorgu("UPDATE users SET premium=1 WHERE username=?", (u_name,), commit=True)
                vt_sorgu("UPDATE licenses SET kullanildi=1 WHERE kod=?", (l_kod,), commit=True)
                st.success("Tebrikler! Premium aktif."); st.rerun()
            else: st.error("Geçersiz veya kullanılmış kod!")
            
    if st.button("Oturumu Kapat"):
        del st.session_state.user
        st.rerun()
    
    st.divider()
    admin_sifre_giris = st.text_input("Yönetici Kilidi", type="password")
    is_admin = (admin_sifre_giris == ADMIN_SIFRE)

# Deneme süresi kontrolü
if kalan_gun <= 0 and not premium_mu:
    st.error("🛑 Deneme süreniz doldu. Eğitime devam etmek için Premium Lisans almalısınız.")
    st.stop()

# --- 6. ANA MODÜLLER ---
tab_secenekleri = ["📚 Ders Çalış", "📊 Gelişim Analizi"]
if is_admin: tab_secenekleri.append("🛡️ Admin Paneli")
ana_tabs = st.tabs(tab_secenekleri)

with ana_tabs[0]:
    u_sinif = vt_sorgu("SELECT sinif FROM users WHERE username=?", (u_name,))[0][0][0] # İlk harf/rakam
    # Sınıfa göre dersleri getir
    sinif_bilgisi = vt_sorgu("SELECT sinif FROM users WHERE username=?", (u_name,))[0][0]
    ders_listesi, _ = vt_sorgu("SELECT DISTINCT ders FROM konular WHERE sinif=?", (sinif_bilgisi,))
    
    if ders_listesi:
        secilen_ders = st.selectbox("Çalışmak İstediğin Ders", [d[0] for d in ders_listesi])
        konu_listesi, _ = vt_sorgu("SELECT id, konu_adi FROM konular WHERE ders=? AND sinif=?", (secilen_ders, sinif_bilgisi))
        
        if konu_listesi:
            secilen_konu_ad = st.selectbox("Konu Seçimi", [k[1] for k in konu_listesi])
            k_id = [k[0] for k in konu_listesi if k[1] == secilen_konu_ad][0]
            k_detay, _ = vt_sorgu("SELECT icerik, ses_yolu FROM konular WHERE id=?", (k_id,))
            
            c1, c2, c3 = st.tabs(["📖 Konu Anlatımı", "🎧 Sesli Dinle", "📝 Test Çöz"])
            with c1: st.markdown(k_detay[0][0])
            with c2: 
                if os.path.exists(k_detay[0][1]): st.audio(k_detay[0][1])
                else: st.info("Bu konu için henüz ses kaydı üretilmemiş.")
            with c3:
                # Test Motoru
                sorular, _ = vt_sorgu("SELECT * FROM sorular WHERE konu_id=? ORDER BY RANDOM() LIMIT 15", (k_id,))
                if sorular:
                    with st.form(f"test_form_{k_id}"):
                        kullanici_cevaplari = {}
                        for i, soru in enumerate(sorular):
                            st.write(f"**Soru {i+1}:** {soru[2]}")
                            kullanici_cevaplari[i] = st.radio(f"Seçeneğin {i}", ["a", "b", "c", "d"], horizontal=True, key=f"soru_{soru[0]}")
                        
                        if st.form_submit_button("Sınavı Tamamla"):
                            dogru_sayisi = sum(1 for i, s in enumerate(sorular) if kullanici_cevaplari[i] == s[7])
                            yanlis_sayisi = len(sorular) - dogru_sayisi
                            net_skor = dogru_sayisi - (yanlis_sayisi * 0.25)
                            xp_kazanc = dogru_sayisi * 20
                            
                            vt_sorgu("UPDATE users SET xp = xp + ? WHERE username=?", (xp_kazanc, u_name), commit=True)
                            vt_sorgu("INSERT INTO test_sonuclari (username, ders, dogru, yanlis, net, tarih) VALUES (?,?,?,?,?,?)",
                                     (u_name, secilen_ders, dogru_sayisi, yanlis_sayisi, net_skor, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                            st.success(f"Test bitti! {dogru_sayisi} Doğru ile {xp_kazanc} XP kazandın."); st.balloons()
                else: st.info("Bu konu hakkında henüz soru eklenmemiş.")
    else: st.info("Henüz sistemde ders/konu bulunmuyor. Admin panelinden içerik üretebilirsin.")

with ana_tabs[1]:
    st.header("📊 Senin Gelişimin")
    veriler, _ = vt_sorgu("SELECT ders, dogru, yanlis, net, tarih FROM test_sonuclari WHERE username=?", (u_name,))
    if veriler:
        df = pd.DataFrame(veriler, columns=["Ders", "Doğru", "Yanlış", "Net", "Tarih"])
        st.dataframe(df, use_container_width=True)
        st.line_chart(df.set_index("Tarih")["Net"])
    else: st.info("Henüz analiz edilecek bir test verisi yok.")

# --- 7. ADMIN PANELİ (GÜÇLENDİRİLMİŞ ÜRETİM) ---
if is_admin:
    with ana_tabs[-1]:
        st.header("🛡️ Yönetici Karargahı")
        col_lisans, col_ai = st.columns(2)
        
        with col_lisans:
            st.subheader("🔑 Lisans Üretimi")
            if st.button("10 Adet Yeni Lisans Oluştur"):
                yeni_lisanslar = [lisans_uret_pro() for _ in range(10)]
                for l in yeni_lisanslar:
                    vt_sorgu("INSERT INTO licenses (kod) VALUES (?)", (l,), commit=True)
                st.code("\n".join(yeni_lisanslar))
                st.success("Lisanslar veritabanına mühürlendi.")

        with col_ai:
            st.subheader("🤖 Yıldırım Soru Fabrikası")
            a_sinif = st.selectbox("Hedef Sınıf", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
            a_ders = st.text_input("Ders İsmi")
            a_konu = st.text_input("Konu İsmi")
            a_miktar = st.number_input("Üretilecek Miktar", 10, 200, 50)
            
            if st.button("🚀 Üretimi Başlat"):
                if not a_ders or not a_konu:
                    st.error("Ders ve Konu alanları boş bırakılamaz!"); st.stop()
                
                # Konu ID tespiti
                k_kontrol, _ = vt_sorgu("SELECT id FROM konular WHERE ders=? AND sinif=? AND konu_adi=?", (a_ders, a_sinif, a_konu))
                if k_kontrol: kid = k_kontrol[0][0]
                else:
                    vt_sorgu("INSERT INTO konular (ders, sinif, konu_adi, icerik, ses_yolu) VALUES (?,?,?,?,?)",
                             (a_ders, a_sinif, a_konu, f"{a_konu} hakkında temel bilgiler.", ""), commit=True)
                    kid, _ = vt_sorgu("SELECT id FROM konular WHERE ders=? AND sinif=? AND konu_adi=?", (a_ders, a_sinif, a_konu))
                    kid = kid[0][0]

                toplam_basarili = 0
                deneme_limiti = 0
                max_deneme = a_miktar * 2
                batch_size = 20
                p_bar = st.progress(0.0)
                
                while toplam_basarili < a_miktar and deneme_limiti < max_deneme:
                    deneme_limiti += 1
                    kalan_ihtiyac = min(batch_size, a_miktar - toplam_basarili)
                    
                    prompt = f"""
                    Sen profesyonel bir ÖSYM soru uzmanısın. {a_sinif} {a_ders} dersi, {a_konu} konusu için {kalan_ihtiyac} adet soru üret.
                    KURALLAR:
                    1. Mantık ve muhakeme içermeli.
                    2. SADECE geçerli bir JSON array döndür. Başka metin yazma.
                    3. Format: [{"soru": "...", "a": "...", "b": "...", "c": "...", "d": "...", "cevap": "a/b/c/d"}]
                    """
                    
                    try:
                        response = MODEL.generate_content(prompt)
                        temiz_json = response.text.replace("```json", "").replace("```", "").strip()
                        gelen_sorular = json.loads(temiz_json)
                        
                        if not isinstance(gelen_sorular, list): raise ValueError()

                        for s in gelen_sorular:
                            if s["cevap"].lower() in ["a", "b", "c", "d"]:
                                # v2.9: Rowcount ile yıldırım hızında kontrol
                                _, row = vt_sorgu("""
                                    INSERT OR IGNORE INTO sorular (konu_id, soru_metni, a, b, c, d, cevap)
                                    VALUES (?,?,?,?,?,?,?)
                                """, (kid, s["soru"], s["a"], s["b"], s["c"], s["d"], s["cevap"].lower()), commit=True)
                                
                                if row > 0: toplam_basarili += 1
                        
                        p_bar.progress(min(toplam_basarili / a_miktar, 1.0))
                        time.sleep(1.3) # Rate limit koruması
                    except:
                        time.sleep(2)
                        continue
                
                st.success(f"✅ İşlem tamamlandı! Toplam {toplam_basarili} yeni soru eklendi."); st.balloons()
