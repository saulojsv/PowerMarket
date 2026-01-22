import sys
import warnings
import json

# Silencia SyntaxWarnings internos de bibliotecas de terceiros
warnings.filterwarnings("ignore", category=SyntaxWarning)

# PATCH DE COMPATIBILIDADE: lxml.html.clean
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
import re
from datetime import datetime
from newspaper import Article
from google import genai # Nova SDK do Google (v2026)
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE INTERFACE ---
st.set_page_config(page_title="XTI NEURAL | TERMINAL v10.9", layout="wide")
st_autorefresh(interval=60000, key="terminal_refresh")

# --- CSS PROFISSIONAL (DARK TOTAL - MANTIDO) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; }
    header, [data-testid="stHeader"] { background-color: #000000; }
    div[data-baseweb="textarea"], div[data-baseweb="input"] { 
        background-color: #0a0a0a !important; 
        border-radius: 8px; 
        border: 1px solid #1a1a1a !important; 
    }
    textarea, input { 
        background-color: #0a0a0a !important; 
        color: #00FF41 !important; 
        font-family: 'JetBrains Mono' !important; 
    }
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
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.model_id = "gemini-1.5-flash"
        self.load_lexicons_from_json()

    def load_lexicons_from_json(self):
        """Carrega léxicos e sites do arquivo verificado pelo usuário"""
        try:
            with open('verified_lexicons.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.bullish_keywords = data.get('bullish', {})
                self.bearish_keywords = data.get('bearish', {})
                self.oil_sources = data.get('sites', [])
                st.sidebar.success("✅ CORE: verified_lexicons.json LOADED")
        except:
            st.sidebar.error("⚠️ verified_lexicons.json não encontrado. Usando léxicos base.")
            # Fallback (seu código original)
            self.bullish_keywords = {"production cut": 0.8, "inventory draw": 0.7}
            self.bearish_keywords = {"inventory build": -0.6, "shale output": -0.4}
            self.oil_sources = []

    def scrap_full_article(self, url):
        try:
            article = Article(url)
            article.download(); article.parse()
            return article.text[:4000]
        except: return None

    def get_deep_neural_analysis(self, content, is_url=False):
        if not self.client: return 0.0, "AI INACTIVE"
        try:
            # Envia os lexicons para a IA aprender o padrão de classificação
            context_lex = list(self.bullish_keywords.keys()) + list(self.bearish_keywords.keys())
            prompt = f"Como Analista Senior (WTI), considere estes léxicos base: {context_lex}. Analise o impacto para: {content}. Retorne [SCORE: -1.0 a 1.0] e [RESUMO: 1 frase]."
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            score_match = re.findall(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", response.text)
            score = float(score_match[0]) if score_match else 0.0
            summary = response.text.split("RESUMO:")[-1].strip() if "RESUMO:" in response.text else "Processado."
            return score, summary
        except: return 0.0, "Falha neural."

    def process_input(self, text):
        is_url = bool(re.match(r'^https?://', text.strip()))
        if is_url:
            content = self.scrap_full_article(text)
            if content:
                score, summary = self.get_deep_neural_analysis(content, is_url=True)
                return score, "DEEP READER", summary, text[:50]+"..."
            return 0.0, "ERROR", "URL inacessível.", text
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
    if 'manual_corpus' not in st.session_state:
        st.session_state.manual_corpus = ""

    with st.sidebar:
        st.markdown("### 🛰️ UPLINK: JSON CORE")
        gemini_api = st.text_input("Gemini API Key", type="password")
        
        # Botão para varrer sites definidos no seu JSON
        engine = XTINeuralEngine(api_key=gemini_api)
        if st.button("🔎 SCAN VERIFIED SITES"):
            with st.spinner("Varrendo fontes do JSON..."):
                titles = []
                for site in engine.oil_sources[:10]:
                    try:
                        a = Article(site); a.download(); a.parse()
                        if a.title: titles.append(a.title)
                    except: continue
                st.session_state.manual_corpus = "\n".join(titles)

        if st.button("Limpar Corpus"): 
            st.session_state.manual_corpus = ""
            st.rerun()

        manual_corpus = st.text_area("Corpus (URLs ou Manchetes):", value=st.session_state.manual_corpus, height=300)
        dxy_manual = st.slider("DXY Fix (%)", -2.0, 2.0, -0.25)

    st.markdown(f"### < XTI/USD NEURAL TERMINAL v10.9 // JSON CORE >")
    
    prices_raw, dxy_auto = get_market_intelligence()
    dxy_delta = dxy_manual / 100 if dxy_manual != -0.25 else dxy_auto
    
    if not prices_raw:
        st.warning("Aguardando dados..."); prices = [0.0, 0.0]; z_score = 0.0
    else:
        prices = prices_raw
        series = pd.Series(prices)
        z_score = float((series.iloc[-1] - series.mean()) / series.std()) if series.std() != 0 else 0.0

    inputs = [i.strip() for i in manual_corpus.split('\n') if len(i.strip()) > 5]
    impact_sum = 0.0
    
    col_news, col_verdict = st.columns([1.8, 1])

    with col_news:
        if not inputs: st.info("Sincronize o Corpus ou use SCAN VERIFIED SITES.")
        for item in inputs:
            with st.spinner("Decodificando contexto..."):
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
        label = "BUY" if final_score > 0.1 else "SELL" if final_score < -0.1 else "NEUTRAL"
        
        st.markdown(f'<div class="status-box" style="border-color:{color}; color:{color};">{label}<br><span style="font-size:0.8rem; color:white;">CONFIDENCE: {abs(final_score)*100:.1f}%</span></div>', unsafe_allow_html=True)
        
        fig = go.Figure(go.Scatter(y=prices[-50:], line=dict(color='#00FF41', width=3), fill='tozeroy', fillcolor='rgba(0,255,65,0.05)'))
        fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False), yaxis=dict(side="right"))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

if __name__ == "__main__":
    main()
