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
from streamlit_autorefresh import st_autorefresh # Necessário para atualização automática

# --- DATABASE ---
DB_FILE = "Oil_Station_V26.csv"

# Atualização automática a cada 60.000ms (1 minuto)
st_autorefresh(interval=60000, key="datarefresh")

RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "gCaptain": "https://gcaptain.com/feed/"
}

# 22 DADOS LEXICON ORIGINAIS
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

# DICIONÁRIO DE RIGOR (Para novos termos)
POLARITY_SIGNALS = {
    "bullish": ["surge", "jump", "spike", "tighten", "deficit", "up", "climb"],
    "bearish": ["plunge", "drop", "slump", "glut", "surplus", "down", "fall"]
}

def analyze_new_term_bias(title):
    t_lower = title.lower()
    for word in POLARITY_SIGNALS["bullish"]:
        if word in t_lower: return 1.0 # Positivo
    for word in POLARITY_SIGNALS["bearish"]:
        if word in t_lower: return -1.0 # Negativo
    return 0.0

def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    t_lower = entry.title.lower()
                    found = False
                    for pattern, params in LEXICON_TOPICS.items():
                        if re.search(pattern, t_lower):
                            alpha = params[0] * params[1]
                            prob = 1 / (1 + np.exp(-0.5 * alpha))
                            sent = f"{prob*100:.1f}% COMPRA" if prob > 0.5 else f"{(1-prob)*100:.1f}% VENDA"
                            data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Cat": params[2], "Sent": sent, "Alpha": alpha, "TS": datetime.now().isoformat(), "Tipo": "Lexicon"}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
                            found = True
                    if not found:
                        words = re.findall(r'\b[a-zA-Z]{6,}\b', t_lower)
                        for nw in words:
                            bias = analyze_new_term_bias(t_lower)
                            if bias != 0: # SÓ APRENDE SE HOUVER SINAL DE DIREÇÃO (RIGOR)
                                data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Cat": "Aprendizado", "Sent": "Calculando...", "Alpha": 2.0 * bias, "TS": datetime.now().isoformat(), "Tipo": "Novo"}
                                pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

def main():
    st.set_page_config(page_title="ANÁLISE DE NOTÍCIAS E TERMOS LÉXICOS", layout="wide")
    st.markdown("""<style>
        .stApp, [data-testid="stSidebar"] { background-color: #0A192F !important; }
        * { color: #FFFFFF !important; }
        div[data-testid="stDataFrame"] td { font-weight: bold !important; border-bottom: 1px solid #1B2B48 !important; font-size: 14px !important;}
        .status-on { color: #39FF14 !important; font-weight: bold; }
    </style>""", unsafe_allow_html=True)

    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    with st.sidebar:
        st.header("📡 TERMINAIS ONLINE")
        for s in RSS_SOURCES.keys(): st.markdown(f"• {s}: <span class='status-on'>ATIVO</span>", unsafe_allow_html=True)
        st.divider()
        st.markdown("### 🧠 TERMOS APRENDIDOS (RIGOROSOS)")
        if os.path.exists(DB_FILE):
            df_sidebar = pd.read_csv(DB_FILE)
            novos = df_sidebar[df_sidebar['Tipo'] == 'Novo']['Manchete'].unique()
            for n in novos[:5]: st.caption(f"⚡ {n[:30]}...")

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        
        # VELOCÍMETRO
        net_alpha = df['Alpha'].sum()
        prob_global = 100 / (1 + np.exp(-0.08 * net_alpha))
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.title(TERMINAL - XTIUSD")
            st.write(f"Sincronizado: {datetime.now().strftime('%H:%M:%S')} (Auto-refresh 60s)")
        with c2:
            fig = go.Figure(go.Indicator(mode="gauge+number", value=prob_global, number={'suffix': "%"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#64FFDA"}}))
            fig.update_layout(height=160, margin=dict(t=0, b=0), paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

        tab_fluxo, tab_mapa = st.tabs(["FLUXO DE NOTÍCIAS", "HEATMAP POR CATEGORIA"])
        
        with tab_fluxo:
            # TABELA CORRIGIDA: Agora exibe todas as colunas essenciais para sua leitura singular
            st.dataframe(df[['Hora', 'Fonte', 'Manchete', 'Sent', 'Cat']].head(50), use_container_width=True)

        with tab_mapa:
            cat_df = df['Cat'].value_counts(normalize=True).reset_index()
            fig_tree = px.treemap(cat_df, path=['Cat'], values='proportion', color_discrete_sequence=['#112240', '#64FFDA'])
            st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("Conectando terminais... Aguarde 60 segundos.")

if __name__ == "__main__": main()
