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

# --- 1. YAPILANDIRMA VE GENİŞLETİLMİŞ MÜFREDAT ---
st.set_page_config(page_title="T-BOZKURT v3.2", layout="wide", page_icon="🐺")

MUFREDAT = {
    "9. Sınıf": {
        "Matematik": ["Mantık", "Kümeler", "Denklemler ve Eşitsizlikler", "Üçgenler", "Veri"],
        "Türk Dili ve Edebiyatı": ["Giriş", "Hikaye", "Şiir", "Masal/Fabl", "Roman", "Tiyatro"],
        "Fizik": ["Fizik Bilimine Giriş", "Madde ve Özellikleri", "Hareket ve Kuvvet", "Enerji", "Isı ve Sıcaklık", "Elektrostatik"],
        "Kimya": ["Kimya Bilimi", "Atom ve Periyodik Sistem", "Kimyasal Türler Arası Etkileşimler", "Maddenin Halleri"],
        "Biyoloji": ["Yaşam Bilimi Biyoloji", "Hücre", "Canlılar Dünyası"],
        "Tarih": ["Tarih ve Zaman", "İnsanlığın İlk Dönemleri", "Orta Çağ’da Dünya", "Türk Dünyası", "İslam Medeniyeti"],
        "Coğrafya": ["Doğa ve İnsan", "Harita Bilgisi", "Atmosfer ve İklim"]
    },
    "10. Sınıf": {
        "Matematik": ["Sayma ve Olasılık", "Fonksiyonlar", "Polinomlar", "İkinci Dereceden Denklemler", "Dörtgenler"],
        "Türk Dili ve Edebiyatı": ["Halk Hikayesi", "Mesnevi", "Destan", "Divan Edebiyatı", "Tanzimat Edebiyatı"],
        "Fizik": ["Elektrik ve Manyetizma", "Basınç ve Kaldırma Kuvveti", "Dalgalar", "Optik"],
        "Kimya": ["Kimyanın Temel Kanunları", "Karışımlar", "Asitler, Bazlar ve Tuzlar"],
        "Biyoloji": ["Hücre Bölünmeleri", "Kalıtım", "Ekosistem Ekolojisi"],
        "Tarih": ["Selçuklu Türkiyesi", "Osmanlı Kuruluş", "Osmanlı Yükselme"],
        "Coğrafya": ["Yer Yapısı", "Dış Kuvvetler", "Türkiye Yer Şekilleri"]
    },
    "11. Sınıf": {
        "Matematik (AYT)": ["Trigonometri", "Analitik Geometri", "Denklem Sistemleri", "Çember ve Daire"],
        "Fizik (AYT)": ["Vektörler", "Bağıl Hareket", "Newton Yasaları", "Atışlar", "Momentum", "Tork"],
        "Kimya (AYT)": ["Atom Teorisi", "Gazlar", "Çözeltiler", "Enerji", "Hız", "Denge"],
        "Biyoloji (AYT)": ["Sistemler", "Sinir Sistemi", "Dolaşım Sistemi", "Sindirim Sistemi"]
    },
    "12. Sınıf": {
        "Matematik (AYT)": ["Logaritma", "Diziler", "Trigonometri 2", "Türev", "İntegral"],
        "Türk Dili ve Edebiyatı": ["Cumhuriyet Romanı", "Deneme", "Nutuk", "Küçürek Hikaye"],
        "Fizik (AYT)": ["Çembersel Hareket", "Harmonik Hareket", "Dalga Mekaniği", "Modern Fizik"],
        "Biyoloji (AYT)": ["Genden Proteine", "Enerji Dönüşümleri", "Bitki Biyolojisi"]
    }
}

try:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    MODEL = genai.GenerativeModel('gemini-1.5-flash')
    ADMIN_SIFRE = st.secrets["ADMIN_KEY"]
except:
    st.error("⚠️ Secrets ayarları eksik!")

# --- 2. GÜÇLENDİRİLMİŞ VERİTABANI MOTORU ---
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
        return [], 0 # Hata durumunda boş dönerek sistemi çökertmiyoruz
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
def lisans_uret_pro(): return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(15))

def deneme_bilgisi(username):
    res, _ = vt_sorgu("SELECT kayit_tarihi, premium, xp FROM users WHERE username=?", (username,))
    if not res: return 0, 0, 0
    k_dt = datetime.strptime(res[0][0], "%Y-%m-%d %H:%M")
    kalan = 7 - (datetime.now() - k_dt).total_seconds() / 86400
    return max(0, int(kalan)), res[0][1], res[0][2]

