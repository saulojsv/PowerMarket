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

# --- CONFIGURAÇÃO DE ARQUIVO ---
DB_FILE = "Oil_Station_V25_Final.csv"

# --- TERMINAIS RSS ---
RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "gCaptain": "https://gcaptain.com/feed/"
}

# --- 22 DADOS LEXICON ORIGINAIS ---
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

# --- FUNÇÕES DE MOTOR ---
def discover_new_terms(title):
    words = re.findall(r'\b[a-zA-Z]{6,}\b', title.lower())
    lex_str = "|".join(LEXICON_TOPICS.keys()).lower()
    ignore = ['market', 'prices', 'energy', 'report', 'stocks', 'global', 'crude', 'oilprice']
    return [w for w in words if w not in lex_str and w not in ignore]

def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:15]:
                    t_lower = entry.title.lower()
                    found = False
                    for pattern, params in LEXICON_TOPICS.items():
                        if re.search(pattern, t_lower):
                            alpha = params[0] * params[1]
                            prob = 1 / (1 + np.exp(-0.5 * alpha))
                            sent = f"{prob*100:.1f}% COMPRA" if prob > 0.5 else f"{(1-prob)*100:.1f}% VENDA"
                            data = {"Hora": datetime.now().strftime("%H:%M:%S"), "Fonte": source, "Manchete": entry.title, "Cat": params[2], "Termo": re.search(pattern, t_lower).group(), "Sent": sent, "Alpha": alpha, "TS": datetime.now().isoformat(), "Tipo": "Consolidado"}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
                            found = True
                    if not found:
                        new_words = discover_new_terms(entry.title)
                        for nw in new_words:
                            data = {"Hora": datetime.now().strftime("%H:%M:%S"), "Fonte": source, "Manchete": entry.title, "Cat": "Aprendizado", "Termo": nw, "Sent": "Pendente", "Alpha": 0, "TS": datetime.now().isoformat(), "Tipo": "Descoberta"}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

# --- INTERFACE ---
def main():
    st.set_page_config(page_title="OIL STATION", layout="wide")
    
    st.markdown("""<style>
        .stApp, [data-testid="stSidebar"], .stSidebar { background-color: #0A192F !important; }
        * { color: #FFFFFF !important; }
        div[data-testid="stDataFrame"] div { background-color: #112240 !important; }
        div[data-testid="stDataFrame"] td { color: #FFFFFF !important; font-weight: bold !important; border-bottom: 1px solid #1B2B48 !important; }
        .status-on { color: #39FF14 !important; font-weight: bold; }
        .new-term { color: #64FFDA !important; font-size: 14px; font-weight: bold; }
    </style>""", unsafe_allow_html=True)

    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    # SIDEBAR: STATUS E APRENDIZADO
    with st.sidebar:
        st.header("📡 SITES ONLINE")
        for s in RSS_SOURCES.keys(): st.markdown(f"• {s}: <span class='status-on'>ONLINE</span>", unsafe_allow_html=True)
        st.divider()
        st.markdown("###  NOVOS TERMOS (CRIVO)")
        if os.path.exists(DB_FILE):
            raw_df = pd.read_csv(DB_FILE)
            discoveries = raw_df[raw_df['Tipo'] == 'Descoberta']
            counts = discoveries['Termo'].value_counts()
            sources = discoveries.groupby('Termo')['Fonte'].nunique()
            learned = 0
            for t, c in counts.items():
                if c > 3 or sources[t] > 1: # Crivo: >3 vezes ou >1 fonte
                    st.markdown(f"<span class='new-term'>⚡ {t.upper()}</span>", unsafe_allow_html=True)
                    learned += 1
            if learned == 0: st.caption("Buscando padrões relevantes...")
        st.divider()
        st.caption("Fundo: Navy | Texto: Branco Pure")

    # ÁREA PRINCIPAL
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        consolidated = df[df['Tipo'] == 'Consolidado']
        
        # 1. VELOCÍMETRO GLOBAL
        net_alpha = consolidated['Alpha'].sum()
        prob_global = 100 / (1 + np.exp(-0.08 * net_alpha))
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.title("OIL STATION")
            st.write(f"Análise Singular de Manchetes | {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        with c2:
            fig = go.Figure(go.Indicator(mode="gauge+number", value=prob_global, 
                number={'suffix': "%", 'font': {'color': "#FFFFFF"}},
                gauge={'axis': {'range': [0, 100], 'tickcolor': "white"}, 'bar': {'color': "#64FFDA"}}))
            fig.update_layout(height=180, margin=dict(t=0, b=0), paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

        # 2. ABAS DE VISUALIZAÇÃO
        tab_fluxo, tab_heat = st.tabs([" FLUXO SINGULAR", " MAPA CATEGORIAL"])
        
        with tab_fluxo:
            # Tabela com as informações cruciais para a foto
            st.dataframe(consolidated[['Hora', 'Fonte', 'Manchete', 'Sent', 'Cat']].head(40), use_container_width=True)

        with tab_heat:
            st.subheader("Market Share de Narrativas (%)")
            cat_df = consolidated['Cat'].value_counts(normalize=True).reset_index()
            cat_df.columns = ['Categoria', 'Share']
            cat_df['%'] = (cat_df['Share'] * 100).round(1).astype(str) + '%'
            
            fig_tree = px.treemap(cat_df, path=['Categoria'], values='Share', 
                                 color_discrete_sequence=['#112240', '#64FFDA', '#1B2B48'])
            fig_tree.update_traces(texttemplate="<b>%{label}</b><br>%{customdata[0]}", customdata=cat_df[['%']])
            fig_tree.update_layout(height=400, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("Inicializando conexão com os terminais RSS...")

if __name__ == "__main__": main()
