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
DB_FILE = "Oil_Station_V49_Master.csv"
BRAIN_FILE = "Market_Brain_V49.csv"
st_autorefresh(interval=60000, key="v49_refresh")

# --- 2. TERMINAIS RSS ---
RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "gCaptain": "https://gcaptain.com/feed/"
}

# --- 3. SEUS 22 DADOS LEXICON ---
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

# --- 4. MOTOR ANALÍTICO (INTERPRETATION) ---
def get_interpretation(title, alpha, pattern, type_news):
    t_lower = title.lower()
    direcao = "BULLISH (Alta)" if alpha > 0 else "BEARISH (Baixa)"
    impacto_base = abs(alpha)
    
    # Resumo da decisão
    resumo = f"[{type_news}] '{pattern}' indica {direcao}. "
    
    # Lógica de Intensidade
    if impacto_base >= 9: resumo += "Impacto Crítico na oferta global. "
    elif impacto_base >= 7: resumo += "Impacto Moderado. "
    else: resumo += "Driver Secundário. "
    
    # Lógica de Incerteza (Probabilidade)
    if any(x in t_lower for x in ["may", "could", "potential", "rumor", "possible"]):
        resumo += "Cálculo reduzido em 25% por incerteza verbal."
    else:
        resumo += "Confiança nominal mantida (Fato Concretizado)."
        
    return resumo

def calculate_logic(title, alpha, pattern, type_news):
    t_lower = title.lower()
    # Sigmoide para conversão em %
    prob = 1 / (1 + np.exp(-0.12 * abs(alpha)))
    
    if any(x in t_lower for x in ["may", "could", "potential", "rumor"]):
        prob *= 0.75 # Penalidade por incerteza
    
    side = "COMPRA" if alpha > 0 else "VENDA"
    interpretation = get_interpretation(title, alpha, pattern, type_news)
    
    return f"{np.clip(prob, 0.52, 0.91)*100:.1f}% {side}", alpha, interpretation

# --- 5. MONITOR DE NOTÍCIAS ---
def news_monitor():
    while True:
        for source, url in RSS_SOURCES.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    t_lower = entry.title.lower()
                    found = False
                    for pat, par in LEXICON_TOPICS.items():
                        match = re.search(pat, t_lower)
                        if match:
                            sent, f_alpha, interp = calculate_logic(entry.title, par[0] * par[1], match.group(), "LEXICON")
                            data = {"Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title, "Sent": sent, "Interpretation": interp, "Alpha": f_alpha, "TS": datetime.now().isoformat()}
                            pd.DataFrame([data]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
                            found = True
                            break
                    # Lógica para termos aprendidos (IA Evolutiva)
                    if not found and any(x in t_lower for x in ["surge", "plunge", "spike"]):
                        words = re.findall(r'\b[a-zA-Z]{7,}\b', t_lower)
                        # ... lógica de update_brain simplificada para o exemplo ...
            except: pass
        time.sleep(60)

# --- 6. INTERFACE STREAMLIT ---
def main():
    st.set_page_config(page_title="QUANT STATION V49", layout="wide")
    
    st.markdown("""<style>
        .stApp { background-color: #050C1A !important; }
        .decision-badge { padding: 15px; border-radius: 8px; text-align: center; font-family: 'Arial Black'; font-size: 24px; margin-bottom: 20px; border: 2px solid; }
        .stDataFrame td { background-color: #050C1A !important; color: #64FFDA !important; font-weight: bold !important; }
    </style>""", unsafe_allow_html=True)

    if 'monitor' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor'] = True

    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE).drop_duplicates(subset=['Manchete']).sort_values('TS', ascending=False)
        
        c1, c2 = st.columns([1.5, 1.5])
        with c1:
            st.title("QUANT V49")
            # Velocímetro simplificado
            avg_a = df.head(50)['Alpha'].mean() if not df.empty else 0
            val = np.clip(50 + (avg_a * 4.5), 0, 100)
            fig = go.Figure(go.Indicator(mode="gauge+number", value=val, number={'suffix': "%", 'font': {'color': '#64FFDA'}},
                gauge={'axis': {'range': [0, 100]}, 'bar': {'color': '#64FFDA'}}))
            fig.update_layout(height=180, margin=dict(t=0,b=0), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.write("RESUMO DO SENTIMENTO GLOBAL")
            if val >= 70: st.markdown('<div class="decision-badge" style="color: #39FF14; border-color: #39FF14; background: rgba(57,255,20,0.1)">FORTE COMPRA</div>', unsafe_allow_html=True)
            elif val <= 30: st.markdown('<div class="decision-badge" style="color: #FF4B4B; border-color: #FF4B4B; background: rgba(255,75,75,0.1)">FORTE VENDA</div>', unsafe_allow_html=True)
            else: st.markdown('<div class="decision-badge" style="color: #E0E0E0; border-color: #E0E0E0; background: rgba(224,224,224,0.1)">NEUTRO</div>', unsafe_allow_html=True)

        st.subheader("FLUXO ADAPTATIVO COM INTERPRETAÇÃO")
        # Coluna Interpretation adicionada ao dataframe principal
        st.dataframe(df[['Hora', 'Manchete', 'Sent', 'Interpretation']].head(100), width='stretch')

if __name__ == "__main__": main()
