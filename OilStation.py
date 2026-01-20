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

# --- CONFIGURAÇÃO ---
DB_FILE = "Oil_Station_V9_Final.xlsx"

RSS_FEEDS = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Energy Exch": "https://www.energyexch.com/news.php?do=newsrss",
    "Investing (Macro)": "https://www.investing.com/rss/news_11.rss",
    "Ground News": "https://ground.news/rss/interest/oil-and-gas-sector",
    "gCaptain (Logistica)": "https://gcaptain.com/feed/"
}

LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict": [9.5, 1, "Geopolítica (Risco)"],
    r"opec|saudi|cut|quota|production curb": [9.0, 1, "Política OPEP"],
    r"force majeure|shut-in|outage|pipeline leak|fire": [9.5, 1, "Choque Físico"],
    r"inventory|stockpile|draw|drawdown": [7.0, 1, "Dados de Estoque"],
    r"build|glut|oversupply": [7.0, -1, "Dados de Estoque"],
    r"china|stimulus|recovery|growth": [7.5, 1, "Demanda (China)"],
    r"recession|slowdown|weak|contracting": [8.0, -1, "Macro (Recessão)"],
    r"fed|rate hike|hawkish|inflation": [6.5, -1, "Macro (Monetário)"],
    r"dovish|rate cut|liquidity": [6.5, 1, "Macro (Monetário)"],
    r"dollar|dxy|greenback": [6.0, -1, "Correlação FX"],
    r"backwardation|premium": [7.0, 1, "Estrutura de Mercado"],
    r"contango|discount": [7.0, -1, "Estrutura de Mercado"]
}

# --- MOTOR DE ANÁLISE ---
def analyze_news(title):
    title_lower = title.lower()
    for pattern, params in LEXICON_TOPICS.items():
        if re.search(pattern, title_lower):
            return {"Alpha": params[0] * params[1], "Categoria": params[2], "Viés": "COMPRA" if params[1] > 0 else "VENDA"}
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
                        save_data({"Timestamp": datetime.now().isoformat(), "Hora": datetime.now().strftime("%H:%M:%S"),
                                   "Fonte": source, "Manchete": entry.title, "Categoria": analysis["Categoria"],
                                   "Alpha": analysis["Alpha"], "Viés": analysis["Viés"]})
            except: pass
        time.sleep(60)

# --- DASHBOARD ---
def main():
    st.set_page_config(page_title="QUANT STATION V9", layout="wide")
    
    # CSS Customizado: Fundo Marinho, Tabela Branca e Botão Invisível com Borda
    st.markdown("""
        <style>
        .stApp { background-color: #0A192F; color: #FFFFFF; }
        
        /* Estilização da Tabela para Foto */
        .stDataFrame { background-color: #FFFFFF !important; border-radius: 5px; }
        div[data-testid="stDataFrame"] td { color: #000000 !important; font-weight: 500; }
        
        /* AJUSTE DO BOTÃO DE DOWNLOAD: Transparente com Borda Neon */
        div.stDownloadButton > button {
            background-color: transparent !important;
            color: #64FFDA !important;
            border: 2px solid #64FFDA !important;
            border-radius: 5px;
            padding: 10px 24px;
            font-weight: bold;
            transition: 0.3s;
        }
        div.stDownloadButton > button:hover {
            background-color: rgba(100, 255, 218, 0.1) !important;
            border: 2px solid #FFFFFF !important;
            color: #FFFFFF !important;
        }

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] { background-color: #112240; }
        .stTabs [data-baseweb="tab"] { color: #8892B0; }
        .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #64FFDA; }
        </style>
        """, unsafe_allow_html=True)

    if 'monitor_active' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    if os.path.exists(DB_FILE):
        df = pd.read_excel(DB_FILE)
        
        # Probabilidade Adaptativa (Sigmoide)
        net_alpha = df['Alpha'].sum()
        global_prob = 100 / (1 + np.exp(-0.1 * net_alpha))
        df['Impacto_%'] = (df['Alpha'] / df['Alpha'].abs().sum() * 100).round(2)

        # UI
        c1, c2 = st.columns([2, 1])
        with c1:
            st.title("🛢️ OIL ANALYTICS: V9 PRO")
            st.subheader(f"Global Sentiment: {global_prob:.1f}%")
        
        with c2:
            g_color = "#39FF14" if global_prob > 70 else ("#FF3131" if global_prob < 30 else "#FFD700")
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=global_prob,
                number={'suffix': "%", 'font': {'color': g_color}},
                gauge={'axis': {'range': [0, 100], 'tickcolor': "#FFF"}, 'bar': {'color': g_color},
                       'bgcolor': "#112240", 'steps': [{'range': [0, 30], 'color': "rgba(255, 49, 49, 0.2)"},
                                                       {'range': [70, 100], 'color': "rgba(57, 255, 20, 0.2)"}]}))
            fig.update_layout(height=180, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

        t1, t2 = st.tabs(["📊 DATA STATION", "🔥 RATIONALE HEATMAP"])
        with t1:
            st.download_button("📥 EXPORTAR DATASET (EXCEL)", df.to_csv(index=False).encode('utf-8'), "oil_data.csv")
            st.dataframe(df[['Hora', 'Manchete', 'Categoria', 'Impacto_%', 'Viés']].sort_values('Hora', ascending=False), use_container_width=True)

        with t2:
            heat_df = df.groupby(['Viés', 'Categoria']).agg({'Alpha': 'sum', 'Manchete': 'count'}).reset_index()
            fig_tree = px.treemap(heat_df, path=[px.Constant("Market"), 'Viés', 'Categoria'], values='Manchete', color='Alpha',
                                 color_continuous_scale=['#FF3131', '#112240', '#39FF14'])
            fig_tree.update_layout(height=450, paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("Sincronizando terminais...")

if __name__ == "__main__": main()
