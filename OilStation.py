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

st.set_page_config(page_title="TERMINAL XTIUSD - V80 FULL", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=300000, key="v80_refresh") 

# Arquivos de Memória
MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"

st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle, #0D1421 0%, #050A12 100%); color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1rem;}
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    [data-testid="stMetricLabel"] { font-size: 10px !important; color: #94A3B8 !important; text-transform: uppercase; }
    
    .live-status {
        display: flex; justify-content: space-between; align-items: center; 
        padding: 10px; background: rgba(30, 41, 59, 0.3); 
        border-bottom: 2px solid #00FFC8; margin-bottom: 20px;
    }
    .arbitrage-monitor { padding: 20px; border-radius: 5px; border: 1px solid #1E293B; background: rgba(0, 0, 0, 0.4); margin-bottom: 20px; text-align: center; }
    .scroll-container { height: 480px; overflow-y: auto; border: 1px solid rgba(30, 41, 59, 0.5); background: rgba(0, 0, 0, 0.2); }
    .scroll-container::-webkit-scrollbar { width: 4px; }
    .scroll-container::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 10px; }
    
    .learned-box { border: 1px solid #334155; padding: 15px; border-radius: 8px; margin-bottom: 10px; background: #0F172A; }
    .learned-term { color: #FACC15; font-weight: bold; font-family: monospace; font-size: 14px; }
    
    .pos-score { color: #00FFC8; font-weight: bold; }
    .neg-score { color: #FF4B4B; font-weight: bold; }

    div.stButton > button { width: 100%; border-radius: 4px; font-weight: bold; height: 32px; font-size: 11px; }
    .btn-approve button { background-color: #00FFC8 !important; color: #050A12 !important; }
    .btn-reject button { background-color: #FF4B4B !important; color: #FFFFFF !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LEXICONS (SITES E TÓPICOS) ---
RSS_SOURCES = {
    "Bloomberg Energy": "https://www.bloomberg.com/feeds/bview/energy.xml", "Reuters Oil": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "CNBC Commodities": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135", "FT Commodities": "https://www.ft.com/commodities?format=rss",
    "WSJ Energy": "https://feeds.a.dj.com/rss/RSSWSJ.xml", "OilPrice Main": "https://oilprice.com/rss/main",
    "Rigzone": "https://www.rigzone.com/news/rss/rigzone_latest.xml", "S&P Global Platts": "https://www.spglobal.com/platts/en/rss-feed/news/oil",
    "Energy Voice": "https://www.energyvoice.com/category/oil-and-gas/feed/", "EIA Today": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "Investing.com": "https://www.investing.com/rss/news_11.rss", "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Yahoo Finance Oil": "https://finance.yahoo.com/rss/headline?s=CL=F", "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Foreign Policy": "https://foreignpolicy.com/feed/", "Lloyds List": "https://lloydslist.maritimeintelligence.informa.com/RSS/News",
    "Marine Insight": "https://www.marineinsight.com/feed/", "Splash 247": "https://splash247.com/feed/",
    "OPEC Press": "https://www.opec.org/opec_web/en/press_room/311.xml", "IEA News": "https://www.iea.org/news/rss",
    "BOC News": "https://www.bankofcanada.ca/feed/", "Fed News": "https://www.federalreserve.gov/feeds/press_all.xml"
}

LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation": [9.8, 1, "Geopolitics"],
    r"sanction|embargo|ban|price cap": [9.0, 1, "Sanctions"],
    r"iran|strait of hormuz|red sea|houthis": [9.8, 1, "Chokepoints"],
    r"israel|gaza|hezbollah|lebanon|tehran": [9.2, 1, "Middle East"],
    r"opec|saudi|russia|cut|quota": [9.5, 1, "OPEC+"],
    r"shale|fracking|permian|rig count": [7.5, -1, "US Supply"],
    r"inventory|stockpile|draw|api|eia": [8.0, 1, "Stocks"],
    r"build|glut|oversupply|surplus": [8.0, -1, "Surplus"],
    r"recession|slowdown|weak|china": [8.8, -1, "Demand"],
    r"fed|rate hike|hawkish|inflation|boc": [7.5, -1, "Macro Tightening"],
    r"dovish|rate cut|powell|easing": [7.5, 1, "Macro Easing"],
    r"dollar|dxy|greenback|usdcad": [7.0, -1, "FX Correl"]
}

# --- 3. FUNÇÕES DE SUPORTE (JSON) ---
def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)

def learn_patterns(text, cat, score, memory):
    text = re.sub(r'[^a-z\s]', '', text.lower())
    tokens = text.split()
    if len(tokens) < 2: return memory
    phrases = [' '.join(tokens[i:i+2]) for i in range(len(tokens)-1)]
    if cat not in memory: memory[cat] = {}
    for ph in phrases:
        if ph not in memory[cat]: memory[cat][ph] = {"count": 0, "sum": 0.0}
        memory[cat][ph]["count"] += 1
        memory[cat][ph]["sum"] += score
    return memory

# --- 4. ENGINE ---
def fetch_news():
    news_list = []
    memory = load_json(MEMORY_FILE)
    verified = load_json(VERIFIED_FILE)
    
    for source, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                score, cat = 0.0, "General"
                title_low = entry.title.lower()
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        score = float(w * d)
                        cat = c
                        break
                
                # Checar se existe termo verificado manualmente
                if cat in verified:
                    for ph, val in verified[cat].items():
                        if ph in title_low: score += val

                if score != 0:
                    news_list.append({"Data": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title[:100], "Alpha": score, "Cat": cat})
                    memory = learn_patterns(entry.title, cat, score, memory)
        except: continue
    
    save_json(MEMORY_FILE, memory)
    if news_list: pd.DataFrame(news_list).to_csv("Oil_Station_V54_Master.csv", index=False)

@st.cache_data(ttl=600)
def get_market_metrics():
    try:
        data = yf.download(["CL=F", "USDCAD=X"], period="5d", interval="15m", progress=False, threads=False)
        p_wti = data['Close']['CL=F'].iloc[-1]
        p_cad = data['Close']['USDCAD=X'].iloc[-1]
        ratio = data['Close']['CL=F'] / data['Close']['USDCAD=X']
        z = (ratio.iloc[-1] - ratio.mean()) / ratio.std()
        return {"WTI": p_wti, "USDCAD": p_cad, "Z": float(z), "status": "Online"}
    except: return {"WTI": 75.0, "USDCAD": 1.35, "Z": 0.0, "status": "Offline"}

# --- 5. MAIN ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df_news = pd.read_csv("Oil_Station_V54_Master.csv") if os.path.exists("Oil_Station_V54_Master.csv") else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0.0
    ica_val = (avg_alpha + (mkt['Z'] * -5)) / 2

    # Status Bar
    st.markdown(f'<div class="live-status"><div style="font-weight:800; color:#00FFC8;">TERMINAL XTIUSD | QUANT V80</div><div style="font-family:monospace;">{datetime.now().strftime("%H:%M:%S")} <span style="color:#00FFC8;">● {mkt["status"]}</span></div></div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📊 DASHBOARD", "🧠 IA LEARNING", "🤖 AI SITREP"])

    with tab1:
        color = "#00FFC8" if ica_val > 0 else "#FF4B4B"
        st.markdown(f'<div class="arbitrage-monitor" style="border-color:{color}; color:{color};"><strong>ICA SCORE: {ica_val:.2f}</strong></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI", f"$ {mkt['WTI']:.2f}")
        c2.metric("USDCAD", f"{mkt['USDCAD']:.4f}")
        c3.metric("Z-SCORE", f"{mkt['Z']:.2f}")
        c4.metric("ALPHA", f"{avg_alpha:.2f}")
        
        if not df_news.empty:
            st.markdown(f'<div class="scroll-container">{df_news.to_html(escape=False, index=False)}</div>', unsafe_allow_html=True)

    with tab2:
        st.subheader("Novas Expressões Detectadas")
        memory = load_json(MEMORY_FILE)
        verified = load_json(VERIFIED_FILE)
        
        for cat, phrases in memory.items():
            st.write(f"📂 Categoria: {cat}")
            cols = st.columns(2)
            for i, (ph, data) in enumerate(phrases.items()):
                if data['count'] < 3: continue # Só mostra o que repetiu 3x
                with cols[i % 2]:
                    st.markdown(f'<div class="learned-box"><span class="learned-term">"{ph}"</span> (Visto {data["count"]}x)</div>', unsafe_allow_html=True)
                    if st.button(f"Aprovar {ph}", key=f"app_{ph}"):
                        if cat not in verified: verified[cat] = {}
                        verified[cat][ph] = data['sum'] / data['count']
                        save_json(VERIFIED_FILE, verified)
                        st.success("Adicionado ao Léxico!")
                    if st.button(f"Negar {ph}", key=f"neg_{ph}"):
                        del memory[cat][ph]
                        save_json(MEMORY_FILE, memory)
                        st.rerun()

    with tab3:
        if not df_news.empty:
            try:
                analise = client.models.generate_content(model="gemini-2.0-flash", contents=f"Resuma o risco: {'. '.join(df_news['Manchete'].head(5))}")
                st.info(analise.text)
            except: st.write("IA indisponível.")

if __name__ == "__main__": main()
