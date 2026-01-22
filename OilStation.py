import sys
import warnings
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import re
from newspaper import Article
from google import genai
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE AMBIENTE ---
warnings.filterwarnings("ignore", category=SyntaxWarning)
st.set_page_config(page_title="XTI NEURAL", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# --- CSS WIDE & DEEP READER VISUAL ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; padding: 1rem 3rem; }
    [data-testid="stSidebar"] { display: none; } 
    
    .news-card { 
        background-color: #0a0a0a; border: 1px solid #1a1a1a; 
        padding: 15px; margin-bottom: 12px; border-radius: 4px;
        border-left: 5px solid #333;
    }
    .sentiment-tag {
        font-size: 0.75rem; font-weight: 800; padding: 3px 8px; border-radius: 3px;
        text-transform: uppercase; margin-bottom: 8px; display: inline-block;
    }
    .bullish { color: #000; background: #00FF41; border-left-color: #00FF41 !important; }
    .bearish { color: #000; background: #FF3131; border-left-color: #FF3131 !important; }
    .neutral { color: #fff; background: #333; }
    
    .status-box { 
        border: 2px solid #00FF41; padding: 30px; text-align: center; 
        font-weight: 800; font-size: 3rem; background-color: #050505;
        font-family: 'JetBrains Mono';
    }
    .terminal-header { font-family: 'JetBrains Mono'; color: #00FF41; margin-bottom: 25px; border-bottom: 1px solid #1a1a1a; padding-bottom: 10px; }
    .ai-summary { color: #00FF41; font-family: 'JetBrains Mono'; font-size: 0.85rem; margin-top: 8px; border-top: 1px solid #1a1a1a; padding-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self):
        # Acesso automático via Secrets
        self.api_key = st.secrets.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = "gemini-1.5-flash"
        self.load_verified_data()

    def load_verified_data(self):
        try:
            with open('verified_lexicons.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.bullish_keywords = data.get('bullish', {})
                self.bearish_keywords = data.get('bearish', {})
                self.oil_sources = data.get('sites', [])
        except:
            self.oil_sources = ["https://oilprice.com"]

    def get_deep_analysis(self, text):
        """Avaliação completa pelo Deep Reader da IA"""
        if not self.client: return 0.0, "NEUTRAL", "IA OFFLINE"
        try:
            contexto = list(self.bullish_keywords.keys()) + list(self.bearish_keywords.keys())
            prompt = f"Analise o impacto no WTI Crude Oil: '{text}'. Use seus léxicos: {contexto}. Retorne rigorosamente neste formato: [SCORE: -1.0 a 1.0] [LABEL: Bullish, Bearish ou Neutral] [DEEP_READER: 1 frase de conclusão técnica]"
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            
            score = float(re.findall(r"SCORE:\s*([-+]?\d*\.\d+|\d+)", response.text)[0])
            label = re.findall(r"LABEL:\s*(\w+)", response.text)[0].upper()
            summary = response.text.split("DEEP_READER:")[-1].strip()
            return score, label, summary
        except: return 0.0, "NEUTRAL", "Erro na análise neural."

@st.cache_data(ttl=300)
def auto_fetch_headlines(sources):
    collected = []
    for url in sources[:8]:
        try:
            article = Article(url)
            article.download(); article.parse()
            if len(article.title) > 10: collected.append(article.title)
        except: continue
    return collected

def main():
    engine = XTINeuralEngine()
    st.markdown('<div class="terminal-header">### < XTI/USD NEURAL TERMINAL v11.2 // DEEP READER ANALYTICS ></div>', unsafe_allow_html=True)
    
    # 1. SCAN AUTOMÁTICO DE NOTÍCIAS
    headlines = auto_fetch_headlines(engine.oil_sources)
    
    col_news, col_metrics = st.columns([1.8, 1])

    with col_news:
        st.write("🛰️ **LIVE NEWS FEED & AI EVALUATION**")
        impact_accumulator = []
        
        if not headlines:
            st.info("Varrendo fontes configuradas no JSON...")
        
        for news in headlines:
            score, label, summary = engine.get_deep_analysis(news)
            impact_accumulator.append(score)
            
            css_class = label.lower() if label in ["BULLISH", "BEARISH", "NEUTRAL"] else "neutral"
            
            st.markdown(f"""
                <div class="news-card {css_class}">
                    <div class="sentiment-tag {css_class}">{label} | SCORE: {score:+.2f}</div>
                    <div style="color:white; font-weight:700; font-size:1.1rem;">{news}</div>
                    <div class="ai-summary">DEEP READER: {summary}</div>
                </div>
            """, unsafe_allow_html=True)

    with col_metrics:
        # 2. MERCADO E VEREDITO
        try:
            data = yf.download("CL=F", period="1d", interval="1m", progress=False)
            price = data['Close'].iloc[-1].values[0]
            change = ((price - data['Open'].iloc[0].values[0]) / data['Open'].iloc[0].values[0]) * 100
        except: price = 0.0; change = 0.0

        avg_score = np.mean(impact_accumulator) if impact_accumulator else 0.0
        veredito = "BUY" if avg_score > 0.15 else "SELL" if avg_score < -0.15 else "HOLD"
        v_color = "#00FF41" if veredito == "BUY" else "#FF3131" if veredito == "SELL" else "#FFFF00"
        
        st.markdown(f"""
            <div class="status-box" style="border-color:{v_color}; color:{v_color};">
                {veredito}<br>
                <span style="font-size:1rem; color:white;">SYSTEM CONFIDENCE: {abs(avg_score)*100:.1f}%</span>
            </div>
        """, unsafe_allow_html=True)

        st.metric("WTI CRUDE OIL", f"${price:.2f}", f"{change:+.2f}%")
        
        if not data.empty:
            fig = go.Figure(go.Scatter(y=data['Close'].values.flatten(), line=dict(color='#00FF41', width=3), fill='tozeroy'))
            fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(visible=False), yaxis=dict(side="right"))
            # Atualizado para seguir a regra de 2026: use width='stretch'
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

if __name__ == "__main__":
    main()
