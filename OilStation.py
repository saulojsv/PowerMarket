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
from datetime import datetime

# --- AMBIENTE ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="XTI NEURAL v13.0", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS TERMINAL (Design Preservado) ---
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
    </style>
    """, unsafe_allow_html=True)

class TerminalEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
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
        prompt = f"Trader Analysis for Crude Oil. News: {title}. Content: {text[:2000]}. Return JSON with keys: score (float), label (string), insight (string)."
        try:
            # Correção do endpoint para evitar 404
            response = self.client.models.generate_content(
                model="gemini-1.5-flash", 
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            data = json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())
            return float(data.get('score', 0.0)), data.get('label', 'NEUTRAL'), data.get('insight', 'Sucesso.')
        except:
            return 0.0, "NEUTRAL", "Erro de Parsing Neural"

@st.cache_data(ttl=300)
def fetch_market_news():
    sources = ["https://oilprice.com", "https://www.worldoil.com/news/"]
    data = []
    config = Config()
    config.browser_user_agent = 'Mozilla/5.0'
    config.request_timeout = 10
    for site in sources:
        try:
            paper = newspaper.build(site, config=config, memoize_articles=False)
            for article in paper.articles[:5]:
                article.download(); article.parse()
                if len(article.text) > 200:
                    data.append({"title": article.title, "text": article.text, "url": article.url})
        except: continue
    return data

def main():
    engine = TerminalEngine()
    st.markdown("### < XTI/USD NEURAL TERMINAL v13.0 // STABLE >")

    with st.status("🔍 Varredura de Mercado Ativa...", expanded=False) as status:
        news_list = fetch_market_news()
        status.update(label="✅ Sincronização Concluída", state="complete")

    processed = []
    for item in news_list:
        lex_l, lex_h = engine.run_lexicon(item['text'])
        s, ai_l, ins = engine.deep_analyze(item['title'], item['text'])
        processed.append({"t": item['title'], "u": item['url'], "ll": lex_l, "s": s, "al": ai_l, "i": ins})

    tab_dash, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 IA DEEP ANALYSIS"])

    with tab_dash:
        col_1, col_2 = st.columns([1.8, 1])
        with col_1:
            for p in processed:
                st.markdown(f'<div class="news-card {p["al"]}"><div class="lexicon-box">LEX: {p["ll"]}</div><br><b>{p["t"]}</b><br><small>IA Score: {p["s"]}</small></div>', unsafe_allow_html=True)
        
        with col_2:
            avg_s = np.mean([x['s'] for x in processed]) if processed else 0.0
            v_text = "BUY" if avg_s > 0.1 else "SELL" if avg_s < -0.1 else "HOLD"
            st.markdown(f'<div class="status-box">{v_text}</div>', unsafe_allow_html=True)
            
            # --- FIX: ROBUSTEZ ABSOLUTA NO PREÇO ---
            try:
                p_data = yf.download("CL=F", period="2d", interval="1m", progress=False)
                if not p_data.empty:
                    # Garante que p_data['Close'] seja apenas uma coluna
                    close_col = p_data['Close'].squeeze()
                    if isinstance(close_col, pd.DataFrame): close_col = close_col.iloc[:, 0]
                    
                    last_p = float(close_col.iloc[-1])
                    prev_p = float(close_col.iloc[-2])
                    st.metric("WTI SPOT", f"${last_p:.2f}", delta=f"{((last_p/prev_p)-1)*100:.2f}%")
            except: st.error("Dados de mercado temporariamente indisponíveis.")

    with tab_neural:
        for p in processed:
            with st.expander(f"NEWS: {p['t'][:50]}..."):
                st.write(f"**Veredito:** {p['al']} | **Insight:** {p['i']}")

if __name__ == "__main__":
    main()
