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

st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=300000, key="v80_refresh") 

MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"

st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle, #0D1421 0%, #050A12 100%); color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1rem;}
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: rgba(30, 41, 59, 0.3); border-bottom: 2px solid #00FFC8; margin-bottom: 20px; }
    .site-tag { background: #00FFC8; color: #050A12; padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: 800; margin-right: 8px; display: inline-block; margin-bottom: 8px; }
    .learned-box { border: 1px solid #1E293B; padding: 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.6); margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. OS 22 LEXICONS (INTEGRAIS) ---
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
    r"dovish|rate cut|powell|easing": [7.5, 1, "Macro Easing"],
    r"emergency release|spr|biden": [8.5, -1, "Policy Supply"],
    r"hurricane|storm|refinery shut": [7.0, 1, "Disruption"],
    r"pipeline|leak|outage": [6.5, 1, "Logistics"],
    r"ev|electric vehicle|transition": [5.0, -1, "Long-term Demand"],
    r"green energy|renewables": [4.0, -1, "Alt Energy"],
    r"libya|unrest|shutdown": [8.2, 1, "African Supply"],
    r"venezuela|pdvsa|maduro": [7.8, 1, "Latam Geopol"],
    r"cpi|ppi|jobs report": [6.0, -1, "Data Macro"],
    r"bullish|upside|target increase": [5.5, 1, "Sentiment"],
    r"bearish|downside|selloff": [5.5, -1, "Sentiment"],
    r"rigs|drilling|exploration": [6.2, -1, "Investment"],
    r"storage|hub|cushing": [7.3, 1, "Inventory Hub"]
}

NEWS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC Energy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "MarketWatch": "https://www.marketwatch.com/rss/market-data",
    "Reuters Cmdty": "https://www.reutersagency.com/feed/?best-topics=commodities&post_type=best",
    "Yahoo Energy": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "EIA Reports": "https://www.eia.gov/about/rss/todayinenergy.xml"
}

# --- 3. SUPORTE & ENGINE ---
def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)

def get_ai_val(title):
    try:
        prompt = f"Impacto WTI (1,-1,0) e 2 termos: '{title}'. JSON: {{\"alpha\": v, \"termos\": [\"t1\", \"t2\"]}}"
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res)
    except: return {"alpha": 0, "termos": []}

def fetch_news():
    news_list = []
    memory = load_json(MEMORY_FILE)
    for source, url in NEWS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]:
                ai_data = get_ai_val(entry.title)
                for t in ai_data.get("termos", []):
                    t = t.lower()
                    if t not in memory: memory[t] = {"count": 1, "alpha": ai_data.get("alpha", 0)}
                    else: memory[t]["count"] += 1
                news_list.append({
                    "Data": datetime.now().strftime("%H:%M"),
                    "Fonte": source, "Manchete": entry.title[:100], "Alpha": float(ai_data.get("alpha", 0) * 10)
                })
        except: continue
    save_json(MEMORY_FILE, memory)
    if news_list: pd.DataFrame(news_list).to_csv("Oil_Station_V80_Hybrid.csv", index=False)

@st.cache_data(ttl=1500)
def get_market_metrics():
    try:
        data = yf.download(["CL=F", "USDCAD=X"], period="2d", interval="15m", progress=False)
        wti = float(data['Close']['CL=F'].dropna().iloc[-1])
        cad = float(data['Close']['USDCAD=X'].dropna().iloc[-1])
        ratio = data['Close']['CL=F'] / data['Close']['USDCAD=X']
        z = float((ratio.iloc[-1] - ratio.mean()) / ratio.std())
        return {"WTI": wti, "CAD": cad, "Z": z, "status": "Online"}
    except: return {"WTI": 75.20, "CAD": 1.380, "Z": 0.0, "status": "Cooldown"}

# --- 4. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    memory = load_json(MEMORY_FILE)
    verified = load_json(VERIFIED_FILE)
    df_news = pd.read_csv("Oil_Station_V80_Hybrid.csv") if os.path.exists("Oil_Station_V80_Hybrid.csv") else pd.DataFrame()
    
    avg_alpha = df_news['Alpha'].mean() if not df_news.empty else 0.0
    ica_val = (avg_alpha + (mkt['Z'] * -5)) / 2

    st.markdown(f'<div class="live-status"><b>TERMINAL XTIUSD V80 HYBRID</b> ● {mkt["status"]}</div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📊 DASHBOARD", "🧠 IA TRAINING & LEXICONS"])

    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI", f"$ {mkt['WTI']:.2f}")
        c2.metric("USDCAD", f"{mkt['CAD']:.4f}")
        c3.metric("Z-SCORE", f"{mkt['Z']:.2f}")
        c4.metric("ICA SCORE", f"{ica_val:.2f}")

        col_g, col_n = st.columns([1, 2])
        with col_g:
            fig = go.Figure(go.Indicator(
                mode = "gauge+number", value = ica_val,
                gauge = {'axis': {'range': [-10, 10]}, 'bar': {'color': "#00FFC8"},
                         'steps': [{'range': [-10, -3], 'color': '#450a0a'}, {'range': [3, 10], 'color': '#064E3B'}]}))
            fig.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, width='stretch')
        with col_n:
            if not df_news.empty: st.dataframe(df_news, width='stretch', height=350)

    with tab2:
        st.subheader("🌐 FONTES E LÉXICOS (SISTEMA INTEGRAL)")
        sites_html = "".join([f'<span class="site-tag">{s}</span>' for s in NEWS_SOURCES.keys()])
        st.markdown(f'<div>{sites_html}</div>', unsafe_allow_html=True)
        
        st.divider()
        
        c_left, c_right = st.columns(2)
        with c_left:
            st.subheader(f"📖 Dicionário Ativo ({len(LEXICON_TOPICS)} Termos)")
            df_lex = pd.DataFrame([{"Padrão": k, "Peso": v[0], "Categoria": v[2]} for k, v in LEXICON_TOPICS.items()])
            st.dataframe(df_lex, width='stretch', height=450)
        with c_right:
            st.subheader("🧠 Treinar Novos Termos")
            if not memory: st.info("Aguardando novas capturas da IA...")
            for term in list(memory.keys())[:12]:
                with st.container():
                    ci, ca, cr = st.columns([2, 1, 1])
                    ci.markdown(f'<div class="learned-box">{term.upper()}</div>', unsafe_allow_html=True)
                    if ca.button("✅", key=f"a_{term}"):
                        verified[term] = memory[term]["alpha"]
                        del memory[term]
                        save_json(VERIFIED_FILE, verified); save_json(MEMORY_FILE, memory); st.rerun()
                    if cr.button("❌", key=f"r_{term}"):
                        del memory[term]; save_json(MEMORY_FILE, memory); st.rerun()

if __name__ == "__main__": main()
