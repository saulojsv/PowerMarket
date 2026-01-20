import pandas as pd
import re
import feedparser
import os
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÕES E ESTILO ---
st.set_page_config(page_title="Terminal - XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_pro")

st.markdown("""
    <style>
    .stApp { background-color: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1.5rem;}
    
    /* Metrics High Contrast */
    [data-testid="stMetricValue"] { font-size: 28px !important; color: #00FFC8 !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { font-size: 12px !important; color: #94A3B8 !important; text-transform: uppercase; }
    
    /* Cards de Tendência */
    .trend-card {
        padding: 15px; border-radius: 10px; background: #0D1421; 
        border: 1px solid #1E293B; text-align: center;
    }
    .trend-label { color: #94A3B8; font-size: 11px; font-weight: 600; text-transform: uppercase; }
    .trend-value { font-size: 18px; font-weight: 700; margin-top: 4px; }
    </style>
""", unsafe_allow_html=True)

# --- PARÂMETROS ---
DB_FILE = "Oil_Station_V54_Master.csv"
SUSPECT_ASSETS = ["CL=F", "DX-Y.NYB", "^VIX", "^TNX"]

# --- 2. BASE DE CONHECIMENTO COMPLETA (20 FONTES E 22 LEXICONS) ---
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
                news_data.append({
                    "Data": datetime.now().strftime("%H:%M"), 
                    "Fonte": name, 
                    "Manchete": entry.title[:85], 
                    "Alpha": score, 
                    "Cat": cat,
                    "Link": entry.link
                })
        except: continue
    if news_data:
        df_new = pd.DataFrame(news_data)
        if os.path.exists(DB_FILE):
            df_old = pd.read_csv(DB_FILE)
            df_new = pd.concat([df_new, df_old]).drop_duplicates(subset=['Manchete']).head(100)
        df_new.to_csv(DB_FILE, index=False)

@st.cache_data(ttl=300)
def get_market_analysis():
    try:
        data_h1 = yf.download("CL=F", period="10d", interval="1h", progress=False)['Close'].ffill()
        data_d1 = yf.download("CL=F", period="60d", interval="1d", progress=False)['Close'].ffill()
        
        day_trend = "BULLISH" if data_h1.iloc[-1] > data_h1.rolling(20).mean().iloc[-1] else "BEARISH"
        swing_trend = "BULLISH" if data_d1.iloc[-1] > data_d1.rolling(50).mean().iloc[-1] else "BEARISH"
        
        return {
            "price": data_h1.iloc[-1],
            "delta": ((data_h1.iloc[-1] / data_h1.iloc[0]) - 1) * 100,
            "day_trend": day_trend, "swing_trend": swing_trend,
            "vix": yf.download("^VIX", period="1d", progress=False)['Close'].iloc[-1]
        }
    except: return None

# --- 4. INTERFACE ---
def main():
    run_global_scrap()
    analysis = get_market_analysis()
    if not analysis: return
        
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0
    
    # Header e Tendências
    col_met, col_trend = st.columns([2, 1])
    with col_met:
        c1, c2, c3 = st.columns(3)
        c1.metric("WTI CRUDE", f"$ {analysis['price']:.2f}", f"{analysis['delta']:.2f}%")
        c2.metric("IA ALPHA", f"{avg_alpha:.2f}")
        c3.metric("BANCA", "300.00 €")

    with col_trend:
        dt_c = "#00FFC8" if analysis['day_trend'] == "BULLISH" else "#FF4B4B"
        st_c = "#00FFC8" if analysis['swing_trend'] == "BULLISH" else "#FF4B4B"
        st.markdown(f"""
            <div style="display: flex; gap: 10px;">
                <div class="trend-card" style="flex: 1; border-bottom: 3px solid {dt_c};">
                    <div class="trend-label">Daytrade (H1)</div>
                    <div class="trend-value" style="color: {dt_c};">{analysis['day_trend']}</div>
                </div>
                <div class="trend-card" style="flex: 1; border-bottom: 3px solid {st_c};">
                    <div class="trend-label">Swing (D1)</div>
                    <div class="trend-value" style="color: {st_c};">{analysis['swing_trend']}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    # Velocímetro e Tabela
    col_v, col_n = st.columns([1, 1.8])
    with col_v:
        fig_v = go.Figure(go.Indicator(
            mode = "gauge+number", value = avg_alpha,
            gauge = {
                'axis': {'range': [-10, 10], 'tickcolor': "#94A3B8"},
                'bar': {'color': "#00FFC8" if avg_alpha > 0 else "#FF4B4B"},
                'bgcolor': "#0D1421",
                'steps': [{'range': [-10, -5], 'color': 'rgba(255, 75, 75, 0.1)'}, {'range': [5, 10], 'color': 'rgba(0, 255, 200, 0.1)'}]}
        ))
        fig_v.update_layout(height=260, margin=dict(t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
        st.plotly_chart(fig_v, use_container_width=True)
    
    with col_n:
        st.markdown("### Terminal - XTIUSD")
        if not df_news.empty:
            # Lógica de Cor + Hiperlink
            def make_clickable(link):
                return f'<a href="{link}" target="_blank" style="color: #00FFC8; text-decoration: none; font-weight: bold;">OPEN LINK</a>'

            df_display = df_news.head(15).copy()
            df_display['Link'] = df_display['Link'].apply(make_clickable)

            # Estilização da Tabela
            st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
