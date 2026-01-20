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

# --- CONFIGURAÇÃO E FONTES ORIGINAIS ---
DB_FILE = "Oil_Station_V5_Rationale.xlsx"
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

LEXICON_MODIFIERS = {
    r"unexpected|surprise|shock|massive|surge|soar|jump|skyrocket": 1.5,
    r"plunge|crash|collapse|freefall|dump": 1.5,
    r"breakout|critical|pivotal|major": 1.25,
    r"rumor|unconfirmed|reportedly|maybe|potential|possible|could": 0.5,
    r"muted|flat|steady|unchanged|considers|weighs": 0.6
}

# --- MOTOR DE ANÁLISE ---
def analyze_news(title):
    title_lower = title.lower()
    base_alpha, direction, category, multiplier, highlight = 0, 0, "Geral", 1.0, "N/A"
    
    # Detecção de Tópico (Rationale)
    for pattern, params in LEXICON_TOPICS.items():
        match = re.search(pattern, title_lower)
        if match:
            base_alpha, direction, category = params[0], params[1], params[2]
            highlight = match.group()
            break
    
    if direction == 0: return None # Ignora se não houver match

    # Detecção de Modificador
    for pattern, mod_val in LEXICON_MODIFIERS.items():
        if re.search(pattern, title_lower):
            multiplier = mod_val
            break
            
    alpha = base_alpha * direction * multiplier
    return {
        "Alpha": alpha,
        "Categoria": category,
        "Rationale": f"{category} ({'Bullish' if direction > 0 else 'Bearish'})",
        "Palavra_Chave": highlight,
        "Viés": "COMPRA" if direction > 0 else "VENDA"
    }

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
                for entry in feed.entries[:10]:
                    analysis = analyze_news(entry.title)
                    if analysis:
                        save_data({
                            "Timestamp": datetime.now().isoformat(),
                            "Hora": datetime.now().strftime("%H:%M:%S"),
                            "Fonte": source,
                            "Manchete": entry.title,
                            "Categoria": analysis["Categoria"],
                            "Rationale": analysis["Rationale"],
                            "Destaque": analysis["Palavra_Chave"],
                            "Alpha": analysis["Alpha"],
                            "Viés": analysis["Viés"]
                        })
            except: pass
        time.sleep(60)

# --- DASHBOARD ---
def main():
    st.set_page_config(page_title="QUANT STATION PRO V5", layout="wide")
    
    st.markdown("""<style>
        .stApp { background-color: #0E1117; color: #E0E0E0; }
        .stMetric { background-color: #161B22; border: 1px solid #30363D; padding: 10px; border-radius: 8px; }
    </style>""", unsafe_allow_html=True)

    if 'monitor_active' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    st.title("OIL ANALYTICS: CLASSIFICAÇÃO DE MOTIVOS")

    if os.path.exists(DB_FILE):
        df = pd.read_excel(DB_FILE)
        
        tab_dados, tab_analise = st.tabs([" DATA STATION", " RATIONALE HEATMAP"])

        with tab_dados:
            c1, c2, c3 = st.columns([1,1,1])
            net_alpha = df['Alpha'].sum()
            c1.metric("Net Alpha", f"{net_alpha:.2f}")
            
            # Cálculo de Percentual Recorrente
            vies_counts = df['Viés'].value_counts(normalize=True) * 100
            buy_pct = vies_counts.get("COMPRA", 0)
            c2.metric("Dominância de Compra", f"{buy_pct:.1f}%")
            
            # Download Excel
            st.download_button(" Exportar para Excel", df.to_csv(index=False).encode('utf-8'), "oil_rationale_data.csv", "text/csv")
            
            st.subheader("Registros Processados")
            st.dataframe(df.sort_values('Timestamp', ascending=False), use_container_width=True)

        with tab_analise:
            st.subheader("Análise de Frequência de Rationale")
            
            # Preparação do Heatmap focado em recorrência
            heat_df = df.groupby(['Viés', 'Categoria', 'Rationale']).agg({
                'Manchete': 'count',
                'Alpha': 'sum'
            }).rename(columns={'Manchete': 'Frequência', 'Alpha': 'Impacto_Total'}).reset_index()

            fig = px.treemap(
                heat_df,
                path=[px.Constant("Oil Market"), 'Viés', 'Categoria', 'Rationale'],
                values='Frequência',
                color='Impacto_Total',
                color_continuous_scale=['#FF0000', '#1B1E23', '#00FF00'],
                color_continuous_midpoint=0
            )
            fig.update_layout(height=550, margin=dict(t=30, l=10, r=10, b=10), paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
            
            # Painel de Palavras Destaque
            st.divider()
            st.subheader("Palavras-Chave de Maior Recorrência")
            c_key, c_info = st.columns([1, 2])
            with c_key:
                st.table(df['Destaque'].value_counts().head(12))
            with c_info:
                st.info("O tamanho dos blocos no Heatmap acima representa as categorias mais frequentes. Use isso para identificar qual narrativa (Rationale) está sustentando o preço atual.")

    else:
        st.info("Aguardando novas notícias nos feeds RSS...")

if __name__ == "__main__":
    main()
