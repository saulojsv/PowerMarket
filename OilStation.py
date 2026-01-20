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

# --- 1. CONFIGURAÇÕES E BANCO DE DADOS ---
DB_FILE = "Oil_Station_V46_Master.csv"
BRAIN_FILE = "Market_Brain_V46.csv"
st_autorefresh(interval=60000, key="v46_refresh")

# --- 2. TERMINAIS RSS ---
RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "gCaptain": "https://gcaptain.com/feed/"
}

# --- 3. LEXICON (22 ITENS) ---
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

# --- 4. MOTOR DE IA E CATEGORIZAÇÃO ---
def get_auto_category(word, title):
    t_lower = title.lower()
    if any(x in t_lower for x in ["opec", "saudi", "vienna"]): return "Política Energética"
    if any(x in t_lower for x in ["fed", "inflation", "rate"]): return "Macro & Financeiro"
    if any(x in t_lower for x in ["war", "strike", "missile"]): return "Risco Geopolítico"
    return "Driver de Mercado Emergente"

def update_brain(word, title, initial_bias=2.0):
    if not os.path.exists(BRAIN_FILE):
        df_brain = pd.DataFrame(columns=['Termo', 'Contagem', 'Peso_Alpha', 'Categoria', 'Ultima_Vez'])
    else:
        df_brain = pd.read_csv(BRAIN_FILE)
    cat = get_auto_category(word, title)
    if word in df_brain['Termo'].values:
        idx = df_brain['Termo'] == word
        count = df_brain.loc[idx, 'Contagem'].values[0] + 1
        new_weight = np.clip(initial_bias + (count * 0.1), 1.0, 9.5)
        df_brain.loc[idx, ['Contagem', 'Peso_Alpha', 'Ultima_Vez']] = [count, new_weight, datetime.now().strftime("%H:%M:%S")]
    else:
        df_brain = pd.concat([df_brain, pd.DataFrame([{'Termo': word, 'Contagem': 1, 'Peso_Alpha': initial_bias, 'Categoria': cat, 'Ultima_Vez': datetime.now().strftime("%H:%M:%S")}])], ignore_index=True)
    df_brain.to_csv(BRAIN_FILE, index=False)
    return df_brain[df_brain['Termo'] == word].iloc[0]

def calculate_realistic_sentiment(title, alpha):
    t_lower = title.lower()
    prob = 1 / (1 + np.exp(-0.12 * abs(alpha)))
    if any(x in t_lower for x in ["may", "could", "potential"]): prob *= 0.7
    side = "COMPRA" if alpha > 0 else "VENDA"
    return f"{np.clip(prob, 0.52, 0.91)*100:.1f}% {side}", alpha

# --- 5. MONITOR ---
def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    t_lower = entry.title.lower()
                    found = False
                    for pat, par in LEXICON_TOPICS.items():
                        if re.search(pat, t_lower):
                            sent, f_alpha = calculate_realistic_sentiment(entry.title, par[0] * par[1])
                            data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Sent": sent, "Cat": par[2], "Link": entry.link, "Alpha": f_alpha, "TS": datetime.now().isoformat(), "Tipo": "Lexicon"}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
                            found = True
                    if not found and any(x in t_lower for x in ["surge", "plunge", "spike", "drop"]):
                        words = re.findall(r'\b[a-zA-Z]{7,}\b', t_lower)
                        for nw in words:
                            brain_row = update_brain(nw, entry.title)
                            if brain_row['Contagem'] >= 30:
                                bias = 1.0 if any(x in t_lower for x in ["surge", "spike"]) else -1.0
                                sent, f_alpha = calculate_realistic_sentiment(entry.title, brain_row['Peso_Alpha'] * bias)
                                data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Sent": sent, "Cat": brain_row['Categoria'], "Link": entry.link, "Alpha": f_alpha, "TS": datetime.now().isoformat(), "Tipo": "Aprendido"}
                                pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

# --- 6. UI ---
def main():
    st.set_page_config(page_title="QUANT STATION V46", layout="wide")
    st.markdown("""<style>
        .stApp { background-color: #050C1A !important; }
        /* SIDEBAR DE ALTO CONTRASTE */
        [data-testid="stSidebar"] { background-color: #081225 !important; border-right: 1px solid #1B2B48; }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span { 
            color: #FFFFFF !important; font-weight: 800 !important; font-family: 'Arial Black', sans-serif;
        }
        .status-on { color: #39FF14 !important; font-weight: bold; text-shadow: 0px 0px 8px #39FF14; }
        .stDataFrame td { background-color: #050C1A !important; color: #64FFDA !important; font-weight: bold !important; }
    </style>""", unsafe_allow_html=True)

    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    with st.sidebar:
        st.header("CÉREBRO IA")
        if os.path.exists(BRAIN_FILE):
            b_df = pd.read_csv(BRAIN_FILE)
            st.metric("Termos em Análise", len(b_df))
            st.metric("Graduados (30x)", len(b_df[b_df['Contagem'] >= 30]))
        st.divider()
        st.header("📡 SITES ONLINE")
        for s in RSS_SOURCES.keys(): st.markdown(f"• {s}: <span class='status-on'>ATIVO</span>", unsafe_allow_html=True)

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        c1, c2 = st.columns([2, 1])
        with c1:
            st.title("🛢️ QUANT STATION V46")
            search = st.text_input("🔍 FILTRO DE FLUXO", "")
        with c2:
            recent_df = df.head(50)
            avg_a = recent_df['Alpha'].mean() if not recent_df.empty else 0
            gauge_val = np.clip(50 + (avg_a * 4.5), 0, 100)
            
            # Lógica de Nome Conforme Percentual
            if gauge_val >= 70: label, color = "FORTE COMPRA", "#39FF14"
            elif gauge_val <= 30: label, color = "FORTE VENDA", "#FF4B4B"
            else: label, color = "NEUTRO", "#E0E0E0"

            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=gauge_val,
                number={'suffix': "%", 'font': {'color': color, 'size': 55}},
                title={'text': label, 'font': {'size': 26, 'color': color, 'family': 'Arial Black'}},
                gauge={'axis': {'range': [0, 100]}, 'bar': {'color': color},
                       'steps': [{'range': [0, 30], 'color': "#3D0000"}, {'range': [70, 100], 'color': "#003D00"}]}
            ))
            fig.update_layout(height=220, margin=dict(t=40, b=0, l=20, r=20), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, use_container_width=True)

        tab_fluxo, tab_heat, tab_brain = st.tabs(["📝 FLUXO", "🗺️ HEATMAP", "🧠 DICIONÁRIO IA"])
        with tab_fluxo:
            if search: df = df[df['Manchete'].str.contains(search, case=False, na=False)]
            st.dataframe(df[['Hora', 'Fonte', 'Manchete', 'Sent', 'Cat', 'Link']].head(60), column_config={"Link": st.column_config.LinkColumn("Fonte")}, width='stretch')
        with tab_heat:
            st.plotly_chart(px.treemap(df['Cat'].value_counts().reset_index(), path=['Cat'], values='count', color_discrete_sequence=['#0D1B2A', '#64FFDA']), width='stretch')
        with tab_brain:
            if os.path.exists(BRAIN_FILE):
                st.dataframe(pd.read_csv(BRAIN_FILE).sort_values('Contagem', ascending=False), column_config={"Contagem": st.column_config.ProgressColumn("Progresso", min_value=0, max_value=30)}, width='stretch')

if __name__ == "__main__": main()
