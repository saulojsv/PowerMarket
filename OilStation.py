import sys
import warnings
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import re
from newspaper import Article
from google import genai
from streamlit_autorefresh import st_autorefresh

# --- AMBIENTE & REGRAS 2026 ---
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

st.set_page_config(page_title="XTI NEURAL | TERMINAL v11.7", layout="wide")
# Autorefresh geral da página
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS PERSONALIZADO ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; padding: 1rem 3rem; }
    [data-testid="stSidebar"] { display: none; } 
    .news-card-mini { 
        background-color: #0a0a0a; border: 1px solid #1a1a1a; 
        padding: 12px; margin-bottom: 8px; border-radius: 4px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .label-tag { font-weight: 800; font-size: 0.75rem; padding: 2px 8px; border-radius: 3px; }
    .BULLISH { color: #00FF41; border: 1px solid #00FF41; border-left: 4px solid #00FF41 !important; }
    .BEARISH { color: #FF3131; border: 1px solid #FF3131; border-left: 4px solid #FF3131 !important; }
    .NEUTRAL { color: #888; border: 1px solid #888; }
    .status-box { 
        border: 2px solid #00FF41; padding: 30px; text-align: center; 
        font-weight: 800; font-size: 3rem; background-color: #050505;
        font-family: 'JetBrains Mono';
    }
    .lexicon-chip {
        display: inline-block; background: #111; color: #00FF41;
        padding: 2px 10px; margin: 3px; border-radius: 5px; font-size: 0.8rem;
        border: 1px solid #00FF41; font-family: 'JetBrains Mono';
    }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = "gemini-1.5-flash"
        self.load_verified_data()

    def load_verified_data(self):
        self.bullish_keywords = {}
        self.bearish_keywords = {}
        self.oil_sources = ["https://oilprice.com", "https://www.reuters.com/business/energy/"]
        try:
            with open('verified_lexicons.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.bullish_keywords = data.get('bullish', {})
                self.bearish_keywords = data.get('bearish', {})
                if data.get('sites'): self.oil_sources = data.get('sites')
        except: pass

    def get_deep_analysis(self, text):
        if not self.client: return 0.0, "NEUTRAL", "IA OFFLINE", "NONE"
        try:
            contexto = list(self.bullish_keywords.keys()) + list(self.bearish_keywords.keys())
            prompt = (f"Analise WTI: '{text}'. Léxicos: {contexto}. Retorne: [SCORE: -1.0 a 1.0] [LABEL: Bullish, Bearish ou Neutral] [DEEP_READER: 1 frase] [NEW_TERM: 1 termo]")
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            score = float(re.findall(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", response.text)[0])
            label = re.findall(r"LABEL:\s*(\w+)", response.text)[0].upper()
            summary = response.text.split("DEEP_READER:")[-1].split("[NEW_TERM:")[0].strip()
            new_term = response.text.split("NEW_TERM:")[-1].replace("]", "").strip().upper()
            return score, label, summary, new_term
        except: return 0.0, "NEUTRAL", "Erro Neural", "NONE"

# --- CACHE DE NOTÍCIAS (Fontes Externas) ---
@st.cache_data(ttl=120)
def auto_scan(sources):
    collected = []
    for url in sources[:10]:
        try:
            a = Article(url); a.download(); a.parse()
            if len(a.title) > 10: collected.append(a.title)
        except: continue
    return collected

# --- CACHE DO YAHOO (WTI SPOT - 5 MINUTOS) ---
@st.cache_data(ttl=300)
def get_market_data():
    try:
        xti = yf.download("CL=F", period="1d", interval="1m", progress=False)
        if not xti.empty:
            price = xti['Close'].iloc[-1].values[0]
            return xti, price
    except: pass
    return pd.DataFrame(), 0.0

def main():
    engine = XTINeuralEngine()
    st.markdown("###XTI/USD TERMINAL")
    
    # Processamento de Notícias
    headlines = auto_scan(engine.oil_sources)
    analysis_results = []
    sugestoes_aprendizado = {"bullish": [], "bearish": []}

    for h in headlines:
        score, label, summary, new_term = engine.get_deep_analysis(h)
        analysis_results.append({"h": h, "s": score, "l": label, "sum": summary})
        if new_term != "NONE" and len(new_term) > 2:
            if label == "BULLISH" and new_term not in engine.bullish_keywords:
                sugestoes_aprendizado["bullish"].append(new_term)
            elif label == "BEARISH" and new_term not in engine.bearish_keywords:
                sugestoes_aprendizado["bearish"].append(new_term)

    tab_home, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 NEURAL INTELLIGENCE"])

    with tab_home:
        col_feed, col_market = st.columns([1.8, 1])
        with col_feed:
            st.write("🛰️ **LIVE RESUME FEED**")
            for item in analysis_results:
                st.markdown(f'<div class="news-card-mini {item["l"]}"><span style="color:white; font-weight:500;">{item["h"][:110]}...</span><span class="label-tag {item["l"]}">{item["l"]}</span></div>', unsafe_allow_html=True)

        with col_market:
            # Busca dados do mercado com cache de 5min
            xti_data, spot_price = get_market_data()
            
            avg_score = np.mean([x['s'] for x in analysis_results]) if analysis_results else 0.0
            veredito = "BUY" if avg_score > 0.15 else "SELL" if avg_score < -0.15 else "HOLD"
            v_color = "#00FF41" if veredito == "BUY" else "#FF3131" if veredito == "SELL" else "#FFFF00"
            
            st.markdown(f'<div class="status-box" style="border-color:{v_color}; color:{v_color};">{veredito}</div>', unsafe_allow_html=True)
            st.metric("WTI SPOT (5m Cache)", f"${spot_price:.2f}")
            
            if not xti_data.empty:
                fig = go.Figure(go.Scatter(y=xti_data['Close'].values.flatten(), line=dict(color='#00FF41', width=3)))
                fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(visible=False), yaxis=dict(side="right"))
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    with tab_neural:
        st.write("### 🧠 DEEP READER & KNOWLEDGE AUDIT")
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write(f"Bullish ({len(engine.bullish_keywords)}):")
            st.markdown(" ".join([f'<span class="lexicon-chip">{k}</span>' for k in engine.bullish_keywords.keys()]) if engine.bullish_keywords else "Nenhum", unsafe_allow_html=True)
            st.write(f"Bearish ({len(engine.bearish_keywords)}):")
            st.markdown(" ".join([f'<span class="lexicon-chip" style="border-color:#FF3131; color:#FF3131;">{k}</span>' for k in engine.bearish_keywords.keys()]) if engine.bearish_keywords else "Nenhum", unsafe_allow_html=True)
        with c2:
            for res in analysis_results:
                with st.expander(f"DECISÃO: {res['l']} | SCORE: {res['s']:+.2f}"):
                    st.write(f"**Manchete:** {res['h']}")
                    st.success(f"**Conclusão IA:** {res['sum']}")

if __name__ == "__main__":
    main()
