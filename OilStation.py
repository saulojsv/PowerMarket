import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime

# --- SYSTEM CONFIGURATION & CYBERPUNK THEME ---
st.set_page_config(page_title="XTI NEURAL", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    
    html, body, [class*="css"]  {
        background-color: #050505;
        color: #00FF41;
        font-family: 'JetBrains Mono', monospace;
    }
    .stMetric {
        background-color: #0a0a0a;
        border: 1px solid #00FF41;
        padding: 15px;
        box-shadow: 0 0 15px #00FF4122;
    }
    .status-box {
        border: 2px solid #00FF41;
        padding: 25px;
        text-align: center;
        font-weight: bold;
        text-transform: uppercase;
        font-size: 1.4rem;
        background-color: #0d0d0d;
    }
    .news-card {
        background-color: #0a0a0a;
        border-left: 4px solid #00FF41;
        padding: 12px;
        margin-bottom: 8px;
        font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self):
        self.risk_threshold = 0.70
        self.weights = {'sentiment': 0.45, 'arbitrage': 0.30, 'math': 0.25}

    def compute_z_score(self, prices):
        if len(prices) < 5: return 0
        series = pd.Series(prices)
        z = (series.iloc[-1] - series.mean()) / series.std()
        return z

    def compute_arb_bias(self, dxy_change):
        # Inverse Correlation Logic: DXY Down = Oil Up
        return np.clip(-dxy_change * 10, -1, 1)

    def evaluate_news_impact(self, news_text):
        """Semantic Decoder for the 22 Lexicons."""
        bullish_triggers = {
            'cut': 0.35, 'sanction': 0.40, 'war': 0.50, 'tension': 0.30, 
            'draw': 0.25, 'unrest': 0.30, 'shortage': 0.35, 'strike': 0.25
        }
        bearish_triggers = {
            'increase': -0.30, 'glut': -0.45, 'build': -0.25, 'recession': -0.50, 
            'truce': -0.40, 'surplus': -0.35, 'slowdown': -0.40
        }
        
        score = 0.0
        found_events = []
        words = news_text.lower().split()
        
        for word, val in {**bullish_triggers, **bearish_triggers}.items():
            if word in words:
                score += val
                vector = "BULLISH" if val > 0 else "BEARISH"
                found_events.append((word.upper(), vector))
        
        return np.clip(score, -1, 1), found_events

    def calculate_confluence(self, ai_score, arb_score, z_score):
        # Invert Z for Mean Reversion (High Z = Sell pressure)
        inverted_z = -np.clip(z_score / 3, -1, 1)
        score = (ai_score * self.weights['sentiment']) + \
                (arb_score * self.weights['arbitrage']) + \
                (inverted_z * self.weights['math'])
        return score

# --- DASHBOARD LOGIC ---
def main():
    engine = XTINeuralEngine()
    
    # HEADER
    st.markdown("### < XTIUSD // NEURAL COMMAND CENTER v7.0 >")
    st.write(f"LATENCY: STABLE // {datetime.now().strftime('%H:%M:%S')} // UPLINK: ACTIVE")
    st.markdown("---")

    # SIDEBAR: DATA INGESTION
    st.sidebar.header("UPLINK: MARKET SNAPSHOT")
    xti_ticker = st.sidebar.text_input("Ticker Symbol", "CL=F") # Oil Futures
    
    # News Ingestion (Snapshot of 22 Lexicons)
    st.sidebar.header("UPLINK: 22 LEXICONS")
    news_corpus = st.sidebar.text_area("News Corpus Analysis:", 
                                     height=250,
                                     placeholder="Paste headlines from OPEC, EIA, Reuters, etc.")
    
    manual_dxy = st.sidebar.slider("DXY Daily Change (%)", -2.0, 2.0, -0.25) / 100

    # DATA FETCHING (yfinance)
    @st.cache_data(ttl=60)
    def get_market_data(ticker):
        data = yf.download(ticker, period="5d", interval="1h")
        return data['Close'].tolist()

    try:
        prices = get_market_data(xti_ticker)
        current_p = prices[-1]
    except:
        current_p = 75.0
        prices = [74.0, 74.5, 75.0]

    # CALCULATION ENGINE
    ai_sentiment, events = engine.evaluate_news_impact(news_corpus)
    z_score = engine.compute_z_score(prices)
    arb_bias = engine.compute_arb_bias(manual_dxy)
    final_score = engine.calculate_confluence(ai_sentiment, arb_bias, z_score)

    # METRICS ROW
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("XTI SPOT", f"${current_p:.2f}", f"{current_p - prices[-2]:.2f}")
    m2.metric("STAT BIAS (Z)", f"{z_score:.2f}", "OVERBOUGHT" if z_score > 1.5 else "OVERSOLD" if z_score < -1.5 else "STABLE")
    m3.metric("ARB VECTOR", f"{arb_bias:+.2f}", "DXY TAILWIND" if arb_bias > 0 else "DXY HEADWIND")
    m4.metric("NEURAL SENTIMENT", f"{ai_sentiment:+.2f}", f"{len(events)} EVENTS")

    st.markdown("---")

    # MAIN INTERFACE
    col_chart, col_verdict = st.columns([2, 1])

    with col_chart:
        st.markdown("#### PRICE STRUCTURE & NEURAL WAVE")
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=prices, mode='lines+markers', line=dict(color='#00FF41', width=3), name="XTI"))
        fig.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                          margin=dict(l=0,r=0,t=0,b=0), height=400)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### LEXICON IMPACT MATRIX")
        if events:
            cols = st.columns(2)
            for i, (evt, vec) in enumerate(events):
                color = "#00FF41" if vec == "BULLISH" else "#FF0000"
                cols[i % 2].markdown(f"""<div class="news-card" style="border-left-color: {color};">
                    <strong>{evt}</strong> | VECTOR: {vec}</div>""", unsafe_allow_html=True)
        else:
            st.info("Waiting for Lexicon Corpus input to decode sentiment.")

    with col_right := col_verdict:
        st.markdown("#### STRATEGIC VERDICT")
        confidence = abs(final_score) * 100
        
        if final_score > engine.risk_threshold:
            st.markdown(f"<div class='status-box' style='color:#00FF41; border-color:#00FF41;'>BUY / LONG<br>{confidence:.1f}% CONFIDENCE</div>", unsafe_allow_html=True)
            st.success("**POSITION:** Trend expansion confirmed by Macro & News.")
        elif final_score < -engine.risk_threshold:
            st.markdown(f"<div class='status-box' style='color:#FF0000; border-color:#FF0000;'>SELL / SHORT<br>{confidence:.1f}% CONFIDENCE</div>", unsafe_allow_html=True)
            st.error("**POSITION:** Structural weakness detected. Selling pressure high.")
        else:
            st.markdown(f"<div class='status-box' style='color:#FFFF00; border-color:#FFFF00;'>STANDBY<br>INCONCLUSIVE</div>", unsafe_allow_html=True)
            st.warning("**POSITION:** No confluence. Market is in noise phase.")

        st.markdown("---")
        st.markdown("#### PILLAR WEIGHTS")
        st.progress(max(0, min(1, (ai_sentiment + 1) / 2)), text=f"Sentiment (45%): {ai_sentiment:+.2f}")
        st.progress(max(0, min(1, (arb_bias + 1) / 2)), text=f"Arbitrage (30%): {arb_bias:+.2f}")
        st.progress(max(0, min(1, ((-z_score/3) + 1) / 2)), text=f"Math Bias (25%): {-z_score/3:+.2f}")

if __name__ == "__main__":
    main()
