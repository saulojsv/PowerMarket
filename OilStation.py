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
from collections import Counter

# --- DATABASE ---
DB_FILE = "Oil_Station_V21.csv"

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

# --- MOTOR DE APRENDIZADO CRÍTICO ---
def discover_new_terms(title, source):
    # Palavras que não estão no Lexicon mas aparecem com frequência
    words = re.findall(r'\b[a-zA-Z]{5,}\b', title.lower()) # Apenas palavras > 5 letras
    valid_new = []
    lexicon_words = "|".join(LEXICON_TOPICS.keys()).lower()
    
    for word in words:
        if word not in lexicon_words and word not in ['energy', 'market', 'prices', 'crude']:
            valid_new.append(word)
    return valid_new

def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    t_lower = entry.title.lower()
                    # 1. Checa Lexicon Existente
                    found = False
                    for pattern, params in LEXICON_TOPICS.items():
                        match = re.search(pattern, t_lower)
                        if match:
                            alpha = params[0] * params[1]
                            prob = 1 / (1 + np.exp(-0.5 * alpha))
                            sent = f"{prob*100:.1f}% COMPRA" if prob > 0.5 else f"{(1-prob)*100:.1f}% VENDA"
                            data = {"Hora": datetime.now().strftime("%H:%M:%S"), "Fonte": source, "Manchete": entry.title[:100], "Categoria": params[2], "Termo": match.group(), "Sentimento": sent, "Alpha": alpha, "Timestamp": datetime.now().isoformat(), "Tipo": "Consolidado"}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
                            found = True
                    
                    # 2. Se não achou, tenta "Aprender" com Crivo Crítico
                    if not found:
                        new_words = discover_new_terms(entry.title, source)
                        for nw in new_words:
                            data = {"Hora": datetime.now().strftime("%H:%M:%S"), "Fonte": source, "Manchete": entry.title[:100], "Categoria": "Aprendizado", "Termo": nw, "Sentimento": "Analisando...", "Alpha": 0, "Timestamp": datetime.now().isoformat(), "Tipo": "Descoberta"}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

def main():
    st.set_page_config(page_title="V21 - CRITICAL LEARNING", layout="wide")
    
    st.markdown("""<style>
        .stApp, [data-testid="stSidebar"], .stSidebar { background-color: #0A192F !important; }
        * { color: #FFFFFF !important; }
        div[data-testid="stDataFrame"] div { background-color: #112240 !important; }
        .status-on { color: #39FF14 !important; font-weight: bold; }
        .new-term { color: #64FFDA !important; font-style: italic; }
    </style>""", unsafe_allow_html=True)

    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('Timestamp', ascending=False)
        
        # SIDEBAR COM APRENDIZADO CRÍTICO
        with st.sidebar:
            st.markdown("### 📡 SITES ONLINE")
            for s in RSS_SOURCES.keys():
                st.markdown(f"• {s}: <span class='status-on'>ON</span>", unsafe_allow_html=True)
            
            st.divider()
            st.markdown("### 🧠 TERMOS EM VALIDAÇÃO")
            # Crivo Crítico: Só mostra se aparecer em mais de 1 fonte ou mais de 3 vezes
            potential_terms = df[df['Tipo'] == 'Descoberta']
            term_counts = potential_terms['Termo'].value_counts()
            term_sources = potential_terms.groupby('Termo')['Fonte'].nunique()
            
            learned_list = []
            for term, count in term_counts.items():
                if count > 3 or term_sources[term] > 1:
                    learned_list.append(term)
                    st.markdown(f"<span class='new-term'>⚡ {term.upper()}</span>", unsafe_allow_html=True)
            
            if not learned_list: st.caption("Nenhum termo relevante detectado ainda.")

        # DASHBOARD CENTRAL
        net_alpha = df['Alpha'].sum()
        prob = 100 / (1 + np.exp(-0.08 * net_alpha))

        c1, c2 = st.columns([3, 1])
        with c1:
            st.title("🛢️ QUANT TERMINAL V21")
            st.write("Filtro Crítico de Aprendizado Ativo")
        with c2:
            st.metric("BIAS GLOBAL", f"{prob:.1f}%", f"{net_alpha:.2f} Alpha")

        st.subheader("📊 Narrativas por Categoria")
        cat_df = df[df['Tipo'] == 'Consolidado']['Categoria'].value_counts(normalize=True).reset_index()
        fig = px.treemap(cat_df, path=['Categoria'], values='proportion', color_discrete_sequence=['#112240', '#64FFDA'])
        fig.update_layout(height=200, paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=0, l=0, r=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📝 Fluxo de Notícias")
        st.dataframe(df[['Hora', 'Fonte', 'Manchete', 'Categoria', 'Termo', 'Sentimento']].head(30), use_container_width=True)

if __name__ == "__main__": main()
