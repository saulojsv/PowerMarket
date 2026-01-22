import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import feedparser
import json
import os
import re
from datetime import datetime
# Necessário: pip install streamlit-autorefresh
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE INTERFACE PROFISSIONAL ---
st.set_page_config(page_title="XTI NEURAL | TERMINAL v9.4", layout="wide")

# Refresh Automático: Atualiza a dashboard a cada 60 segundos
st_autorefresh(interval=60000, key="terminal_refresh")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; }
    header, [data-testid="stHeader"] { background-color: #000000; }
    
    html, body, [class*="css"] { 
        background-color: #000000; 
        color: #e0e0e0; 
        font-family: 'JetBrains Mono', monospace; 
    }

    /* News Cards com Alto Contraste */
    .news-card { 
        background-color: #0a0a0a; 
        border: 1px solid #333333;
        border-left: 5px solid #00FF41; 
        padding: 18px; 
        margin-bottom: 12px; 
        border-radius: 6px;
    }
    .news-title { 
        font-weight: 700; 
        font-size: 1rem; 
        color: #ffffff !important; 
        margin-bottom: 8px;
        display: block;
    }
    /* Destaque para palavras aprendidas nos Lexicons */
    .highlight {
        color: #00FF41;
        background: rgba(0, 255, 65, 0.15);
        font-weight: bold;
        padding: 0 4px;
        border-radius: 3px;
    }
    .news-ai { 
        font-size: 0.8rem; 
        color: #00FF41; 
        font-weight: bold;
        text-transform: uppercase; 
        letter-spacing: 1.2px;
        background: rgba(0, 255, 65, 0.1);
        padding: 2px 8px;
        border-radius: 4px;
    }
    .news-ai-bear { color: #FF3131 !important; background: rgba(255, 49, 49, 0.1) !important; }

    div[data-testid="stMetric"] { 
        background-color: #0a0a0a !important; 
        border: 1px solid #262626 !important; 
        padding: 20px !important; 
        border-radius: 8px !important;
    }
    
    .status-box { 
        border: 2px solid #00FF41; 
        padding: 40px; 
        text-align: center; 
        font-weight: 800; 
        text-transform: uppercase; 
        font-size: 2.2rem; 
        background-color: #050505;
        box-shadow: 0 0 30px rgba(0, 255, 65, 0.1);
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self):
        self.risk_threshold = 0.70
        self.lexicon_file = 'verified_lexicons.json'
        self.load_lexicons()

    def load_lexicons(self):
        # Carrega a base que você forneceu
        if os.path.exists(self.lexicon_file):
            with open(self.lexicon_file, 'r') as f:
                data = json.load(f)
                self.bullish_keywords = data.get('bullish', {})
                self.bearish_keywords = data.get('bearish', {})
        else:
            self.bullish_keywords = {'cut': 0.8, 'inventory draw': 0.7}
            self.bearish_keywords = {'inventory build': -0.6, 'oil glut': -0.9}

    def analyze_single_news(self, title):
        title_low = title.lower()
        impact = 0.0
        display_title = title
        
        # Unifica léxicos para busca
        all_terms = {**self.bullish_keywords, **self.bearish_keywords}
        # Ordena por tamanho para pegar termos compostos primeiro (ex: 'production cut' antes de 'cut')
        for word in sorted(all_terms.keys(), key=len, reverse=True):
            if word in title_low:
                impact += all_terms[word]
                # Destaca a palavra no título para a foto
                reg = re.compile(re.escape(word), re.IGNORECASE)
                display_title = reg.sub(f'<span class="highlight">{word}</span>', display_title)

        sentiment = "NEUTRAL / STABLE"
        css_class = ""
        if impact > 0:
            sentiment = f"BULLISH | IMPACT: +{impact:.2f}"
        elif impact < 0:
            sentiment = f"BEARISH | IMPACT: {impact:.2f}"
            css_class = "news-ai-bear"
            
        return sentiment, css_class, impact, display_title

@st.cache_data(ttl=60)
def fetch_headlines():
    feeds = ["https://oilprice.com/rss/main", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"]
    headlines = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:8]: headlines.append(entry.title)
        except: continue
    return headlines if headlines else ["Sincronizando feeds globais..."]

@st.cache_data(ttl=60)
def get_market_intelligence():
    try:
        xti = yf.download("CL=F", period="2d", interval="1m", progress=False)
        dxy = yf.download("DX-Y.NYB", period="2d", interval="1m", progress=False)
        prices = xti['Close'].iloc[:, 0].tolist() if isinstance(xti['Close'], pd.DataFrame) else xti['Close'].tolist()
        dxy_close = dxy['Close'].iloc[:, 0] if isinstance(dxy['Close'], pd.DataFrame) else dxy['Close']
        dxy_pct = dxy_close.pct_change().iloc[-1]
        return [float(p) for p in prices], float(dxy_pct)
    except:
        return [75.0]*10, 0.0

def main():
    engine = XTINeuralEngine()
    st.markdown("### < XTI/USD NEURAL TERMINAL v9.4 >")
    
    tab_ops, tab_lex = st.tabs(["⚡ OPERATIONAL TERMINAL", "🧠 AI KNOWLEDGE BASE"])

    with tab_ops:
        st.write(f"CORE: ACTIVE // SYNC: {datetime.now().strftime('%H:%M:%S')} // REFRESH: 60s")
        
        headlines = fetch_headlines()
        prices, dxy_delta = get_market_intelligence()
        
        news_impact_sum = 0.0
        interpreted_news = []
        for h in headlines:
            sentiment, css_class, impact, h_display = engine.analyze_single_news(h)
            interpreted_news.append({"title": h_display, "ai_desc": sentiment, "class": css_class})
            news_impact_sum += impact

        # Cálculo de Veredito
        ai_sentiment = float(np.clip(news_impact_sum / 2, -1, 1))
        z_score = float((pd.Series(prices).iloc[-1] - pd.Series(prices).mean()) / pd.Series(prices).std())
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
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    with tab_lex:
        st.markdown("#### 🧠 LÉXICOS VERIFICADOS EM USO")
        col_b, col_s = st.columns(2)
        with col_b:
            st.success(f"🟢 BULLISH ({len(engine.bullish_keywords)} termos)")
            st.json(engine.bullish_keywords)
        with col_s:
            st.error(f"🔴 BEARISH ({len(engine.bearish_keywords)} termos)")
            st.json(engine.bearish_keywords)

if __name__ == "__main__":
    main()
