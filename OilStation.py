import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import feedparser  # Necessário: pip install feedparser
from datetime import datetime

# --- CONFIGURAÇÃO E ESTÉTICA ---
st.set_page_config(page_title="XTI", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    html, body, [class*="css"] { background-color: #050505; color: #00FF41; font-family: 'JetBrains Mono', monospace; }
    .stMetric { background-color: #0a0a0a; border: 1px solid #00FF41; padding: 15px; box-shadow: 0 0 15px #00FF4122; }
    .status-box { border: 2px solid #00FF41; padding: 25px; text-align: center; font-weight: bold; text-transform: uppercase; font-size: 1.4rem; background-color: #0d0d0d; }
    .news-card { background-color: #0a0a0a; border-left: 4px solid #00FF41; padding: 10px; margin-bottom: 5px; font-size: 0.8rem; line-height: 1.2; }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self):
        self.risk_threshold = 0.70
        self.weights = {'sentiment': 0.45, 'arbitrage': 0.30, 'math': 0.25}

    def compute_z_score(self, prices):
        if len(prices) < 5: return 0
        series = pd.Series(prices)
        return (series.iloc[-1] - series.mean()) / series.std()

    def evaluate_news_impact(self, news_list):
        bullish = {'cut': 0.35, 'sanction': 0.40, 'war': 0.50, 'tension': 0.30, 'draw': 0.25, 'unrest': 0.30}
        bearish = {'increase': -0.30, 'glut': -0.45, 'build': -0.25, 'recession': -0.50, 'surplus': -0.35}
        
        total_score, detected_events = 0.0, []
        full_text = " ".join(news_list).lower()
        
        for word, val in {**bullish, **bearish}.items():
            if word in full_text:
                total_score += val
                detected_events.append((word.upper(), "BULLISH" if val > 0 else "BEARISH"))
        
        return np.clip(total_score, -1, 1), detected_events

# --- CAPTURA AUTOMÁTICA DE NOTÍCIAS (RSS) ---
@st.cache_data(ttl=600)
def fetch_auto_news():
    """Varre feeds RSS de energia automaticamente."""
    feeds = [
        "https://oilprice.com/rss/main",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"
    ]
    headlines = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:8]:
                headlines.append(entry.title)
        except: continue
    return headlines

def main():
    engine = XTINeuralEngine()
    
    st.markdown("### < XTIUSD // NEURAL COMMAND v7.5 - FULL AUTO >")
    st.write(f"CORE_SYSTEM: ONLINE // {datetime.now().strftime('%H:%M:%S')} // UPLINK: GEMINI_RSS_ACTIVE")
    st.markdown("---")

    # AUTO FETCH DATA
    with st.spinner('Sincronizando Lexicons e Mercado...'):
        headlines = fetch_auto_news()
        
        @st.cache_data(ttl=300)
        def get_market_data():
            try:
                # Baixa Petróleo e Dólar (DXY) simultaneamente
                xti = yf.download("CL=F", period="5d", interval="1h", progress=False)
                dxy = yf.download("DX-Y.NYB", period="2d", interval="1h", progress=False)
                
                prices = xti['Close'].tolist()
                dxy_pct = dxy['Close'].pct_change().iloc[-1]
                return prices, dxy_pct
            except:
                return [75.0]*10, 0.0

        prices, dxy_delta = get_market_data()

    # PROCESSAMENTO
    ai_sentiment, events = engine.evaluate_news_impact(headlines)
    z_score = engine.compute_z_score(prices)
    arb_bias = np.clip(-dxy_delta * 10, -1, 1)
    
    final_score = (ai_sentiment * 0.45) + (arb_bias * 0.30) + (-np.clip(z_score/3, -1, 1) * 0.25)

    # UI METRICS
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("XTI SPOT", f"${prices[-1]:.2f}", f"{prices[-1]-prices[-2]:.2f}")
    m2.metric("STAT BIAS (Z)", f"{z_score:.2f}", "STABLE")
    m3.metric("ARB VECTOR", f"{arb_bias:+.2f}", "DXY AUTO")
    m4.metric("NEURAL SENTIMENT", f"{ai_sentiment:+.2f}", f"{len(headlines)} HEADLINES")

    st.markdown("---")
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("#### LIVE LEXICON FEED (AUTOMATIC)")
        for h in headlines[:12]:
            st.markdown(f'<div class="news-card">{h}</div>', unsafe_allow_html=True)
        
        st.markdown("#### DETECTED VECTORS")
        if events:
            ev_cols = st.columns(4)
            for i, (ev, vec) in enumerate(list(set(events))[:8]):
                color = "#00FF41" if vec == "BULLISH" else "#FF0000"
                ev_cols[i%4].markdown(f"<span style='color:{color}'>● {ev}</span>", unsafe_allow_html=True)

    with col_right:
        st.markdown("#### STRATEGIC VERDICT")
        conf = abs(final_score) * 100
        
        if final_score > engine.risk_threshold:
            st.markdown(f"<div class='status-box' style='color:#00FF41; border-color:#00FF41;'>BUY / LONG<br>{conf:.1f}% CONFIDENCE</div>", unsafe_allow_html=True)
        elif final_score < -engine.risk_threshold:
            st.markdown(f"<div class='status-box' style='color:#FF0000; border-color:#FF0000;'>SELL / SHORT<br>{conf:.1f}% CONFIDENCE</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='status-box' style='color:#FFFF00; border-color:#FFFF00;'>STANDBY / NEUTRAL</div>", unsafe_allow_html=True)

        st.markdown("---")
        # Gráfico minificado para scannability rápida
        fig = go.Figure(go.Scatter(y=prices, line=dict(color='#00FF41', width=2), fill='tozeroy'))
        fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0),
                          xaxis_visible=False, yaxis_visible=True, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, width='stretch')

if __name__ == "__main__":
    main()
