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

# --- 1. CONFIGURAÇÃO DE AMBIENTE E ESTILO ---
st.set_page_config(page_title="QUANT STATION V54 | PRO", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh")

DB_FILE = "Oil_Station_V54_Master.csv"
TRADE_LOG_FILE = "Trade_Simulation_V54.csv"

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .stApp { background-color: #02060C; color: #E0E0E0; font-family: 'JetBrains Mono', monospace; }
        [data-testid="stMetricValue"] { font-size: 20px !important; color: #39FF14 !important; }
        div[data-testid="stMetric"] { background-color: #0B121D; border-left: 4px solid #39FF14; padding: 10px; border-radius: 4px; }
        .pnl-pos { color: #39FF14; font-weight: bold; }
        .pnl-neg { color: #FF4B4B; font-weight: bold; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] { background-color: #0B121D; border-radius: 4px; color: #8a96a3; }
        .stTabs [aria-selected="true"] { border-bottom-color: #39FF14 !important; color: #39FF14 !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. OS 10 SITES (FONTES RSS/XML) ---
RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing Oil": "https://www.investing.com/rss/news_11.rss",
    "CNBC Energy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA Reports": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Yahoo Finance": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "Bloomberg": "https://www.bloomberg.com/feeds/bview/energy.xml",
    "S&P Global": "https://www.spglobal.com/platts/en/rss-feed/news/oil",
    "Rigzone": "https://www.rigzone.com/news/rss/rigzone_latest.xml"
}

# --- 3. OS 22 LEXICONS (EIXOS MACRO) ---
LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation|invasion": [9.8, 1, "Geopolítica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolítica (Sanções)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Risco de Chokepoint"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Tensões Regionais"],
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "Política OPEP+"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "Oferta OPEP+"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "Oferta EUA (Shale)"],
    r"non-opec|brazil|guyana|canada|output surge": [7.0, -1, "Oferta Extra-OPEP"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Estoques (Déficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Estoques (Excesso)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refino/Margens"],
    r"crack spread|heating oil|jet fuel|diesel demand": [6.5, 1, "Derivados"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Demanda Fraca)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Demanda Forte)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate": [7.5, -1, "Macro (Aperto Fed)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Estímulo Fed)"],
    r"dollar|dxy|greenback|fx|yields": [7.0, -1, "Correlação DXY"],
    r"gdp|pmi|manufacturing|industrial production": [6.8, 1, "Indicadores Macro"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Fluxo Especulativo"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Análise Técnica"],
    r"volatility|vix|contango|backwardation": [6.2, 1, "Estrutura de Termo"],
    r"algorithmic trading|ctas|margin call|liquidation": [6.0, 1, "Fluxo Quant"]
}

# --- 4. MOTOR DE DADOS E SIMULAÇÃO ---
def get_market_intel():
    try:
        tickers = ["CL=F", "DX-Y.NYB", "USDCAD=X", "GC=F"]
        data = yf.download(tickers, period="2d", interval="15m", progress=False)['Close']
        last = data.iloc[-1]
        delta = ((last / data.iloc[0]) - 1) * 100
        return last, delta, data.corr()
    except: return None, None, None

def log_trade(side, price, reason):
    new_t = pd.DataFrame([{"Hora": datetime.now().strftime("%H:%M:%S"), "Lote": 1.0, 
                           "Tipo": side, "Entrada": price, "Contexto": reason, "TS": datetime.now().timestamp()}])
    if os.path.exists(TRADE_LOG_FILE):
        log = pd.read_csv(TRADE_LOG_FILE)
        if (datetime.now().timestamp() - log['TS'].iloc[-1]) > 900:
            pd.concat([log, new_t], ignore_index=True).to_csv(TRADE_LOG_FILE, index=False)
    else: new_t.to_csv(TRADE_LOG_FILE, index=False)

# --- 5. INTERFACE ---
def main():
    prices, deltas, corr_matrix = get_market_intel()
    
    st.title("TERMINAL XTI")
    
    if prices is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI OIL", f"${prices['CL=F']:.2f}", f"{deltas['CL=F']:.2f}%")
        c2.metric("DXY", f"{prices['DX-Y.NYB']:.2f}", f"{deltas['DX-Y.NYB']:.2f}%", delta_color="inverse")
        c3.metric("USDCAD", f"{prices['USDCAD=X']:.4f}", f"{deltas['USDCAD=X']:.2f}%", delta_color="inverse")
        c4.metric("GOLD", f"${prices['GC=F']:.1f}", f"{deltas['GC=F']:.2f}%")

    tab_news, tab_corr, tab_pnl = st.tabs(["📊 NEWS FLOW", "🔗 CORRELATIONS", "🏦 TRADING PNL"])

    with tab_news:
        if os.path.exists(DB_FILE):
            df = pd.read_csv(DB_FILE).sort_values('TS', ascending=False)
            st.dataframe(df[['Data', 'Fonte', 'Manchete', 'Alpha', 'Cat']].head(50), use_container_width=True, hide_index=True)
            avg_a = df.head(10)['Alpha'].mean()
        else: avg_a = 0

    with tab_corr:
        st.subheader("Intermarket Correlation Matrix (WTI base)")
        if corr_matrix is not None:
            oil_c = corr_matrix[['CL=F']].sort_values(by='CL=F', ascending=False)
            st.table(oil_c.style.background_gradient(cmap='RdYlGn'))
        
        

    with tab_pnl:
        if prices is not None:
            # Lógica de Estratégia Cross-Asset
            if avg_a > 1.5 and deltas['USDCAD=X'] < -0.01 and deltas['DX-Y.NYB'] < 0:
                log_trade("BUY", prices['CL=F'], "Alpha + CAD Strong + DXY Weak")
            elif avg_a < -1.5 and deltas['USDCAD=X'] > 0.01 and deltas['DX-Y.NYB'] > 0:
                log_trade("SELL", prices['CL=F'], "Alpha + CAD Weak + DXY Strong")

        if os.path.exists(TRADE_LOG_FILE):
            trades = pd.read_csv(TRADE_LOG_FILE).sort_values('TS', ascending=False)
            trades['Preço_Atual'] = prices['CL=F']
            trades['PnL_Points'] = trades.apply(lambda r: prices['CL=F'] - r['Entrada'] if r['Tipo']=="BUY" else r['Entrada'] - prices['CL=F'], axis=1)
            trades['PnL_USD'] = trades['PnL_Points'] * 1000
            
            st.table(trades[['Hora', 'Tipo', 'Lote', 'Entrada', 'Preço_Atual', 'PnL_Points', 'PnL_USD', 'Contexto']])
            st.metric("TOTAL PNL", f"${trades['PnL_USD'].sum():,.2f}")
        else: st.info("Aguardando confluência macro para entrar.")

if __name__ == "__main__": main()
