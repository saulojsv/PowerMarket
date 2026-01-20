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
DB_FILE = "Oil_Station_V51_Master.csv"
BRAIN_FILE = "Market_Brain_V51.csv"
st_autorefresh(interval=60000, key="v51_refresh")

RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "gCaptain": "https://gcaptain.com/feed/"
}

# --- 2. SEUS 22 DADOS LEXICON ORIGINAIS ---
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

# --- 3. MOTOR DE INTELIGÊNCIA ADAPTATIVA ---
def get_auto_category(word):
    w = word.lower()
    if any(x in w for x in ["opec", "saudi", "cut"]): return "Política Energética"
    if any(x in w for x in ["war", "strike", "attack"]): return "Risco Geopolítico"
    if any(x in w for x in ["fed", "rate", "inflation"]): return "Macro & Financeiro"
    return "Driver Emergente"

def update_brain(word, title):
    if not os.path.exists(BRAIN_FILE):
        df_brain = pd.DataFrame(columns=['Termo', 'Contagem', 'Peso_Alpha', 'Categoria', 'Ultima_Vez'])
    else:
        df_brain = pd.read_csv(BRAIN_FILE)
    
    if word in df_brain['Termo'].values:
        idx = df_brain['Termo'] == word
        count = df_brain.loc[idx, 'Contagem'].values[0] + 1
        new_weight = np.clip(2.0 + (count * 0.1), 1.0, 9.5)
        df_brain.loc[idx, ['Contagem', 'Peso_Alpha', 'Ultima_Vez']] = [count, new_weight, datetime.now().strftime("%H:%M")]
    else:
        new_row = {'Termo': word, 'Contagem': 1, 'Peso_Alpha': 2.0, 'Categoria': get_auto_category(word), 'Ultima_Vez': datetime.now().strftime("%H:%M")}
        df_brain = pd.concat([df_brain, pd.DataFrame([new_row])], ignore_index=True)
    
    df_brain.to_csv(BRAIN_FILE, index=False)
    return df_brain[df_brain['Termo'] == word].iloc[0]

# --- 4. MOTOR DE FUSÃO (MULTIVARIÁVEL) ---
def analyze_reality(title):
    t_lower = title.lower()
    weights = []
    found_elements = []
    
    # 1. Checa todos os Lexicons (Não para no primeiro)
    for pat, par in LEXICON_TOPICS.items():
        if re.search(pat, t_lower):
            weights.append(par[0] * par[1])
            found_elements.append(f"Lexicon({re.search(pat, t_lower).group()})")
            
    # 2. Checa Cérebro IA (Palavras Aprendidas)
    if os.path.exists(BRAIN_FILE):
        brain = pd.read_csv(BRAIN_FILE)
        graduados = brain[brain['Contagem'] >= 30]
        for _, row in graduados.iterrows():
            if row['Termo'].lower() in t_lower:
                bias = 1.0 if any(x in t_lower for x in ["surge", "spike", "up"]) else -1.0
                weights.append(row['Peso_Alpha'] * bias)
                found_elements.append(f"IA({row['Termo']})")

    # 3. Aprendizado de Novas Palavras (Regra dos 30)
    if any(x in t_lower for x in ["surge", "plunge", "spike", "drop"]):
        words = re.findall(r'\b[a-zA-Z]{7,}\b', t_lower)
        for nw in words: update_brain(nw, title)

    if not weights: return None
    
    # Cálculo Final
    avg_alpha = sum(weights) / len(weights)
    prob = 1 / (1 + np.exp(-0.12 * abs(avg_alpha)))
    if any(x in t_lower for x in ["may", "could", "potential", "rumor"]): prob *= 0.75
    
    side = "COMPRA" if avg_alpha > 0 else "VENDA"
    interpretation = f"Fusão de {len(found_elements)} fatores: {', '.join(found_elements)}. Média Alpha: {avg_alpha:.2f}."
    
    return f"{np.clip(prob, 0.52, 0.95)*100:.1f}% {side}", avg_alpha, interpretation

# --- 5. MONITOR RSS ---
def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    analysis = analyze_reality(entry.title)
                    if analysis:
                        sent, alpha, interp = analysis
                        data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Sent": sent, "Interpretation": interp, "Alpha": alpha, "Link": entry.link, "TS": datetime.now().isoformat()}
                        pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
            except: pass
        time.sleep(60)

# --- 6. UI ---
def main():
    st.set_page_config(page_title="QUANT STATION V51", layout="wide")
    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    st.markdown("""<style>
        .stApp { background-color: #050C1A !important; }
        .decision-box { padding: 25px; border-radius: 15px; text-align: center; font-family: 'Arial Black'; font-size: 35px; border: 3px solid; text-transform: uppercase; }
        .stDataFrame td { font-size: 13px !important; color: #64FFDA !important; }
    </style>""", unsafe_allow_html=True)

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        
        c1, c2 = st.columns([1.5, 1.5])
        with c1:
            st.title("ENGINE TEST")
            avg_a = df.head(30)['Alpha'].mean()
            val = np.clip(50 + (avg_a * 4.5), 0, 100)
            fig = go.Figure(go.Indicator(mode="gauge+number", value=val, number={'suffix': "%", 'font': {'color': '#64FFDA'}},
                                         gauge={'axis': {'range': [0, 100]}, 'bar': {'color': '#64FFDA'}}))
            fig.update_layout(height=220, margin=dict(t=0,b=0), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            if val >= 70: st.markdown('<div class="decision-box" style="color:#39FF14; border-color:#39FF14;">FORTE COMPRA</div>', unsafe_allow_html=True)
            elif val <= 30: st.markdown('<div class="decision-box" style="color:#FF4B4B; border-color:#FF4B4B;">FORTE VENDA</div>', unsafe_allow_html=True)
            else: st.markdown('<div class="decision-box" style="color:#E0E0E0; border-color:#E0E0E0;">AGUARDAR</div>', unsafe_allow_html=True)

        t1, t2, t3 = st.tabs(["FLUXO REALITY", "HEATMAP", "CÉREBRO ADAPTATIVO"])
        with t1:
            st.dataframe(df[['Hora', 'Manchete', 'Sent', 'Interpretation', 'Link']].head(100), 
                         column_config={"Link": st.column_config.LinkColumn("Notícia")}, width='stretch')
        with t2:
            st.plotly_chart(px.treemap(df.head(100), path=['Fonte'], values='Alpha', color='Alpha', color_continuous_scale='RdYlGn'), use_container_width=True)
        with t3:
            if os.path.exists(BRAIN_FILE):
                st.dataframe(pd.read_csv(BRAIN_FILE).sort_values('Contagem', ascending=False), 
                             column_config={"Contagem": st.column_config.ProgressColumn("Amostras (30x)", min_value=0, max_value=30)}, width='stretch')

if __name__ == "__main__": main()
