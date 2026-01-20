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

# --- 1. CONFIGURAÇÕES E ESTÉTICA DE TERMINAL BLOOMBERG ---
st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v56_refresh")

st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle, #0D1421 0%, #050A12 100%); color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1rem;}
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { font-size: 11px !important; color: #94A3B8 !important; text-transform: uppercase; }
    .ai-brain-box {
        background: rgba(0, 255, 200, 0.03);
        border: 1px solid rgba(0, 255, 200, 0.2);
        padding: 15px; border-radius: 8px; margin-bottom: 20px;
    }
    table { width: 100%; border-collapse: collapse; background: transparent !important; color: #FFFFFF !important; }
    th { color: #94A3B8 !important; font-size: 12px; text-transform: uppercase; border-bottom: 1px solid #1E293B; padding: 8px; text-align: left; }
    td { font-size: 13px; padding: 8px; border-bottom: 1px solid #0D1421; color: #FFFFFF !important; }
    a { color: #00FFC8 !important; text-decoration: none; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. BASE DE DADOS COMPLETA (20 SITES / 22 LEXICONS) ---
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
def fetch_news():
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

@st.cache_data(ttl=60)
def get_market_data():
    tickers = {"WTI": "CL=F", "BRENT": "BZ=F", "DXY": "DX-Y.NYB", "VIX": "^VIX", "US10Y": "^TNX"}
    try:
        data = yf.download(list(tickers.values()), period="5d", interval="1h", progress=False)['Close']
        data = data.ffill().bfill()
        prices = {name: data[ticker].iloc[-1] for name, ticker in tickers.items()}
        corr = data.pct_change(fill_method=None).corr()
        return prices, corr
    except:
        return {k: 0.0 for k in tickers.keys()}, pd.DataFrame()

# --- 4. RENDERIZAÇÃO ---
def main():
    fetch_news()
    prices, correlations = get_market_data()
    DB_FILE = "Oil_Station_V54_Master.csv"
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0.0

    st.markdown(f"""
        <div class="ai-brain-box">
            <span style="color: #94A3B8; font-size: 10px; font-weight: 700; text-transform: uppercase;">SISTEMA AUTÔNOMO DE ANÁLISE QUANTITATIVA</span><br>
            <span style="font-size: 14px;">
                {'ALTA CONVICÇÃO: Confluência entre prêmio de risco geopolítico e fraqueza do DXY detectada.' if avg_alpha > 5 and prices['DXY'] < 104 else 'ANALISANDO: Ruído de mercado elevado. Aguardando confirmação de fluxo em Chokepoints.'}
            </span>
        </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["TERMINAL OPERACIONAL", "CORRELAÇÕES", "ANÁLISE MACRO SÊNIOR"])

    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI CRUDE", f"$ {prices['WTI']:.2f}")
        c2.metric("ALPHA SENTIMENT", f"{avg_alpha:.2f}")
        c3.metric("DXY INDEX", f"{prices['DXY']:.2f}")
        c4.metric("VOLATILIDADE VIX", f"{prices['VIX']:.2f}")

        st.markdown("---")
        
        col_gauges, col_table = st.columns([1.2, 1.8])
        
        with col_gauges:
            # Gauge Alpha
            fig1 = go.Figure(go.Indicator(
                mode="gauge+number", value=avg_alpha, title={'text': "SENTIMENTO (ALPHA)", 'font': {'size': 14}},
                gauge={'axis': {'range': [-10, 10]}, 'bar': {'color': "#00FFC8" if avg_alpha > 0 else "#FF4B4B"}, 'bgcolor': "#0D1421"}
            ))
            fig1.update_layout(height=200, margin=dict(t=30, b=10, l=30, r=30), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig1, use_container_width=True)

            # Gauge Pressão Cambial
            mkt_val = (105 - prices['DXY']) * 2
            fig2 = go.Figure(go.Indicator(
                mode="gauge+number", value=mkt_val, title={'text': "PRESSÃO DXY (INVERSA)", 'font': {'size': 14}},
                gauge={'axis': {'range': [-10, 10]}, 'bar': {'color': "#00FFC8" if mkt_val > 0 else "#FF4B4B"}, 'bgcolor': "#0D1421"}
            ))
            fig2.update_layout(height=200, margin=dict(t=30, b=10, l=30, r=30), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig2, use_container_width=True)

        with col_table:
            if not df_news.empty:
                df_display = df_news.head(15).copy()
                df_display['Link'] = df_display['Link'].apply(lambda x: f'<a href="{x}" target="_blank">ACESSAR</a>')
                st.markdown(df_display[['Data', 'Fonte', 'Manchete', 'Alpha', 'Link']].to_html(escape=False, index=False), unsafe_allow_html=True)

    with tab2:
        if not correlations.empty:
            st.markdown("### Matriz de Cointegração (WTI vs Ativos Globais)")
            st.table(correlations['CL=F'].sort_values(ascending=False))
        else:
            st.warning("Servidor de dados sob carga. Recarregando matriz...")

    with tab3:
        st.markdown("### Parecer Técnico Estrutural")
        st.info(f"""
        ANÁLISE DE RISCO XTIUSD:
        1. DINÂMICA DE JUROS: Com o US10Y em {prices['US10Y']:.2f}, o mercado testa a resiliência da demanda industrial. Yields em ascensão são o maior risco deflacionário para o barril.
        2. VIES DE ALPHA: O score de {avg_alpha:.2f} indica que o mercado já precificou parte das tensões. O risco agora reside em uma 'desescalada' súbita.
        3. CORRELAÇÃO DXY: A força do dólar ({prices['DXY']:.2f}) permanece como o pivô central. Qualquer movimento abaixo de 103.50 abrirá espaço para teste de resistências no WTI.
        """)

if __name__ == "__main__":
    main()
