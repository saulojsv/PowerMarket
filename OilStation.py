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

# --- 1. PARAMETROS DE BANCA E RISCO (300 EUR) ---
BANCA_INICIAL = 300.00
MULTIPLICADOR_MICRO = 10.0
IA_STOP_LOSS = 7.50
IA_TAKE_PROFIT = 15.00

st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_pro")

DB_FILE = "Oil_Station_V54_Master.csv"
TRADE_LOG_FILE = "Trade_Simulation_V54.csv"

# --- 2. FONTES RSS (20 SITES) ---
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

# --- 3. LEXICONS (22 CATEGORIAS) ---
LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation|invasion": [9.8, 1, "Geopolitica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolitica (Sancoes)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Risco Chokepoint"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Tensoes Regionais"],
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "Politica OPEC+"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "Oferta OPEC+"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "Oferta EUA"],
    r"non-opec|brazil|guyana|canada|output surge": [7.0, -1, "Oferta Extra-OPEC"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Estoques (Deficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Estoques (Excesso)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refino/Margens"],
    r"crack spread|heating oil|jet fuel|diesel demand": [6.5, 1, "Derivados"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Demanda Fraca)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Demanda Forte)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate": [7.5, -1, "Macro (Aperto Fed)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Estimulo Fed)"],
    r"dollar|dxy|greenback|fx|yields": [7.0, -1, "Correlacao DXY"],
    r"gdp|pmi|manufacturing|industrial production": [6.8, 1, "Indicadores Macro"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Fluxo Especulativo"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Analise Tecnica"],
    r"volatility|vix|contango|backwardation": [6.2, 1, "Estrutura de Termo"],
    r"algorithmic trading|ctas|margin call|liquidation": [6.0, 1, "Fluxo Quant"]
}

# --- 4. SUSPECT ASSETS (INTERMARKET) ---
SUSPECT_ASSETS = {
    "CL=F": "WTI Oil",
    "BZ=F": "Brent Oil",
    "DX-Y.NYB": "DXY Index",
    "USDCAD=X": "USD/CAD",
    "^VIX": "VIX (Medo)",
    "^TNX": "10Y Yield",
    "AUDJPY=X": "AUD/JPY (Risco)",
    "XLE": "S&P500 Energy"
}

# --- 5. LOGICA DE CONFLUENCIA E MOTOR IA ---
def get_confluence_score(prices, deltas, avg_alpha):
    score = 0
    if abs(avg_alpha) >= 3.0: score += 30
    if np.sign(deltas['CL=F']) == np.sign(deltas['BZ=F']): score += 25
    if prices['^VIX'] < 22: score += 20
    if (deltas['AUDJPY=X'] > 0 and avg_alpha > 0) or (deltas['AUDJPY=X'] < 0 and avg_alpha < 0):
        score += 25
    return score

def run_ia_management(current_oil, avg_alpha, c_score):
    if not os.path.exists(TRADE_LOG_FILE):
        pd.DataFrame(columns=["Data", "Tipo", "Entrada", "Status", "PnL", "Conf"]).to_csv(TRADE_LOG_FILE, index=False)
    
    df = pd.read_csv(TRADE_LOG_FILE)
    if not df.empty and (df['Status'] == 'OPEN').any():
        idx = df[df['Status'] == 'OPEN'].index[0]
        row = df.iloc[idx]
        pnl = (current_oil - row['Entrada']) * MULTIPLICADOR_MICRO if row['Tipo'] == 'BUY' else (row['Entrada'] - current_oil) * MULTIPLICADOR_MICRO
        if pnl >= IA_TAKE_PROFIT or pnl <= -IA_STOP_LOSS:
            df.at[idx, 'Status'] = 'CLOSED'; df.at[idx, 'PnL'] = pnl; df.to_csv(TRADE_LOG_FILE, index=False)
    else:
        side = "BUY" if avg_alpha >= 3.5 and c_score >= 75 else "SELL" if avg_alpha <= -3.5 and c_score >= 75 else None
        if side:
            new_row = {"Data": datetime.now().strftime("%H:%M"), "Tipo": side, "Entrada": current_oil, "Status": "OPEN", "PnL": 0, "Conf": c_score}
            pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(TRADE_LOG_FILE, index=False)

