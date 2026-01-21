import pandas as pd
import re
import feedparser
import os
import json
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from google import genai 
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO IA & ESTÉTICA ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")

st.set_page_config(page_title="TERMINAL XTIUSD - V80 HYBRID", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=300000, key="v80_refresh") 

MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"
CROSS_VAL_FILE = "cross_validation_log.json"

st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle, #0D1421 0%, #050A12 100%); color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1rem;}
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    [data-testid="stMetricLabel"] { font-size: 10px !important; color: #94A3B8 !important; text-transform: uppercase; }
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: rgba(30, 41, 59, 0.3); border-bottom: 2px solid #00FFC8; margin-bottom: 20px; }
    .arbitrage-monitor { padding: 20px; border-radius: 5px; border: 1px solid #1E293B; background: rgba(0, 0, 0, 0.4); margin-bottom: 20px; text-align: center; }
    .scroll-container { height: 480px; overflow-y: auto; border: 1px solid rgba(30, 41, 59, 0.5); background: rgba(0, 0, 0, 0.2); }
    .match-tag { background: #064E3B; color: #34D399; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .veto-tag { background: #450a0a; color: #f87171; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LEXICONS ---
LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation": [9.8, 1, "Geopolitics"],
    r"sanction|embargo|ban|price cap": [9.0, 1, "Sanctions"],
    r"iran|strait of hormuz|red sea|houthis": [9.8, 1, "Chokepoints"],
    r"israel|gaza|hezbollah|lebanon|tehran": [9.2, 1, "Middle East"],
    r"opec|saudi|russia|cut|quota": [9.5, 1, "OPEC+"],
    r"shale|fracking|permian|rig count": [7.5, -1, "US Supply"],
    r"inventory|stockpile|draw|api|eia": [8.0, 1, "Stocks"],
    r"recession|slowdown|weak|china": [8.8, -1, "Demand"],
    r"fed|rate hike|hawkish|inflation": [7.5, -1, "Macro Tightening"],
    r"dovish|rate cut|powell|easing": [7.5, 1, "Macro Easing"]
}

# --- 3. SUPORTE ---
def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return [] if "log" in p else {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)

def get_ai_val(title):
    try:
        prompt = f"Analise impacto WTI (1, -1, 0) para: '{title}'. Responda JSON: {{\"alpha\": v, \"termos\": []}}"
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res)
    except: return {"alpha": 0, "termos": []}

# --- 4. ENGINE DE NOTÍCIAS (CONFLUÊNCIA FLEXÍVEL) ---
def fetch_news():
    news_list = []
    logs = load_json(CROSS_VAL_FILE)
    sources = {
        "OilPrice": "https://oilprice.com/rss/main",
        "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
        "Investing": "https://www.investing.com/rss/news_11.rss"
    }
    
    for source, url in sources.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                lex_score, lex_dir = 0.0, 0
                title_low = entry.title.lower()
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        lex_score, lex_dir = float(w * d), d
                
                ai_data = get_ai_val(entry.title)
                ai_dir = ai_data.get("alpha", 0)
                
                consenso = (ai_dir == lex_dir)
                # Aceita se houver consenso OU impacto léxico extremo
                if consenso or abs(lex_score) >= 9.5:
                    news_list.append({
                        "Data": datetime.now().strftime("%H:%M"),
                        "Fonte": source,
                        "Manchete": entry.title[:100],
                        "Alpha": lex_score if lex_score != 0 else float(ai_dir * 8),
                        "Status": "CONFLUÊNCIA" if consenso else "DIVERGÊNCIA"
                    })
                logs.insert(0, {"Data": datetime.now().strftime("%H:%M"), "Manchete": entry.title[:60], "Lex": lex_dir, "AI": ai_dir, "Result": "OK" if consenso else "DIV"})
        except: continue
    
    save_json(CROSS_VAL_FILE, logs[:50])
    if news_list: pd.DataFrame(news_list).to_csv("Oil_Station_V80_Hybrid.csv", index=False)

# --- 5. MÉTRICAS COM PROTEÇÃO CONTRA RATE LIMIT ---
@st.cache_data(ttl=1200) # 20 minutos de cache para acalmar a API
def get_market_metrics():
    # Valores de segurança (fallback) caso o Yahoo bloqueie tudo
    fallback = {"WTI": 75.20, "CAD": 1.3800, "Z": 0.0, "status": "Cooldown Mode"}
    try:
        data = yf.download(["CL=F", "USDCAD=X"], period="2d", interval="15m", progress=False)
        if data.empty or 'CL=F' not in data['Close']: 
            return fallback
        
        wti = float(data['Close']['CL=F'].dropna().iloc[-1])
        cad = float(data['Close']['USDCAD=X'].dropna().iloc[-1])
        ratio = data['Close']['CL=F'] / data['Close']['USDCAD=X']
        z = float((ratio.iloc[-1] - ratio.mean()) / ratio.std())
        return {"WTI": wti, "CAD": cad, "Z": z, "status": "Online"}
    except:
        return fallback

# --- 6. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df_news = pd.read_csv("Oil_Station_V80_Hybrid.csv") if os.path.exists("Oil_Station_V80_Hybrid.csv") else pd.DataFrame()
    
    avg_alpha = df_news['Alpha'].mean() if not df_news.empty else 0.0
    ica_val = (avg_alpha + (mkt['Z'] * -5)) / 2

    st.markdown(f'<div class="live-status"><div style="font-weight:800; color:#00FFC8;">TERMINAL XTIUSD | QUANT V80</div><div>{datetime.now().strftime("%H:%M")} <span style="color:#00FFC8;">● {mkt["status"]}</span></div></div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("WTI", f"$ {mkt['WTI']:.2f}")
    c2.metric("USDCAD", f"{mkt['CAD']:.4f}")
    c3.metric("Z-SCORE", f"{mkt['Z']:.2f}")
    c4.metric("ALPHA", f"{avg_alpha:.2f}")

    st.markdown(f'<div class="arbitrage-monitor"><strong>ICA SCORE: {ica_val:.2f}</strong></div>', unsafe_allow_html=True)

    if not df_news.empty:
        df_disp = df_news.copy()
        df_disp['Status'] = df_disp['Status'].apply(lambda x: f'<span class="match-tag">{x}</span>' if x=="CONFLUÊNCIA" else f'<span class="veto-tag">{x}</span>')
        st.markdown(f'<div class="scroll-container">{df_disp[["Data", "Fonte", "Manchete", "Alpha", "Status"]].to_html(escape=False, index=False)}</div>', unsafe_allow_html=True)

if __name__ == "__main__": main()
