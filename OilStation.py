import sys
import warnings
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import re
import json
import requests
from bs4 import BeautifulSoup
import newspaper
from newspaper import Config
from google import genai
from google.genai import types
from streamlit_autorefresh import st_autorefresh

# --- AMBIENTE ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="XTI NEURAL v12.8", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS TERMINAL (Mantido conforme solicitado) ---
st.markdown("""
    <style>
    .main { background-color: #000 !important; font-family: 'JetBrains Mono'; }
    [data-testid="stAppViewContainer"] { background-color: #000000; }
    .news-card { 
        background: #0a0a0a; border: 1px solid #1a1a1a; padding: 15px; 
        margin-bottom: 10px; border-radius: 4px;
    }
    .lexicon-box {
        font-size: 0.75rem; padding: 4px 8px; border-radius: 3px;
        display: inline-block; margin-bottom: 8px; font-weight: bold; background:#222; border:1px solid #444;
    }
    .BULLISH { border-left: 5px solid #00FF41 !important; color: #00FF41; }
    .BEARISH { border-left: 5px solid #FF3131 !important; color: #FF3131; }
    .NEUTRAL { border-left: 5px solid #888 !important; color: #888; }
    .status-box { border: 2px solid #00FF41; padding: 20px; text-align: center; font-size: 2.5rem; color: #00FF41; background: #050505; }
    .analysis-text { color: #e0e0e0; font-size: 0.9rem; line-height: 1.4; background: #111; padding: 12px; border-radius: 4px; border-left: 2px solid #333; }
    </style>
    """, unsafe_allow_html=True)

class AdvancedNeuralEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        
        # 22 Lexicons para Petróleo
        self.lex_bull = ['cut', 'opec+', 'shortage', 'sanction', 'tension', 'drawdown', 'strike', 'escalation', 'outage', 'unrest', 'war', 'attack']
        self.lex_bear = ['glut', 'surplus', 'increase', 'shale', 'recession', 'slowdown', 'inventory-build', 'oversupply', 'weak-demand', 'output-rise']

    def run_lexicon(self, text):
        t = text.lower()
        b_hits = sum(1 for w in self.lex_bull if w in t)
        be_hits = sum(1 for w in self.lex_bear if w in t)
        if b_hits > be_hits: return "BULLISH", b_hits
        if be_hits > b_hits: return "BEARISH", be_hits
        return "NEUTRAL", 0

    def deep_analyze(self, title, text):
        if not self.client: return 0.0, "NEUTRAL", "IA OFFLINE"
        
        # Configuração de bypass de segurança para notícias financeiras pesadas
        safety = [
            types.SafetySetting(category="HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARASSMENT", threshold="OFF"),
            types.SafetySetting(category="DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="SEXUALLY_EXPLICIT", threshold="OFF"),
        ]

        prompt = f"""
        Analyze this Oil Market News and return a JSON object.
        Article: {title}
        Body: {text[:2500]}
        
        Return ONLY valid JSON:
        {{
            "score": float between -1.0 and 1.0,
            "label": "BULLISH", "BEARISH" or "NEUTRAL",
            "insight": "short trading insight"
        }}
        """
        try:
            response = self.client.models.generate_content(
                model="gemini-1.5-flash", 
                contents=prompt,
                config=types.GenerateContentConfig(safety_settings=safety, response_mime_type="application/json")
            )
            # Carrega o JSON da resposta
            data = json.loads(response.text)
            return float(data.get('score', 0.0)), data.get('label', 'NEUTRAL'), data.get('insight', 'OK')
        except:
            # Fallback se o JSON falhar
            return 0.0, "NEUTRAL", "Erro de Parsing JSON Neural"

@st.cache_data(ttl=300)
def fetch_verified_news():
    sources = ["https://oilprice.com", "https://www.worldoil.com/news/", "https://finance.yahoo.com/news/"]
    data = []
    config = Config()
    config.browser_user_agent = 'Mozilla/5.0'
    config.request_timeout = 10
    
    for site in sources:
        try:
            paper = newspaper.build(site, config=config, memoize_articles=False)
            for article in paper.articles[:5]:
                article.download()
                article.parse()
                if len(article.text) > 300:
                    data.append({"title": article.title, "text": article.text, "url": article.url})
        except: continue
    return data

def main():
    engine = AdvancedNeuralEngine()
    st.markdown("### < XTI/USD TERMINAL v12.8 // NEURAL FIX >")

    # Tag superior de varredura
    with st.status("🔍 Sincronizando Redes Neurais...", expanded=False) as status:
        news_list = fetch_verified_news()
        status.update(label=f"✅ {len(news_list)} Notícias lidas e prontas para análise.", state="complete")

    processed = []
    for item in news_list:
        lex_l, lex_h = engine.run_lexicon(item['text'])
        s, ai_l, ins = engine.deep_analyze(item['title'], item['text'])
        processed.append({"t": item['title'], "u": item['url'], "ll": lex_l, "lh": lex_h, "s": s, "al": ai_l, "i": ins})

    tab_dash, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 IA DEEP ANALYSIS"])

    with tab_dash:
        col_1, col_2 = st.columns([1.8, 1])
        with col_1:
            st.write("📡 **FEED ATIVO (LEXICON + IA)**")
            for p in processed:
                st.markdown(f'''
                    <div class="news-card {p['al']}">
                        <div class="lexicon-box">LEXICON: {p['ll']} ({p['lh']} gatilhos)</div>
                        <div style="font-weight:bold; font-size:1rem; margin-bottom:5px;">{p['t']}</div>
                        <div style="font-size:0.75rem; color:#aaa;">IA VERDICT: {p['al']} | SCORE: {p['s']}</div>
                    </div>
                ''', unsafe_allow_html=True)

        with col_2:
            avg_s = np.mean([x['s'] for x in processed]) if processed else 0.0
            v_text = "BUY" if avg_s > 0.1 else "SELL" if avg_s < -0.1 else "HOLD"
            v_color = "#00FF41" if v_text == "BUY" else "#FF3131" if v_text == "SELL" else "#FFFF00"
            st.markdown(f'<div class="status-box" style="border-color:{v_color}; color:{v_color};">{v_text}</div>', unsafe_allow_html=True)
            
            try:
                p_data = yf.download("CL=F", period="2d", interval="15m", progress=False)
                if not p_data.empty:
                    if isinstance(p_data.columns, pd.MultiIndex): p_data.columns = p_data.columns.get_level_values(0)
                    last = float(p_data['Close'].iloc[-1])
                    prev = float(p_data['Close'].iloc[-2])
                    delta = ((last / prev) - 1) * 100
                    st.metric("WTI SPOT", f"${last:.2f}", delta=f"{delta:.2f}%")
            except: st.error("Erro de conexão com mercado.")

    with tab_neural:
        st.write("🧠 **PROCESSAMENTO DE CONTEÚDO INTEGRAL**")
        for p in processed:
            with st.expander(f"ANALYSIS: {p['t'][:60]}..."):
                st.markdown(f"**Conclusão Lexicon:** `{p['ll']}`")
                st.markdown(f"**Insight Neural:**")
                st.markdown(f'<div class="analysis-text">{p["i"]}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
