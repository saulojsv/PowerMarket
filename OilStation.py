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

# --- CONFIGURAÇÃO E REFRESH ---
DB_FILE = "Oil_Station_V30.csv"
st_autorefresh(interval=60000, key="v30_refresh") # Atualiza a cada 1 min

# --- 1. OS 6 TERMINAIS RSS (SITES) ---
RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "gCaptain": "https://gcaptain.com/feed/"
}

# --- 2. OS 22 DADOS LEXICON (O CÉREBRO) ---
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

# --- MOTOR DE MONITORAMENTO E APRENDIZADO ---
def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    t_lower = entry.title.lower()
                    found = False
                    # Validação pelo Lexicon
                    for pattern, params in LEXICON_TOPICS.items():
                        if re.search(pattern, t_lower):
                            alpha = params[0] * params[1]
                            prob = 1 / (1 + np.exp(-0.5 * alpha))
                            sent = f"{prob*100:.1f}% COMPRA" if prob > 0.5 else f"{(1-prob)*100:.1f}% VENDA"
                            data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Cat": params[2], "Sent": sent, "Alpha": alpha, "TS": datetime.now().isoformat(), "Tipo": "Lexicon", "Termo": re.search(pattern, t_lower).group()}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
                            found = True
                    # Validação por Aprendizado (Rigoroso)
                    if not found:
                        words = re.findall(r'\b[a-zA-Z]{6,}\b', t_lower)
                        for nw in words:
                            # Só adiciona se houver sinal direcional (RIGOR)
                            if any(x in t_lower for x in ["surge", "jump", "plunge", "drop", "spike"]):
                                bias = 1.0 if any(x in t_lower for x in ["surge", "jump", "spike"]) else -1.0
                                data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Cat": f"Validação: {nw}", "Sent": "Calculando...", "Alpha": 2.0 * bias, "TS": datetime.now().isoformat(), "Tipo": "Novo", "Termo": nw}
                                pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

# --- UI E CSS ---
def main():
    st.set_page_config(page_title="V30 - FULL STACK QUANT", layout="wide")
    st.markdown("""<style>
        .stApp, [data-testid="stSidebar"] { background-color: #0A192F !important; }
        * { color: #FFFFFF !important; }
        div[data-baseweb="input"] { background-color: #112240 !important; border: 1px solid #64FFDA !important; }
        input { color: #64FFDA !important; }
        div[data-testid="stDataFrame"] td { font-weight: bold !important; border-bottom: 1px solid #1B2B48 !important; }
        .status-on { color: #39FF14 !important; font-weight: bold; }
    </style>""", unsafe_allow_html=True)

    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    # SIDEBAR: SITES E LISTA DOS 22 LEXICONS
    with st.sidebar:
        st.header("📡 SITES ONLINE")
        for s in RSS_SOURCES.keys(): st.markdown(f"• {s}: <span class='status-on'>ATIVO</span>", unsafe_allow_html=True)
        st.divider()
        st.header("🧠 22 DADOS LEXICON")
        for k, v in LEXICON_TOPICS.items():
            st.caption(f"• {v[2]} (α: {v[0]})")

    # DASHBOARD
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        
        # Consolidação de Categorias Novas (6 termos -> Agrupa)
        for bias, label in zip([1.0, -1.0], ["NARRATIVA BULLISH", "NARRATIVA BEARISH"]):
            novos_termos = df[(df['Tipo'] == 'Novo') & (df['Alpha'] * bias > 0)]['Termo'].unique()
            if len(novos_termos) >= 6:
                df.loc[(df['Tipo'] == 'Novo') & (df['Alpha'] * bias > 0), 'Cat'] = label
                df.loc[(df['Tipo'] == 'Novo') & (df['Alpha'] * bias > 0), 'Sent'] = "90.0% COMPRA" if bias > 0 else "90.0% VENDA"

        # VELOCÍMETRO
        net_alpha = df[df['Sent'] != "Calculando..."]['Alpha'].sum()
        prob = 100 / (1 + np.exp(-0.08 * net_alpha))
        c1, c2 = st.columns([2, 1])
        with c1:
            st.title("🛢️ QUANT TERMINAL V30")
            search_query = st.text_input("🔍 FILTRAR FLUXO (Navy Box)", "")
        with c2:
            fig = go.Figure(go.Indicator(mode="gauge+number", value=prob, number={'suffix': "%"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#64FFDA"}}))
            fig.update_layout(height=150, margin=dict(t=0, b=0), paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

        tab_fluxo, tab_heat = st.tabs(["📝 FLUXO ORGANIZADO", "🗺️ HEATMAP POR CATEGORIA"])
        
        with tab_fluxo:
            if search_query:
                df = df[df['Manchete'].str.contains(search_query, case=False) | df['Cat'].str.contains(search_query, case=False)]
            # Separação: Percentuais primeiro, "Calculando" depois
            res = pd.concat([df[df['Sent'] != "Calculando..."], df[df['Sent'] == "Calculando..."]])
            st.dataframe(res[['Hora', 'Fonte', 'Manchete', 'Sent', 'Cat']].head(60), use_container_width=True)

        with tab_heat:
            cat_df = df['Cat'].value_counts(normalize=True).reset_index()
            fig_tree = px.treemap(cat_df, path=['Cat'], values='proportion', color_discrete_sequence=['#112240', '#64FFDA'])
            st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("Conectando terminais...")

if __name__ == "__main__": main()