# --- 4. OTURUM VE GİRİŞ ---
if "user" not in st.session_state:
    st.title("🐺 T-BOZKURT: Akademik Karargah")
    t1, t2 = st.tabs(["Karargaha Gir", "Deneme Başlat"])
    with t2:
        with st.form("kayit"):
            u = st.text_input("Kullanıcı Adı")
            p = st.text_input("Şifre", type="password")
            s = st.selectbox("Sınıfın", list(MUFREDAT.keys()))
            if st.form_submit_button("Katıl"):
                res, _ = vt_sorgu("SELECT * FROM users WHERE username=?", (u,))
                if res: st.error("Bu isim alınmış.")
                else:
                    vt_sorgu("INSERT INTO users (username, password, sinif, kayit_tarihi) VALUES (?,?,?,?)",
                             (u, hash_pass(p), s, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                    st.success("Kayıt Başarılı!"); st.balloons()
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
        st.warning(f"⏳ {k_gun} Gün Kaldı")
        l_kod = st.text_input("Lisans Kodu")
        if st.button("Aktif Et"):
            res, _ = vt_sorgu("SELECT * FROM licenses WHERE kod=? AND kullanildi=0", (l_kod,))
            if res:
                vt_sorgu("UPDATE users SET premium=1 WHERE username=?", (u_name,), commit=True)
                vt_sorgu("UPDATE licenses SET kullanildi=1 WHERE kod=?", (l_kod,), commit=True)
                st.success("Premium Aktif!"); st.rerun()
    else: st.success("💎 PREMIUM")
    if st.button("Oturumu Kapat"): del st.session_state.user; st.rerun()
    st.divider()
    is_admin = (st.text_input("Admin Kilidi", type="password") == ADMIN_SIFRE)

if k_gun <= 0 and not is_pre: st.error("Süre doldu!"); st.stop()

# --- 6. ANA MODÜLLER ---
tabs = st.tabs(["📚 Çalış", "📊 Analiz", "🛠️ Admin"] if is_admin else ["📚 Çalış", "📊 Analiz"])

with tabs[0]:
    r_s, _ = vt_sorgu("SELECT sinif FROM users WHERE username=?", (u_name,))
    if r_s:
        s_bilgi = r_s[0][0]
        d_list, _ = vt_sorgu("SELECT DISTINCT ders FROM konular WHERE sinif=?", (s_bilgi,))
        if d_list:
            s_ders = st.selectbox("Ders", [d[0] for d in d_list])
            k_list, _ = vt_sorgu("SELECT id, konu_adi FROM konular WHERE ders=? AND sinif=?", (s_ders, s_bilgi))
            if k_list:
                s_konu_ad = st.selectbox("Konu", [k[1] for k in k_list])
                kid = [k[0] for k in k_list if k[1] == s_konu_ad][0]
                detay, _ = vt_sorgu("SELECT icerik FROM konular WHERE id=?", (kid,))
                
                c1, c2 = st.tabs(["📖 Anlatım", "📝 Test"])
                with c1: st.markdown(detay[0][0])
                with c2:
                    sorular, _ = vt_sorgu("SELECT * FROM sorular WHERE konu_id=? ORDER BY RANDOM() LIMIT 15", (kid,))
                    if sorular:
                        with st.form(f"t_{kid}"):
                            cevaplar = {}
                            for i, s in enumerate(sorular):
                                st.write(f"**{i+1}.** {s[2]}")
                                cevaplar[i] = st.radio(f"Cevap {i}", ["a","b","c","d"], horizontal=True, key=f"s_{s[0]}")
                            if st.form_submit_button("Bitir"):
                                d_s = sum(1 for i, s in enumerate(sorular) if cevaplar[i] == s[7])
                                n = d_s - ((len(sorular)-d_s)*0.25)
                                vt_sorgu("UPDATE users SET xp = xp + ? WHERE username=?", (d_s*20, u_name), commit=True)
                                vt_sorgu("INSERT INTO test_sonuclari (username, ders, dogru, yanlis, net, tarih) VALUES (?,?,?,?,?,?)",
                                         (u_name, s_ders, d_s, len(sorular)-d_s, n, datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
                                st.success(f"Netin: {n}"); st.balloons()
                    else: st.info("Soru henüz eklenmemiş.")

with tabs[1]:
    v, _ = vt_sorgu("SELECT ders, net, tarih FROM test_sonuclari WHERE username=?", (u_name,))
    if v:
        df = pd.DataFrame(v, columns=["Ders", "Net", "Tarih"])
        st.line_chart(df.set_index("Tarih")["Net"])

# --- 7. ADMIN (KESİN ÇÖZÜMLÜ ÜRETİM) ---
if is_admin:
    with tabs[-1]:
        st.subheader("🏛️ Müfredat Entegrasyonu")
        if st.button("📌 Tüm Müfredatı Yükle"):
            sayac = 0
            for snf, drsler in MUFREDAT.items():
                for drs, knlar in drsler.items():
                    for kn in knlar:
                        kon, _ = vt_sorgu("SELECT id FROM konular WHERE ders=? AND sinif=? AND konu_adi=?", (drs, snf, kn))
                        if not kon:
                            vt_sorgu("INSERT INTO konular (ders, sinif, konu_adi, icerik, ses_yolu) VALUES (?,?,?,?,?)",
                                     (drs, snf, kn, f"{kn} akademik çalışma notları...", ""), commit=True)
                            sayac += 1
            st.success(f"{sayac} Konu Kaydedildi!")

        st.divider()
        st.subheader("🤖 Profesyonel Soru Fabrikası")
        f_s = st.selectbox("Sınıf", list(MUFREDAT.keys()))
        d_l, _ = vt_sorgu("SELECT DISTINCT ders FROM konular WHERE sinif=?", (f_s,))
        f_d = st.selectbox("Ders", [d[0] for d in d_l] if d_l else ["Boş"])
        k_l, _ = vt_sorgu("SELECT id, konu_adi FROM konular WHERE ders=? AND sinif=?", (f_d, f_s))
        f_k_ad = st.selectbox("Konu", [k[1] for k in k_l] if k_l else ["Boş"])
        f_n = st.number_input("Adet", 10, 200, 50)
        
        if st.button("🚀 Üretimi Başlat"):
            f_kid = [k[0] for k in k_l if k[1] == f_k_ad][0]
            toplam, deneme, max_d, batch = 0, 0, f_n*2, 5 # Küçük batch = yüksek başarı
            pb = st.progress(0.0)
            status = st.empty()
            
            while toplam < f_n and deneme < max_d:
                deneme += 1
                kalan = min(batch, f_n - toplam)
                status.info(f"⏳ {toplam}/{f_n} tamamlandı. AI batch hazırlıyor...")
                
                prompt = f"""
                Sen bir ÖSYM uzmanısın. {f_s} {f_d} dersi, {f_k_ad} konusu için {kalan} adet profesyonel soru üret.
                KURALLAR:
                1. SADECE JSON array döndür.
                2. Soru içinde çift tırnak (") kullanma, gerekiyorsa tek tırnak (') kullan.
                3. JSON format: [{{"soru": "...", "a": "...", "b": "...", "c": "...", "d": "...", "cevap": "a/b/c/d"}}]
                """
                try:
                    res = MODEL.generate_content(prompt)
                    raw_text = res.text.strip()
                    # Markdown temizliği
                    if "```" in raw_text:
                        raw_text = raw_text.split("```")[1]
                        if raw_text.startswith("json"): raw_text = raw_text[4:]
                    
                    s_list = json.loads(raw_text.strip())
                    for s in s_list:
                        if all(k in s for k in ("soru", "a", "b", "c", "d", "cevap")):
                            _, row = vt_sorgu("""
                                INSERT OR IGNORE INTO sorular (konu_id, soru_metni, a, b, c, d, cevap) 
                                VALUES (?,?,?,?,?,?,?)
                            """, (f_kid, s["soru"], s["a"], s["b"], s["c"], s["d"], s["cevap"].lower()), commit=True)
                            if row > 0: toplam += 1
                    pb.progress(min(toplam/f_n, 1.0))
                    time.sleep(1.5)
                except Exception as e:
                    status.warning(f"⚠️ Batch atlatıldı. Hata: {str(e)[:50]}")
                    time.sleep(2)
            
            status.success(f"✅ {toplam} soru karargaha eklendi!")
            st.balloons()
