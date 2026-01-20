import pandas as pd
import re
import feedparser
import time
import os
import streamlit as st
import plotly.graph_objects as go
import numpy as np
import yfinance as yf
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÕES E ESTILO ---
st.set_page_config(page_title="Terminal - XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_pro")

st.markdown("""
    <style>
    .stApp { background-color: #050A12; color: #E0E0E0; }
    .status-bar {
        padding: 15px; border-radius: 10px; border-left: 5px solid #00FFC8;
        background: #0D1421; margin-bottom: 25px; font-family: 'Courier New', monospace;
    }
    .trade-signal {
        padding: 20px; border-radius: 15px; text-align: center;
        font-weight: bold; font-size: 24px; border: 1px solid #1B263B;
    }
    [data-testid="stMetricValue"] { font-size: 26px !important; color: #00FFC8 !important; }
    div[data-testid="metric-container"] {
        background-color: #0D1421; border: 1px solid #1B263B;
        padding: 15px; border-radius: 12px; box-shadow: 0px 4px 15px rgba(0,0,0,0.5);
    }
    </style>
""", unsafe_allow_html=True)

# --- PARÂMETROS ---
DB_FILE = "Oil_Station_V54_Master.csv"
TRADE_LOG_FILE = "Trade_Simulation_V54.csv"
SUSPECT_ASSETS = ["CL=F", "BZ=F", "DX-Y.NYB", "USDCAD=X", "^VIX", "^TNX", "AUDJPY=X", "XLE"]

# --- 2. BASE DE CONHECIMENTO (20 FONTES E 22 LEXICONS CRÍTICOS EM INGLÊS) ---
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
    for name, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                score, cat = 0, "Neutral"
                title_low = entry.title.lower()
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        score = w * d; cat = c; break
                news_data.append({"Data": datetime.now().strftime("%H:%M"), "Fonte": name, "Manchete": entry.title[:85], "Alpha": score, "Cat": cat})
        except: continue
    
    if news_data:
        df_new = pd.DataFrame(news_data)
        if os.path.exists(DB_FILE):
            df_old = pd.read_csv(DB_FILE)
            df_new = pd.concat([df_new, df_old]).drop_duplicates(subset=['Manchete']).head(100)
        df_new.to_csv(DB_FILE, index=False)

@st.cache_data(ttl=300)
def get_market_intel():
    try:
        data = yf.download(SUSPECT_ASSETS, period="7d", interval="1h", progress=False)['Close']
        if data.empty: return None
        data = data.ffill().bfill()
        prices = data.iloc[-1]
        deltas = ((data.iloc[-1] / data.iloc[0]) - 1) * 100
        return prices, deltas, data.corr().fillna(0)
    except: return None

# --- AVALIAÇÃO DE SENSAÇÃO (LÓGICA DE TOMADA DE DECISÃO) ---
def get_bias_evaluation(alpha, delta_wti):
    score = (alpha * 0.5) + (delta_wti * 10) # Peso combinado IA + Preço
    if score > 5: return "STRONG BUY BIAS", "#00FFC8", "Market feeling bullish on supply fear/demand growth."
    if score < -5: return "STRONG SELL BIAS", "#FF4B4B", "Market feeling bearish on macro headwinds/excess supply."
    return "NEUTRAL / WAIT", "#E0E0E0", "No clear directional sensation. Scalp with caution."

# --- 4. INTERFACE ---
def main():
    run_global_scrap()
    market = get_market_intel()
    if market is None: return
        
    prices, deltas, corr_matrix = market
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0
    bias, b_color, b_desc = get_bias_evaluation(avg_alpha, deltas.get('CL=F', 0))
    
    # Barra de Status
    st.markdown(f'<div class="status-bar">TERMINAL XTIUSD | CRITICAL MODE | ALPHA: {avg_alpha:.2f}</div>', unsafe_allow_html=True)

    # Métricas
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("WTI", f"$ {prices.get('CL=F', 0):.2f}", f"{deltas.get('CL=F', 0):.2f}%")
    m2.metric("VIX", f"{prices.get('^VIX', 0):.2f}", f"{deltas.get('^VIX', 0):.2f}%")
    m3.metric("ALPHA IA", f"{avg_alpha:.2f}")
    
    lucro = 0
    if os.path.exists(TRADE_LOG_FILE):
        try: lucro = pd.read_csv(TRADE_LOG_FILE)['PnL'].sum()
        except: pass
    m4.metric("BANCA", f"{300 + lucro:.2f} €")

    st.markdown("---")
    
    # Bloco de Avaliação de Sensação
    col_sig, col_gauge = st.columns([1, 1])
    with col_sig:
        st.write("### Decision Sensitivity")
        st.markdown(f"""
            <div class="trade-signal" style="color: {b_color}; border-color: {b_color}; background: rgba(0,0,0,0.2)">
                {bias}<br><small style="font-size: 14px; color: #888;">{b_desc}</small>
            </div>
        """, unsafe_allow_html=True)
    
    with col_gauge:
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = avg_alpha,
            gauge = {'axis': {'range': [-10, 10]}, 'bar': {'color': b_color}, 
                     'steps': [{'range': [-10, -5], 'color': 'rgba(255, 75, 75, 0.2)'}, {'range': [5, 10], 'color': 'rgba(0, 255, 200, 0.2)'}]},
            title = {'text': "IA Sensation Score"}
        ))
        fig_gauge.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=250, margin=dict(t=30, b=0))
        st.plotly_chart(fig_gauge, use_container_width=True)

    # TABELA TERMINAL - XTIUSD
    st.markdown("### Terminal - XTIUSD")
    if not df_news.empty:
        # Estilização: Verde para Alpha+, Vermelho para Alpha-, Cinza para Neutro
        def style_rows(row):
            if row['Alpha'] > 0: return ['color: #00FFC8'] * len(row)
            if row['Alpha'] < 0: return ['color: #FF4B4B'] * len(row)
            return ['color: #888888'] * len(row)

        st.dataframe(df_news.head(30).style.apply(style_rows, axis=1), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
