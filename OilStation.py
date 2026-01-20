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
import requests
from datetime import datetime

# --- DATABASE ---
DB_FILE = "Oil_Station_V19.csv"

# --- STATUS DOS SITES ---
RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "gCaptain": "https://gcaptain.com/feed/",
    "Bloomberg (Alt)": "https://www.bloomberg.com/feeds/bpol/mostread.xml"
}

# --- 22 DADOS LEXICON (O CÉREBRO) ---
LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation": [9.5, 1, "Geopolítica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade": [8.5, 1, "Geopolítica (Sanções)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab": [9.8, 1, "Risco de Chokepoint"],
    r"election|policy shift|white house|kremlin": [7.0, 0, "Risco Político"],
    r"opec|saudi|cut|quota|production curb|voluntary": [9.0, 1, "Política OPEP+"],
    r"compliance|cheating|overproduction": [7.5, -1, "OPEP (Excesso)"],
    r"shale|fracking|permian|rig count|drilling": [7.0, -1, "Oferta EUA (Shale)"],
    r"spare capacity|tight supply": [8.0, 1, "Capacidade Ociosa"],
    r"force majeure|shut-in|outage|pipeline leak|fire": [9.5, 1, "Interrupção Física"],
    r"refinery|maintenance|turnaround|crack spread": [6.5, 1, "Refino (Margens)"],
    r"spr|strategic petroleum reserve|emergency release": [7.0, -1, "SPR (Intervenção)"],
    r"tanker|freight|vessel|shipping rates": [6.0, 1, "Custos Logísticos"],
    r"inventory|stockpile|draw|drawdown|depletion": [7.0, 1, "Estoques (Déficit)"],
    r"build|glut|oversupply|surplus": [7.0, -1, "Estoques (Excesso)"],
    r"china|stimulus|recovery|growth|pmi|beijing": [8.0, 1, "Demanda (China)"],
    r"gasoline|diesel|heating oil|jet fuel": [7.5, 1, "Consumo de Produtos"],
    r"recession|slowdown|weak|contracting|hard landing": [8.5, -1, "Macro (Recessão)"],
    r"fed|rate hike|hawkish|inflation|cpi": [7.0, -1, "Macro (Aperto)"],
    r"dovish|rate cut|powell|liquidity|easing": [7.0, 1, "Macro (Estímulo)"],
    r"dollar|dxy|greenback|fx": [6.5, -1, "Correlação DXY"],
    r"backwardation|premium|physical tightness": [7.5, 1, "Estrutura (Bullish)"],
    r"contango|discount|storage play": [7.5, -1, "Estrutura (Bearish)"]
}

# --- MOTOR DE CAPTURA ---
def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    t_lower = entry.title.lower()
                    for pattern, params in LEXICON_TOPICS.items():
                        match = re.search(pattern, t_lower)
                        if match:
                            alpha = params[0] * params[1]
                            prob = 1 / (1 + np.exp(-0.5 * alpha))
                            sent = f"{prob*100:.1f}% COMPRA" if prob > 0.5 else f"{(1-prob)*100:.1f}% VENDA"
                            
                            data = {
                                "Hora": datetime.now().strftime("%H:%M:%S"),
                                "Fonte": source,
                                "Manchete": entry.title[:100],
                                "Categoria": params[2],
                                "Termo": match.group(), # O que ele absorveu
                                "Sentimento": sent,
                                "Alpha": alpha,
                                "Timestamp": datetime.now().isoformat()
                            }
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

# --- INTERFACE VISUAL ---
def main():
    st.set_page_config(page_title="V19 - FULL SPECTRUM", layout="wide")
    
    st.markdown("""<style>
        .stApp { background-color: #0A192F; }
        * { color: #FFFFFF !important; }
        div[data-testid="stDataFrame"] div { background-color: #112240 !important; }
        div[data-testid="stDataFrame"] td { color: #FFFFFF !important; font-size: 13px !important; }
        .status-on { color: #39FF14 !important; font-weight: bold; }
    </style>""", unsafe_allow_html=True)

    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    # SIDEBAR COM OS SITES
    with st.sidebar:
        st.title("📡 TERMINAIS")
        for s in RSS_SOURCES.keys():
            st.markdown(f"• {s}: <span class='status-on'>ONLINE</span>", unsafe_allow_html=True)
        st.divider()
        st.write("22 Tópicos Lexicon Ativos")

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('Timestamp', ascending=False)
        
        c1, c2 = st.columns([3, 1])
        with c1:
            st.title("OIL STATION")
            st.write(f"Monitorando {len(RSS_SOURCES)} fontes com sensibilidade singular.")
        with c2:
            net_alpha = df['Alpha'].sum()
            prob = 100 / (1 + np.exp(-0.08 * net_alpha))
            st.metric("BIAS GLOBAL", f"{prob:.1f}%", f"{net_alpha:.2f} α")

        # HEATMAP SÓ CATEGORIAS (Como solicitado)
        st.subheader("Share de Narrativas (Por Categoria)")
        cat_counts = df['Categoria'].value_counts(normalize=True).reset_index()
        cat_counts.columns = ['Categoria', 'Share']
        cat_counts['Percentual'] = (cat_counts['Share'] * 100).round(1).astype(str) + '%'
        
        fig = px.treemap(cat_counts, path=['Categoria'], values='Share', 
                         color_discrete_sequence=['#112240', '#1B2B48', '#64FFDA'])
        fig.update_traces(texttemplate="<b>%{label}</b><br>%{customdata[0]}", customdata=cat_counts[['Percentual']])
        fig.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', font={'color': "#FFFFFF", 'size': 16})
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Fluxo de Inteligência")
        st.dataframe(df[['Hora', 'Fonte', 'Manchete', 'Categoria', 'Termo', 'Sentimento']].head(25), use_container_width=True)
    else:
        st.info("Conectando aos terminais...")

if __name__ == "__main__": main()

