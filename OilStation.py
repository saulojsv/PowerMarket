import pandas as pd
import re
import feedparser
import time
import os
import threading
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import yfinance as yf
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO DE PÁGINA ---
st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_full")

# Arquivos de Dados
DB_FILE = "Oil_Station_V54_Master.csv"
TRADE_LOG_FILE = "Simulation_Log_V54.csv"

# --- 2. OS 22 LEXICONS E TODAS AS FONTES (FULL CONFIG) ---
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

# --- 3. MOTOR DE ANÁLISE E SIMULAÇÃO ---

def analyze_reality(title):
    t_lower = title.lower()
    weights, labels = [], []
    for pat, par in LEXICON_TOPICS.items():
        if re.search(pat, t_lower):
            weights.append(par[0] * par[1])
            labels.append(par[2])
    if not weights: return None
    avg_alpha = sum(weights) / len(weights)
    return avg_alpha, labels[0]

def log_simulated_trade(side, price, reason):
    new_trade = pd.DataFrame([{"Horário": datetime.now().strftime("%H:%M:%S"), "Tipo": side, 
                               "Entrada": price, "Contexto": reason, "TS": datetime.now().timestamp()}])
    if os.path.exists(TRADE_LOG_FILE):
        log = pd.read_csv(TRADE_LOG_FILE)
        if (datetime.now().timestamp() - log['TS'].iloc[-1]) > 600: # Intervalo 10min
            pd.concat([log, new_trade], ignore_index=True).to_csv(TRADE_LOG_FILE, index=False)
    else: new_trade.to_csv(TRADE_LOG_FILE, index=False)

# --- 4. INTERFACE ---
def main():
    # Coleta de Dados de Mercado com Fallback
    try:
        mkt = yf.download(["CL=F", "USDCAD=X"], period="1d", interval="5m", progress=False)
        oil_now = mkt['Close']['CL=F'].iloc[-1]
        cad_now = mkt['Close']['USDCAD=X'].iloc[-1]
        cad_open = mkt['Open']['USDCAD=X'].iloc[0]
        cad_delta = ((cad_now / cad_open) - 1) * 100
    except: oil_now, cad_delta = 0.0, 0.0

    st.title("QUANT STATION V54 | PRO SIMULATOR")

    tab_monitor, tab_sim, tab_lexicons = st.tabs(["LIVE MONITOR", "SIMULATION LOG", "WORD LOG"])

    with tab_monitor:
        if os.path.exists(DB_FILE):
            df = pd.read_csv(DB_FILE).sort_values('TS', ascending=False)
            avg_a = df.head(10)['Alpha'].mean()
            
            # Lógica de Gatilho (Conflito Macro)
            divergence = (avg_a > 1.0 and cad_delta > 0.02)
            if avg_a > 1.5 and not divergence:
                log_simulated_trade("BUY", oil_now, "Bullish News + CAD Strength")
            elif avg_a < -1.5 and cad_delta > 0.02:
                log_simulated_trade("SELL", oil_now, "Bearish News + CAD Weakness")

            st.metric("OIL PRICE", f"${oil_now:.2f}", f"CAD Delta: {cad_delta:.2f}%")
            st.dataframe(df.head(40), width='stretch', hide_index=True)

    with tab_sim:
        if os.path.exists(TRADE_LOG_FILE):
            trades = pd.read_csv(TRADE_LOG_FILE).sort_values('TS', ascending=False)
            trades['PnL_Points'] = trades.apply(lambda r: oil_now - r['Entrada'] if r['Tipo']=="BUY" else r['Entrada'] - oil_now, axis=1)
            
            st.metric("TOTAL PNL (POINTS)", f"{trades['PnL_Points'].sum():+.2f}")
            st.dataframe(trades, width='stretch', hide_index=True)

    with tab_lexicons:
        st.write("Estes são os 22 eixos macroeconômicos monitorados em tempo real:")
        lex_df = pd.DataFrame([{"Lexicon": k, "Impacto": v[0], "Direção": "Alta" if v[1]>0 else "Baixa", "Categoria": v[2]} for k,v in LEXICON_TOPICS.items()])
        st.table(lex_df)

if __name__ == "__main__": main()

