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

# --- 1. CONFIGURAÇÕES ---
DB_FILE = "Oil_Station_V40_Master.csv"
st_autorefresh(interval=60000, key="v40_refresh")

# --- 2. TERMINAIS RSS (SITES) ---
RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "gCaptain": "https://gcaptain.com/feed/"
}

# --- 3. SEUS 22 LEXICONS (CÉREBRO) ---
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

# --- 4. MOTOR DE HONESTIDADE CONTEXTUAL ---
CONTEXT_RULES = {"BULL": ["cut", "surge", "war", "sanction"], "BEAR": ["increase", "plunge", "peace", "glut"]}

def analyze_honest_bias(title, base_alpha):
    t_lower = title.lower()
    score = base_alpha
    for w in CONTEXT_RULES["BULL"]:
        if w in t_lower: score += 1.5
    for w in CONTEXT_RULES["BEAR"]:
        if w in t_lower: score -= 1.5
    if any(x in t_lower for x in ["may", "could", "potential"]): score *= 0.6
    prob = 1 / (1 + np.exp(-0.35 * abs(score)))
    side = "COMPRA" if score > 0 else "VENDA"
    return f"{np.clip(prob, 0.51, 0.97)*100:.1f}% {side}", score

# --- 5. MONITOR DE NOTÍCIAS (CORRIGIDO) ---
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
                            sent, f_alpha = analyze_honest_bias(entry.title, par[0] * par[1])
                            data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Sent": sent, "Cat": par[2], "Link": entry.link, "Alpha": f_alpha, "TS": datetime.now().isoformat(), "Tipo": "Lexicon", "Termo": re.search(pat, t_lower).group()}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
                            found = True
                    if not found and any(x in t_lower for x in ["surge", "plunge", "spike"]):
                        words = re.findall(r'\b[a-zA-Z]{7,}\b', t_lower)
                        for nw in words:
                            sent, f_alpha = analyze_honest_bias(entry.title, 0)
                            if abs(f_alpha) > 1.0:
                                data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Sent": sent, "Cat": f"Validação: {nw}", "Link": entry.link, "Alpha": f_alpha, "TS": datetime.now().isoformat(), "Tipo": "Novo", "Termo": nw}
                                pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

# --- 6. UI PRINCIPAL ---
def main():
    st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide")
    st.markdown("""<style>
        .stApp, [data-testid="stSidebar"] { background-color: #050C1A !important; }
        * { color: #E0E0E0 !important; }
        div[data-baseweb="input"], input { background-color: #0D1B2A !important; color: #64FFDA !important; border: 1px solid #1B2B48 !important; }
        div[data-testid="stDataFrame"] td { background-color: #050C1A !important; font-weight: bold !important; border-bottom: 1px solid #1B2B48 !important; }
        .status-on { color: #39FF14 !important; font-weight: bold; }
    </style>""", unsafe_allow_html=True)

    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    with st.sidebar:
        st.header("📡 SITES ONLINE")
        for s in RSS_SOURCES.keys(): st.markdown(f"• {s}: <span class='status-on'>ATIVO</span>", unsafe_allow_html=True)
        st.divider()
        st.header("LEXICON ATIVO")
        for k, v in LEXICON_TOPICS.items(): st.caption(f"• {v[2]}")

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        
        # --- PREVENÇÃO DE KEYERROR ---
        if 'Termo' not in df.columns: df['Termo'] = "N/A"
        if 'Tipo' not in df.columns: df['Tipo'] = "Lexicon"

        for cat_label in ["NARRATIVA BULLISH", "NARRATIVA BEARISH"]:
            target = "COMPRA" if "BULLISH" in cat_label else "VENDA"
            if not df.empty:
                # Lógica protegida contra colunas inexistentes
                mask = (df['Tipo'] == 'Novo') & (df['Sent'].str.contains(target, na=False))
                termos_novos = df[mask]['Termo'].unique()
                if len(termos_novos) >= 6:
                    df.loc[mask, 'Cat'] = cat_label

        c1, c2 = st.columns([3, 1])
        with c1:
            st.title(" MONITORIZAR XTIUSD")
            search = st.text_input("FILTRAR FLUXO", "")
        with c2:
            avg_a = df['Alpha'].mean() if 'Alpha' in df.columns else 0
            prob = 100 / (1 + np.exp(-0.15 * avg_a))
            st.metric("FORÇA DO FLUXO", f"{prob:.1f}%")

        tab_fluxo, tab_heat = st.tabs(["FLUXO COM LINKS", "HEATMAP"])
        with tab_fluxo:
            if search: df = df[df['Manchete'].str.contains(search, case=False, na=False)]
            cols = [c for c in ['Hora', 'Fonte', 'Manchete', 'Sent', 'Cat', 'Link'] if c in df.columns]
            st.dataframe(df[cols].head(60), column_config={"Link": st.column_config.LinkColumn("Link")}, width='stretch')
        with tab_heat:
            if not df.empty:
                cat_df = df['Cat'].value_counts(normalize=True).reset_index()
                st.plotly_chart(px.treemap(cat_df, path=['Cat'], values='proportion', color_discrete_sequence=['#0D1B2A', '#64FFDA']), width='stretch')

if __name__ == "__main__": main()
