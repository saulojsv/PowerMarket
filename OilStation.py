import pandas as pd
import feedparser
import os
import json
import streamlit as st
import yfinance as yf
from google import genai 
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE NÚCLEO ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")
VERIFIED_FILE = "verified_lexicons.json"
AUDIT_CSV = "Oil_Station_Audit.csv"

# Lexicons Iniciais (Os 22 serão protegidos aqui)
INITIAL_LEXICONS = {
    "production cut": 0.8, "inventory build": -0.6, "inventory draw": 0.7,
    "opec quota": 0.5, "geopolitical tension": 0.8, "recession fears": -0.8,
    "shale output": -0.4, "strategic reserve": -0.3, "sanctions": 0.7
}

st.set_page_config(page_title="XTIUSD TERMINAL", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="terminal_v2") 

# --- CSS HIGH-TECH CYBERPUNK ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=JetBrains+Mono:wght@400;700&display=swap');
    
    .stApp { background: #05070A; color: #00FFC8; font-family: 'JetBrains Mono', monospace; }
    header {visibility: hidden;}
    
    /* Terminal Header */
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 15px; background: #0A0F16; border: 1px solid #1E293B; border-left: 5px solid #00FFC8; margin-bottom: 25px; border-radius: 4px; }
    .status-live { color: #00FFC8; font-family: 'Orbitron', sans-serif; font-weight: bold; text-shadow: 0 0 8px #00FFC8; }
    
    /* Metrics Layout */
    .metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }
    .driver-card { background: #0D1117; border: 1px solid #1E293B; padding: 15px; border-radius: 8px; text-align: center; }
    .driver-val { font-size: 24px; font-weight: bold; color: #FFFFFF; font-family: 'Orbitron', sans-serif; }
    .driver-label { font-size: 10px; color: #64748B; text-transform: uppercase; margin-bottom: 8px; }
    
    /* Tabela sem Bug de Cor */
    div[data-testid="stDataFrame"] { background-color: #0A0F16 !important; border: 1px solid #1E293B !important; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { background-color: #0A0F16 !important; color: #E2E8F0 !important; border: 1px solid #1E293B !important; }
    
    .ai-insight { background: rgba(0, 255, 200, 0.05); border: 1px solid #00FFC8; padding: 15px; border-radius: 4px; color: #00FFC8; margin-bottom: 20px; }
    
    /* Tabs Customization */
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #161B22; border: 1px solid #1E293B; color: #94A3B8; padding: 8px 16px; border-radius: 4px; }
    .stTabs [data-baseweb="tab-highlight"] { background-color: #00FFC8; }
    </style>
""", unsafe_allow_html=True)

# --- NÚCLEO DE MEMÓRIA E APRENDIZADO ---
def safe_load_lexicons():
    if not os.path.exists(VERIFIED_FILE) or os.stat(VERIFIED_FILE).st_size == 0:
        with open(VERIFIED_FILE, 'w') as f: json.dump(INITIAL_LEXICONS, f, indent=4)
        return INITIAL_LEXICONS
    try:
        with open(VERIFIED_FILE, 'r') as f: return json.load(f)
    except: return INITIAL_LEXICONS

def auto_train_engine(headline):
    """Lógica de aprendizado constante corrigida"""
    try:
        prompt = f"Analyze market impact: '{headline}'. Reply JSON: {{\"term\": \"technical word\", \"weight\": 0.0}}"
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        # Limpeza para evitar bugs de JSON corrompido
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        
        lexicons = safe_load_lexicons()
        lexicons[data['term'].lower()] = data['weight']
        
        with open(VERIFIED_FILE, 'w') as f: json.dump(lexicons, f, indent=4)
        return data['weight']
    except: return 0.0

# --- DATA PIPELINE ---
def fetch_and_process():
    sources = {"OilPrice": "https://oilprice.com/rss/main", "Investing": "https://www.investing.com/rss/news_11.rss"}
    news_data = []
    for src, url in sources.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                if not any(x in entry.title.lower() for x in ["oil", "wti", "crude"]): continue
                impact = auto_train_engine(entry.title)
                news_data.append({
                    "Timestamp": datetime.now(),
                    "Time": datetime.now().strftime("%H:%M"),
                    "Source": src,
                    "Manchete": entry.title,
                    "Impact": impact,
                    "Match": "HIGH" if abs(impact) > 0.4 else "MID"
                })
        except: continue
    
    if news_data:
        new_df = pd.DataFrame(news_data)
        if os.path.exists(AUDIT_CSV):
            old_df = pd.read_csv(AUDIT_CSV)
            combined = pd.concat([old_df, new_df]).drop_duplicates(subset=['Manchete']).sort_values(by="Timestamp", ascending=False)
            combined.to_csv(AUDIT_CSV, index=False)
        else: new_df.to_csv(AUDIT_CSV, index=False)

def get_market_data():
    try:
        cl = yf.Ticker("CL=F").history(period="2d")
        price = cl['Close'].iloc[-1]
        change = ((price - cl['Close'].iloc[-2]) / cl['Close'].iloc[-2]) * 100
        return {"price": price, "change": round(change / 1.2, 2)}
    except: return {"price": 0.0, "change": 0.0}

# --- INTERFACE ---
def main():
    fetch_and_process()
    mkt = get_market_data()
    df = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    
    # Header
    st.markdown(f'<div class="live-status"><div><span style="color:#64748B">ID:</span> XTIUSD_TERMINAL</div><div class="status-live">● LIVE FEED | {datetime.now().strftime("%H:%M:%S")}</div></div>', unsafe_allow_html=True)

    # Metrics Grid
    sentiment = df['Impact'].mean() if not df.empty else 0.0
    ica_score = (sentiment + (mkt['change'] * -5)) / 2
    
    st.markdown(f'''
        <div class="metric-container">
            <div class="driver-card"><div class="driver-label">WTI PRICE</div><div class="driver-val">$ {mkt["price"]:.2f}</div></div>
            <div class="driver-card"><div class="driver-label">SENTIMENT</div><div class="driver-val">{sentiment:.2f}</div></div>
            <div class="driver-card"><div class="driver-label">VOL Z-SCORE</div><div class="driver-val">{mkt["change"]:.2f}</div></div>
            <div class="driver-card" style="border-color:#00FFC8"><div class="driver-label">ICA SCORE</div><div class="driver-val" style="color:#00FFC8">{ica_score:.2f}</div></div>
        </div>
    ''', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 AUDIT", "🧠 BRAIN"])

    with t1:
        st.markdown(f'<div class="ai-insight">⚡ ALPHA_LOG: IA detectou um ICA SCORE de {ica_score:.2f}. Analisando fluxos de oferta...</div>', unsafe_allow_html=True)
        if not df.empty:
            # Tabela limpa e funcional
            st.dataframe(df.head(15)[["Time", "Match", "Manchete"]], width='stretch', hide_index=True)

    with t2:
        if not df.empty:
            st.dataframe(df, width='stretch', hide_index=True)

    with t3:
        st.markdown("### 🧠 Neural Lexicon Memory")
        st.json(safe_load_lexicons())

if __name__ == "__main__":
    main()
