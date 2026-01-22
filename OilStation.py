import sys

# PATCH DE COMPATIBILIDADE: lxml.html.clean para Python 3.13+
try:
    import lxml.html.clean
except ImportError:
    try:
        import lxml_html_clean as clean
        sys.modules['lxml.html.clean'] = clean
    except ImportError:
        pass

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import json
import os
import re
import google.generativeai as genai
from datetime import datetime
from newspaper import Article
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE INTERFACE ---
st.set_page_config(page_title="XTI NEURAL", layout="wide")
st_autorefresh(interval=60000, key="terminal_refresh")

# --- CSS PROFISSIONAL (DARK TOTAL) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; }
    header, [data-testid="stHeader"] { background-color: #000000; }
    
    /* Remoção de fundos brancos em inputs */
    div[data-baseweb="textarea"], div[data-baseweb="input"] { background-color: #0a0a0a !important; border-radius: 8px; border: 1px solid #1a1a1a !important; }
    textarea, input { background-color: #0a0a0a !important; color: #00FF41 !important; font-family: 'JetBrains Mono' !important; }

    .news-card { 
        background-color: #0a0a0a; border: 1px solid #333333; border-left: 5px solid #00FF41; 
        padding: 18px; margin-bottom: 12px; border-radius: 6px;
    }
    .deep-tag {
        font-size: 0.7rem; color: #000; background: #00FF41; 
        padding: 2px 6px; border-radius: 3px; font-weight: bold; margin-bottom: 5px; display: inline-block;
    }
    .news-title { font-weight: 700; color: #ffffff !important; display: block; margin-bottom: 5px; }
    .news-ai { font-size: 0.85rem; color: #00FF41; font-weight: bold; }
    .news-ai-bear { color: #FF3131 !important; }

    .status-box { 
        border: 2px solid #00FF41; padding: 40px; text-align: center; font-weight: 800; 
        text-transform: uppercase; font-size: 2.2rem; background-color: #050505;
        box-shadow: 0 0 30px rgba(0, 255, 65, 0.1); margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self, api_key=None):
        self.risk_threshold = 0.70
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None
        self.load_lexicons()

    def load_lexicons(self):
        self.bullish_keywords = {
            "production cut": 0.8, "inventory draw": 0.7, "opec quota": 0.5,
            "supply disruption": 0.9, "demand growth": 0.6, "refinery outage": 0.5,
            "geopolitical tension": 0.8, "sanctions": 0.7, "rig count decrease": 0.4,
            "export ban": 0.8, "soft landing": 0.4, "crude imports": 0.3, "output freeze": 0.6
        }
        self.bearish_keywords = {
            "inventory build": -0.6, "shale output": -0.4, "strategic reserve": -0.3,
            "interest rate hike": -0.5, "dollar strength": -0.4, "oil glut": -0.9,
            "rig count increase": -0.3, "recession fears": -0.8, "well completion": -0.3,
            "drilling productivity": -0.4, "upstream investment": -0.2, "fuel switching": -0.3,
            "industrial activity contraction": -0.7, "electric vehicle penetration": -0.5
        }

    def scrap_full_article(self, url):
        try:
            article = Article(url)
            article.download()
            article.parse()
            return article.text[:4000]
        except:
            return None

    def get_deep_neural_analysis(self, content, is_url=False):
        if not self.model: return 0.0, "AI INACTIVE"
        try:
            prompt = f"""
            Analise este {'artigo completo' if is_url else 'título'} de petróleo.
            Retorne exatamente neste formato:
            SCORE: [valor de -1.0 a 1.0]
            RESUMO: [uma frase curta do impacto no WTI]
            CONTEÚDO: {content}
            """
            response = self.model.generate_content(prompt)
            score_match = re.findall(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", response.text)
            score = float(score_match[0]) if score_match else 0.0
            summary = response.text.split("RESUMO:")[-1].strip() if "RESUMO:" in response.text else "Análise concluída."
            return score, summary
        except: return 0.0, "Erro neural."

    def process_input(self, text):
        is_url = bool(re.match(r'^https?://', text.strip()))
        if is_url:
            content = self.scrap_full_article(text)
            if content:
                score, summary = self.get_deep_neural_analysis(content, is_url=True)
                return score, "DEEP READER", summary, text[:50]+"..."
            return 0.0, "ERROR", "Falha ao acessar URL.", text
        else:
            lex_impact = sum(v for k, v in {**self.bullish_keywords, **self.bearish_keywords}.items() if k in text.lower())
            score, summary = self.get_deep_neural_analysis(text, is_url=False)
            return (lex_impact + score) / 2, "LEXICON+AI", summary, text

@st.cache_data(ttl=60)
def get_market_intelligence():
    try:
        xti = yf.download("CL=F", period="2d", interval="5m", progress=False)
        dxy = yf.download("DX-Y.NYB", period="2d", interval="5m", progress=False)
        if xti.empty or dxy.empty: return None, 0.0
        prices = xti['Close'].iloc[:, 0].dropna().tolist()
        dxy_pct = dxy['Close'].iloc[:, 0].pct_change().iloc[-1]
        return prices, float(dxy_pct)
    except: return None, 0.0

def main():
    with st.sidebar:
        st.markdown("### 🛰️ UPLINK: DEEP CONFIG")
        gemini_api = st.text_input("Gemini API Key", type="password")
        manual_corpus = st.text_area("Corpus (URLs ou Manchetes):", height=300)
        dxy_manual = st.slider("DXY Fix (%)", -2.0, 2.0, -0.25)

    engine = XTINeuralEngine(api_key=gemini_api)
    st.markdown(f"### < XTI/USD NEURAL TERMINAL v10.2 // DEEP READER >")
    
    tab_ops, tab_lex = st.tabs(["⚡ OPERATIONAL", "🧠 KNOWLEDGE"])

    with tab_ops:
        prices_raw, dxy_auto = get_market_intelligence()
        dxy_delta = dxy_manual / 100 if dxy_manual != -0.25 else dxy_auto
        
        if not prices_raw:
            st.warning("Aguardando uplink..."); prices = [0.0, 0.0]; z_score = 0.0
        else:
            prices = prices_raw
            series = pd.Series(prices)
            z_score = float((series.iloc[-1] - series.mean()) / series.std()) if series.std() != 0 else 0.0

        inputs = [i.strip() for i in manual_corpus.split('\n') if len(i.strip()) > 5]
        impact_sum = 0.0
        
        col_news, col_verdict = st.columns([1.8, 1])

        with col_news:
            if not inputs: st.info("Aguardando entrada de dados no Corpus...")
            for item in inputs:
                with st.spinner("Analisando contexto profundo..."):
                    score, method, summary, title = engine.process_input(item)
                    impact_sum += score
                    css = "news-ai-bear" if score < 0 else ""
                    st.markdown(f"""
                        <div class="news-card">
                            <span class="deep-tag">{method}</span>
                            <span class="news-title">{title}</span>
                            <span class="news-ai {css}">IMPACT: {score:+.2f} >> {summary}</span>
                        </div>
                    """, unsafe_allow_html=True)

        with col_verdict:
            ai_sentiment = float(np.clip(impact_sum / (len(inputs) or 1), -1, 1))
            arb_bias = float(np.clip(-dxy_delta * 10, -1, 1))
            final_score = (ai_sentiment * 0.45) + (arb_bias * 0.35) + (-np.clip(z_score/3, -1, 1) * 0.20)
            
            color = "#00FF41" if final_score > engine.risk_threshold else "#FF3131" if final_score < -engine.risk_threshold else "#FFFF00"
            st.markdown(f'<div class="status-box" style="border-color:{color}; color:{color};">{"BUY" if final_score > 0.1 else "SELL" if final_score < -0.1 else "HOLD"}<br><span style="font-size:0.8rem; color:white;">CONFIDENCE: {abs(final_score)*100:.1f}%</span></div>', unsafe_allow_html=True)
            
            fig = go.Figure(go.Scatter(y=prices[-50:], line=dict(color='#00FF41', width=3), fill='tozeroy', fillcolor='rgba(0,255,65,0.05)'))
            fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False), yaxis=dict(side="right"))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

if __name__ == "__main__":
    main()
