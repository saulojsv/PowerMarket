import pandas as pd
import re
import feedparser
import os
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÕES E HARMONIA VISUAL (CORREÇÃO DE TELA PRETA) ---
st.set_page_config(page_title="Terminal - XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_pro")

st.markdown("""
    <style>
    /* Gradiente Profundo para evitar tela preta travada */
    .stApp { 
        background: radial-gradient(circle, #0D1421 0%, #050A12 100%); 
        color: #FFFFFF; 
    }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1.5rem;}
    
    /* Tipografia de Alta Legibilidade */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Métricas e Cards */
    [data-testid="stMetricValue"] { font-size: 28px !important; color: #00FFC8 !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { font-size: 12px !important; color: #94A3B8 !important; text-transform: uppercase; }
    
    .ai-brain {
        background: rgba(0, 255, 200, 0.05);
        border: 1px solid rgba(0, 255, 200, 0.2);
        padding: 20px; border-radius: 12px; margin-bottom: 20px;
    }

    /* Tabela Estilizada */
    .reportview-container table { color: #FFFFFF; }
    a { color: #00FFC8 !important; text-decoration: none; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. BASE DE CONHECIMENTO COMPLETA (20 FONTES / 22 LEXICONS) ---
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
    "IEA News": "https://www.iea.org/news/rss"
}

LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation|invasion": [9.8, 1, "Geopolitics (Conflict)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolitics (Sanctions)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Chokepoint Risk"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Regional Tensions"],
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "OPEC+ Policy"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "OPEC+ Supply"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "US Supply"],
    r"non-opec|brazil|guyana|canada|output surge": [7.0, -1, "Non-OPEC Supply"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Stocks (Deficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Stocks (Surplus)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refining/Margins"],
    r"crack spread|heating oil|jet fuel|diesel demand": [6.5, 1, "Distillates"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Weak Demand)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Strong Demand)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate": [7.5, -1, "Macro (Fed Tightening)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Fed Easing)"],
    r"dollar|dxy|greenback|fx|yields": [7.0, -1, "DXY Correlation"],
    r"gdp|pmi|manufacturing|industrial production": [6.8, 1, "Macro Indicators"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Speculative Flow"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Technical Analysis"],
    r"volatility|vix|contango|backwardation": [6.2, 1, "Term Structure"],
    r"algorithmic trading|ctas|margin call|liquidation": [6.0, 1, "Quant Flow"]
}

# --- 3. MOTOR DE INTELIGÊNCIA ---
def run_global_scrap():
    news_data = []
    DB_FILE = "Oil_Station_V54_Master.csv"
    for name, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                score, cat = 0, "Neutral"
                title_low = entry.title.lower()
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        score = w * d; cat = c; break
                news_data.append({"Data": datetime.now().strftime("%H:%M"), "Fonte": name, "Manchete": entry.title[:85], "Alpha": score, "Cat": cat, "Link": entry.link})
        except: continue
    if news_data:
        df_new = pd.DataFrame(news_data)
        if os.path.exists(DB_FILE):
            df_old = pd.read_csv(DB_FILE)
            df_new = pd.concat([df_new, df_old]).drop_duplicates(subset=['Manchete']).head(100)
        df_new.to_csv(DB_FILE, index=False)

@st.cache_data(ttl=300)
def get_intel():
    try:
        data_h1 = yf.download("CL=F", period="10d", interval="1h", progress=False)['Close'].ffill()
        data_d1 = yf.download("CL=F", period="60d", interval="1d", progress=False)['Close'].ffill()
        price = data_h1.iloc[-1]
        day_trend = "BULLISH" if price > data_h1.rolling(20).mean().iloc[-1] else "BEARISH"
        swing_trend = "BULLISH" if price > data_d1.rolling(50).mean().iloc[-1] else "BEARISH"
        return {"price": price, "day": day_trend, "swing": swing_trend, "delta": ((price/data_h1.iloc[0])-1)*100}
    except: return None

# --- 4. INTERFACE ---
def main():
    run_global_scrap()
    intel = get_intel()
    DB_FILE = "Oil_Station_V54_Master.csv"
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0.0

    # IA Autonomous Brain
    st.markdown(f"""
        <div class="ai-brain">
            <span style="color: #00FFC8; font-weight: 700; font-size: 13px;">IA INITIATIVE ENGINE</span>
            <div style="margin-top: 8px; font-size: 15px;">
                {'ALTA CONVICÇÃO: Alpha Geopolítico alinhado à tendência de H1.' if avg_alpha > 7 and intel and intel['day'] == "BULLISH" else '⚖️ MONITORANDO: Fluxo neutro ou sinais divergentes.'}
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Métricas
    c1, c2, c3, c4 = st.columns(4)
    if intel:
        c1.metric("WTI", f"$ {intel['price']:.2f}", f"{intel['delta']:.2f}%")
        c2.metric("IA ALPHA", f"{avg_alpha:.2f}")
        c3.metric("DAYTRADE", intel['day'])
        c4.metric("SWING", intel['swing'])

    st.markdown("---")

    col_v, col_n = st.columns([1, 1.8])
    with col_v:
        fig = go.Figure(go.Indicator(
            mode = "gauge+number", value = avg_alpha,
            gauge = {'axis': {'range': [-10, 10]}, 'bar': {'color': "#00FFC8" if avg_alpha > 0 else "#FF4B4B"}, 'bgcolor': "#0D1421"}
        ))
        fig.update_layout(height=250, margin=dict(t=0,b=0), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
        st.plotly_chart(fig, width='stretch')

    with col_n:
        st.markdown("### Terminal - XTIUSD")
        if not df_news.empty:
            df_display = df_news.head(15).copy()
            df_display['Link'] = df_display['Link'].apply(lambda x: f'<a href="{x}" target="_blank">OPEN LINK</a>')
            st.markdown(df_display[['Data', 'Fonte', 'Manchete', 'Alpha', 'Link']].to_html(escape=False, index=False), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
