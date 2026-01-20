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
DB_FILE = "Oil_Station_V7_Legibility.xlsx"
HALFLIFE_MINUTES = 60

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
    r"force majeure|shut-in|outage|pipeline leak|fire": [9.5, 1, "Choque Físico (Oferta)"],
    r"sanction|ban|embargo|price cap": [8.0, 1, "Geopolítica (Sanções)"],
    r"inventory|stockpile|draw|drawdown": [7.0, 1, "Dados de Estoque"],
    r"build|glut|oversupply": [7.0, -1, "Dados de Estoque"],
    r"china|stimulus|recovery|growth": [7.5, 1, "Demanda (China)"],
    r"recession|slowdown|weak|contracting|pmi miss": [8.0, -1, "Macro (Recessão)"],
    r"fed|rate hike|hawkish|inflation|cpi": [6.5, -1, "Macro (Monetário)"],
    r"dovish|rate cut|powell|liquidity": [6.5, 1, "Macro (Monetário)"],
    r"dollar|dxy|greenback": [6.0, -1, "Correlação FX"],
    r"backwardation|premium": [7.0, 1, "Estrutura de Mercado"],
    r"contango|discount": [7.0, -1, "Estrutura de Mercado"]
}

# --- MOTOR DE ANÁLISE ---
def analyze_and_discover(title):
    title_lower = title.lower()
    for pattern, params in LEXICON_TOPICS.items():
        match = re.search(pattern, title_lower)
        if match:
            alpha = params[0] * params[1]
            return {
                "Alpha": alpha,
                "Categoria": params[2],
                "Rationale": f"{params[2]} ({'Bullish' if params[1]>0 else 'Bearish'})",
                "Destaque": match.group(),
                "Viés": "COMPRA" if params[1] > 0 else "VENDA"
            }, []
    return None, []

def save_data(data):
    df_new = pd.DataFrame([data])
    if not os.path.exists(DB_FILE):
        df_new.to_excel(DB_FILE, index=False)
    else:
        df_old = pd.read_excel(DB_FILE)
        pd.concat([df_old, df_new], ignore_index=True).drop_duplicates(subset=['Manchete']).to_excel(DB_FILE, index=False)

def news_monitor():
    while True:
        for source, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:8]:
                    analysis, _ = analyze_and_discover(entry.title)
                    if analysis:
                        save_data({
                            "Timestamp": datetime.now().isoformat(),
                            "Hora": datetime.now().strftime("%H:%M:%S"),
                            "Fonte": source,
                            "Manchete": entry.title,
                            "Categoria": analysis["Categoria"],
                            "Rationale": analysis["Rationale"],
                            "Destaque": analysis["Destaque"],
                            "Alpha": analysis["Alpha"],
                            "Viés": analysis["Viés"]
                        })
            except: pass
        time.sleep(60)

# --- DASHBOARD ---
def main():
    st.set_page_config(page_title="QUANT STATION V7", layout="wide")
    
    # CSS Customizado para Legibilidade Extrema (Texto Branco, Fundo profundo, Tabela Clara)
    st.markdown("""
        <style>
        /* Fundo Geral Azul Marinho Profundo */
        .stApp { background-color: #0A192F; color: #FFFFFF; }
        
        /* Títulos com contraste máximo */
        h1, h2, h3, p { color: #FFFFFF !important; font-weight: 600; }
        
        /* Estilização da Tabela para Fotos (Fundo Branco, Letra Preta) */
        .stDataFrame, div[data-testid="stTable"] { 
            background-color: #FFFFFF !important; 
            border-radius: 5px; 
            padding: 5px;
        }
        
        /* Forçar texto da tabela a ser legível */
        div[data-testid="stDataFrame"] td, div[data-testid="stDataFrame"] th {
            color: #000000 !important;
        }

        /* Tabs customizadas */
        .stTabs [data-baseweb="tab-list"] { background-color: #112240; border-radius: 10px; padding: 5px; }
        .stTabs [data-baseweb="tab"] { color: #8892B0; }
        .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #64FFDA; font-weight: bold; }
        </style>
        """, unsafe_allow_html=True)

    if 'monitor_active' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    if os.path.exists(DB_FILE):
        df = pd.read_excel(DB_FILE)
        
        # HEADER
        col_header, col_gauge = st.columns([2, 1])
        with col_header:
            st.title(" OIL ANALYTICS PRO: LEGIBILITY MODE")
            st.write(f"Sincronizado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

        with col_gauge:
            vies_counts = df['Viés'].value_counts(normalize=True) * 100
            buy_pct = vies_counts.get("COMPRA", 0)
            g_color = "#00FF00" if buy_pct > 70 else ("#FF0000" if buy_pct < 30 else "#FFD700")

            fig_gauge = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = buy_pct,
                number = {'suffix': "%", 'font': {'color': g_color, 'size': 40}},
                gauge = {
                    'axis': {'range': [0, 100], 'tickcolor': "#FFFFFF"},
                    'bar': {'color': g_color},
                    'bgcolor': "#112240",
                    'steps': [
                        {'range': [0, 30], 'color': "rgba(255, 0, 0, 0.2)"},
                        {'range': [70, 100], 'color': "rgba(0, 255, 0, 0.2)"}
                    ]
                }
            ))
            fig_gauge.update_layout(height=200, margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor='rgba(0,0,0,0)', font={'color': "#FFFFFF"})
            st.plotly_chart(fig_gauge, use_container_width=True)

        tab_data, tab_heat = st.tabs(["📝 REGISTROS E EXPORTAÇÃO", "🗺️ MAPA DE RATIONALE"])

        with tab_data:
            st.markdown("### Histórico de Notícias (Captura em Tempo Real)")
            st.download_button("Downloaad dos dados para Excel", df.to_csv(index=False).encode('utf-8'), "oil_data_legible.csv", "text/csv")
            # Exibindo a tabela com contraste (Fundo branco forçado pelo CSS)
            st.dataframe(df.sort_values('Timestamp', ascending=False), use_container_width=True)

        with tab_heat:
            st.markdown("### Mapa de Calor de Sentimento")
            heat_df = df.groupby(['Viés', 'Categoria', 'Rationale']).agg({'Manchete': 'count', 'Alpha': 'sum'}).reset_index()
            fig_tree = px.treemap(
                heat_df, 
                path=[px.Constant("Oil Sentiment"), 'Viés', 'Categoria', 'Rationale'], 
                values='Manchete', 
                color='Alpha', 
                color_continuous_scale=['#FF3131', '#112240', '#39FF14']
            )
            fig_tree.update_layout(height=500, margin=dict(t=30, l=10, r=10, b=10), paper_bgcolor='rgba(0,0,0,0)', font={'color': "#FFFFFF"})
            st.plotly_chart(fig_tree, use_container_width=True)

    else:
        st.info("Inicializando conexão com os terminais RSS...")

if __name__ == "__main__":
    main()
