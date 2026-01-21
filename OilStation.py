import pandas as pd
import re
import feedparser
import os
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
import numpy as np
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÕES E ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD - ARBITRAGEM", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v69_refresh")

st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle, #0D1421 0%, #050A12 100%); color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1rem;}
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    [data-testid="stMetricLabel"] { font-size: 10px !important; color: #94A3B8 !important; text-transform: uppercase; }
    
    .arbitrage-monitor {
        padding: 20px;
        border-radius: 5px;
        border: 1px solid #1E293B;
        background: rgba(0, 0, 0, 0.4);
        margin-bottom: 20px;
        text-align: center;
    }

    .scroll-container {
        height: 480px;
        overflow-y: auto;
        border: 1px solid rgba(30, 41, 59, 0.5);
        background: rgba(0, 0, 0, 0.2);
    }
    .scroll-container::-webkit-scrollbar { width: 4px; }
    .scroll-container::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 10px; }
    
    table { width: 100%; border-collapse: collapse; }
    th { color: #94A3B8 !important; font-size: 10px; text-transform: uppercase; border-bottom: 1px solid #1E293B; padding: 10px; position: sticky; top: 0; background: #050A12; z-index: 10; }
    td { font-size: 12px; padding: 10px; border-bottom: 1px solid #0D1421; }
    .pos-score { color: #00FFC8; font-weight: bold; }
    .neg-score { color: #FF4B4B; font-weight: bold; }
    a { color: #00FFC8 !important; text-decoration: none; font-size: 10px; font-weight: 700; border: 1px solid #00FFC8; padding: 2px 5px; border-radius: 3px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. BASE DE DADOS (20 SITES / 22 LEXICONS MANTIDOS) ---
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
def fetch_filtered_news():
    news_data = []
    DB_FILE = "Oil_Station_V54_Master.csv"
    for name, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                score, cat = 0.0, None
                title_low = entry.title.lower()
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        score = float(w * d)
                        cat = c
                        break
                if score != 0:
                    news_data.append({
                        "Data": datetime.now().strftime("%H:%M:%S"),
                        "Fonte": name,
                        "Manchete": entry.title[:90],
                        "Alpha": score,
                        "Cat": cat,
                        "Link": entry.link
                    })
        except:
            continue
    if news_data:
        df_new = pd.DataFrame(news_data)
        if os.path.exists(DB_FILE):
            df_old = pd.read_csv(DB_FILE)
            df_final = pd.concat([df_new, df_old]).drop_duplicates(subset=['Manchete']).head(300)
            df_final.to_csv(DB_FILE, index=False)
        else:
            df_new.to_csv(DB_FILE, index=False)

@st.cache_data(ttl=60)
def get_market_metrics():
    tickers = {"WTI": "CL=F", "BRENT": "BZ=F", "DXY": "DX-Y.NYB"}
    prices = {"WTI": 0.0, "BRENT": 0.0, "DXY": 0.0}
    wti_momentum = 0.0
    z_score = 0.0
    try:
        data = yf.download(list(tickers.values()), period="5d", interval="15m", progress=False, ignore_tz=True)
        if not data.empty and 'Close' in data:
            closes = data['Close'].ffill()
            for k, v in tickers.items():
                if v in closes.columns:
                    prices[k] = float(closes[v].iloc[-1])
            
            # Cálculo de Arbitragem Estatística (Z-Score do Spread Brent/WTI)
            if "BZ=F" in closes.columns and "CL=F" in closes.columns:
                spread_series = closes["BZ=F"] - closes["CL=F"]
                mean_spread = spread_series.mean()
                std_spread = spread_series.std()
                z_score = (spread_series.iloc[-1] - mean_spread) / std_spread
                
                wti_series = closes["CL=F"]
                wti_momentum = float(wti_series.pct_change(fill_method=None).iloc[-1]) if len(wti_series) > 1 else 0.0
    except:
        pass 
    return prices, wti_momentum, z_score

# --- 4. RENDERIZAÇÃO ---
def main():
    fetch_filtered_news()
    prices, momentum, z_score = get_market_metrics()
    DB_FILE = "Oil_Station_V54_Master.csv"
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0.0

    # LÓGICA DE ARBITRAGEM MULTIFATORIAL
    # Combina Sentimento IA (Alpha) + Divergência de Preço + Arbitragem Estatística (Z-Score)
    if avg_alpha > 6.0 and z_score < -1.5:
        arb_status, arb_color = "ARBITRAGEM: COMPRA AGRESSIVA (ALPHA ALTO + SPREAD BAIXO)", "#00FFC8"
    elif avg_alpha < -6.0 and z_score > 1.5:
        arb_status, arb_color = "ARBITRAGEM: VENDA AGRESSIVA (ALPHA BAIXO + SPREAD ALTO)", "#FF4B4B"
    elif abs(z_score) > 2.0:
        arb_status, arb_color = f"ALERTA DE ARBITRAGEM: REVERSÃO DE SPREAD (Z-SCORE: {z_score:.2f})", "#EAB308"
    else:
        arb_status, arb_color = "MERCADO EM EQUILÍBRIO DE ARBITRAGEM", "#94A3B8"

    st.markdown(f"""
        <div class="arbitrage-monitor" style="border-color: {arb_color}; color: {arb_color};">
            <small>SISTEMA DE ARBITRAGEM ESTATÍSTICA & SENTIMENTO</small><br>
            <strong style="font-size: 20px;">{arb_status}</strong>
        </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("WTI CRUDE", f"$ {prices['WTI']:.2f}", f"{momentum:.2%}")
    spread = prices['BRENT'] - prices['WTI']
    c2.metric("SPREAD B/W (Z-SCORE)", f"$ {spread:.2f}", f"Z: {z_score:.2f}")
    c3.metric("IA ALPHA SCORE", f"{avg_alpha:.2f}")
    c4.metric("DXY INDEX", f"$ {prices['DXY']:.2f}")

    st.markdown("---")
    
    col_gauge, col_table = st.columns([1, 2])
    
    with col_gauge:
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=avg_alpha,
            title={'text': "SENTIMENTO ALPHA", 'font': {'size': 14}},
            gauge={'axis': {'range': [-10, 10]}, 'bar': {'color': arb_color}}
        ))
        fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, margin=dict(t=50, b=20))
        st.plotly_chart(fig, width='stretch')

    with col_table:
        if not df_news.empty:
            df_display = df_news.copy()
            def color_logic(v):
                color = "pos-score" if v > 0 else "neg-score"
                return f'<span class="{color}">{v}</span>'
            df_display['Alpha'] = df_display['Alpha'].apply(color_logic)
            df_display['Link'] = df_display['Link'].apply(lambda x: f'<a href="{x}" target="_blank">DETALHES</a>')
            table_html = df_display[['Data', 'Fonte', 'Manchete', 'Alpha', 'Link']].to_html(escape=False, index=False)
            st.markdown(f'<div class="scroll-container">{table_html}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
