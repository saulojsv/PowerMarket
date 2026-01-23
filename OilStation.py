import sys
import warnings
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import re
import requests
from bs4 import BeautifulSoup
import newspaper
from newspaper import Config
from google import genai
from streamlit_autorefresh import st_autorefresh

# --- REGRAS DE AMBIENTE ---
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

st.set_page_config(page_title="XTI NEURAL", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS DE ALTA PERFORMANCE ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; padding: 1rem 2rem; }
    .news-card-mini { 
        background-color: #0a0a0a; border: 1px solid #1a1a1a; 
        padding: 10px; margin-bottom: 6px; border-radius: 4px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .BULLISH { border-left: 5px solid #00FF41 !important; color: #00FF41; }
    .BEARISH { border-left: 5px solid #FF3131 !important; color: #FF3131; }
    .NEUTRAL { border-left: 5px solid #555 !important; color: #888; }
    .status-box { 
        border: 2px solid #00FF41; padding: 20px; text-align: center; 
        font-weight: 800; font-size: 2.5rem; background-color: #050505;
        font-family: 'JetBrains Mono';
    }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = "gemini-1.5-flash"

    def get_deep_analysis(self, title, content):
        if not self.client: return 0.0, "NEUTRAL", "IA OFFLINE"
        
        # PROMPT OTIMIZADO PARA EVITAR NEUTRALIDADE EXCESSIVA
        prompt = f"""
        ACT AS A WTI CRUDE OIL TRADER. Analyze the sentiment of this news for oil prices.
        
        CRITERIA:
        - BULLISH: Supply cuts, geopolitical tension in Middle East, high demand, weak dollar.
        - BEARISH: Increased production, high inventories, economic recession, strong dollar.
        
        TITLE: {title}
        CONTENT: {content[:2000]}
        
        RETURN EXACTLY THIS FORMAT:
        SCORE: (value from -1.0 to 1.0)
        LABEL: (BULLISH, BEARISH, or NEUTRAL)
        SUMMARY: (max 12 words)
        """
        try:
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            res_text = response.text.upper()
            
            score = float(re.search(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", res_text).group(1))
            label = re.search(r"LABEL:\s*(\w+)", res_text).group(1)
            summary = re.search(r"SUMMARY:\s*(.*)", res_text).group(1).strip()
            return score, label, summary
        except:
            return 0.0, "NEUTRAL", "Erro no processamento neural."

# --- SCANNER COM CACHE DE BACKGROUND (Simulado via TTL) ---
@st.cache_data(ttl=300) # O scan roda uma vez a cada 5 min e serve para todos
def background_scan():
    sources = [
        "https://oilprice.com", "https://www.worldoil.com/news/",
        "https://www.offshore-energy.biz/oil-and-gas/",
        "https://finance.yahoo.com/news/", "https://www.energyvoice.com/category/oil-and-gas/"
    ]
    collected = []
    keywords = ['oil', 'crude', 'wti', 'opec', 'inventory', 'production']
    config = Config()
    config.browser_user_agent = 'Mozilla/5.0'
    config.request_timeout = 10

    for site in sources:
        try:
            paper = newspaper.build(site, config=config, memoize_articles=False)
            for article in paper.articles[:5]:
                if any(kw in article.url.lower() for kw in keywords):
                    article.download()
                    article.parse()
                    if len(article.title) > 15:
                        collected.append({"title": article.title, "text": article.text, "url": article.url})
        except: continue
    return collected

def main():
    engine = XTINeuralEngine()
    st.markdown("### < XTI/USD NEURAL TERMINAL v12.3 // BACKGROUND SYNC >")

    # Execução do Scan (Usa cache se disponível)
    with st.spinner("Sincronizando rede neural..."):
        news_data = background_scan()

    analysis_results = []
    for item in news_data:
        # Analisa cada notícia (Também pode ser cacheado para economizar API)
        s, l, sum_ = engine.get_deep_analysis(item['title'], item['text'])
        analysis_results.append({"title": item['title'], "url": item['url'], "s": s, "l": l, "sum": sum_})

    tab_dash, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 NEURAL DATA"])

    with tab_dash:
        col_a, col_b = st.columns([1.8, 1])
        with col_a:
            st.write(f"🛰️ **FEED ATIVO ({len(analysis_results)} notícias)**")
            for res in analysis_results:
                st.markdown(f'''
                    <div class="news-card-mini {res['l']}">
                        <div style="font-size:0.85rem;">
                            <a href="{res['url']}" target="_blank" style="text-decoration:none; color:inherit;">🔗 {res['title'][:80]}...</a>
                        </div>
                        <div style="font-weight:bold; font-size:0.7rem;">{res['l']} ({res['s']})</div>
                    </div>
                ''', unsafe_allow_html=True)

        with col_b:
            # Cálculo de Mercado
            avg_score = np.mean([x['s'] for x in analysis_results]) if analysis_results else 0.0
            veredito = "BUY" if avg_score > 0.1 else "SELL" if avg_score < -0.1 else "HOLD"
            v_color = "#00FF41" if veredito == "BUY" else "#FF3131" if veredito == "SELL" else "#FFFF00"
            
            st.markdown(f'<div class="status-box" style="border-color:{v_color}; color:{v_color};">{veredito}</div>', unsafe_allow_html=True)
            
            # Gráfico Rápido
            df = yf.download("CL=F", period="1d", interval="15m", progress=False)
            if not df.empty:
                fig = go.Figure(go.Scatter(x=df.index, y=df['Close'], line=dict(color=v_color)))
                fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig, width='stretch')

    with tab_neural:
        for res in analysis_results:
            with st.expander(f"RAW ANALYSIS: {res['title'][:50]}..."):
                st.write(f"**Sumário:** {res['sum']}")
                st.progress((res['s'] + 1) / 2) # Normaliza -1 a 1 para 0 a 1

if __name__ == "__main__":
    main()
