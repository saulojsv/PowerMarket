import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import json
import os
import re
import google.generativeai as genai
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE INTERFACE ---
st.set_page_config(page_title="XTI NEURAL | TERMINAL v9.9", layout="wide")
st_autorefresh(interval=60000, key="terminal_refresh")

# --- CSS PROFISSIONAL (FIM DOS FUNDOS BRANCOS) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    
    /* Reset Global para Dark Mode Total */
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; }
    header, [data-testid="stHeader"] { background-color: #000000; }
    
    /* Estilização de Text Areas e Inputs - Removendo fundos brancos */
    div[data-baseweb="textarea"] { background-color: #0a0a0a !important; border-radius: 8px; }
    textarea { background-color: #0a0a0a !important; color: #00FF41 !important; font-family: 'JetBrains Mono' !important; }
    div[data-baseweb="input"] { background-color: #0a0a0a !important; }
    input { background-color: #0a0a0a !important; color: #00FF41 !important; }

    /* Estilização de JSON e Code blocks */
    div[data-testid="stJson"] { background-color: #0a0a0a !important; border: 1px solid #1a1a1a; }
    
    /* Cards de Notícias */
    .news-card { 
        background-color: #0a0a0a; border: 1px solid #333333; border-left: 5px solid #00FF41; 
        padding: 18px; margin-bottom: 12px; border-radius: 6px;
    }
    .news-title { font-weight: 700; font-size: 1rem; color: #ffffff !important; display: block; margin-bottom: 8px; }
    .highlight { color: #00FF41; background: rgba(0, 255, 65, 0.15); font-weight: bold; padding: 0 4px; border-radius: 3px; }
    .news-ai { 
        font-size: 0.8rem; color: #00FF41; font-weight: bold; text-transform: uppercase; 
        background: rgba(0, 255, 65, 0.1); padding: 4px 10px; border-radius: 4px;
    }
    .news-ai-bear { color: #FF3131 !important; background: rgba(255, 49, 49, 0.1) !important; }

    /* Verdict Box */
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
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None
        self.load_lexicons()

    def load_lexicons(self):
        # Base Sincronizada com 22 léxicos das imagens fornecidas
        self.bullish_keywords = {
            "production cut": 0.8, "inventory draw": 0.7, "opec quota": 0.5,
            "supply disruption": 0.9, "demand growth": 0.6, "refinery outage": 0.5,
            "geopolitical tension": 0.8, "sanctions": 0.7, "rig count decrease": 0.4,
            "export ban": 0.8, "soft landing": 0.4, "crude imports": 0.3, "output freeze": 0.6
        }
        self.bearish_keywords = {
            "inventory build": -0.6, "shale output": -0.4, "strategic reserve": -0.3,
            "interest rate hike": -0.5, "dollar strength": -0.4, "oil glut": -0.9,
            "rig count increase": -0.3, "recession fears": -0.8, "well completion": -0.3,
            "drilling productivity": -0.4, "upstream investment": -0.2, "fuel switching": -0.3,
            "industrial activity contraction": -0.7, "electric vehicle penetration": -0.5
        }

    def get_neural_sentiment(self, text):
        """Usa a API do Gemini para análise profunda de sentimento"""
        if not self.model: return 0.0
        try:
            prompt = f"Analise o impacto no preço do petróleo (WTI) para esta manchete. Retorne APENAS um número entre -1.0 (muito bearish) e 1.0 (muito bullish): {text}"
            response = self.model.generate_content(prompt)
            score = float(re.findall(r"[-+]?\d*\.\d+|\d+", response.text)[0])
            return score
        except: return 0.0

    def analyze_single_news(self, title):
        title_low = title.lower()
        impact = 0.0
        display_title = title
        
        # 1. Análise Léxica (Regex)
        all_terms = {**self.bullish_keywords, **self.bearish_keywords}
        for word in sorted(all_terms.keys(), key=len, reverse=True):
            if word in title_low:
                impact += all_terms[word]
                reg = re.compile(re.escape(word), re.IGNORECASE)
                display_title = reg.sub(f'<span class="highlight">{word}</span>', display_title)

        # 2. Análise Neural (Gemini) - Peso de 50% na decisão final da notícia
        neural_score = self.get_neural_sentiment(title)
        final_impact = (impact + neural_score) / 2 if neural_score != 0 else impact

        sentiment = "NEUTRAL / STABLE"
        css_class = ""
        if final_impact > 0:
            sentiment = f"BULLISH | IMPACT: +{final_impact:.2f}"
        elif final_impact < 0:
            sentiment = f"BEARISH | IMPACT: {final_impact:.2f}"
            css_class = "news-ai-bear"
            
        return sentiment, css_class, final_impact, display_title

@st.cache_data(ttl=60)
def get_market_intelligence():
    try:
        xti = yf.download("CL=F", period="2d", interval="5m", progress=False)
        dxy = yf.download("DX-Y.NYB", period="2d", interval="5m", progress=False)
        if xti.empty or dxy.empty: return None, 0.0
        prices = xti['Close'].iloc[:, 0].dropna().tolist()
        dxy_close = dxy['Close'].iloc[:, 0]
        dxy_pct = dxy_close.pct_change().iloc[-1]
        return prices, float(dxy_pct)
    except: return None, 0.0

def main():
    # --- SIDEBAR: CONTROLE DE ENTRADA (MÉTODO FOTO ANTES) ---
    with st.sidebar:
        st.markdown("### 🛰️ UPLINK: MARKET SNAPSHOT")
        ticker = st.text_input("Ticker Symbol", "CL=F")
        gemini_api = st.text_input("Gemini API Key", type="password")
        
        st.markdown("---")
        st.markdown("### 🧠 UPLINK: 22 LEXICONS")
        manual_corpus = st.text_area("News Corpus Analysis:", placeholder="Cole aqui as manchetes da OPEC, EIA, Reuters...", height=300)
        
        dxy_manual = st.slider("DXY Daily Change (%)", -2.0, 2.0, -0.25)

    engine = XTINeuralEngine(api_key=gemini_api)
    st.markdown(f"### < XTI/USD NEURAL TERMINAL v9.9 // AI: {'ACTIVE' if gemini_api else 'LEXICON ONLY'} >")
    
    tab_ops, tab_lex = st.tabs(["⚡ OPERATIONAL TERMINAL", "🧠 AI KNOWLEDGE BASE"])

    with tab_ops:
        prices_raw, dxy_auto = get_market_intelligence()
        # Prioriza o slider manual se o usuário estiver ajustando para a foto
        dxy_delta = dxy_manual / 100 if dxy_manual != -0.25 else dxy_auto
        
        if prices_raw is None or len(prices_raw) < 2:
            st.warning("Aguardando uplink de dados...")
            prices = [0.0, 0.0]
            z_score = 0.0
        else:
            prices = prices_raw
            series = pd.Series(prices)
            z_score = float((series.iloc[-1] - series.mean()) / series.std()) if series.std() != 0 else 0.0

        # Processamento das Notícias do Corpus Manual
        headlines = [h.strip() for h in manual_corpus.split('\n') if len(h.strip()) > 5]
        if not headlines: headlines = ["Sincronizando feeds globais... Aguardando Corpus."]
        
        news_impact_sum = 0.0
        interpreted_news = []
        for h in headlines:
            sentiment, css_class, impact, h_display = engine.analyze_single_news(h)
            interpreted_news.append({"title": h_display, "ai_desc": sentiment, "class": css_class})
            news_impact_sum += impact

        # --- LÓGICA DE VEREDITO ---
        ai_sentiment = float(np.clip(news_impact_sum / (len(headlines) or 1), -1, 1))
        arb_bias = float(np.clip(-dxy_delta * 10, -1, 1))
        final_score = (ai_sentiment * 0.45) + (arb_bias * 0.35) + (-np.clip(z_score/3, -1, 1) * 0.20)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI CRUDE", f"${prices[-1]:.2f}", f"{prices[-1]-prices[-2]:.2f}")
        c2.metric("SENTIMENT", f"{ai_sentiment:+.2f}")
        c3.metric("DXY ARB", f"{arb_bias:+.2f}")
        c4.metric("MATH BIAS", f"{z_score:+.2f}")

        st.markdown("---")
        col_news, col_verdict = st.columns([1.8, 1])

        with col_news:
            st.markdown("#### IA LEXICON INTERPRETATION")
            for item in interpreted_news:
                st.markdown(f"""
                    <div class="news-card">
                        <span class="news-title">{item['title']}</span>
                        <span class="news-ai {item['class']}">AI DECODER >> {item['ai_desc']}</span>
                    </div>
                """, unsafe_allow_html=True)

        with col_verdict:
            st.markdown("#### STRATEGIC VERDICT")
            conf = abs(final_score) * 100
            color = "#00FF41" if final_score > engine.risk_threshold else "#FF3131" if final_score < -engine.risk_threshold else "#FFFF00"
            label = "BUY / LONG" if final_score > engine.risk_threshold else "SELL / SHORT" if final_score < -engine.risk_threshold else "NEUTRAL"
            
            st.markdown(f"""
                <div class="status-box" style="border-color: {color}; color: {color};">
                    {label}<br>
                    <span style="font-size: 0.9rem; color: #ffffff; opacity: 0.8;">CONFIDENCE: {conf:.1f}%</span>
                </div>
            """, unsafe_allow_html=True)

            fig = go.Figure(go.Scatter(y=prices[-50:], line=dict(color='#00FF41', width=3), fill='tozeroy', fillcolor='rgba(0,255,65,0.05)'))
            fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False), yaxis=dict(showgrid=True, gridcolor='#1a1a1a', side="right"))
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    with tab_lex:
        st.markdown("#### 🧠 LÉXICOS VERIFICADOS (SYNC v9.9)")
        col_b, col_s = st.columns(2)
        with col_b:
            st.success(f"🟢 BULLISH ({len(engine.bullish_keywords)} termos)")
            st.json(engine.bullish_keywords)
        with col_s:
            st.error(f"🔴 BEARISH ({len(engine.bearish_keywords)} termos)")
            st.json(engine.bearish_keywords)

if __name__ == "__main__":
    main()