# --- 6. SCRAPING E MERCADO ---
def run_global_scrap():
    news_data = []
    for name, url in RSS_SOURCES.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            score, cat = 0, "Neutral"
            for patt, (w, d, c) in LEXICON_TOPICS.items():
                if re.search(patt, entry.title.lower()):
                    score = w * d; cat = c; break
            news_data.append({"Data": datetime.now().strftime("%H:%M"), "Fonte": name, "Manchete": entry.title[:80], "Alpha": score, "Cat": cat})
    df = pd.DataFrame(news_data)
    if os.path.exists(DB_FILE):
        df = pd.concat([df, pd.read_csv(DB_FILE)]).drop_duplicates(subset=['Manchete']).head(100)
    df.to_csv(DB_FILE, index=False)

def get_market_intel():
    try:
        data = yf.download(list(SUSPECT_ASSETS.keys()), period="2d", interval="15m", progress=False)['Close']
        return data.iloc[-1], ((data.iloc[-1]/data.iloc[0])-1)*100, data.corr()
    except: return None

# --- 7. MAIN INTERFACE ---
def main():
    st.markdown("""<style> .stApp { background-color: #02060C; color: #E0E0E0; } </style>""", unsafe_allow_html=True)
    run_global_scrap()
    market = get_market_intel()
    if not market: return
    prices, deltas, corr_matrix = market
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0
    c_score = get_confluence_score(prices, deltas, avg_alpha)
    run_ia_management(prices['CL=F'], avg_alpha, c_score)

    # CABECALHO DINAMICO
    col_main, col_gauge = st.columns([1, 2])
    with col_main:
        st.subheader("XTIUSD | BANCA 300 EUR")
        st.metric("PRECO WTI", f"$ {prices['CL=F']:.2f}", f"{deltas['CL=F']:.2f}%")
        st.metric("CONFLUENCIA", f"{c_score}%", "THRESHOLD: 75%")
        df_trades = pd.read_csv(TRADE_LOG_FILE) if os.path.exists(TRADE_LOG_FILE) else pd.DataFrame()
        pnl_total = df_trades['PnL'].sum() if not df_trades.empty else 0
        st.metric("EQUITY", f"EUR {300 + pnl_total:.2f}", f"{pnl_total:+.2f}")

    with col_gauge:
        fig = go.Figure(go.Indicator(
            mode = "gauge+number", value = avg_alpha,
            title = {'text': "SENTIMENTO ALPHA GLOBAL", 'font': {'size': 16}},
            gauge = {
                'axis': {'range': [-10, 10]},
                'bar': {'color': "#39FF14" if avg_alpha >= 0 else "#FF4B4B"},
                'steps': [{'range': [-10, -3], 'color': "rgba(255, 75, 75, 0.2)"},
                          {'range': [3, 10], 'color': "rgba(57, 255, 20, 0.2)"}]
            }
        ))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "#E0E0E0"}, height=280)
        st.plotly_chart(fig, use_container_width=True)

    # ABAS
    t_news, t_tracker, t_trades = st.tabs(["NEWS FLOW", "SUSPECT TRACKER", "IA LOG"])
    with t_news: st.dataframe(df_news.head(50), use_container_width=True, hide_index=True)
    with t_tracker: 
        st.plotly_chart(go.Figure(go.Bar(x=corr_matrix['CL=F'].index, y=corr_matrix['CL=F'].values, marker_color='#39FF14')), use_container_width=True)
        st.dataframe(deltas)
    with t_trades: st.table(df_trades.sort_index(ascending=False).head(20))

if __name__ == "__main__":
    main()
