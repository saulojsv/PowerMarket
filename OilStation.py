import sys
import warnings
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import re
import requests
from bs4 import BeautifulSoup
import newspaper
from newspaper import Article, Config
from google import genai
from streamlit_autorefresh import st_autorefresh

# --- AMBIENTE & REGRAS 2026 ---
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

st.set_page_config(page_title="XTI NEURAL | TERMINAL v12.0", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS PERSONALIZADO ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; padding: 1rem 2rem; }
    [data-testid="stSidebar"] { display: none; } 
    .news-card-mini { 
        background-color: #0a0a0a; border: 1px solid #1a1a1a; 
        padding: 10px; margin-bottom: 6px; border-radius: 4px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .news-text { color: #e0e0e0; font-size: 0.85rem; font-weight: 500; }
    .label-tag { font-weight: 800; font-size: 0.7rem; padding: 2px 6px; border-radius: 3px; margin-left: 10px; min-width: 65px; text-align: center; }
    .BULLISH { color: #00FF41; border: 1px solid #00FF41; border-left: 4px solid #00FF41 !important; }
    .BEARISH { color: #FF3131; border: 1px solid #FF3131; border-left: 4px solid #FF3131 !important; }
    .NEUTRAL { color: #888; border: 1px solid #333; }
    .status-box { 
        border: 2px solid #00FF41; padding: 20px; text-align: center; 
        font-weight: 800; font-size: 2.5rem; background-color: #050505;
        font-family: 'JetBrains Mono'; margin-bottom: 15px;
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
            "https://www.cnbc.com/oil/",
            "https://www.bloomberg.com/energy",
            "https://www.investing.com/commodities/crude-oil-news"
        ]
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    def get_deep_analysis(self, title, url):
        if not self.client: return 0.0, "NEUTRAL", "IA OFFLINE"
        clean_title = re.sub('<[^<]+?>', '', title)[:150]
        try:
            r = requests.get(url, headers=self.headers, timeout=8)
            soup = BeautifulSoup(r.text, 'html.parser')
            for s in soup(['script', 'style']): s.decompose()
            text_content = re.sub(r'\s+', ' ', soup.get_text(separator=' '))[:2500]
        except: text_content = clean_title

        try:
            prompt = (f"Analyze WTI Oil Sentiment.\nNews: {clean_title}\nContent: {text_content}\n\n"
                      f"Return exactly:\nSCORE: [value]\nLABEL: [BULLISH/BEARISH/NEUTRAL]\nSUMMARY: [one sentence]")
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            score = float(re.search(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", response.text).group(1))
            label = re.search(r"LABEL:\s*(\w+)", response.text).group(1).upper()
            summary = re.search(r"SUMMARY:\s*(.*)", response.text).group(1).strip()
            return score, label, summary
        except: return 0.0, "NEUTRAL", "Parsing Neural em modo de segurança."

@st.cache_data(ttl=60)
def auto_scan_real_news(sources):
    collected = []
    keywords = ['oil', 'crude', 'wti', 'brent', 'energy', 'inventory', 'opec']
    config = Config()
    config.request_timeout = 10
    for site_url in sources:
        try:
            paper = newspaper.build(site_url, config=config, memoize_articles=False)
            for article in paper.articles[:5]:
                if any(kw in article.url.lower() for kw in keywords):
                    article.download(); article.parse()
                    if len(article.title) > 10:
                        collected.append({"title": article.title, "url": article.url})
                    if len(collected) >= 8: return collected
        except: continue
    return collected

@st.cache_data(ttl=30)
def get_market_data():
    try:
        df = yf.download("CL=F", period="5d", interval="15m", progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            prices = df['Close'].dropna()
            last = float(prices.iloc[-1])
            prev = float(prices.iloc[-2])
            pct_change = ((last - prev) / prev) * 100
            return prices, last, pct_change
    except: pass
    return pd.Series(), 0.0, 0.0

def main():
    engine = XTINeuralEngine()
    st.markdown("### < XTI/USD NEURAL TERMINAL v12.0 // STABLE BUILD >")
    
    headlines_data = auto_scan_real_news(engine.oil_sources)
    
    analysis_results = []
    for item in headlines_data:
        s, l, sum_ = engine.get_deep_analysis(item['title'], item['url'])
        analysis_results.append({
            "title": item['title'], 
            "url": item['url'], 
            "s": s, 
            "l": l, 
            "sum": sum_
        })

    tab_home, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 NEURAL INTELLIGENCE"])

    with tab_home:
        col_feed, col_market = st.columns([1.7, 1])
        with col_feed:
            st.write(f"🛰️ **FEED ATIVO ({len(analysis_results)} Notícias)**")
            for item in analysis_results:
                title_text = item.get('title', 'Unknown News')
                display_h = re.sub(r'[^\w\s\-\(\)\.\,\']', '', title_text)[:85]
                label = item.get('l', 'NEUTRAL')
                
                st.markdown(f'''
                    <div class="news-card-mini {label}">
                        <div style="display: flex; align-items: center; overflow: hidden;">
                            <a href="{item.get('url', '#')}" target="_blank" style="color:#00FF41; text-decoration:none; margin-right:12px;">🔗</a>
                            <span class="news-text">{display_h}...</span>
                        </div>
                        <span class="label-tag {label}">{label}</span>
                    </div>
                ''', unsafe_allow_html=True)

        with col_market:
            prices_series, spot_price, pct = get_market_data()
            avg_score = np.mean([x['s'] for x in analysis_results]) if analysis_results else 0.0
            veredito = "BUY" if avg_score > 0.15 else "SELL" if avg_score < -0.15 else "HOLD"
            v_color = "#00FF41" if veredito == "BUY" else "#FF3131" if veredito == "SELL" else "#FFFF00"
            
            st.markdown(f'<div class="status-box" style="border-color:{v_color}; color:{v_color};">{veredito}</div>', unsafe_allow_html=True)
            st.metric("WTI SPOT", f"${spot_price:.2f}", delta=f"{pct:.2f}%")
            
            if not prices_series.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=prices_series.index, y=prices_series.values, fill='tozeroy', 
                                         line=dict(color='#00FF41', width=2), fillcolor='rgba(0, 255, 65, 0.08)'))
                fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0),
                                  xaxis=dict(visible=False), yaxis=dict(side="right", gridcolor="#111", autorange=True),
                                  paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                
                # AJUSTE: use_container_width substituído por width='stretch'
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    with tab_neural:
        for res in analysis_results:
            title_brief = res.get('title', 'Analysis')[:80]
            with st.expander(f"ANALYSIS: {title_brief}..."):
                st.info(f"**IA:** {res.get('sum', 'Sem sumário disponível.')}")
                st.write(f"Score: `{res.get('s', 0.0)}` | Status: `{res.get('l', 'NEUTRAL')}`")

if __name__ == "__main__":
    main()
