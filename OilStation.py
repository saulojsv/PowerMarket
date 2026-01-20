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

# --- 1. CONFIGURAÇÃO DE PÁGINA (ESTILO TERMINAL BLOOMBERG) ---
st.set_page_config(page_title="QUANT STATION V54 | MASTER", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_pro")

if 'last_market_data' not in st.session_state:
    st.session_state.last_market_data = {"oil": [0.0, 0.0], "dxy": [0.0], "cad": [0.0, 0.0]}

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .stApp { background-color: #02060C; color: #E0E0E0; font-family: 'JetBrains Mono', monospace; }
        [data-testid="stMetricValue"] { font-size: 22px !important; color: #39FF14 !important; }
        div[data-testid="stMetric"] { background-color: #0B121D; border-left: 4px solid #39FF14; padding: 10px; border-radius: 4px; }
        .live-tag { color: #39FF14; font-weight: bold; animation: blinker 1.5s linear infinite; font-size: 12px; }
        @keyframes blinker { 50% { opacity: 0.1; } }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURAÇÕES MASTER (LEXICONS & FONTES) ---
DB_FILE = "Oil_Station_V54_Master.csv"
BRAIN_FILE = "Market_Brain_V54.csv"

RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing Oil": "https://www.investing.com/rss/news_11.rss",
    "CNBC Energy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA Reports": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Yahoo Finance": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "Bloomberg": "https://www.bloomberg.com/feeds/bview/energy.xml"
}

# OS 22 LEXICONS ESTRUTURADOS PARA MÁXIMA COBERTURA
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

# --- 3. MOTOR DE DADOS ---

def get_market_context():
    try:
        data = yf.download(["CL=F", "DX-Y.NYB", "USDCAD=X"], period="1d", interval="5m", progress=False)
        if data.empty: return st.session_state.last_market_data
        
        oil_p = data['Close']['CL=F'].iloc[-1]
        oil_d = ((oil_p / data['Open']['CL=F'].iloc[0]) - 1) * 100
        dxy_p = data['Close']['DX-Y.NYB'].iloc[-1]
        cad_p = data['Close']['USDCAD=X'].iloc[-1]
        cad_d = ((cad_p / data['Open']['USDCAD=X'].iloc[0]) - 1) * 100
        
        ctx = {"oil": [oil_p, oil_d], "dxy": [dxy_p], "cad": [cad_p, cad_d]}
        st.session_state.last_market_data = ctx
        return ctx
    except:
        return st.session_state.last_market_data

def analyze_reality(title):
    t_lower = title.lower()
    weights, labels, cats = [], [], []
    for pat, par in LEXICON_TOPICS.items():
        if re.search(pat, t_lower):
            weights.append(par[0] * par[1])
            labels.append(par[2])
    
    if not weights: return None
    avg_alpha = sum(weights) / len(weights)
    side = "COMPRA" if avg_alpha > 0 else "VENDA"
    return f"{abs(avg_alpha):.1f} {side}", avg_alpha, labels[0]

# --- 4. INTERFACE ---
def main():
    ctx = get_market_context()
    
    # Header Monitor
    c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
    with c1: st.markdown(f"### CRUDE OIL: **${ctx['oil'][0]:.2f}**")
    with c2: st.metric("DXY", f"{ctx['dxy'][0]:.2f}")
    with c3: st.metric("USDCAD", f"{ctx['cad'][0]:.4f}", f"{ctx['cad'][1]:.2f}%", delta_color="inverse")
    with c4: st.markdown('<div class="live-tag">● LIVE FEED</div>', unsafe_allow_html=True)

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        
        # Filtro de Decaimento de 30 minutos
        now = datetime.now().timestamp()
        df['Decay'] = np.exp(-(now - df['TS']) / 1800)
        df['Alpha_W'] = df['Alpha'] * df['Decay']
        
        avg_weighted = df.head(15)['Alpha_W'].mean()
        val = np.clip(50 + (avg_weighted * 5), 0, 100)

        st.divider()
        col_left, col_right = st.columns([1.2, 1])
        
        with col_left:
            fig = go.Figure(go.Indicator(mode="gauge+number", value=val, number={'suffix': "%"},
                gauge={'axis': {'range': [0, 100]}, 'bar': {'color': '#39FF14'}}))
            fig.update_layout(height=280, margin=dict(t=30, b=0), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, width='stretch')

        with col_right:
            # Validação: Se Sentimento > 0 mas USDCAD sobe (CAD fraco), algo está errado.
            divergence = (avg_weighted > 0.5 and ctx['cad'][1] > 0.05)
            st.markdown(f"""
                <div style="background:#0B121D; padding:15px; border-radius:8px; border-left: 5px solid {'#FF4B4B' if divergence else '#39FF14'};">
                    <p style="margin:0; font-size:12px; color:#8a96a3;">SISTEMA DE VALIDAÇÃO</p>
                    <h3 style="margin:5px 0; color:{'#FF4B4B' if divergence else '#39FF14'};">
                        {'DIVERGÊNCIA (CUIDADO)' if divergence else 'FLUXO VALIDADO'}
                    </h3>
                    <p style="font-size:11px;">Alpha Ponderado: {avg_weighted:.2f} | CAD Corr: {ctx['cad'][1]:.2f}%</p>
                </div>
            """, unsafe_allow_html=True)
            
            p_color = "#39FF14" if val >= 65 else "#FF4B4B" if val <= 35 else "#8a96a3"
            st.markdown(f'<div style="margin-top:15px; padding:15px; text-align:center; border:2px solid {p_color}; color:{p_color}; font-weight:bold; font-size:24px;">POSIÇÃO: {"BUY" if val >= 65 else "SELL" if val <= 35 else "WAIT"}</div>', unsafe_allow_html=True)

        st.subheader("Flow de Dados (22 Lexicons Active)")
        st.dataframe(df[['Data', 'Fonte', 'Manchete', 'Alpha_W', 'Cat']].head(50), width='stretch', hide_index=True)

if __name__ == "__main__": main()
