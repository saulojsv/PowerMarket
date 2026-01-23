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
st.set_page_config(page_title="XTI NEURAL v12.6", layout="wide")
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
        display: inline-block; margin-bottom: 8px; font-weight: bold; background:#222; border:1px solid #444;
    }
    .BULLISH { border-left: 5px solid #00FF41 !important; color: #00FF41; }
    .BEARISH { border-left: 5px solid #FF3131 !important; color: #FF3131; }
    .NEUTRAL { border-left: 5px solid #888 !important; color: #888; }
    .status-box { border: 2px solid #00FF41; padding: 20px; text-align: center; font-size: 2.5rem; color: #00FF41; background: #050505; }
    .analysis-text { color: #e0e0e0; font-size: 0.9rem; line-height: 1.4; background: #111; padding: 12px; border-radius: 4px; border-left: 2px solid #333; }
    </style>
    """, unsafe_allow_html=True)

class RobustNeuralEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = "gemini-1.5-flash"
        
        # Lexicons atualizados para Oil Market 2026
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
        
        # Limpeza de texto para evitar quebras no prompt
        clean_text = re.sub(r'\s+', ' ', text)[:3000]
        
        prompt = f"""
        OIL MARKET TRADER ANALYSIS:
        Analyze the text and return the sentiment for WTI Crude Oil.
        
        ARTICLE: {title}
        CONTENT: {clean_text}
        
        MANDATORY FORMAT (No other text):
        SCORE: [X.X]
        LABEL: [BULLISH/BEARISH/NEUTRAL]
        INSIGHT: [Trading summary]
        """
        try:
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            raw = response.text
            
            # Parsing robusto sem depender apenas de regex rígido
            lines = [line.strip() for line in raw.split('\n') if ':' in line]
            data = {line.split(':')[0].upper(): line.split(':')[1].strip() for line in lines}
            
            score = float(re.findall(r"[-+]?\d*\.\d+|\d+", data.get('SCORE', '0.0'))[0])
            label = data.get('LABEL', 'NEUTRAL').replace('[','').replace(']','')
            insight = data.get('INSIGHT', 'Análise processada com sucesso.')
            
            return score, label, insight
        except Exception as e:
            return 0.0, "NEUTRAL", f"Falha na interpretação neural: {str(e)[:50]}"

@st.cache_data(ttl=300)
def fetch_and_clean_news():
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
                # Aumentei o rigor da limpeza: se não tem texto real, ignora
                if len(article.text) > 300:
                    data.append({"title": article.title, "text": article.text, "url": article.url})
        except: continue
    return data

def main():
    engine = RobustNeuralEngine()
    st.markdown("### < XTI/USD TERMINAL v12.6 // DEEP CONTENT SCAN >")

    # Tag superior de varredura (Mantida)
    with st.status("🔍 Verificando Fontes e Extraindo Conteúdo Integral...", expanded=False) as status:
        news_list = fetch_and_clean_news()
        status.update(label=f"✅ Sincronização Completa: {len(news_list)} eventos detectados.", state="complete")

    processed = []
    for item in news_list:
        lex_l, lex_h = engine.run_lexicon(item['text'])
        s, ai_l, ins = engine.deep_analyze(item['title'], item['text'])
        processed.append({"t": item['title'], "u": item['url'], "ll": lex_l, "lh": lex_h, "s": s, "al": ai_l, "i": ins})

    tab_dash, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 IA DEEP ANALYSIS"])

    with tab_dash:
        col_1, col_2 = st.columns([1.8, 1])
        with col_1:
            st.write("📡 **FEED ATIVO (LEXICON PRIORITÁRIO)**")
            for p in processed:
                st.markdown(f'''
                    <div class="news-card {p['al']}">
                        <div class="lexicon-box">LEXICON: {p['ll']} ({p['lh']} gatilhos)</div>
                        <div style="font-weight:bold; font-size:1rem; margin-bottom:5px;">{p['t']}</div>
                        <div style="font-size:0.75rem; color:#aaa;">SCORE IA: {p['s']} | <a href="{p['u']}" target="_blank" style="color:#00FF41;">LINK</a></div>
                    </div>
                ''', unsafe_allow_html=True)

        with col_2:
            avg_s = np.mean([x['s'] for x in processed]) if processed else 0.0
            v_text = "BUY" if avg_s > 0.15 else "SELL" if avg_s < -0.15 else "HOLD"
            v_color = "#00FF41" if v_text == "BUY" else "#FF3131" if v_text == "SELL" else "#FFFF00"
            st.markdown(f'<div class="status-box" style="border-color:{v_color}; color:{v_color};">{v_text}</div>', unsafe_allow_html=True)
            
            p_data = yf.download("CL=F", period="1d", interval="15m", progress=False)
            if not p_data.empty:
                st.metric("WTI SPOT", f"${p_data['Close'].iloc[-1]:.2f}", delta=f"{((p_data['Close'].iloc[-1]/p_data['Close'].iloc[-2])-1)*100:.2f}%")

    with tab_neural:
        st.write("🧠 **PROCESSAMENTO DE CONTEÚDO INTEGRAL**")
        for p in processed:
            with st.expander(f"ANALYSIS: {p['t'][:60]}..."):
                c1, c2 = st.columns(2)
                c1.metric("Lexicon Status", p['ll'])
                c2.metric("Neural Score", p['s'])
                st.markdown("**Insight Interpretativo:**")
                st.markdown(f'<div class="analysis-text">{p['i']}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
