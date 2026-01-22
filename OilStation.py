import pandas as pd
import feedparser
import os
import json
import streamlit as st
import yfinance as yf
from google import genai 
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE CHAVES ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")
VERIFIED_FILE = "verified_lexicons.json"
AUDIT_CSV = "Oil_Station_Audit.csv"

# --- CONFIGURAÇÃO ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v102_refresh") 

# CSS Unificado: Forçando tabelas a saírem do branco e corrigindo dimensões
st.markdown("""
    <style>
    .stApp { background: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    
    /* ESTILO DAS MÉTRICAS */
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0F172A; border-bottom: 1px solid #00FFC8; margin-bottom: 20px; font-family: monospace; font-size: 12px; }
    .status-live { color: #00FFC8; font-weight: bold; }
    .driver-card { background: #111827; border-left: 3px solid #1E293B; padding: 12px; border-radius: 4px; }
    .driver-val { font-size: 20px; font-weight: bold; color: #F8FAFC; font-family: monospace; }
    .driver-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; }
    
    /* CORREÇÃO DEFINITIVA DO FUNDO BRANCO (FOTOS ANTERIORES) */
    div[data-testid="stDataFrame"], div[data-testid="stTable"] {
        background-color: #020617 !important;
        border: 1px solid #1E293B !important;
        border-radius: 4px;
    }
    
    /* Forçar texto claro dentro das células da tabela */
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {
        color: #F8FAFC !important;
    }

    .ai-insight { background: #0F172A; border: 1px solid #00FFC8; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 13px; color: #00FFC8; margin-top: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- NÚCLEO DE INTELIGÊNCIA AUTOMÁTICA ---
def auto_train_lexicon(headline):
    try:
        prompt = f"Analise: '{headline}'. Extraia termo técnico e peso (-1.0 a 1.0). Responda apenas JSON: {{\"termo\": \"...\", \"peso\": 0.0}}"
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        data = json.loads(response.text)
        
        verified = {}
        if os.path.exists(VERIFIED_FILE):
            with open(VERIFIED_FILE, 'r') as f: verified = json.load(f)
        
        verified[data['termo'].lower()] = data['peso']
        with open(VERIFIED_FILE, 'w') as f: json.dump(verified, f)
        
        return data['peso']
    except: return 0.0

# --- LÓGICA DE DADOS ---
def fetch_news():
    sources = {"OilPrice": "https://oilprice.com/rss/main", "Investing": "https://www.investing.com/rss/news_11.rss"}
    news_list = []
    for source, url in sources.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                if not any(x in entry.title.lower() for x in ["oil", "wti", "crude"]): continue
                peso_ia = auto_train_lexicon(entry.title)
                news_list.append({
                    "Timestamp": datetime.now(),
                    "Data": datetime.now().strftime("%d/%m %H:%M"),
                    "Fonte": source,
                    "Manchete": entry.title,
                    "Alpha": peso_ia * 10,
                    "Match": "YES" if abs(peso_ia) > 0.3 else "MID"
                })
        except: continue
    
    if news_list:
        new_df = pd.DataFrame(news_list)
        if os.path.exists(AUDIT_CSV):
            old_df = pd.read_csv(AUDIT_CSV)
            combined = pd.concat([old_df, new_df]).drop_duplicates(subset=['Manchete']).sort_values(by="Timestamp", ascending=False)
            combined.to_csv(AUDIT_CSV, index=False)
        else: new_df.to_csv(AUDIT_CSV, index=False)

def get_market():
    try:
        wti = yf.Ticker("CL=F").history(period="2d")
        price = wti['Close'].iloc[-1]
        change = ((price - wti['Close'].iloc[-2]) / wti['Close'].iloc[-2]) * 100
        return {"WTI": price, "Z": round(change / 1.2, 2)}
    except: return {"WTI": 0.0, "Z": 0.0}

# --- INTERFACE ---
def main():
    fetch_news()
    mkt = get_market()
    df = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    
    st.markdown(f'<div class="live-status"><div><b>XTIUSD TERMINAL</b></div><div class="status-live">● LIVE | {datetime.now().strftime("%H:%M:%S")}</div></div>', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 AUDIT FEED", "🧠 BRAIN"])

    with t1:
        sentiment = df['Alpha'].mean() if not df.empty else 0.0
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="driver-card"><div class="driver-label">WTI</div><div class="driver-val">$ {mkt["WTI"]:.2f}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="driver-card"><div class="driver-label">SENTIMENT</div><div class="driver-val">{sentiment:.2f}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="driver-card"><div class="driver-label">Z-SCORE</div><div class="driver-val">{mkt["Z"]:.2f}</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="driver-card"><div class="driver-label">ICA SCORE</div><div class="driver-val" style="color:#00FFC8">{(sentiment + (mkt["Z"]*-5))/2:.2f}</div></div>', unsafe_allow_html=True)

        if not df.empty:
            st.markdown("<br>", unsafe_allow_html=True)
            # RESOLUÇÃO DO ERRO: width='stretch' substitui use_container_width
            st.dataframe(df.head(15)[["Data", "Match", "Manchete"]], width='stretch', hide_index=True)

    with t2:
        st.markdown("### 🔍 Professional Audit Trail")
        if not df.empty:
            # RESOLUÇÃO DO ERRO: width='stretch'
            st.dataframe(df, width='stretch', hide_index=True)

    with t3:
        st.markdown("### 🧠 Autonomous Brain")
        if os.path.exists(VERIFIED_FILE):
            with open(VERIFIED_FILE, 'r') as f: verified = json.load(f)
            st.json(verified)

if __name__ == "__main__": main()
