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

# --- DATABASE (CSV para Estabilidade) ---
DB_FILE = "Oil_Station_Frequency.csv"

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

# --- LÉXICO COM TODOS OS TERMOS TÉCNICOS ---
LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation": [9.5, 1, "Geopolítica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade": [8.5, 1, "Geopolítica (Sanções)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab": [9.8, 1, "Risco de Chokepoint"],
    r"election|policy shift|white house|kremlin": [7.0, 0, "Risco Político"],
    r"opec|saudi|cut|quota|production curb|voluntary|aramco": [9.0, 1, "Política OPEP+"],
    r"compliance|cheating|overproduction": [7.5, -1, "OPEP (Excesso)"],
    r"shale|fracking|permian|rig count|drilling": [7.0, -1, "Oferta EUA (Shale)"],
    r"spare capacity|tight supply": [8.0, 1, "Capacidade Ociosa"],
    r"force majeure|shut-in|outage|pipeline leak|fire|explosion": [9.5, 1, "Interrupção Física"],
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

# --- MOTOR DE MONITORAMENTO ---
def check_feeds_health():
    status = {}
    for name, url in RSS_FEEDS.items():
        try:
            r = requests.get(url, timeout=3)
            status[name] = "Ativo" if r.status_code == 200 else "Instável"
        except: status[name] = "Offline"
    return status

def analyze_news(title):
    t_lower = title.lower()
    for pattern, params in LEXICON_TOPICS.items():
        match = re.search(pattern, t_lower)
        if match:
            return {
                "Alpha": params[0] * params[1], 
                "Cat": params[2], 
                "Termo": match.group(),
                "Viés": "COMPRA" if params[1] >= 0 else "VENDA"
            }
    return None

def save_data(data):
    try:
        df_new = pd.DataFrame([data])
        if not os.path.exists(DB_FILE): df_new.to_csv(DB_FILE, index=False)
        else: df_new.to_csv(DB_FILE, mode='a', header=False, index=False)
    except: pass

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
                            "Termo": analysis["Termo"], "Alpha": analysis["Alpha"], "Viés": analysis["Viés"]
                        })
            except: pass
        time.sleep(60)

# --- INTERFACE ---
def main():
    st.set_page_config(page_title="V13 - Rationale Potency", layout="wide")
    
    st.markdown("""<style>
        .stApp { background-color: #0A192F; color: #FFFFFF; }
        .stDataFrame { background-color: #FFFFFF !important; }
        div[data-testid="stDataFrame"] td { color: #000000 !important; font-weight: 600; }
        .status-on { color: #39FF14; } .status-off { color: #FF3131; }
    </style>""", unsafe_allow_html=True)

    if 'monitor_active' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    with st.sidebar:
        st.title("Status Sites")
        health = check_feeds_health()
        for s, v in health.items():
            st.markdown(f"{s}: <span class='{'status-on' if v=='Ativo' else 'status-off'}'>{v}</span>", unsafe_allow_html=True)

    if os.path.exists(DB_FILE):
        try:
            df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete'])
            
            # Cálculo de Probabilidade Adaptativa
            net_alpha = df['Alpha'].sum()
            global_prob = 100 / (1 + np.exp(-0.08 * net_alpha))
            df['Impacto_%'] = (df['Alpha'] / df['Alpha'].abs().sum() * 100).round(2)

            # TOP DASHBOARD
            c1, c2 = st.columns([2, 1])
            with c1:
                st.title(" POTENCIAL DE RATIONALE")
                st.metric("Global Adaptive Bias", f"{global_prob:.1f}%", delta=f"{net_alpha:.2f} Alpha")
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

            t1, t2 = st.tabs([" DATA STATION", " RATIONALE FREQUENCY"])
            
            with t1:
                st.download_button("DOWNLOAD BASE DE DADOS", df.to_csv(index=False).encode('utf-8'), "oil_v13.csv")
                st.dataframe(df[['Hora', 'Manchete', 'Categoria', 'Termo', 'Impacto_%']].sort_values('Hora', ascending=False), use_container_width=True)

            with t2:
                st.subheader("Potencial por Recorrência de Termos")
                # Agrupamento para Heatmap: Tamanho = Frequência | Cor = Impacto (Alpha)
                heat_df = df.groupby(['Viés', 'Categoria', 'Termo']).agg({'Manchete': 'count', 'Alpha': 'sum'}).reset_index()
                heat_df.columns = ['Viés', 'Categoria', 'Termo', 'Frequência', 'Potencial_Alpha']

                fig_tree = px.treemap(
                    heat_df, 
                    path=[px.Constant("Oil Market"), 'Viés', 'Categoria', 'Termo'], 
                    values='Frequência', 
                    color='Potencial_Alpha',
                    color_continuous_scale=['#FF3131', '#112240', '#39FF14'],
                    title="Tamanho do bloco = Frequência nas Notícias | Cor = Força do Alpha"
                )
                st.plotly_chart(fig_tree, use_container_width=True)
                
                # Tabela de Top Termos (Potencial)
                st.markdown("### Top Termos em Destaque")
                st.table(df['Termo'].value_counts().head(10))

        except Exception as e:
            st.error(f"Erro ao processar: {e}. O arquivo pode estar sendo atualizado.")
    else:
        st.info("Aguardando novas entradas de dados...")

if __name__ == "__main__": main()

