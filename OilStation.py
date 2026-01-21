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

# --- 1. CONFIGURAÇÃO IA & ESTÉTICA TERMINAL ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")

st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=300000, key="v80_refresh") 

MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"
CROSS_VAL_FILE = "cross_validation_log.json"

# Estética Estilo Bloomberg/Reuters
st.markdown("""
    <style>
    .stApp { background: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #111827; border-bottom: 2px solid #00FFC8; margin-bottom: 20px; font-family: monospace; }
    .scroll-container { height: 450px; overflow-y: auto; border: 1px solid #1E293B; background: #020617; font-family: 'Courier New', monospace; }
    .match-tag { background: #064E3B; color: #34D399; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .veto-tag { background: #450a0a; color: #f87171; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .learned-box { border: 1px solid #1E293B; padding: 10px; background: #0F172A; margin-bottom: 5px; border-left: 4px solid #FACC15; }
    .site-tag { background: #1E293B; color: #00FFC8; padding: 2px 8px; border-radius: 10px; font-size: 10px; margin-right: 5px; border: 1px solid #00FFC8; }
    table { width: 100%; border-collapse: collapse; color: #CBD5E1; font-size: 13px; }
    th { background: #1E293B; color: #00FFC8; text-align: left; padding: 8px; }
    td { padding: 8px; border-bottom: 1px solid #1E293B; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 22 LEXICONS & 7 FONTES ---
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
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "MarketWatch": "https://www.marketwatch.com/rss/market-data",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=commodities&post_type=best",
    "Yahoo": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml"
}

# --- 3. SUPORTE ---
def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)

def get_ai_val(title):
    try:
        prompt = f"Analise impacto Petróleo WTI (1, -1 ou 0) e extraia 2 termos técnicos: '{title}'. JSON: {{\"alpha\": v, \"termos\": [\"t1\", \"t2\"]}}"
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res)
    except: return {"alpha": 0, "termos": []}

# --- 4. ENGINE DE ARBITRAGEM (IA vs LEXICON) ---
def fetch_news():
    news_list = []
    memory = load_json(MEMORY_FILE)
    
    for source, url in NEWS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]:
                title_low = entry.title.lower()
                lex_dir = 0
                # Lógica de Convergência
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        lex_dir = d
                        break
                
                ai_data = get_ai_val(entry.title)
                ai_dir = ai_data.get("alpha", 0)
                
                # Salva termos para treino
                for t in ai_data.get("termos", []):
                    t = t.lower()
                    if t not in memory: memory[t] = {"alpha": ai_dir}

                status = "CONFLUÊNCIA" if ai_dir == lex_dir and ai_dir != 0 else "DIVERGÊNCIA"
                if lex_dir == 0 and ai_dir != 0: status = "IA SOLO"

                news_list.append({
                    "Data": datetime.now().strftime("%H:%M"),
                    "Fonte": source,
                    "Manchete": entry.title[:90],
                    "Alpha": float(ai_dir * 10),
                    "Status": status
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
    except: return {"WTI": 75.0, "CAD": 1.38, "Z": 0.0, "status": "Cooldown"}

# --- 5. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    memory = load_json(MEMORY_FILE)
    df_news = pd.read_csv("Oil_Station_V80_Hybrid.csv") if os.path.exists("Oil_Station_V80_Hybrid.csv") else pd.DataFrame()
    
    avg_alpha = df_news['Alpha'].mean() if not df_news.empty else 0.0
    ica_val = (avg_alpha + (mkt['Z'] * -5)) / 2

    st.markdown(f'<div class="live-status"><div><b>TERMINAL QUANT</b> | XTIUSD V80</div><div>{mkt["status"]} ● {datetime.now().strftime("%H:%M")}</div></div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📊 DASHBOARD", "🧠 IA TRAINING & LEXICONS"])

    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI", f"$ {mkt['WTI']:.2f}")
        c2.metric("USDCAD", f"{mkt['CAD']:.4f}")
        c3.metric("Z-SCORE", f"{mkt['Z']:.2f}")
        c4.metric("ICA", f"{ica_val:.2f}")

        col_g, col_n = st.columns([1, 2])
        with col_g:
            fig = go.Figure(go.Indicator(
                mode = "gauge+number", value = ica_val,
                gauge = {'axis': {'range': [-10, 10]}, 'bar': {'color': "#00FFC8"},
                         'steps': [{'range': [-10, -3], 'color': '#450a0a'}, {'range': [3, 10], 'color': '#064E3B'}]}))
            fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, width='stretch')

        with col_n:
            if not df_news.empty:
                # Tabela Estilo Bloomberg/Reuters
                html = "<table><tr><th>DATA</th><th>FONTE</th><th>MANCHETE</th><th>ALPHA</th><th>STATUS</th></tr>"
                for _, row in df_news.iterrows():
                    tag = f'<span class="match-tag">{row["Status"]}</span>' if row["Status"]=="CONFLUÊNCIA" else f'<span class="veto-tag">{row["Status"]}</span>'
                    html += f"<tr><td>{row['Data']}</td><td>{row['Fonte']}</td><td>{row['Manchete']}</td><td>{row['Alpha']}</td><td>{tag}</td></tr>"
                html += "</table>"
                st.markdown(f'<div class="scroll-container">{html}</div>', unsafe_allow_html=True)

    with tab2:
        st.subheader("🌐 FONTES ATIVAS")
        st.markdown(" ".join([f'<span class="site-tag">{s}</span>' for s in NEWS_SOURCES.keys()]), unsafe_allow_html=True)
        
        st.divider()
        cl, cr = st.columns(2)
        with cl:
            st.subheader("📖 Lexicons Bases (22)")
            st.dataframe(pd.DataFrame([{"Termo": k, "Peso": v[0]} for k, v in LEXICON_TOPICS.items()]), width='stretch', height=400)
        with cr:
            st.subheader("🧠 Treino de Novas Palavras")
            for term in list(memory.keys())[:10]:
                with st.container():
                    c_t, c_b = st.columns([3, 1])
                    c_t.markdown(f'<div class="learned-box"><b>{term.upper()}</b> (Impacto: {memory[term]["alpha"]})</div>', unsafe_allow_html=True)
                    if c_b.button("✅", key=f"a_{term}"):
                        # Aqui você salvaria no verified_lexicons.json se quiser
                        del memory[term]; save_json(MEMORY_FILE, memory); st.rerun()
                    if c_b.button("❌", key=f"r_{term}"):
                        del memory[term]; save_json(MEMORY_FILE, memory); st.rerun()

if __name__ == "__main__": main()
