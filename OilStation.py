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
    [data-testid="stMetricValue"] { font-size: 26px !important; color: #00FFC8 !important; }
    div[data-testid="metric-container"] {
        background-color: #0D1421; border: 1px solid #1B263B;
        padding: 15px; border-radius: 12px; box-shadow: 0px 4px 15px rgba(0,0,0,0.5);
    }
    </style>
""", unsafe_allow_html=True)

# --- PARÂMETROS ---
BANCA_INICIAL = 300.00
DB_FILE = "Oil_Station_V54_Master.csv"
TRADE_LOG_FILE = "Trade_Simulation_V54.csv"
SUSPECT_ASSETS = ["CL=F", "BZ=F", "DX-Y.NYB", "USDCAD=X", "^VIX", "^TNX", "AUDJPY=X", "XLE"]

# --- 2. BASE DE CONHECIMENTO (20 FONTES E 22 LEXICONS) ---
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
    r"war|attack|missile|drone|strike|conflict|escalation|invasion": [9.8, 1, "Geopolítica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolítica (Sanções)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Risco Chokepoint"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Tensões Regionais"],
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "Política OPEC+"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "Oferta OPEC+"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "Oferta EUA"],
    r"non-opec|brazil|guyana|canada|output surge": [7.0, -1, "Oferta Extra-OPEC"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Estoques (Déficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Estoques (Excesso)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refino/Margens"],
    r"crack spread|heating oil|jet fuel|diesel demand": [6.5, 1, "Derivados"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Demanda Fraca)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Demanda Forte)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate": [7.5, -1, "Macro (Aperto Fed)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Estimulo Fed)"],
    r"dollar|dxy|greenback|fx|yields": [7.0, -1, "Correlação DXY"],
    r"gdp|pmi|manufacturing|industrial production": [6.8, 1, "Indicadores Macro"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Fluxo Especulativo"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Análise Técnica"],
    r"volatility|vix|contango|backwardation": [6.2, 1, "Estrutura de Termo"],
    r"algorithmic trading|ctas|margin call|liquidation": [6.0, 1, "Fluxo Quant"]
}

# --- 3. MOTOR DE INTELIGÊNCIA ---
def run_global_scrap():
    news_data = []
    for name, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                score, cat = 0, "Neutral"
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, entry.title.lower()):
                        score = w * d; cat = c; break
                news_data.append({"Data": datetime.now().strftime("%H:%M"), "Fonte": name, "Manchete": entry.title[:80], "Alpha": score, "Cat": cat})
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
        # Aumentamos para 7d para garantir dados em fins de semana/feriados
        data = yf.download(SUSPECT_ASSETS, period="7d", interval="1h", progress=False)['Close']
        if data.empty: return None
        
        # Limpeza de dados: preenche NaN com o último valor disponível (Forward Fill)
        data = data.ffill().bfill()
        
        prices = data.iloc[-1]
        deltas = ((data.iloc[-1] / data.iloc[0]) - 1) * 100
        # Preenche correlações vazias com 0 para evitar erros no gráfico
        corr = data.corr().fillna(0)
        
        return prices, deltas, corr
    except: return None

# --- 4. INTERFACE ---
def main():
    run_global_scrap()
    market = get_market_intel()
    if market is None:
        st.warning("Aguardando sincronização de mercado...")
        return
        
    prices, deltas, corr_matrix = market
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0
    
    # Barra de Status Dinâmica
    status_color = "#00FFC8" if abs(avg_alpha) > 2 else "#FFA500"
    st.markdown(f"""
        <div class="status-bar" style="border-left-color: {status_color}">
            V54 NEON QUANT | IA Treinada com 22 Lexicons | Regime: {"Fase de Tendência" if abs(deltas.get('CL=F', 0)) > 0.5 else "Fase Lateral"}
        </div>
    """, unsafe_allow_html=True)

    # Grid de Métricas Protegido contra Erros
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("WTI", f"$ {prices.get('CL=F', 0):.2f}", f"{deltas.get('CL=F', 0):.2f}%")
    m2.metric("VIX", f"{prices.get('^VIX', 0):.2f}", f"{deltas.get('^VIX', 0):.2f}%")
    m3.metric("ALPHA", f"{avg_alpha:.2f}")
    
    lucro = 0
    if os.path.exists(TRADE_LOG_FILE):
        try:
            lucro = pd.read_csv(TRADE_LOG_FILE)['PnL'].sum()
        except: pass
    m4.metric("BANCA", f"{300 + lucro:.2f} €")

    st.markdown("---")
    
    c_left, c_right = st.columns(2)
    with c_left:
        # Radar de Suspeitos com tratamento de NaN
        labels = ['DXY', 'VIX', 'Yields', 'CAD', 'XLE', 'AUD/JPY']
        r_vals = [
            abs(deltas.get('DX-Y.NYB', 0))*20, 
            abs(deltas.get('^VIX', 0)), 
            abs(deltas.get('^TNX', 0))*10, 
            abs(deltas.get('USDCAD=X', 0))*150, 
            abs(deltas.get('XLE', 0))*10, 
            abs(deltas.get('AUDJPY=X', 0))*20
        ]
        fig_radar = go.Figure(data=go.Scatterpolar(r=r_vals, theta=labels, fill='toself', line_color='#00FFC8'))
        fig_radar.update_layout(polar=dict(bgcolor="#0D1421"), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=350)
        st.plotly_chart(fig_radar, use_container_width=True)
    
    with c_right:
        # Heatmap de Correlação
        fig_corr = go.Figure(data=go.Heatmap(z=corr_matrix.values, x=corr_matrix.columns, y=corr_matrix.index, colorscale='Viridis'))
        fig_corr.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_corr, use_container_width=True)

    st.tabs(["Notícias Treinadas", "Logs"])[0].dataframe(df_news.head(25), use_container_width=True)

if __name__ == "__main__":
    main()
