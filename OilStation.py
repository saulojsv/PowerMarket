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

st.set_page_config(page_title="TERMINAL XTIUSD - V90 QUANT HYBRID", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=300000, key="v90_refresh") 

# Arquivos de Dados para persistência
MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"
CROSS_VAL_FILE = "cross_validation_log.json"

st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle, #0D1421 0%, #050A12 100%); color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1rem;}
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    [data-testid="stMetricValue"] { font-size: 22px !important; color: #00FFC8 !important; }
    [data-testid="stMetricLabel"] { font-size: 10px !important; color: #94A3B8 !important; text-transform: uppercase; }
    
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: rgba(30, 41, 59, 0.3); border-bottom: 2px solid #00FFC8; margin-bottom: 20px; }
    .arbitrage-monitor { padding: 20px; border-radius: 5px; border: 1px solid #1E293B; background: rgba(0, 0, 0, 0.4); margin-bottom: 20px; text-align: center; }
    .scroll-container { height: 450px; overflow-y: auto; background: rgba(0, 0, 0, 0.2); border: 1px solid #1E293B; }
    
    .pos-score { color: #00FFC8; font-weight: bold; }
    .neg-score { color: #FF4B4B; font-weight: bold; }
    .match-tag { background: #004d3d; color: #00FFC8; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
    .mismatch-tag { background: #4d0000; color: #FF4B4B; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. OS 22 SITES (FONTES RSS) ---
RSS_SOURCES = {
    "Bloomberg Energy": "https://www.bloomberg.com/feeds/bview/energy.xml",
    "Reuters Oil": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "CNBC Commodities": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "FT Commodities": "https://www.ft.com/commodities?format=rss",
    "WSJ Energy": "https://feeds.a.dj.com/rss/RSSWSJ.xml",
    "OilPrice Main": "https://oilprice.com/rss/main",
    "Rigzone": "https://www.rigzone.com/news/rss/rigzone_latest.xml",
    "S&P Global Platts": "https://www.spglobal.com/platts/en/rss-feed/news/oil",
    "Energy Voice": "https://www.energyvoice.com/category/oil-and-gas/feed/",
    "EIA Today": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "Investing.com": "https://www.investing.com/rss/news_11.rss",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Yahoo Finance Oil": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Foreign Policy": "https://foreignpolicy.com/feed/",
    "Lloyds List": "https://lloydslist.maritimeintelligence.informa.com/RSS/News",
    "Marine Insight": "https://www.marineinsight.com/feed/",
    "Splash 247": "https://splash247.com/feed/",
    "OPEC Press": "https://www.opec.org/opec_web/en/press_room/311.xml",
    "IEA News": "https://www.iea.org/news/rss",
    "BOC News": "https://www.bankofcanada.ca/feed/",
    "Fed News": "https://www.federalreserve.gov/feeds/press_all.xml"
}

# --- 3. OS 22 LEXICONS BASE ---
LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation|invasion": [9.8, 1, "Geopolitics (Conflict)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolitics (Sanctions)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Chokepoint Risk"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Regional Tensions"],
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "OPEC+ Policy"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "OPEC+ Supply"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "US Supply"],
    r"non-opec|brazil|guyana|canada|alberta|output surge": [7.0, -1, "Non-OPEC Supply"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Stocks (Deficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Stocks (Surplus)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refining/Margins"],
    r"crack spread|heating oil|jet fuel|diesel demand": [6.5, 1, "Distillates"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Weak Demand)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Strong Demand)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate|boc": [7.5, -1, "Macro (Fed Tightening)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Fed Easing)"],
    r"dollar|dxy|greenback|fx|yields|usdcad": [7.0, -1, "DXY Correlation"],
    r"gdp|pmi|manufacturing|industrial production": [6.8, 1, "Macro Indicators"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Speculative Flow"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Technical Analysis"],
    r"volatility|vix|contango|backwardation": [6.2, 1, "Term Structure"],
    r"algorithmic trading|ctas|margin call|liquidation": [6.0, 1, "Quant Flow"]
}

# --- 4. FUNÇÕES DE SUPORTE ---
def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return [] if "log" in p else {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)

def get_ai_validation(title):
    try:
        prompt = f"Analise o viés para o petróleo: '{title}'. Responda apenas um número: 1 (Alta), -1 (Baixa) ou 0 (Neutro)."
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        res = response.text.strip()
        return int(res) if res in ['1', '-1', '0'] else 0
    except: return 0

def fetch_and_validate():
    news_data, logs = [], load_json(CROSS_VAL_FILE)
    
    for source, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                lex_score, cat = 0.0, "General"
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, entry.title.lower()):
                        lex_score, cat = float(w * d), c
                        break
                
                if lex_score != 0:
                    ai_dir = get_ai_validation(entry.title)
                    lex_dir = 1 if lex_score > 0 else -1
                    status = "CONFLUÊNCIA" if ai_dir == lex_dir else "DIVERGÊNCIA"
                    
                    news_data.append({
                        "Data": datetime.now().strftime("%H:%M"),
                        "Fonte": source,
                        "Manchete": entry.title,
                        "Alpha": lex_score,
                        "Status": status
                    })
                    
                    logs.insert(0, {"Data": datetime.now().strftime("%H:%M"), "Manchete": entry.title[:70], "Lex": lex_dir, "AI": ai_dir, "Result": status})
        except: continue
    
    save_json(CROSS_VAL_FILE, logs[:100])
    if news_data: pd.DataFrame(news_data).to_csv("Oil_Station_V90.csv", index=False)

# --- 5. INTERFACE PRINCIPAL ---
def main():
    fetch_and_validate()
    
    # Simulação de market metrics (usar a função do código anterior)
    mkt = {"WTI": 75.40, "Z": 1.2, "status": "Online"} 
    df_news = pd.read_csv("Oil_Station_V90.csv") if os.path.exists("Oil_Station_V90.csv") else pd.DataFrame()
    
    st.markdown(f'<div class="live-status"><div>TERMINAL XTIUSD V90</div><div>{datetime.now().strftime("%H:%M")}</div></div>', unsafe_allow_html=True)
    
    t1, t2, t3, t4 = st.tabs(["📊 MONITOR", "🧠 LEARNING", "🤖 SITREP", "⚖️ VALIDAÇÃO"])

    with t1:
        c1, c2, c3 = st.columns(3)
        c1.metric("WTI", f"$ {mkt['WTI']}")
        c2.metric("Z-SCORE", mkt['Z'])
        c3.metric("FEED", mkt['status'])
        
        if not df_news.empty:
            df_view = df_news.copy()
            df_view['Status'] = df_view['Status'].apply(lambda x: f'<span class="{"match-tag" if x=="CONFLUÊNCIA" else "mismatch-tag"}">{x}</span>')
            st.write(df_view.to_html(escape=False, index=False), unsafe_allow_html=True)

    with t4:
        st.subheader("Log de Validação Cruzada (IA vs Lexicon)")
        logs = load_json(CROSS_VAL_FILE)
        if logs:
            st.table(pd.DataFrame(logs).head(20))

if __name__ == "__main__": main()
