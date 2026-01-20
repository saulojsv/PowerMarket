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

# --- 1. CONFIGURAÇÃO DE PÁGINA E ESTILO ---
st.set_page_config(page_title="TERMINAL", layout="wide", initial_sidebar_state="collapsed")

if 'freeze' not in st.session_state: st.session_state.freeze = False
if not st.session_state.freeze:
    st_autorefresh(interval=60000, key="v54_refresh")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .stApp { background-color: #02060C; color: #E0E0E0; font-family: 'JetBrains Mono', monospace; }
        [data-testid="stMetricValue"] { font-size: 24px !important; color: #39FF14 !important; }
        [data-testid="stMetricLabel"] { color: #8a96a3 !important; font-size: 11px !important; text-transform: uppercase; }
        div[data-testid="stMetric"] { background-color: #0B121D; border-left: 5px solid #39FF14; padding: 12px; border-radius: 5px; }
        .decision-card { padding: 20px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 28px; border: 2px solid; margin-bottom: 20px; }
        .asym-card { background:#0B121D; padding:15px; border-radius:10px; border-top: 4px solid; }
        .live-status { color: #39FF14; font-weight: bold; animation: blinker 1.5s linear infinite; }
        .freeze-status { color: #FF4B4B; font-weight: bold; }
        @keyframes blinker { 50% { opacity: 0.1; } }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURAÇÕES MASTER (22 LEXICONS & FULL RSS) ---
DB_FILE = "Oil_Station_V54_Master.csv"
BRAIN_FILE = "Market_Brain_V54.csv"
BRAIN_STOP_WORDS = ["TODAY", "PRICES", "MARKET", "REPORT", "ANALYSIS", "OILPRICE", "REUTERS", "BLOOMBERG"]

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

# --- 3. MOTOR QUANTUM (GPS CROSS-ASSET & ASIMETRIA) ---

def get_quantum_context():
    """Busca GPS do mercado: Petróleo, Dólar e Ouro"""
    try:
        assets = yf.download(["CL=F", "DX-Y.NYB", "GC=F"], period="1d", interval="5m", progress=False)
        oil_p = assets['Close']['CL=F'].iloc[-1]
        oil_open = assets['Open']['CL=F'].iloc[0]
        oil_delta = ((oil_p / oil_open) - 1) * 100
        
        dxy_p = assets['Close']['DX-Y.NYB'].iloc[-1]
        dxy_open = assets['Open']['DX-Y.NYB'].iloc[0]
        dxy_delta = ((dxy_p / dxy_open) - 1) * 100
        
        gold_p = assets['Close']['GC=F'].iloc[-1]
        
        return {"oil": [oil_p, oil_delta], "dxy": [dxy_p, dxy_delta], "gold": [gold_p]}
    except: return None

def calculate_asymmetry(avg_alpha, price_delta):
    """Mede o desvio entre sentimento teórico e realidade do preço"""
    expected_move = avg_alpha / 5  # Heurística Quantum
    asymmetry = expected_move - price_delta
    if abs(asymmetry) > 1.5:
        return "ANOMALIA DETECTADA", "#FF4B4B", "O preço está ignorando o fluxo de notícias. Possível exaustão ou intervenção invisível."
    return "REAÇÃO COMUM", "#39FF14", "O preço está reagindo conforme o esperado ao fluxo de sentimento."

def update_brain(word, title):
    word = word.upper()
    if word in BRAIN_STOP_WORDS or len(word) < 4: return
    cols = ['Termo', 'Contagem', 'Peso_Alpha', 'Categoria', 'Ultima_Vez']
    df_brain = pd.read_csv(BRAIN_FILE) if os.path.exists(BRAIN_FILE) else pd.DataFrame(columns=cols)
    if word in df_brain['Termo'].values:
        idx = df_brain['Termo'] == word
        df_brain.loc[idx, 'Contagem'] += 1
        df_brain.loc[idx, 'Peso_Alpha'] = np.clip(df_brain.loc[idx, 'Peso_Alpha'].values[0] + 0.15, 1.0, 9.5)
        df_brain.loc[idx, 'Ultima_Vez'] = datetime.now().strftime("%d/%m %H:%M")
    else:
        new_row = pd.DataFrame([{'Termo': word, 'Contagem': 1, 'Peso_Alpha': 2.0, 'Categoria': 'Emergente', 'Ultima_Vez': datetime.now().strftime("%d/%m %H:%M")}])
        df_brain = pd.concat([df_brain, new_row], ignore_index=True).dropna(axis=1, how='all')
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
            if str(row['Termo']).lower() in t_lower:
                bias = 1.0 if any(x in t_lower for x in ["surge", "spike", "up", "jump"]) else -1.0
                weights.append(row['Peso_Alpha'] * bias); labels.append(f"IA:{row['Termo']}"); cats.append(row['Categoria'])
    if not weights: return None
    avg_alpha = sum(weights) / len(weights)
    prob = (1 / (1 + np.exp(-0.15 * abs(avg_alpha))))
    side = "COMPRA" if avg_alpha > 0 else "VENDA"
    if any(x in t_lower for x in ["surge", "plunge", "spike", "drop"]):
        new_words = re.findall(r'\b[a-zA-Z]{7,}\b', t_lower)
        for nw in new_words: update_brain(nw, title)
    return f"{np.clip(prob, 0.5, 0.98)*100:.1f}% {side}", avg_alpha, f"DOM: {labels[0]}", cats[0]

# --- 4. MONITOR RSS (ALTA VELOCIDADE) ---
def fetch_source(source, url):
    try:
        feed = feedparser.parse(url)
        new_data = []
        for entry in feed.entries[:10]:
            analysis = analyze_reality(entry.title)
            if analysis:
                sent, alpha, interp, cat = analysis
                new_data.append({"Data": datetime.now().strftime("%d/%m %H:%M"), "Fonte": source, "Manchete": entry.title, "Sent": sent, "Interpretation": interp, "Cat": cat, "Alpha": alpha, "Link": entry.link, "TS": datetime.now().timestamp()})
        if new_data:
            pd.DataFrame(new_data).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
    except: pass

def news_monitor_v2():
    while True:
        threads = [threading.Thread(target=fetch_source, args=(s, u)) for s, u in RSS_SOURCES.items()]
        for t in threads: t.start()
        for t in threads: t.join()
        time.sleep(60)

# --- 5. INTERFACE QUANTUM ---
def main():
    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor_v2, daemon=True).start()
        st.session_state['monitor'] = True

    ctx = get_quantum_context()
    if not ctx: st.error("Erro na conexão com dados de mercado."); return

    # Top Bar: GPS Market
    c_h1, c_h2, c_h3, c_h4 = st.columns([1.5, 1, 1, 1])
    with c_h1: st.markdown(f"# TERMINAL <span style='color:#39FF14'>${ctx['oil'][0]:.2f}</span>", unsafe_allow_html=True)
    with c_h2: st.metric("DXY INDEX", f"{ctx['dxy'][0]:.2f}", f"{ctx['dxy'][1]:.2f}%", delta_color="inverse")
    with c_h3: st.metric("GOLD (XAU)", f"${ctx['gold'][0]:.1f}")
    with c_h4:
        if st.button(" SNAPSHOT" if not st.session_state.freeze else " LIVE"):
            st.session_state.freeze = not st.session_state.freeze
            st.rerun()

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        avg_a = df.head(20)['Alpha'].mean()
        val = np.clip(50 + (avg_a * 4.5), 0, 100)
        
        st.divider()
        
        # Dashboard Principal
        col_main, col_side = st.columns([1.2, 1])
        
        with col_main:
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=val, number={'suffix': "%"},
                gauge={'axis': {'range': [0, 100]}, 'bar': {'color': '#39FF14'},
                       'steps': [{'range': [0, 35], 'color': '#FF4B4B'}, {'range': [65, 100], 'color': '#00FF41'}]}))
            fig.update_layout(height=300, margin=dict(t=30, b=0), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, use_container_width=True)

        with col_side:
            asym_label, asym_color, asym_desc = calculate_asymmetry(avg_a, ctx['oil'][1])
            st.markdown(f"""
                <div class="asym-card" style="border-color:{asym_color}">
                    <p style="color:#8a96a3; font-size:12px; margin:0;">QUANTUM ANOMALY DETECTOR</p>
                    <h2 style="color:{asym_color}; margin:10px 0;">{asym_label}</h2>
                    <p style="font-size:14px;">{asym_desc}</p>
                    <hr style="border-color:#1B2B48">
                    <p style="font-size:12px; font-family:monospace;">
                        SENTIMENTO: {avg_a:.2f} Alpha<br>
                        PRICE REACTION: {ctx['oil'][1]:.2f}%<br>
                        DXY BIAS: {"PRESSÃO DE DBAIXA" if ctx['dxy'][1] > 0 else "SUPORTE ALTISTA"}
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            color_p = "#39FF14" if val >= 65 else "#FF4B4B" if val <= 35 else "#E0E0E0"
            side_p = "BUY" if val >= 65 else "SELL" if val <= 35 else "WAIT"
            st.markdown(f'<div class="decision-card" style="color:{color_p}; border-color:{color_p};">POSITION: {side_p}</div>', unsafe_allow_html=True)

        # Tabs de Dados
        t1, t2, t3 = st.tabs([" NEWS FEED", " MARKET MAP", " IA BRAIN"])
        with t1: st.dataframe(df[['Data', 'Fonte', 'Manchete', 'Sent', 'Cat', 'Link']].head(100), hide_index=True)
        with t2: st.plotly_chart(px.treemap(df.head(100), path=['Cat'], values='Alpha', title="DOMINÂNCIA POR CATEGORIA"), use_container_width=True)
        with t3: 
            if os.path.exists(BRAIN_FILE): st.dataframe(pd.read_csv(BRAIN_FILE).sort_values('Contagem', ascending=False))

if __name__ == "__main__": main()
