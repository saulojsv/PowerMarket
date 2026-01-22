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

# Lexicons Iniciais para evitar arquivo vazio
INITIAL_LEXICONS = {
    "production cut": 0.8, "inventory build": -0.6, "inventory draw": 0.7,
    "opec quota": 0.5, "geopolitical tension": 0.8, "recession fears": -0.8
}

st.set_page_config(page_title="XTIUSD TERMINAL", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v105_refresh") 

# --- ESTILO CYBERPUNK (BASEADO NA IMAGEM NANO-BANANA) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    
    .stApp { background: #0D1117; color: #E6EDF3; font-family: 'JetBrains Mono', monospace; }
    header {visibility: hidden;}
    
    /* Top Bar Estilo Imagem */
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 15px; background: #161B22; border-bottom: 2px solid #00FFC8; margin-bottom: 25px; border-radius: 4px; }
    .status-live { color: #00FFC8; font-weight: bold; text-shadow: 0 0 10px #00FFC8; }
    
    /* Cards de Métricas (Velocímetros Visuais) */
    .metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }
    .driver-card { background: #161B22; border: 1px solid #30363D; padding: 20px; border-radius: 8px; text-align: center; transition: 0.3s; }
    .driver-card:hover { border-color: #00FFC8; box-shadow: 0 0 15px rgba(0, 255, 200, 0.1); }
    .driver-val { font-size: 28px; font-weight: bold; color: #FFFFFF; margin-bottom: 5px; }
    .driver-label { font-size: 11px; color: #8B949E; text-transform: uppercase; letter-spacing: 1px; }
    .ica-val { color: #00FFC8 !important; text-shadow: 0 0 10px rgba(0, 255, 200, 0.5); }

    /* Tabelas Cyberpunk Corrigidas */
    div[data-testid="stDataFrame"] { background-color: #0D1117 !important; border: 1px solid #30363D !important; padding: 10px; border-radius: 8px; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { color: #E6EDF3 !important; font-size: 13px !important; }
    
    .match-tag-yes { background: #064E3B; color: #34D399; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 10px; }
    .ai-insight { background: #161B22; border-left: 4px solid #00FFC8; padding: 15px; margin: 20px 0; color: #00FFC8; font-size: 13px; }
    </style>
""", unsafe_allow_html=True)

# --- SISTEMA DE MEMÓRIA (LEXICONS) ---
def load_lexicons():
    if not os.path.exists(VERIFIED_FILE) or os.stat(VERIFIED_FILE).st_size == 0:
        with open(VERIFIED_FILE, 'w') as f: json.dump(INITIAL_LEXICONS, f, indent=4)
        return INITIAL_LEXICONS
    try:
        with open(VERIFIED_FILE, 'r') as f: return json.load(f)
    except: return INITIAL_LEXICONS

def auto_train_lexicon(headline):
    """Extração de termos e aprendizado contínuo"""
    try:
        prompt = f"Extract oil market technical term and sentiment weight (-1.0 to 1.0) from: '{headline}'. Return ONLY JSON: {{\"term\": \"...\", \"weight\": 0.0}}"
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        data = json.loads(response.text)
        
        verified = load_lexicons()
        verified[data['term'].lower()] = data['weight']
        
        with open(VERIFIED_FILE, 'w') as f: json.dump(verified, f, indent=4)
        return data['weight']
    except: return 0.0

# --- PROCESSAMENTO DE DADOS ---
def fetch_news():
    sources = {"OilPrice": "https://oilprice.com/rss/main", "Investing": "https://www.investing.com/rss/news_11.rss"}
    news_list = []
    for source, url in sources.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                if not any(x in entry.title.lower() for x in ["oil", "wti", "crude"]): continue
                peso = auto_train_lexicon(entry.title)
                news_list.append({
                    "Timestamp": datetime.now(),
                    "Data": datetime.now().strftime("%d/%m %H:%M"),
                    "Fonte": source,
                    "Manchete": entry.title,
                    "Alpha": peso * 10,
                    "Match": "YES" if abs(peso) > 0.4 else "MID"
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

# --- INTERFACE TERMINAL ---
def main():
    fetch_news()
    mkt = get_market()
    df = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    
    # Header conforme imagem
    st.markdown(f'''
        <div class="live-status">
            <div style="font-size: 20px; font-weight: bold; letter-spacing: 2px;">XTIUSD TERMINAL</div>
            <div class="status-live">● LIVE | {datetime.now().strftime("%H:%M:%S")}</div>
        </div>
    ''', unsafe_allow_html=True)

    # Grid de Métricas (Substituindo o velocímetro por Cards Neon)
    sentiment = df['Alpha'].mean() if not df.empty else 0.0
    ica = (sentiment + (mkt["Z"] * -5)) / 2
    
    st.markdown(f'''
        <div class="metric-container">
            <div class="driver-card"><div class="driver-label">WTI Price</div><div class="driver-val">$ {mkt["WTI"]:.2f}</div></div>
            <div class="driver-card"><div class="driver-label">Sentiment</div><div class="driver-val">{sentiment:.2f}</div></div>
            <div class="driver-card"><div class="driver-label">Z-Score</div><div class="driver-val">{mkt["Z"]:.2f}</div></div>
            <div class="driver-card" style="border-color: #00FFC8;"><div class="driver-label">ICA Score</div><div class="driver-val ica-val">{ica:.2f}</div></div>
        </div>
    ''', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📊 DASHBOARD", "🔍 AUDIT FEED", "🧠 BRAIN"])

    with tab1:
        st.markdown(f'<div class="ai-insight">🤖 GEMINI INSIGHT: O viés atual do WTI apresenta um score de {ica:.2f} baseado no fluxo de notícias recente.</div>', unsafe_allow_html=True)
        if not df.empty:
            st.dataframe(df.head(15)[["Data", "Match", "Manchete"]], width='stretch', hide_index=True)

    with tab2:
        st.markdown("### 🔍 Historical Sentiment Audit")
        if not df.empty:
            st.dataframe(df, width='stretch', hide_index=True)

    with tab3:
        st.markdown("### 🧠 Autonomous Brain Memory")
        verified = load_lexicons()
        st.json(verified)

if __name__ == "__main__":
    main()
