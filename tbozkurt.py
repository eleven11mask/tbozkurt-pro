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
from datetime import datetime

# --- 1. YAPILANDIRMA VE GENİŞLETİLMİŞ MÜFREDAT (YKS TAM LİSTE) ---
st.set_page_config(page_title="T-BOZKURT v3.1", layout="wide", page_icon="🐺")

MUFREDAT = {
    "9. Sınıf": {
        "Matematik": ["Mantık", "Kümeler", "Denklemler ve Eşitsizlikler", "Üçgenler", "Veri"],
        "Türk Dili ve Edebiyatı": ["Giriş", "Hikaye", "Şiir", "Masal/Fabl", "Roman", "Tiyatro"],
        "Fizik": ["Fizik Bilimine Giriş", "Madde ve Özellikleri", "Hareket ve Kuvvet", "Enerji", "Isı ve Sıcaklık", "Elektrostatik"],
        "Kimya": ["Kimya Bilimi", "Atom ve Periyodik Sistem", "Kimyasal Türler Arası Etkileşimler", "Maddenin Halleri"],
        "Biyoloji": ["Yaşam Bilimi Biyoloji", "Hücre", "Canlılar Dünyası"],
        "Tarih": ["Tarih ve Zaman", "İnsanlığın İlk Dönemleri", "Orta Çağ’da Dünya", "İlk ve Orta Çağlarda Türk Dünyası", "İslam Medeniyetinin Doğuşu"],
        "Coğrafya": ["Doğa ve İnsan", "Dünya’nın Şekli ve Hareketleri", "Yer ve Zaman", "Harita Bilgisi", "Atmosfer ve İklim"]
    },
    "10. Sınıf": {
        "Matematik": ["Sayma ve Olasılık", "Fonksiyonlar", "Polinomlar", "İkinci Dereceden Denklemler", "Dörtgenler ve Çokgenler", "Uzay Geometri"],
        "Türk Dili ve Edebiyatı": ["Dede Korkut", "Halk Hikayesi", "Mesnevi", "Destan/Efsane", "Divan Edebiyatı", "Tanzimat Edebiyatı"],
        "Fizik": ["Elektrik ve Manyetizma", "Basınç ve Kaldırma Kuvveti", "Dalgalar", "Optik"],
        "Kimya": ["Kimyanın Temel Kanunları", "Karışımlar", "Asitler, Bazlar ve Tuzlar", "Kimya Her Yerde"],
        "Biyoloji": ["Hücre Bölünmeleri", "Kalıtımın Genel İlkeleri", "Ekosistem Ekolojisi"],
        "Tarih": ["Selçuklu Türkiyesi", "Osmanlı Devleti Kuruluş", "Osmanlı Devleti Yükselme", "Dünya Gücü Osmanlı"],
        "Coğrafya": ["Yer’in Yapısı ve İç Kuvvetler", "Dış Kuvvetler", "Türkiye’nin Yer Şekilleri", "Su Kaynakları", "Topraklar", "Bitkiler"]
    },
    "11. Sınıf": {
        "Matematik (AYT)": ["Trigonometri", "Analitik Geometri", "Fonksiyonlarda Uygulamalar", "Denklem ve Eşitsizlik Sistemleri", "Çember ve Daire", "Uzay Geometri", "Olasılık"],
        "Türk Dili ve Edebiyatı": ["Edebiyat ve Toplum", "Cumhuriyet Dönemi Şiir", "Makale", "Sohbet ve Fıkra", "Roman Analizi"],
        "Fizik (AYT)": ["Vektörler", "Bağıl Hareket", "Newton’ın Hareket Yasaları", "Bir Boyutta Sabit İvmeli Hareket", "İki Boyutta Hareket", "Enerji ve Hareket", "İtme ve Çizgisel Momentum", "Tork ve Denge"],
        "Kimya (AYT)": ["Modern Atom Teorisi", "Gazlar", "Sıvı Çözeltiler", "Kimyasal Tepkimelerde Enerji", "Hız", "Denge"],
        "Biyoloji (AYT)": ["İnsan Fizyolojisi (Sistemler)", "Denetleyici ve Düzenleyici Sistemler", "Destek ve Hareket Sistemi", "Sindirim Sistemi", "Dolaşım Sistemi"],
        "Tarih": ["Değişen Dünya Dengeleri Karşısında Osmanlı Siyaseti", "Değişim Çağında Avrupa ve Osmanlı", "Uluslararası İlişkilerde Denge Stratejisi"]
    },
    "12. Sınıf": {
        "Matematik (AYT)": ["Üstel ve Logaritmik Fonksiyonlar", "Diziler", "Trigonometri 2", "Türev ve Uygulamaları", "İntegral ve Uygulamaları", "Analitik Geometri (Çember)"],
        "Türk Dili ve Edebiyatı": ["20. Yüzyıl Edebiyatı", "Cumhuriyet Dönemi Roman", "Küçürek Hikaye", "Deneme", "Nutuk"],
        "Fizik (AYT)": ["Çembersel Hareket", "Basit Harmonik Hareket", "Dalga Mekaniği", "Atom Fiziğine Giriş", "Modern Fizik", "Modern Fiziğin Teknolojideki Uygulamaları"],
        "Kimya (AYT)": ["Kimya ve Elektrik", "Karbon Kimyasına Giriş", "Organik Bileşikler", "Enerji Kaynakları"],
        "Biyoloji (AYT)": ["Genden Proteine", "Canlılarda Enerji Dönüşümleri", "Bitki Biyolojisi", "Canlılar ve Çevre"]
    }
}

