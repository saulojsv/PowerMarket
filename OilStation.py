import sys
import warnings
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import re
import newspaper
from newspaper import Article, Config
from google import genai
from streamlit_autorefresh import st_autorefresh

# --- AMBIENTE & REGRAS 2026 ---
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

st.set_page_config(page_title="XTI NEURAL | TERMINAL v11.7", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# Configuração de emulação de navegador para evitar bloqueios
agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
config = Config()
config.browser_user_agent = agent
config.request_timeout = 15

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
    .label-tag { font-weight: 800; font-size: 0.75rem; padding: 2px 8px; border-radius: 3px; margin-left: 10px; }
    .BULLISH { color: #00FF41; border: 1px solid #00FF41; border-left: 4px solid #00FF41 !important; }
    .BEARISH { color: #FF3131; border: 1px solid #FF3131; border-left: 4px solid #FF3131 !important; }
    .NEUTRAL { color: #888; border: 1px solid #888; }
    .news-link { color: #00FF41; text-decoration: none; font-size: 1.2rem; margin-right: 10px; opacity: 0.7; }
    .status-box { 
        border: 2px solid #00FF41; padding: 30px; text-align: center; 
        font-weight: 800; font-size: 3rem; background-color: #050505;
        font-family: 'JetBrains Mono';
    }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self):
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = "gemini-1.5-flash"
        self.oil_sources = [
            "https://oilprice.com", 
            "https://www.reuters.com/business/energy/",
            "https://www.cnbc.com/oil/"
        ]
        self.load_verified_data()

    def load_verified_data(self):
        self.bullish_keywords, self.bearish_keywords = {}, {}
        try:
            with open('verified_lexicons.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.bullish_keywords = data.get('bullish', {})
                self.bearish_keywords = data.get('bearish', {})
        except: pass

    def get_deep_analysis(self, title, full_text):
        if not self.client: return 0.0, "NEUTRAL", "IA OFFLINE"
        
        # Sistema de Fallback: Se o texto for curto (bloqueio), analisa pelo título
        is_fallback = len(full_text) < 200
        analysis_content = f"HEADLINE: {title}" if is_fallback else f"CONTENT: {full_text[:2500]}"
        
        try:
            prompt = (f"Analyze WTI Oil Sentiment.\n"
                      f"{analysis_content}\n\n"
                      f"Return strictly:\nSCORE: [float -1.0 to 1.0]\nLABEL: [BULLISH/BEARISH/NEUTRAL]\nSUMMARY: [1 tech sentence]")
            
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            res_text = response.text
            
            score = float(re.search(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", res_text).group(1))
            label = re.search(r"LABEL:\s*(\w+)", res_text).group(1).upper()
            summary = re.search(r"SUMMARY:\s*(.*)", res_text).group(1).strip()
            
            if is_fallback: summary = "(Headline Analysis) " + summary
            
            return score, label, summary
        except:
            return 0.0, "NEUTRAL", "Falha no parsing neural"

@st.cache_data(ttl=60)
def auto_scan_real_news(sources):
    collected = []
    keywords = ['oil', 'crude', 'wti', 'brent', 'energy', 'inventory', 'opec']
    
    for site_url in sources:
        try:
            # Aplicando a config de Anti-Bloqueio
            paper = newspaper.build(site_url, config=config, memoize_articles=False)
            count = 0
            for article in paper.articles:
                if count >= 3: break
                if any(kw in article.url.lower() for kw in keywords):
                    try:
                        article.download()
                        article.parse()
                        collected.append({
                            "title": article.title,
                            "text": article.text.strip(),
                            "url": article.url
                        })
                        count += 1
                    except: continue
        except: continue
    return collected

@st.cache_data(ttl=30)
def get_market_data():
    try:
        xti = yf.download("CL=F", period="2d", interval="1m", progress=False)
        if not xti.empty:
            last = float(xti['Close'].iloc[-1])
            delta = last - float(xti['Close'].iloc[-2])
            return xti, last, delta
    except: pass
    return pd.DataFrame(), 0.0, 0.0

def main():
    engine = XTINeuralEngine()
    st.markdown("### < XTI/USD NEURAL TERMINAL v11.7 // ANTI-BLOCK ACTIVE >")
    
    headlines_data = auto_scan_real_news(engine.oil_sources)
    analysis_results = []
    
    for item in headlines_data:
        s, l, sum_ = engine.get_deep_analysis(item['title'], item['text'])
        analysis_results.append({"h": item['title'], "url": item['url'], "s": s, "l": l, "sum": sum_})

    tab_home, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 NEURAL INTELLIGENCE"])

    with tab_home:
        col_feed, col_market = st.columns([1.8, 1])
        with col_feed:
            st.write(f"🛰️ **FEED ATIVO ({len(headlines_data)} Notícias)**")
            for item in analysis_results:
                st.markdown(f'''
                    <div class="news-card-mini {item['l']}">
                        <div style="display: flex; align-items: center;">
                            <a href="{item['url']}" target="_blank" class="news-link">🔗</a>
                            <span style="color:white; font-weight:500;">{item['h'][:90]}...</span>
                        </div>
                        <span class="label-tag {item['l']}">{item['l']}</span>
                    </div>
                ''', unsafe_allow_html=True)

        with col_market:
            xti_data, price, delta = get_market_data()
            avg_score = np.mean([x['s'] for x in analysis_results]) if analysis_results else 0.0
            veredito = "BUY" if avg_score > 0.1 else "SELL" if avg_score < -0.1 else "HOLD"
            v_color = "#00FF41" if veredito == "BUY" else "#FF3131" if veredito == "SELL" else "#FFFF00"
            
            st.markdown(f'<div class="status-box" style="border-color:{v_color}; color:{v_color};">{veredito}</div>', unsafe_allow_html=True)
            st.metric("WTI SPOT", f"${price:.2f}", delta=f"{delta:.2f}")
            
            if not xti_data.empty:
                fig = go.Figure(go.Scatter(y=xti_data['Close'].values, line=dict(color='#00FF41', width=3)))
                fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(visible=False), yaxis=dict(side="right"))
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    with tab_neural:
        for res in analysis_results:
            with st.expander(f"DEEP READ: {res['h']}"):
                st.write(f"**Resultado:** {res['sum']}")
                st.write(f"**Score:** {res['s']}")

if __name__ == "__main__":
    main()
