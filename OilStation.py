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
from newspaper import Article
from google import genai
from streamlit_autorefresh import st_autorefresh

# --- AMBIENTE & REGRAS 2026 ---
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

st.set_page_config(page_title="XTI NEURAL | TERMINAL v11.7", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

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
        if not full_text or len(full_text) < 100: return 0.0, "NEUTRAL", "Fonte Bloqueada ou Incompleta"
        
        try:
            contexto = list(self.bullish_keywords.keys()) + list(self.bearish_keywords.keys())
            # Prompt mais rigoroso para evitar quebras de regex
            prompt = (f"Analyze the following text regarding WTI Crude Oil Market Sentiment.\n"
                      f"Context Lexicons: {contexto}\n"
                      f"Article Title: {title}\n"
                      f"Article Content: {full_text[:3000]}\n\n"
                      f"You MUST return the response exactly in this format:\n"
                      f"SCORE: [value between -1.0 and 1.0]\n"
                      f"LABEL: [BULLISH, BEARISH, or NEUTRAL]\n"
                      f"SUMMARY: [one technical sentence]")
            
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            res_text = response.text
            
            # Parsing robusto
            score_match = re.search(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", res_text)
            label_match = re.search(r"LABEL:\s*(\w+)", res_text)
            summary_match = re.search(r"SUMMARY:\s*(.*)", res_text)
            
            score = float(score_match.group(1)) if score_match else 0.0
            label = label_match.group(1).upper() if label_match else "NEUTRAL"
            summary = summary_match.group(1).strip() if summary_match else "Sem resumo disponível"
            
            return score, label, summary
        except Exception as e:
            return 0.0, "NEUTRAL", f"Falha Neural: {str(e)[:50]}"

@st.cache_data(ttl=300)
def auto_scan_real_news(sources):
    collected = []
    keywords = ['oil', 'crude', 'wti', 'brent', 'energy', 'inventory', 'opec', 'gasoline']
    
    for site_url in sources:
        try:
            paper = newspaper.build(site_url, memoize_articles=False, language='en')
            count = 0
            for article in paper.articles:
                if count >= 3: break
                
                # Verificação de URL e Título para relevância
                url_clean = article.url.lower()
                if any(kw in url_clean for kw in keywords):
                    try:
                        article.download()
                        article.parse()
                        # Limpeza básica de texto para não quebrar o prompt
                        clean_text = article.text.replace('\n', ' ').strip()
                        if len(clean_text) > 300:
                            collected.append({
                                "title": article.title,
                                "text": clean_text,
                                "url": article.url
                            })
                            count += 1
                    except: continue
        except: continue
    return collected

@st.cache_data(ttl=300)
def get_market_data():
    try:
        xti = yf.download("CL=F", period="1d", interval="1m", progress=False)
        if not xti.empty: return xti, xti['Close'].iloc[-1]
    except: pass
    return pd.DataFrame(), 0.0

def main():
    engine = XTINeuralEngine()
    st.markdown("### < XTI/USD NEURAL TERMINAL v11.7 // DEEP READ REPAIRED >")
    
    headlines_data = auto_scan_real_news(engine.oil_sources)
    analysis_results = []
    
    for item in headlines_data:
        score, label, summary = engine.get_deep_analysis(item['title'], item['text'])
        analysis_results.append({"h": item['title'], "url": item['url'], "s": score, "l": label, "sum": summary})

    tab_home, tab_neural = st.tabs(["📊 DASHBOARD", "🧠 NEURAL INTELLIGENCE"])

    with tab_home:
        col_feed, col_market = st.columns([1.8, 1])
        with col_feed:
            st.write(f"🛰️ **LIVE ARTICLE FEED ({len(headlines_data)} Notícias Reais)**")
            if not headlines_data:
                st.info("Nenhuma notícia de petróleo detectada nos últimos minutos. Aguardando novos blocos...")
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
            xti_data, spot_price = get_market_data()
            avg_score = np.mean([x['s'] for x in analysis_results]) if analysis_results else 0.0
            veredito = "BUY" if avg_score > 0.1 else "SELL" if avg_score < -0.1 else "HOLD"
            v_color = "#00FF41" if veredito == "BUY" else "#FF3131" if veredito == "SELL" else "#FFFF00"
            st.markdown(f'<div class="status-box" style="border-color:{v_color}; color:{v_color};">{veredito}</div>', unsafe_allow_html=True)
            st.metric("WTI SPOT", f"${spot_price:.2f}")
            if not xti_data.empty:
                fig = go.Figure(go.Scatter(y=xti_data['Close'].values, line=dict(color='#00FF41', width=3)))
                fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(visible=False), yaxis=dict(side="right"))
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    with tab_neural:
        for res in analysis_results:
            with st.expander(f"DEEP READ: {res['h']}"):
                st.write(f"**Análise da IA:** {res['sum']}")
                st.write(f"**Score de Sentimento:** {res['s']}")

if __name__ == "__main__":
    main()
