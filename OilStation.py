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
st.set_page_config(page_title="TERMINAL - XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_pro")

# CSS para deixar o site "muito mais bonito"
st.markdown("""
    <style>
    .stApp { background-color: #050A12; color: #E0E0E0; }
    [data-testid="stMetricValue"] { font-size: 28px !important; color: #00FFC8 !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        background-color: #0D1421; border-radius: 5px; padding: 10px 20px; color: white;
    }
    .stTabs [aria-selected="true"] { border-bottom: 2px solid #00FFC8 !important; }
    div[data-testid="metric-container"] {
        background-color: #0D1421; border: 1px solid #1B263B;
        padding: 15px; border-radius: 10px; box-shadow: 0px 4px 10px rgba(0,0,0,0.3);
    }
    </style>
""", unsafe_allow_html=True)

# --- PARÂMETROS ---
BANCA_INICIAL = 300.00
MULTIPLICADOR_MICRO = 10.0
IA_STOP_LOSS = 7.50
IA_TAKE_PROFIT = 15.00
DB_FILE = "Oil_Station_V54_Master.csv"
TRADE_LOG_FILE = "Trade_Simulation_V54.csv"

# --- DICIONÁRIOS (22 Lexicons e 20 Fontes) ---
# [Mantidos conforme suas instruções anteriores para precisão da IA]
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

SUSPECT_ASSETS = ["CL=F", "BZ=F", "DX-Y.NYB", "USDCAD=X", "^VIX", "^TNX", "AUDJPY=X", "XLE"]

# --- 2. MOTOR DE DADOS ---
@st.cache_data(ttl=300)
def get_market_intel():
    try:
        data = yf.download(SUSPECT_ASSETS, period="2d", interval="15m", progress=False)['Close']
        if data.empty: return None
        prices = data.iloc[-1]
        deltas = ((data.iloc[-1] / data.iloc[0]) - 1) * 100
        corr = data.corr()
        return prices, deltas, corr
    except: return None

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
    df_new = pd.DataFrame(news_data)
    if os.path.exists(DB_FILE):
        df_old = pd.read_csv(DB_FILE)
        df_new = pd.concat([df_new, df_old]).drop_duplicates(subset=['Manchete']).head(100)
    df_new.to_csv(DB_FILE, index=False)

def get_confluence_score(prices, deltas, avg_alpha):
    score = 0
    if abs(avg_alpha) >= 3.0: score += 30
    if np.sign(deltas['CL=F']) == np.sign(deltas['BZ=F']): score += 25
    if prices['^VIX'] < 22: score += 20
    if (deltas['AUDJPY=X'] > 0 and avg_alpha > 0) or (deltas['AUDJPY=X'] < 0 and avg_alpha < 0): score += 25
    return score

# --- 3. INTERFACE ---
def main():
    run_global_scrap()
    market = get_market_intel()
    if not market: 
        st.error("Erro na conexão financeira.")
        return
        
    prices, deltas, corr_matrix = market
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0
    c_score = get_confluence_score(prices, deltas, avg_alpha)
    
    # --- HEADER CARDS ---
    st.title("CORE")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("WTI CRUDE", f"$ {prices['CL=F']:.2f}", f"{deltas['CL=F']:.2f}%")
    with c2: st.metric("BRENT CRUDE", f"$ {prices['BZ=F']:.2f}", f"{deltas['BZ=F']:.2f}%")
    with c3:
        df_trades = pd.read_csv(TRADE_LOG_FILE) if os.path.exists(TRADE_LOG_FILE) else pd.DataFrame()
        lucro = df_trades['PnL'].sum() if not df_trades.empty else 0
        st.metric("BANCA (EUR)", f"{300 + lucro:.2f}", f"{lucro:+.2f}")
    with c4:
        color = "green" if c_score > 70 else "yellow" if c_score > 40 else "red"
        st.metric("CONFLUÊNCIA", f"{c_score}%", help="Score para autorizar entrada")

    st.markdown("---")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        # GAUGE DE SENTIMENTO
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = avg_alpha,
            title = {'text': "SENTIMENTO IA", 'font': {'size': 20, 'color': '#00FFC8'}},
            gauge = {
                'axis': {'range': [-10, 10], 'tickwidth': 1},
                'bar': {'color': "#00FFC8"},
                'bgcolor': "#0D1421",
                'steps': [
                    {'range': [-10, -3], 'color': "#FF4B4B"},
                    {'range': [3, 10], 'color': "#00FFC8"}
                ],
            }
        ))
        fig_gauge.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=350)
        st.plotly_chart(fig_gauge, width="stretch")

    with col_right:
        # RADAR DE ATIVOS SUSPEITOS (Funcional e bonitão)
        st.markdown("<h3 style='text-align: center; color: #00FFC8;'>SUSPECT RADAR</h3>", unsafe_allow_html=True)
        radar_labels = ['DXY (Dólar)', 'VIX (Medo)', 'Yields (Juros)', 'CAD (Canadá)', 'XLE (Energia)', 'AUD/JPY (Risco)']
        radar_values = [abs(deltas['DX-Y.NYB'])*10, abs(deltas['^VIX']), abs(deltas['^TNX'])*5, abs(deltas['USDCAD=X'])*100, abs(deltas['XLE'])*5, abs(deltas['AUDJPY=X'])*10]
        
        fig_radar = go.Figure(data=go.Scatterpolar(
            r=radar_values,
            theta=radar_labels,
            fill='toself',
            line_color='#00FFC8',
            marker=dict(size=8)
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=False), bgcolor="#0D1421"),
            paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=350, margin=dict(t=30, b=30)
        )
        st.plotly_chart(fig_radar, width="stretch")

    # --- TABS ---
    t_news, t_suspects, t_ia = st.tabs(["NOTÍCIAS EM TEMPO REAL", "DETALHES SUSPEITOS", "LOG DA IA"])
    
    with t_news:
        st.dataframe(df_news.head(40), width="stretch", hide_index=True)

    with t_suspects:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Mapa de Correlação (Como os suspeitos afetam o Petróleo)**")
            fig_corr = go.Figure(data=go.Heatmap(
                z=corr_matrix.values, x=corr_matrix.columns, y=corr_matrix.index,
                colorscale='Viridis'
            ))
            fig_corr.update_layout(height=400, paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_corr, width="stretch")
        with c2:
            st.write("**Variação 24h (%)**")
            st.bar_chart(deltas)

    with t_ia:
        st.table(df_trades.sort_index(ascending=False).head(15))

if __name__ == "__main__":
    main()