# --- 2. VERİTABANI MOTORU ---
def vt_sorgu(sorgu, parametre=(), commit=False):
    conn = sqlite3.connect('tbozkurt_pro.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute(sorgu, parametre)
        if commit: conn.commit()
        sonuc = c.fetchall()
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
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(15))

def deneme_bilgisi(username):
    res, _ = vt_sorgu("SELECT kayit_tarihi, premium, xp FROM users WHERE username=?", (username,))
    if not res: return 0, 0, 0
    k_dt = datetime.strptime(res[0][0], "%Y-%m-%d %H:%M")
    kalan = 7 - (datetime.now() - k_dt).total_seconds() / 86400
    return max(0, int(kalan)), res[0][1], res[0][2]

# --- 4. OTURUM ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Akademik Karargah")
    t1, t2 = st.tabs(["Giriş", "Deneme Başlat"])
    with t2:
        with st.form("kayit"):
            u = st.text_input("Kullanıcı Adı")
            p = st.text_input("Şifre", type="password")
            s = st.selectbox("Sınıfın", list(MUFREDAT.keys()))
            if st.form_submit_button("Sisteme Katıl"):
                res, _ = vt_sorgu("SELECT * FROM users WHERE username=?", (u,))
                if res: st.error("Bu isim kullanılıyor.")
                else:
                    vt_sorgu("INSERT INTO users (username, password, sinif, kayit_tarihi) VALUES (?,?,?,?)",
                             (u, hash_pass(p), s, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                    st.success("Kayıt Başarılı! Giriş yapın."); st.balloons()
    with t1:
        with st.form("giris"):
            u_i = st.text_input("Kullanıcı Adı")
            p_i = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap"):
                d, _ = vt_sorgu("SELECT password FROM users WHERE username=?", (u_i,))
                if d and d[0][0] == hash_pass(p_i): st.session_state.user = u_i; st.rerun()
                else: st.error("Hatalı!")
    st.stop()

# --- 5. PANEL ---
u_name = st.session_state.user
k_gun, is_pre, u_xp = deneme_bilgisi(u_name)

with st.sidebar:
    st.title(f"🐺 {u_name}")
    st.metric("🔥 XP", u_xp)
    if not is_pre:
        st.warning(f"⏳ {k_gun} Günün Kaldı")
        l_kod = st.text_input("Lisans Kodu")
        if st.button("Aktif Et"):
            res, _ = vt_sorgu("SELECT * FROM licenses WHERE kod=? AND kullanildi=0", (l_kod,))
            if res:
                vt_sorgu("UPDATE users SET premium=1 WHERE username=?", (u_name,), commit=True)
                vt_sorgu("UPDATE licenses SET kullanildi=1 WHERE kod=?", (l_kod,), commit=True)
                st.success("Premium Aktif!"); st.rerun()
    else: st.success("💎 PREMIUM ÜYE")
    if st.button("Çıkış Yap"): del st.session_state.user; st.rerun()
    st.divider()
    is_admin = (st.text_input("Yönetici Kilidi", type="password") == st.secrets["ADMIN_KEY"])

if k_gun <= 0 and not is_pre: st.error("Deneme süreniz bitti!"); st.stop()

# --- 6. MODÜLLER ---
tabs = st.tabs(["📚 Ders Çalış", "📊 Analiz", "🛠️ Admin"] if is_admin else ["📚 Ders Çalış", "📊 Analiz"])

with tabs[0]:
    r_s, _ = vt_sorgu("SELECT sinif FROM users WHERE username=?", (u_name,))
    if r_s:
        s_bilgi = r_s[0][0]
        d_list, _ = vt_sorgu("SELECT DISTINCT ders FROM konular WHERE sinif=?", (s_bilgi,))
        if d_list:
            s_ders = st.selectbox("Ders Seç", [d[0] for d in d_list])
            k_list, _ = vt_sorgu("SELECT id, konu_adi FROM konular WHERE ders=? AND sinif=?", (s_ders, s_bilgi))
            if k_list:
                s_konu_ad = st.selectbox("Konu Seç", [k[1] for k in k_list])
                kid = [k[0] for k in k_list if k[1] == s_konu_ad][0]
                detay, _ = vt_sorgu("SELECT icerik FROM konular WHERE id=?", (kid,))
                
                c1, c2 = st.tabs(["📖 Konu Anlatımı", "📝 Test Çöz"])
                with c1: st.markdown(detay[0][0])
                with c2:
                    sorular, _ = vt_sorgu("SELECT * FROM sorular WHERE konu_id=? ORDER BY RANDOM() LIMIT 15", (kid,))
                    if sorular:
                        with st.form(f"t_{kid}"):
                            cevaplar = {}
                            for i, s in enumerate(sorular):
                                st.write(f"**{i+1}.** {s[2]}")
                                cevaplar[i] = st.radio(f"Cevap {i}", ["a","b","c","d"], horizontal=True, key=f"s_{s[0]}")
                            if st.form_submit_button("Sınavı Bitir"):
                                d_s = sum(1 for i, s in enumerate(sorular) if cevaplar[i] == s[7])
                                n = d_s - ((len(sorular)-d_s)*0.25)
                                vt_sorgu("UPDATE users SET xp = xp + ? WHERE username=?", (d_s*20, u_name), commit=True)
                                vt_sorgu("INSERT INTO test_sonuclari (username, ders, dogru, yanlis, net, tarih) VALUES (?,?,?,?,?,?)",
                                         (u_name, s_ders, d_s, len(sorular)-d_s, n, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                                st.success(f"Bitti! Netin: {n}"); st.balloons()
                    else: st.info("Bu konu için soru üretilmemiş. Lütfen Admin panelinden soru basın.")
        else: st.info("Müfredat yüklenmemiş.")

with tabs[1]:
    v, _ = vt_sorgu("SELECT ders, net, tarih FROM test_sonuclari WHERE username=?", (u_name,))
    if v:
        df = pd.DataFrame(v, columns=["Ders", "Net", "Tarih"])
        st.line_chart(df.set_index("Tarih")["Net"])

# --- 7. ADMIN (MÜFREDAT VE STABİL ÜRETİM) ---
if is_admin:
    with tabs[-1]:
        st.subheader("🏛️ Müfredat ve Soru Fabrikası")
        if st.button("📌 Tüm Müfredatı (9-12) Sisteme Yükle"):
            sayac = 0
            for snf, drsler in MUFREDAT.items():
                for drs, knlar in drsler.items():
                    for kn in knlar:
                        kon, _ = vt_sorgu("SELECT id FROM konular WHERE ders=? AND sinif=? AND konu_adi=?", (drs, snf, kn))
                        if not kon:
                            vt_sorgu("INSERT INTO konular (ders, sinif, konu_adi, icerik, ses_yolu) VALUES (?,?,?,?,?)",
                                     (drs, snf, kn, f"{kn} konusu akademik çalışma notları hazırlanıyor...", ""), commit=True)
                            sayac += 1
            st.success(f"{sayac} Yeni Konu Eklendi!")

        st.divider()
        f_s = st.selectbox("Üretim Sınıfı", list(MUFREDAT.keys()))
        d_l, _ = vt_sorgu("SELECT DISTINCT ders FROM konular WHERE sinif=?", (f_s,))
        f_d = st.selectbox("Üretim Dersi", [d[0] for d in d_l] if d_l else ["Boş"])
        k_l, _ = vt_sorgu("SELECT id, konu_adi FROM konular WHERE ders=? AND sinif=?", (f_d, f_s))
        f_k_ad = st.selectbox("Üretim Konusu", [k[1] for k in k_l] if k_l else ["Boş"])
        f_n = st.number_input("Kaç Soru?", 10, 200, 50)
        
        if st.button("🚀 AI Soru Üretimini Başlat"):
            f_kid = [k[0] for k in k_l if k[1] == f_k_ad][0]
            toplam, deneme, max_d, batch = 0, 0, f_n*2, 10
            pb = st.progress(0.0)
            st.write("🤖 AI Karargahına bağlanılıyor...")
            
            while toplam < f_n and deneme < max_d:
                deneme += 1
                kalan = min(batch, f_n - toplam)
                prompt = f"""
                Sen bir ÖSYM uzmanısın. {f_s} {f_d} dersi, {f_k_ad} konusu için {kalan} adet profesyonel soru üret.
                Kurallar:
                - Çıktı SADECE saf JSON array olmalı.
                - JSON dışında hiçbir açıklama ekleme.
                - Format: [{{"soru": "...", "a": "...", "b": "...", "c": "...", "d": "...", "cevap": "a/b/c/d"}}]
                """
                try:
                    res = MODEL.generate_content(prompt)
                    # Stabil JSON Ayıklama
                    raw_text = res.text.strip()
                    if "```json" in raw_text:
                        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw_text:
                        raw_text = raw_text.split("```")[1].split("```")[0].strip()
                    
                    s_list = json.loads(raw_text)
                    for s in s_list:
                        if s.get("cevap") and s["cevap"].lower() in ["a", "b", "c", "d"]:
                            _, row = vt_sorgu("INSERT OR IGNORE INTO sorular (konu_id, soru_metni, a, b, c, d, cevap) VALUES (?,?,?,?,?,?,?)",
                                              (f_kid, s["soru"], s["a"], s["b"], s["c"], s["d"], s["cevap"].lower()), commit=True)
                            if row > 0: toplam += 1
                    pb.progress(min(toplam/f_n, 1.0))
                    time.sleep(1.5)
                except Exception as e:
                    st.write(f"⚠️ Ufak bir AI hatası atlatıldı, devam ediliyor...")
                    time.sleep(2)
                    continue
            st.success(f"İşlem Tamam! {toplam} adet yeni soru mühürlendi.")
