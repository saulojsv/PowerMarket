import sys
import warnings
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import re
import json
import newspaper
from newspaper import Config
from google import genai
from google.genai import types
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE AMBIENTE ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="XTI NEURAL v13.1", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS TERMINAL (Design Preservado) ---
st.markdown("""
    <style>
    .main { background-color: #000 !important; font-family: 'JetBrains Mono'; }
    [data-testid="stAppViewContainer"] { background-color: #000000; }
    .news-card { 
        background: #0a0a0a; border: 1px solid #1a1a1a; padding: 15px; 
        margin-bottom: 10px; border-radius: 4px; border-left: 5px solid #333;
    }
    .lexicon-box {
        font-size: 0.72rem; padding: 3px 7px; border-radius: 3px;
        display: inline-block; margin-bottom: 5px; font-weight: bold; background:#111; border:1px solid #333;
    }
    .BULLISH { border-left-color: #00FF41 !important; color: #00FF41; }
    .BEARISH { border-left-color: #FF3131 !important; color: #FF3131; }
    .NEUTRAL { border-left-color: #888 !important; color: #888; }
    .status-box { border: 2px solid #00FF41; padding: 20px; text-align: center; font-size: 2.5rem; color: #00FF41; background: #050505; }
    </style>
    """, unsafe_allow_html=True)

class TerminalEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        # Termos técnicos de mercado
        self.lex_bull = ['cut', 'opec+', 'shortage', 'sanction', 'tension', 'drawdown', 'strike', 'escalation', 'outage', 'unrest', 'war', 'attack', 'deal', 'agreement']
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
        prompt = f"Oil Trader Analysis. News: {title}. Content: {text[:1500]}. Return JSON: {{'score': float, 'label': 'BULLISH/BEARISH/NEUTRAL', 'insight': 'text'}}"
        try:
            response = self.client.models.generate_content(
                model="gemini-1.5-flash", 
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            raw_res = response.text
            # Tenta limpar o JSON de qualquer Markdown
            clean_json = re.search(r'\{.*\}', raw_res, re.DOTALL).group()
            data = json.loads(clean_json)
            return float(data.get('score', 0.0)), data.get('label', 'NEUTRAL'), data.get('insight', 'Análise processada.')
        except Exception as e:
            # Fallback interpretativo manual se a IA falhar no JSON
            return 0.0, "NEUTRAL", f"Falha Técnica: {str(e)[:20]}"

@st.cache_data(ttl=300)
def fetch_news():
    sources = ["https://oilprice.com", "https://www.worldoil.com/news/"]
    data = []
    config = Config()
    config.browser_user_agent = 'Mozilla/5.0'
    config.request_timeout = 8
    for site in sources:
        try:
            paper = newspaper.build(site, config=config, memoize_articles=False)
            for article in paper.articles[:4]:
                article.download(); article.parse()
                if len(article.text) > 250:
                    data.append({"title": article.title, "text": article.text, "url": article.url})
        except: continue
    return data

def main():
    engine = TerminalEngine()
    st.markdown("### < XTI/USD NEURAL TERMINAL v13.1 // HYPER-STABLE >")

    with st.status("🔍 Scanner Ativo...", expanded=False) as status:
        news_list = fetch_news()
        status.update(label=f"✅ {len(news_list)} Eventos Capturados", state="complete")

    processed = []
    for item in news_list:
        lex_l, lex_h = engine.run_lexicon(item['text'])
        s, ai_l, ins = engine.deep_analyze(item['title'], item['text'])
        # A IA herda o label do Lexicon se ela falhar no parsing
        final_label = ai_l if ai_l != "NEUTRAL" else lex_l
        processed.append({"t": item['title'], "u": item['url'], "ll": lex_l, "s": s, "al": final_label, "i": ins})

    tab_dash, tab_ia = st.tabs(["📊 DASHBOARD", "🧠 IA DEEP ANALYSIS"])

    with tab_dash:
        col_1, col_2 = st.columns([1.8, 1])
        with col_1:
            for p in processed:
                st.markdown(f'''
                    <div class="news-card {p['al']}">
                        <div class="lexicon-box">LEXICON: {p['ll']}</div><br>
                        <b>{p['t']}</b><br>
                        <small style="color:#666;">Score Neural: {p['s']} | <a href="{p['u']}" style="color:#00FF41;">LINK</a></small>
                    </div>
                ''', unsafe_allow_html=True)
        
        with col_2:
            avg_s = np.mean([x['s'] for x in processed]) if processed else 0.0
            dec = "BUY" if avg_s > 0.1 else "SELL" if avg_s < -0.1 else "HOLD"
            st.markdown(f'<div class="status-box">{dec}</div>', unsafe_allow_html=True)
            
            try:
                # FIX DEFINITIVO PARA O ERRO DE SERIES
                p_data = yf.download("CL=F", period="2d", interval="1m", progress=False)
                if not p_data.empty:
                    # Achata tudo para numpy para evitar erro de Series format
                    prices = p_data['Close'].to_numpy().flatten()
                    last_val = float(prices[-1])
                    prev_val = float(prices[-2])
                    diff = ((last_val / prev_val) - 1) * 100
                    st.metric("WTI SPOT", f"${last_val:.2f}", delta=f"{diff:.2f}%")
            except: st.error("Erro na extração do WTI Spot.")

    with tab_ia:
        for p in processed:
            with st.expander(f"ANALYSIS: {p['t'][:60]}..."):
                st.write(f"**Insight:** {p['i']}")

if __name__ == "__main__":
    main()
