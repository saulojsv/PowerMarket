import pandas as pd
import feedparser
import os
import json
import streamlit as st
import yfinance as yf
from google import genai 
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- NÚCLEO DE CONFIGURAÇÃO ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")
VERIFIED_FILE = "verified_lexicons.json"
AUDIT_CSV = "Oil_Station_Audit.csv"

# Lexicons iniciais protegidos
INITIAL_LEXICONS = {
    "production cut": 0.8, "inventory build": -0.6, "inventory draw": 0.7,
    "opec quota": 0.5, "geopolitical tension": 0.8, "recession fears": -0.8
}

st.set_page_config(page_title="XTIUSD TERMINAL", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="terminal_vfinal") 

# --- CSS HIGH-CONTRAST CYBERPUNK (REFORMULADO) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=JetBrains+Mono:wght@400;700&display=swap');
    
    .stApp { background: #05070A; color: #E2E8F0; font-family: 'JetBrains Mono', monospace; }
    header {visibility: hidden;}
    
    /* Header Estilo Terminal */
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 15px; background: #0A0F16; border: 1px solid #1E293B; border-left: 5px solid #00FFC8; margin-bottom: 25px; border-radius: 4px; }
    .status-live { color: #00FFC8; font-family: 'Orbitron', sans-serif; font-weight: bold; text-shadow: 0 0 10px rgba(0,255,200,0.4); }
    
    /* Metrics Grid */
    .metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }
    .driver-card { background: #0D1117; border: 1px solid #1E293B; padding: 15px; border-radius: 8px; text-align: center; }
    .driver-val { font-size: 26px; font-weight: bold; color: #FFFFFF; font-family: 'Orbitron', sans-serif; }
    .driver-label { font-size: 10px; color: #64748B; text-transform: uppercase; margin-bottom: 5px; }
    
    /* REFORÇO DE CONTRASTE ABSOLUTO NAS TABELAS */
    div[data-testid="stDataFrame"] { background-color: #05070A !important; border: 1px solid #1E293B !important; }
    
    /* Cabeçalhos da Tabela */
    [data-testid="stDataFrame"] div[role="columnheader"] {
        background-color: #161B22 !important;
        color: #00FFC8 !important;
        font-family: 'Orbitron', sans-serif !important;
        font-size: 10px !important;
    }

    /* Células da Tabela */
    [data-testid="stDataFrame"] div[role="gridcell"] {
        background-color: #05070A !important;
        color: #F8FAFC !important;
        border: 0.1px solid #1E293B !important;
        font-size: 12px !important;
    }

    .ai-insight { background: rgba(0, 255, 200, 0.05); border: 1px solid #00FFC8; padding: 15px; border-radius: 4px; color: #00FFC8; margin-bottom: 20px; font-size: 13px; }
    </style>
""", unsafe_allow_html=True)

# --- SISTEMA DE MEMÓRIA E APRENDIZADO ---
def safe_load_lexicons():
    if not os.path.exists(VERIFIED_FILE) or os.stat(VERIFIED_FILE).st_size == 0:
        with open(VERIFIED_FILE, 'w') as f: json.dump(INITIAL_LEXICONS, f, indent=4)
        return INITIAL_LEXICONS
    try:
        with open(VERIFIED_FILE, 'r') as f: return json.load(f)
    except: return INITIAL_LEXICONS

def auto_train_engine(headline):
    try:
        prompt = f"Extract oil technical term and weight (-1.0 to 1.0) from: '{headline}'. Reply ONLY JSON: {{\"term\": \"...\", \"weight\": 0.0}}"
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        
        lex = safe_load_lexicons()
        lex[data['term'].lower()] = data['weight']
        with open(VERIFIED_FILE, 'w') as f: json.dump(lex, f, indent=4)
        return data['weight']
    except: return 0.0

# --- DATA PIPELINE ---
def fetch_data():
    sources = {"OilPrice": "https://oilprice.com/rss/main", "Investing": "https://www.investing.com/rss/news_11.rss"}
    results = []
    for src, url in sources.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                if not any(x in entry.title.lower() for x in ["oil", "wti", "crude"]): continue
                w = auto_train_engine(entry.title)
                results.append({
                    "Timestamp": datetime.now(),
                    "Hora": datetime.now().strftime("%H:%M"),
                    "Fonte": src,
                    "Manchete": entry.title,
                    "Alpha": w * 10,
                    "Match": "🔴 HIGH" if abs(w) > 0.6 else "🟢 YES" if abs(w) > 0.3 else "⚪ MID"
                })
        except: continue
    
    if results:
        new_df = pd.DataFrame(results)
        if os.path.exists(AUDIT_CSV):
            old_df = pd.read_csv(AUDIT_CSV)
            combined = pd.concat([old_df, new_df]).drop_duplicates(subset=['Manchete']).sort_values(by="Timestamp", ascending=False)
            combined.to_csv(AUDIT_CSV, index=False)
        else: new_df.to_csv(AUDIT_CSV, index=False)

def get_mkt():
    try:
        ticker = yf.Ticker("CL=F").history(period="2d")
        last = ticker['Close'].iloc[-1]
        prev = ticker['Close'].iloc[-2]
        change = ((last - prev) / prev) * 100
        return {"p": last, "z": round(change / 1.2, 2)}
    except: return {"p": 0.0, "z": 0.0}

# --- INTERFACE ---
def main():
    fetch_data()
    m = get_mkt()
    df = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    
    st.markdown(f'<div class="live-status"><div>XTIUSD_TERMINAL_CORE</div><div class="status-live">● LIVE FEED | {datetime.now().strftime("%H:%M:%S")}</div></div>', unsafe_allow_html=True)

    sentiment = df['Alpha'].mean() if not df.empty else 0.0
    ica = (sentiment + (m['z'] * -5)) / 2
    
    st.markdown(f'''
        <div class="metric-container">
            <div class="driver-card"><div class="driver-label">WTI PRICE</div><div class="driver-val">$ {m["p"]:.2f}</div></div>
            <div class="driver-card"><div class="driver-label">SENTIMENT</div><div class="driver-val">{sentiment:.2f}</div></div>
            <div class="driver-card"><div class="driver-label">Z-SCORE</div><div class="driver-val">{m["z"]:.2f}</div></div>
            <div class="driver-card" style="border-color:#00FFC8"><div class="driver-label">ICA SCORE</div><div class="driver-val" style="color:#00FFC8">{ica:.2f}</div></div>
        </div>
    ''', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 AUDIT FEED", "🧠 BRAIN"])

    with t1:
        st.markdown(f'<div class="ai-insight">🤖 ALPHA LOG: O fluxo de dados aponta viés de {ica:.2f}. Sistema em monitoramento de lexicons...</div>', unsafe_allow_html=True)
        if not df.empty:
            # Tabela com as correções de contraste aplicadas
            st.dataframe(df.head(15)[["Hora", "Match", "Manchete"]], width='stretch', hide_index=True)

    with t2:
        if not df.empty:
            st.dataframe(df, width='stretch', hide_index=True)

    with t3:
        st.markdown("### 🧠 Neural Lexicon Memory")
        st.json(safe_load_lexicons())

if __name__ == "__main__":
    main()
