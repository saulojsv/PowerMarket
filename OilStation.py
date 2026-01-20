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
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO DE PÁGINA E ESTILO ---
st.set_page_config(page_title="TERMINAL XTIUSD | OS BIGODERAS", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .stApp { background-color: #02060C; color: #E0E0E0; font-family: 'JetBrains Mono', monospace; }
        [data-testid="stMetricValue"] { font-size: 26px !important; color: #39FF14 !important; }
        [data-testid="stMetricLabel"] { color: #8a96a3 !important; font-size: 12px !important; text-transform: uppercase; }
        div[data-testid="stMetric"] { background-color: #0B121D; border-left: 5px solid #39FF14; padding: 15px; border-radius: 5px; }
        .stDataFrame { border: 1px solid #1B2B48; border-radius: 10px; }
        .decision-card { padding: 25px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 32px; border: 2px solid; margin-bottom: 20px; }
        h1, h2, h3 { color: #39FF14 !important; text-transform: uppercase; letter-spacing: 2px; }
        .live-status { color: #39FF14; font-weight: bold; animation: blinker 1.5s linear infinite; }
        @keyframes blinker { 50% { opacity: 0.1; } }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURAÇÕES DE DADOS (EXPANDIDO) ---
DB_FILE = "Oil_Station_V54_Master.csv"
BRAIN_FILE = "Market_Brain_V54.csv"

RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing Oil": "https://www.investing.com/rss/news_11.rss",
    "CNBC Energy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA Reports": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Bloomberg Energy": "https://www.bloomberg.com/feeds/bpol/sitemap_news.xml", # Simulação via agregador
    "Yahoo Finance": "https://finance.yahoo.com/rss/headline?s=CL=F" # Petróleo Futuro
}

LEXICON_TOPICS = {
    # BLOCO GEOPOLÍTICO (PESO MÁXIMO)
    r"war|attack|missile|drone|strike|conflict|escalation|invasion|military": [9.8, 1, "Geopolítica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolítica (Sanções)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Risco de Chokepoint"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Tensões Regionais"],
    
    # BLOCO OPEP+ E OFERTA
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "Política OPEP+"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "Oferta OPEP+"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "Oferta EUA (Shale)"],
    
    # BLOCO ESTOQUES E FUNDAMENTOS
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Estoques (Déficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Estoques (Excesso)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refino/Margens"],
    
    # BLOCO MACRO E DEMANDA
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Demanda Fraca)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Demanda Forte)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate": [7.5, -1, "Macro (Aperto Fed)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Estímulo Fed)"],
    r"dollar|dxy|greenback|fx|yields": [7.0, -1, "Correlação DXY"],
    
    # BLOCO ESPECULATIVO
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Fluxo Especulativo"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Análise Técnica"]
}

# --- 3. MOTOR DE INTELIGÊNCIA ---
def get_auto_category(word):
    w = word.lower()
    if any(x in w for x in ["opec", "saudi", "russia", "cut"]): return "Política Energética"
    if any(x in w for x in ["war", "strike", "iran", "attack"]): return "Risco Geopolítico"
    if any(x in w for x in ["fed", "inflation", "rate"]): return "Macro/Fed"
    return "Driver Emergente"

def update_brain(word, title):
    cols = ['Termo', 'Contagem', 'Peso_Alpha', 'Categoria', 'Ultima_Vez']
    if not os.path.exists(BRAIN_FILE):
        df_brain = pd.DataFrame(columns=cols).astype({'Termo': 'str', 'Contagem': 'int', 'Peso_Alpha': 'float'})
    else:
        df_brain = pd.read_csv(BRAIN_FILE)
    
    if word in df_brain['Termo'].values:
        idx = df_brain['Termo'] == word
        count = df_brain.loc[idx, 'Contagem'].values[0] + 1
        new_weight = np.clip(2.0 + (count * 0.15), 1.0, 9.5)
        df_brain.loc[idx, ['Contagem', 'Peso_Alpha', 'Ultima_Vez']] = [count, new_weight, datetime.now().strftime("%d/%m %H:%M")]
    else:
        new_row = pd.DataFrame([{'Termo': str(word), 'Contagem': 1, 'Peso_Alpha': 2.0, 'Categoria': get_auto_category(word), 'Ultima_Vez': datetime.now().strftime("%d/%m %H:%M")}])
        df_brain = pd.concat([df_brain, new_row], ignore_index=True)
    df_brain.to_csv(BRAIN_FILE, index=False)

def analyze_reality(title):
    t_lower = title.lower()
    weights, labels, cats = [], [], []
    
    for pat, par in LEXICON_TOPICS.items():
        match = re.search(pat, t_lower)
        if match:
            weights.append(par[0] * par[1])
            labels.append(match.group().upper())
            cats.append(par[2])
            
    if os.path.exists(BRAIN_FILE):
        graduados = pd.read_csv(BRAIN_FILE).query('Contagem >= 30')
        for _, row in graduados.iterrows():
            if row['Termo'].lower() in t_lower:
                bias = 1.0 if any(x in t_lower for x in ["surge", "spike", "up", "jump", "higher"]) else -1.0
                weights.append(row['Peso_Alpha'] * bias)
                labels.append(f"IA:{row['Termo'].upper()}")
                cats.append(row['Categoria'])

    if not weights: return None

    abs_weights = [abs(w) for w in weights]
    dominant_idx = abs_weights.index(max(abs_weights))
    weighted_sum = sum(weights) + weights[dominant_idx] 
    avg_alpha = weighted_sum / (len(weights) + 1)
    
    synergy = "CONVERGENTE" if all(w > 0 for w in weights) or all(w < 0 for w in weights) else "DIVERGENTE"
    speculation_hit = 0.85 if any(x in t_lower for x in ["may", "could", "rumor", "possible"]) else 1.0
    
    prob = (1 / (1 + np.exp(-0.15 * abs(avg_alpha)))) * speculation_hit
    side = "COMPRA" if avg_alpha > 0 else "VENDA"
    interpretation = f"DOM: {labels[dominant_idx]} | {synergy} ({len(weights)} signals)"
    
    if any(x in t_lower for x in ["surge", "plunge", "spike", "drop", "jump", "crash"]):
        new_words = re.findall(r'\b[a-zA-Z]{7,}\b', t_lower)
        for nw in new_words: update_brain(nw, title)

    return f"{np.clip(prob, 0.50, 0.98)*100:.1f}% {side}", avg_alpha, interpretation, cats[dominant_idx]

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

# --- 5. INTERFACE DO UTILIZADOR ---
def main():
    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    c_head1, c_head2 = st.columns([3, 1])
    with c_head1: 
        st.markdown("# TERMINAL - XTIUSD | OS BIGODINS", unsafe_allow_html=True)
    with c_head2: 
        st.markdown(f"""
            <div style="text-align:right; font-family:monospace; font-size:14px; margin-top:10px;">
                STATUS: <span class="live-status">● LIVE FEED</span><br>
                <span style="color:#8a96a3;">{datetime.now().strftime('%H:%M:%S')}</span>
            </div>
        """, unsafe_allow_html=True)

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        avg_a = df.head(30)['Alpha'].mean()
        val = np.clip(50 + (avg_a * 4.5), 0, 100)
        m1.metric("SENTIMENTO MÉDIO", f"{val:.1f}%")
        m2.metric("VOLUMETRIA (TOTAL)", len(df))
        m3.metric("DRIVERS ATIVOS", len(df.head(30)['Interpretation'].unique()))
        m4.metric("ALPHA MÁXIMO", f"{df.head(30)['Alpha'].max():.1f}")

        c_left, c_right = st.columns([1, 1.2])
        with c_left:
            fig = go.Figure(go.Indicator(
                mode="gauge+number", 
                value=val, 
                number={'suffix': "%", 'font': {'color': '#39FF14', 'size': 40}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1},
                    'bar': {'color': '#39FF14'},
                    'steps': [
                        {'range': [0, 30], 'color': '#FF4B4B'},
                        {'range': [30, 70], 'color': '#111b27'},
                        {'range': [70, 100], 'color': '#00FF41'}
                    ]
                }))
            fig.update_layout(height=240, margin=dict(t=20, b=0, l=30, r=30), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, width='stretch')
            
        with c_right:
            color = "#39FF14" if val >= 70 else "#FF4B4B" if val <= 30 else "#E0E0E0"
            label = "STRONG BUY" if val >= 70 else "STRONG SELL" if val <= 30 else "NEUTRAL / HEDGE"
            st.markdown(f'<div class="decision-card" style="color:{color}; border-color:{color}; background:rgba(255,255,255,0.03)">POSITION: {label}</div>', unsafe_allow_html=True)
            
            insight_cat = df.iloc[0]['Cat'] if not df.empty else "N/A"
            st.info(f"**ECONOMIST INSIGHT:** O mercado é impulsionado por **{insight_cat}**. Sinais predominantes indicam um viés de {'ALTA' if avg_a > 0 else 'BAIXA'}.")

        t1, t2, t3 = st.tabs([" INTELLIGENCE FEED", "SECTOR MAP", "IA BRAIN"])
        with t1:
            st.dataframe(df[['Data', 'Manchete', 'Sent', 'Interpretation', 'Link']].head(100), 
                         column_config={"Link": st.column_config.LinkColumn("FONTE", display_text="OPEN")}, 
                         width='stretch', hide_index=True)
        with t2:
            c_h1, c_h2 = st.columns(2)
            with c_h1:
                st.plotly_chart(px.treemap(df.head(100).groupby('Cat')['Alpha'].count().reset_index(name='Volume'), path=['Cat'], values='Volume', color='Volume', color_continuous_scale='GnBu', title="DOMINÂNCIA"), width='stretch')
            with c_h2:
                st.plotly_chart(px.bar(df.head(100).groupby('Cat')['Alpha'].mean().reset_index(), x='Cat', y='Alpha', color='Alpha', color_continuous_scale='RdYlGn', title="SENTIMENTO POR SETOR"), width='stretch')
        with t3:
            if os.path.exists(BRAIN_FILE):
                st.dataframe(pd.read_csv(BRAIN_FILE).sort_values('Contagem', ascending=False), 
                             column_config={"Contagem": st.column_config.ProgressColumn("PROGRESSO IA (30x)", min_value=0, max_value=30)}, 
                             width='stretch', hide_index=True)

if __name__ == "__main__": main()

