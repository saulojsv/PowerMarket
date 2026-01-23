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

# --- AMBIENTE ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="XTI NEURAL v12.5", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS TERMINAL ---
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
        display: inline-block; margin-bottom: 8px; font-weight: bold;
    }
    .BULLISH { border-left: 5px solid #00FF41 !important; color: #00FF41; }
    .BEARISH { border-left: 5px solid #FF3131 !important; color: #FF3131; }
    .NEUTRAL { border-left: 5px solid #888 !important; color: #888; }
    .status-box { border: 2px solid #00FF41; padding: 20px; text-align: center; font-size: 2.5rem; color: #00FF41; background: #050505; }
    .analysis-text { color: #e0e0e0; font-size: 0.9rem; line-height: 1.4; background: #111; padding: 10px; border-radius: 4px; }
    </style>
    """, unsafe_allow_html=True)

class DeepNeuralEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = "gemini-1.5-flash"
        
        # 22 Lexicons de Mercado de Petróleo
        self.lexicon_bull = ['cut', 'opec+', 'shortage', 'sanction', 'tension', 'disruption', 'drawdown', 'strike', 'escalation', 'outage', 'unrest']
        self.lexicon_bear = ['glut', 'surplus', 'increase', 'shale', 'recession', 'slowdown', 'inventory-build', 'oversupply', 'weak-demand', 'easing', 'output-rise']

    def run_lexicon(self, text):
        text_lower = text.lower()
        bull_hits = sum(1 for word in self.lexicon_bull if word in text_lower)
        bear_hits = sum(1 for word in self.lexicon_bear if word in text_lower)
        
        if bull_hits > bear_hits: return "BULLISH", bull_hits
        if bear_hits > bull_hits: return "BEARISH", bear_hits
        return "NEUTRAL", 0

    def deep_analyze(self, title, full_text):
        if not self.client: return 0.0, "NEUTRAL", "SISTEMA OFFLINE"
        
        prompt = f"""
        ANÁLISE TÉCNICA DE MERCADO (WTI CRUDE OIL):
        A notícia abaixo foi pré-classificada pelo Lexicon. Sua tarefa é ler o CONTEÚDO INTEGRAL e realizar uma análise interpretativa profissional.
        
        TÍTULO: {title}
        CONTEÚDO: {full_text[:3500]}
        
        REGRAS:
        1. Identifique o impacto real no preço do barril.
        2. Ignore ruídos políticos irrelevantes ao trade.
        3. Formate a resposta exatamente assim:
        SCORE: [valor de -1.0 a 1.0]
        LABEL: [BULLISH/BEARISH/NEUTRAL]
        INSIGHT: [Análise de 1 parágrafo focada em trading]
        """
        try:
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            txt = response.text.upper()
            score = float(re.search(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", txt).group(1))
            label = re.search(r"LABEL:\s*(\w+)", txt).group(1)
            insight = re.search(r"INSIGHT:\s*(.*)", response.text, re.DOTALL | re.IGNORECASE).group(1).strip()
            return score, label, insight
        except:
            return 0.0, "NEUTRAL", "Erro no processamento da análise profunda."

@st.cache_data(ttl=300)
def fetch_news_content():
    sources = [
        "https://oilprice.com", 
        "https://www.worldoil.com/news/",
        "https://finance.yahoo.com/news/"
    ]
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
                # Garante que há texto suficiente para análise (mínimo 200 caracteres)
                if len(article.text) > 200:
                    data.append({"title": article.title, "text": article.text, "url": article.url})
        except: continue
    return data

def main():
    engine = DeepNeuralEngine()
    st.markdown("### < XTI/USD NEURAL v12.5 // LEXICON + DEEP ANALYSIS >")

    with st.status("📡 Escaneando conteúdos e extraindo texto integral...", expanded=False) as status:
        raw_news = fetch_news_content()
        status.update(label=f"✅ {len(raw_news)} Notícias lidas com sucesso", state="complete")

    processed_data = []
    for item in raw_news:
        # 1. Conclusão do Lexicon primeiro
        lex_label, hits = engine.run_lexicon(item['text'])
        # 2. Análise da IA depois
        score, ai_label, insight = engine.deep_analyze(item['title'], item['text'])
        
        processed_data.append({
            "title": item['title'],
            "url": item['url'],
            "lex_label": lex_label,
            "lex_hits": hits,
            "score": score,
            "ai_label": ai_label,
            "insight": insight
        })

    tab_dash, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 IA DEEP ANALYSIS"])

    with tab_dash:
        col_a, col_b = st.columns([1.8, 1])
        with col_a:
            st.write(f"🛰️ **FEED CONSOLIDADO**")
            for p in processed_data:
                st.markdown(f'''
                    <div class="news-card {p['ai_label']}">
                        <div class="lexicon-box" style="background:#222; border:1px solid #444;">LEXICON: {p['lex_label']} ({p['lex_hits']} gatilhos)</div>
                        <div style="font-weight:bold; font-size:1rem; margin-bottom:5px;">{p['title']}</div>
                        <div style="font-size:0.75rem; color:#00FF41;">
                            IA SCORE: {p['score']} | <a href="{p['url']}" target="_blank" style="color:#888;">FONTE ORIGINAL</a>
                        </div>
                    </div>
                ''', unsafe_allow_html=True)

        with col_b:
            avg = np.mean([x['score'] for x in processed_data]) if processed_data else 0.0
            dec = "BUY" if avg > 0.15 else "SELL" if avg < -0.15 else "HOLD"
            v_color = "#00FF41" if dec == "BUY" else "#FF3131" if dec == "SELL" else "#FFFF00"
            st.markdown(f'<div class="status-box" style="border-color:{v_color}; color:{v_color};">{dec}</div>', unsafe_allow_html=True)
            
            ticker = yf.Ticker("CL=F")
            price = ticker.fast_info.last_price
            st.metric("WTI SPOT", f"${price:.2f}")

    with tab_neural:
        st.write("🔍 **INTERPRETAÇÃO NEURAL DO CONTEÚDO LIDO**")
        for p in processed_data:
            with st.expander(f"ANÁLISE: {p['title'][:60]}..."):
                st.markdown(f"**Conclusão Inicial (Lexicon):** `{p['lex_label']}`")
                st.markdown(f"**Veredito IA:** `{p['ai_label']}` (Score: {p['score']})")
                st.markdown("**Insight para Operação:**")
                st.markdown(f'<div class="analysis-text">{p['insight']}</div>', unsafe_allow_html=True)
                st.write(f"[Acessar conteúdo completo]({p['url']})")

if __name__ == "__main__":
    main()
