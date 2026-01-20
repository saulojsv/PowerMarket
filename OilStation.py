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
import yfinance as yf  # Necessário: pip install yfinance
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO DE PÁGINA E ESTILO ---
st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")

if 'freeze' not in st.session_state: st.session_state.freeze = False
if not st.session_state.freeze:
    st_autorefresh(interval=60000, key="v54_refresh")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .stApp { background-color: #02060C; color: #E0E0E0; font-family: 'JetBrains Mono', monospace; }
        [data-testid="stMetricValue"] { font-size: 26px !important; color: #39FF14 !important; }
        [data-testid="stMetricLabel"] { color: #8a96a3 !important; font-size: 12px !important; text-transform: uppercase; }
        div[data-testid="stMetric"] { background-color: #0B121D; border-left: 5px solid #39FF14; padding: 15px; border-radius: 5px; }
        .decision-card { padding: 25px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 32px; border: 2px solid; margin-bottom: 20px; }
        .live-status { color: #39FF14; font-weight: bold; animation: blinker 1.5s linear infinite; }
        .freeze-status { color: #FF4B4B; font-weight: bold; }
        @keyframes blinker { 50% { opacity: 0.1; } }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURAÇÕES E VALIDAÇÃO (PONTO 2) ---
DB_FILE = "Oil_Station_V54_Master.csv"
BRAIN_FILE = "Market_Brain_V54.csv"

# Lista de exclusão para validar apenas termos com valor semântico real
BRAIN_STOP_WORDS = ["TODAY", "PRICES", "MARKET", "REPORT", "ANALYSIS", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "OILPRICE", "REUTERS", "BLOOMBERG"]

RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing Oil": "https://www.investing.com/rss/news_11.rss",
    "CNBC Energy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA Reports": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Yahoo Finance": "https://finance.yahoo.com/rss/headline?s=CL=F"
}

LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation|invasion|military": [9.8, 1, "Geopolítica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolítica (Sanções)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Risco de Chokepoint"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Tensões Regionais"],
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "Política OPEP+"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "Oferta OPEP+"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "Oferta EUA (Shale)"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Estoques (Déficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Estoques (Excesso)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refino/Margens"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Demanda Fraca)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Demanda Forte)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate": [7.5, -1, "Macro (Aperto Fed)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Estímulo Fed)"],
    r"dollar|dxy|greenback|fx|yields": [7.0, -1, "Correlação DXY"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Fluxo Especulativo"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Análise Técnica"]
}

# --- 3. MOTOR DE INTELIGÊNCIA E PREÇO ---
def get_xtiusd_price():
    try:
        oil = yf.Ticker("CL=F")
        data = oil.history(period="1d", interval="1m")
        if not data.empty:
            price = data['Close'].iloc[-1]
            change = price - data['Open'].iloc[0]
            return price, change
    except: return 0.0, 0.0

def update_brain(word, title):
    word = word.upper()
    if word in BRAIN_STOP_WORDS or len(word) < 4: return # Validação Semântica

    cols = ['Termo', 'Contagem', 'Peso_Alpha', 'Categoria', 'Ultima_Vez']
    df_brain = pd.read_csv(BRAIN_FILE) if os.path.exists(BRAIN_FILE) else pd.DataFrame(columns=cols)
    
    if word in df_brain['Termo'].values:
        idx = df_brain['Termo'] == word
        count = df_brain.loc[idx, 'Contagem'].values[0] + 1
        new_weight = np.clip(2.0 + (count * 0.15), 1.0, 9.5)
        df_brain.loc[idx, ['Contagem', 'Peso_Alpha', 'Ultima_Vez']] = [count, new_weight, datetime.now().strftime("%d/%m %H:%M")]
    else:
        new_row = pd.DataFrame([{'Termo': word, 'Contagem': 1, 'Peso_Alpha': 2.0, 'Categoria': 'Emergente', 'Ultima_Vez': datetime.now().strftime("%d/%m %H:%M")}])
        df_brain = pd.concat([df_brain, new_row], ignore_index=True)
    df_brain.to_csv(BRAIN_FILE, index=False)

def analyze_reality(title):
    t_lower = title.lower()
    weights, labels, cats = [], [], []
    for pat, par in LEXICON_TOPICS.items():
        match = re.search(pat, t_lower)
        if match:
            weights.append(par[0] * par[1]); labels.append(match.group().upper()); cats.append(par[2])
            
    if os.path.exists(BRAIN_FILE):
        graduados = pd.read_csv(BRAIN_FILE).query('Contagem >= 30')
        for _, row in graduados.iterrows():
            if row['Termo'].lower() in t_lower:
                bias = 1.0 if any(x in t_lower for x in ["surge", "spike", "up", "jump"]) else -1.0
                weights.append(row['Peso_Alpha'] * bias); labels.append(f"IA:{row['Termo']}"); cats.append(row['Categoria'])

    if not weights: return None
    avg_alpha = (sum(weights) + weights[0]) / (len(weights) + 1)
    side = "COMPRA" if avg_alpha > 0 else "VENDA"
    prob = (1 / (1 + np.exp(-0.15 * abs(avg_alpha))))
    
    if any(x in t_lower for x in ["surge", "plunge", "spike", "drop", "jump"]):
        new_words = re.findall(r'\b[a-zA-Z]{7,}\b', t_lower)
        for nw in new_words: update_brain(nw, title)

    return f"{np.clip(prob, 0.50, 0.98)*100:.1f}% {side}", avg_alpha, f"DOM: {labels[0]}", cats[0]

# --- 4. MONITOR RSS ---
def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:15]:
                    analysis = analyze_reality(entry.title)
                    if analysis:
                        sent, alpha, interp, cat = analysis
                        data = {"Data": datetime.now().strftime("%d/%m/%Y %H:%M"), "Fonte": source, "Manchete": entry.title, 
                                "Sent": sent, "Interpretation": interp, "Cat": cat, "Alpha": alpha, "Link": entry.link, "TS": datetime.now().timestamp()}
                        pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

# --- 5. INTERFACE ---
def main():
    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    # Busca de Preço em Tempo Real
    price, change = get_xtiusd_price()

    c_head1, c_head2, c_head3 = st.columns([2, 1, 1])
    with c_head1: 
        st.markdown(f"# TERMINAL XTIUSD> <span style='color:#39FF14'>${price:.2f}</span>", unsafe_allow_html=True)
    with c_head2:
        if st.button("SNAPSHOT" if not st.session_state.freeze else "LIVE FEED"):
            st.session_state.freeze = not st.session_state.freeze
            st.rerun()
    with c_head3: 
        status_label = "SNAPSHOT FROZEN" if st.session_state.freeze else "● LIVE FEED"
        status_class = "freeze-status" if st.session_state.freeze else "live-status"
        st.markdown(f'<div style="text-align:right; font-family:monospace; font-size:14px;">STATUS: <span class="{status_class}">{status_label}</span><br>{datetime.now().strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        st.divider()
        
        m1, m2, m3, m4 = st.columns(4)
        avg_a = df.head(30)['Alpha'].mean()
        val = np.clip(50 + (avg_a * 4.5), 0, 100)
        
        with m1:
            st.metric("XTIUSD CRUDE OIL", f"${price:.2f}", f"{change:.2f}")
        m2.metric("SENTIMENTO MÉDIO", f"{val:.1f}%")
        m3.metric("DRIVERS ATIVOS", len(df.head(30)['Interpretation'].unique()))
        m4.metric("VOLUMETRIA (TOTAL)", len(df))

        c_left, c_right = st.columns([1, 1.2])
        with c_left:
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=val, number={'suffix': "%", 'font': {'color': '#39FF14'}},
                gauge={'axis': {'range': [0, 100]}, 'bar': {'color': '#39FF14'},
                       'steps': [{'range': [0, 30], 'color': '#FF4B4B'}, {'range': [70, 100], 'color': '#00FF41'}]}))
            fig.update_layout(height=240, margin=dict(t=20, b=0), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, width='stretch')
            
        with c_right:
            color = "#39FF14" if val >= 70 else "#FF4B4B" if val <= 30 else "#E0E0E0"
            st.markdown(f'<div class="decision-card" style="color:{color}; border-color:{color}; background:rgba(255,255,255,0.03)">POSITION: {"STRONG BUY" if val >= 70 else "STRONG SELL" if val <= 30 else "NEUTRAL"}</div>', unsafe_allow_html=True)
            st.info(f"**ECONOMIST INSIGHT:** O driver dominante agora é **{df.iloc[0]['Cat']}**.")

        t1, t2, t3 = st.tabs(["FEED", "MAP", "BRAIN"])
        with t1: st.dataframe(df[['Data', 'Manchete', 'Sent', 'Interpretation', 'Link']].head(100), width='stretch', hide_index=True)
        with t2: st.plotly_chart(px.treemap(df.head(100).groupby('Cat')['Alpha'].count().reset_index(name='V'), path=['Cat'], values='V', title="DOMINÂNCIA"), width='stretch')
        with t3: 
            if os.path.exists(BRAIN_FILE):
                st.dataframe(pd.read_csv(BRAIN_FILE).sort_values('Contagem', ascending=False), width='stretch', hide_index=True)

if __name__ == "__main__": main()
