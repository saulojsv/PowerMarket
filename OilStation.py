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

# --- DATABASE E FEEDS ---
DB_FILE = "Oil_Station_V11_Institutional.xlsx"

RSS_FEEDS = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Energy Exch": "https://www.energyexch.com/news.php?do=newsrss",
    "Investing (Macro)": "https://www.investing.com/rss/news_11.rss",
    "Ground News": "https://ground.news/rss/interest/oil-and-gas-sector",
    "gCaptain (Logistica)": "https://gcaptain.com/feed/",
    "CNBC Energy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA Reports": "https://www.eia.gov/about/rss/todayinenergy.xml"
}

# --- LÉXICO ULTRA-EXPANDIDO ---
LEXICON_TOPICS = {
    # Geopolítica e Conflitos
    r"war|attack|missile|drone|strike|conflict|escalation": [9.5, 1, "Geopolítica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade": [8.5, 1, "Geopolítica (Sanções)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab": [9.8, 1, "Risco de Chokepoint"],
    r"election|policy shift|white house|kremlin": [7.0, 0, "Risco Político"],
    
    # OPEP+ e Produção
    r"opec|saudi|cut|quota|production curb|voluntary|aramco": [9.0, 1, "Política OPEP+"],
    r"compliance|cheating|overproduction": [7.5, -1, "OPEP (Excesso)"],
    r"shale|fracking|permian|rig count|drilling": [7.0, -1, "Oferta EUA (Shale)"],
    r"spare capacity|tight supply": [8.0, 1, "Capacidade Ociosa"],
    
    # Infraestrutura e Choques Físicos
    r"force majeure|shut-in|outage|pipeline leak|fire|explosion": [9.5, 1, "Interrupção Física"],
    r"refinery|maintenance|turnaround|crack spread": [6.5, 1, "Refino (Margens)"],
    r"spr|strategic petroleum reserve|emergency release": [7.0, -1, "SPR (Intervenção)"],
    r"tanker|freight|vessel|shipping rates": [6.0, 1, "Custos Logísticos"],
    
    # Estoques e Demanda
    r"inventory|stockpile|draw|drawdown|depletion": [7.0, 1, "Estoques (Déficit)"],
    r"build|glut|oversupply|surplus": [7.0, -1, "Estoques (Excesso)"],
    r"china|stimulus|recovery|growth|pmi|beijing": [8.0, 1, "Demanda (Países)"],
    r"gasoline|diesel|heating oil|jet fuel": [7.5, 1, "Consumo de Produtos"],
    r"recession|slowdown|weak|contracting|hard landing": [8.5, -1, "Macro (Recessão)"],
    
    # Monetário e Financeiro
    r"fed|rate hike|hawkish|inflation|cpi": [7.0, -1, "Macro (Aperto)"],
    r"dovish|rate cut|powell|liquidity|easing": [7.0, 1, "Macro (Estímulo)"],
    r"dollar|dxy|greenback|fx": [6.5, -1, "Correlação DXY"],
    
    # Estrutura Técnica
    r"backwardation|premium|physical tightness": [7.5, 1, "Estrutura (Bullish)"],
    r"contango|discount|storage play": [7.5, -1, "Estrutura (Bearish)"]
}

# --- FUNÇÕES DE SUPORTE ---
def check_feeds_health():
    status_report = {}
    for name, url in RSS_FEEDS.items():
        try:
            r = requests.get(url, timeout=3)
            status_report[name] = "Ativo" if r.status_code == 200 else "Instável"
        except: status_report[name] = "Offline"
    return status_report

def analyze_news(title):
    t_lower = title.lower()
    for pattern, params in LEXICON_TOPICS.items():
        if re.search(pattern, t_lower):
            return {"Alpha": params[0] * params[1], "Cat": params[2], "Viés": "COMPRA" if params[1] >= 0 else "VENDA"}
    return None

def save_data(data):
    df_new = pd.DataFrame([data])
    if not os.path.exists(DB_FILE): df_new.to_excel(DB_FILE, index=False)
    else:
        df_old = pd.read_excel(DB_FILE)
        pd.concat([df_old, df_new], ignore_index=True).drop_duplicates(subset=['Manchete']).to_excel(DB_FILE, index=False)

def news_monitor():
    while True:
        for source, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    analysis = analyze_news(entry.title)
                    if analysis:
                        save_data({
                            "Timestamp": datetime.now().isoformat(), "Hora": datetime.now().strftime("%H:%M:%S"),
                            "Fonte": source, "Manchete": entry.title, "Categoria": analysis["Cat"],
                            "Alpha": analysis["Alpha"], "Viés": analysis["Viés"]
                        })
            except: pass
        time.sleep(60)

# --- DASHBOARD ---
def main():
    st.set_page_config(page_title="QUANT STATION V11", layout="wide")
    
    st.markdown("""
        <style>
        .stApp { background-color: #0A192F; color: #FFFFFF; }
        .stDataFrame { background-color: #FFFFFF !important; border-radius: 5px; }
        div[data-testid="stDataFrame"] td { color: #000000 !important; font-weight: 600; font-size: 14px; }
        div.stDownloadButton > button { background-color: transparent !important; color: #64FFDA !important; border: 1px solid #64FFDA !important; }
        .status-on { color: #39FF14; } .status-off { color: #FF3131; }
        </style>
    """, unsafe_allow_html=True)

    if 'monitor_active' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    with st.sidebar:
        st.title("📡 Site Health")
        health = check_feeds_health()
        for s, v in health.items():
            st.markdown(f"{s}: <span class='{'status-on' if v=='Ativo' else 'status-off'}'>{v}</span>", unsafe_allow_html=True)

    if os.path.exists(DB_FILE):
        df = pd.read_excel(DB_FILE)
        net_alpha = df['Alpha'].sum()
        # Probabilidade com base em Sigmoide para adaptabilidade global
        global_prob = 100 / (1 + np.exp(-0.08 * net_alpha))
        df['Impacto_%'] = (df['Alpha'] / df['Alpha'].abs().sum() * 100).round(2)

        c1, c2 = st.columns([2, 1])
        with c1:
            st.title("OIL INTELLIGENCE V11")
            st.markdown(f"**SENTIMENTO GLOBAL ADAPTATIVO: {global_prob:.1f}%**")
        
        with c2:
            g_color = "#39FF14" if global_prob > 70 else ("#FF3131" if global_prob < 30 else "#FFD700")
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=global_prob,
                number={'suffix': "%", 'font': {'color': g_color}},
                gauge={'axis': {'range': [0, 100], 'tickcolor': "#FFF"}, 'bar': {'color': g_color},
                       'bgcolor': "#112240", 'steps': [{'range': [0, 35], 'color': "rgba(255, 49, 49, 0.2)"},
                                                       {'range': [65, 100], 'color': "rgba(57, 255, 20, 0.2)"}]}))
            fig.update_layout(height=180, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

        t1, t2 = st.tabs(["📝 DATA STATION", "RATIONALE HEATMAP"])
        with t1:
            st.download_button("EXCEL DOWNLOAD", df.to_csv(index=False).encode('utf-8'), "oil_v11_data.csv")
            st.dataframe(df[['Hora', 'Manchete', 'Categoria', 'Impacto_%', 'Viés']].sort_values('Hora', ascending=False), use_container_width=True)

        with t2:
            # Heatmap focado em frequência e viés
            heat_df = df.groupby(['Viés', 'Categoria']).agg({'Alpha': 'sum', 'Manchete': 'count'}).reset_index()
            fig_tree = px.treemap(heat_df, path=[px.Constant("Global Market"), 'Viés', 'Categoria'], 
                                 values='Manchete', color='Alpha',
                                 color_continuous_scale=['#FF3131', '#112240', '#39FF14'])
            st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("Aguardando novas manchetes para análise...")

if __name__ == "__main__": main()
