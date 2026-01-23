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
st.set_page_config(page_title="XTI NEURAL v12.4", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS TERMINAL ---
st.markdown("""
    <style>
    .main { background-color: #000 !important; font-family: 'JetBrains Mono'; }
    .news-card { 
        background: #0a0a0a; border: 1px solid #1a1a1a; padding: 12px; 
        margin-bottom: 8px; border-radius: 4px; border-left: 4px solid #333;
    }
    .BULLISH { border-left-color: #00FF41 !important; color: #00FF41; }
    .BEARISH { border-left-color: #FF3131 !important; color: #FF3131; }
    .NEUTRAL { border-left-color: #888 !important; color: #888; }
    .status-box { border: 2px solid #00FF41; padding: 20px; text-align: center; font-size: 2.5rem; color: #00FF41; }
    </style>
    """, unsafe_allow_html=True)

class InterpretativeNeuralEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = "gemini-1.5-flash"

    def interpret_market_event(self, title, partial_text):
        if not self.client: return 0.0, "NEUTRAL", "IA OFFLINE"
        
        # PROMPT INTERPRETATIVO: Força a IA a inferir o impacto mesmo com poucos dados
        prompt = f"""
        URGENT OIL MARKET INTERPRETATION:
        Analyze the likely impact of this event on WTI Crude Oil prices.
        
        DATA:
        Event: {title}
        Context: {partial_text[:1000] if partial_text else "No extra context available. Use Event Title to infer impact."}
        
        TASK:
        Infer if this is BULLISH (price up), BEARISH (price down), or NEUTRAL.
        Be decisive. Avoid Neutral unless the news is purely administrative.
        
        FORMAT:
        SCORE: [value -1.0 to 1.0]
        LABEL: [BULLISH/BEARISH/NEUTRAL]
        REASON: [Short explanation, max 10 words]
        """
        try:
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            txt = response.text.upper()
            score = float(re.search(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", txt).group(1))
            label = re.search(r"LABEL:\s*(\w+)", txt).group(1)
            reason = re.search(r"REASON:\s*(.*)", txt).group(1).strip()
            return score, label, reason
        except:
            return 0.0, "NEUTRAL", "Erro na Inferência Neural"

@st.cache_data(ttl=300)
def fast_interpretative_scan():
    # Fontes que respondem rápido e com bons snippets
    sources = [
        "https://oilprice.com", 
        "https://www.worldoil.com/news/",
        "https://finance.yahoo.com/news/"
    ]
    data = []
    config = Config()
    config.browser_user_agent = 'Mozilla/5.0'
    config.request_timeout = 5 # Timeout agressivo para não travar

    for site in sources:
        try:
            paper = newspaper.build(site, config=config, memoize_articles=False)
            for article in paper.articles[:6]:
                article.download()
                article.parse()
                if len(article.title) > 20:
                    data.append({"title": article.title, "text": article.text, "url": article.url})
        except: continue
    return data

def main():
    engine = InterpretativeNeuralEngine()
    st.markdown("### < XTI/USD TERMINAL v12.4 // INTERPRETATIVE ENGINE >")

    # Background Scan (Cacheado)
    with st.status("🔍 Varredura Interpretativa Ativa...", expanded=False) as status:
        raw_news = fast_interpretative_scan()
        status.update(label="✅ Varredura Concluída", state="complete")

    processed_data = []
    if raw_news:
        for item in raw_news:
            # INTERPRETAÇÃO: Se o 'text' vier vazio (falha no parsing), a IA interpreta o 'title'
            s, l, r = engine.interpret_market_event(item['title'], item['text'])
            processed_data.append({"t": item['title'], "u": item['url'], "s": s, "l": l, "r": r})

    col_a, col_b = st.columns([1.8, 1])

    with col_a:
        st.write(f"🛰️ **FEED NEURAL ({len(processed_data)} notícias)**")
        for p in processed_data:
            st.markdown(f'''
                <div class="news-card {p['l']}">
                    <div style="font-weight:bold; font-size:0.9rem;">{p['t']}</div>
                    <div style="font-size:0.75rem; color:#aaa; margin-top:5px;">{p['r']}</div>
                    <div style="font-size:0.7rem; margin-top:3px;">Score: {p['s']} | <a href="{p['u']}" style="color:#00FF41;">Link</a></div>
                </div>
            ''', unsafe_allow_html=True)

    with col_b:
        avg = np.mean([x['s'] for x in processed_data]) if processed_data else 0.0
        dec = "BUY" if avg > 0.1 else "SELL" if avg < -0.1 else "HOLD"
        st.markdown(f'<div class="status-box">{dec}</div>', unsafe_allow_html=True)
        
        # Market Price
        ticker = yf.Ticker("CL=F")
        price = ticker.fast_info.last_price
        st.metric("WTI SPOT", f"${price:.2f}")

if __name__ == "__main__":
    main()
