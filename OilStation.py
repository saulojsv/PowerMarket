import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- CORE CONFIGURATION & CYBERPUNK STYLING ---
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
        border-radius: 0px;
        box-shadow: 0 0 10px #00FF4122;
    }
    .status-box {
        border: 2px solid #00FF41;
        padding: 20px;
        text-align: center;
        font-weight: bold;
        text-transform: uppercase;
        font-size: 1.2rem;
    }
    .news-card {
        background-color: #0a0a0a;
        border-left: 5px solid #00FF41;
        padding: 10px;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    """
    Quantitative Intelligence Engine v6.0
    Fusion of Mathematical Statistics, Macro Arbitrage, and Semantic AI.
    """
    def __init__(self):
        self.risk_threshold = 0.75
        # Weighted Allocation: News is the primary driver (45%)
        self.weights = {'sentiment': 0.45, 'arbitrage': 0.30, 'math': 0.25}

    def compute_z_score(self, data):
        if len(data) < 2: return 0
        mean = np.mean(data)
        std = np.std(data)
        return (data[-1] - mean) / std if std != 0 else 0

    def compute_arb_bias(self, dxy_delta, cad_delta):
        # Inverse macro correlation logic
        bias = (-dxy_delta * 0.5) + (-cad_delta * 0.5)
        return np.clip(bias * 5, -1, 1)

    def calculate_final_confluence(self, ai_score, arb_score, z_score):
        # Inverting Z-score for Mean Reversion logic
        inverted_z = -np.clip(z_score / 3, -1, 1)
        score = (ai_score * self.weights['sentiment']) + \
                (arb_score * self.weights['arbitrage']) + \
                (inverted_z * self.weights['math'])
        return score

    def evaluate_news_impact(self, news_text):
        """
        Simulates the Gemini Semantic Decoder. 
        In production, this strings the 22 lexicons and returns a score.
        """
        # Dictionary for keyword impact evaluation
        keywords = {
            'cut': 0.3, 'sanction': 0.4, 'war': 0.5, 'tension': 0.3, 'draw': 0.2, # Bullish
            'increase': -0.3, 'glut': -0.4, 'build': -0.2, 'recession': -0.5, 'truce': -0.4 # Bearish
        }
        
        score = 0.0
        words = news_text.lower().split()
        found_triggers = []
        
        for word, impact in keywords.items():
            if word in words:
                score += impact
                found_triggers.append((word.upper(), "BULLISH" if impact > 0 else "BEARISH"))
        
        return np.clip(score, -1, 1), found_triggers

def main():
    engine = XTINeuralEngine()
    
    # --- HEADER ---
    st.markdown("### < XTIUSD // NEURAL COMMAND CENTER v6.0 >")
    st.write(f"CORE_SYSTEM: ONLINE // {datetime.now().strftime('%H:%M:%S')} // UPLINK: GEMINI_AI_ACTIVE")
    st.markdown("---")

    # --- SIDEBAR: DATA INGESTION ---
    st.sidebar.header("MARKET SNAPSHOT")
    xti_price = st.sidebar.number_input("XTIUSD Price", value=78.50, step=0.01)
    dxy_delta = st.sidebar.number_input("DXY % Change", value=-0.20) / 100
    cad_delta = st.sidebar.number_input("USDCAD % Change", value=-0.15) / 100
    
    st.sidebar.header("22 LEXICON INPUT")
    news_input = st.sidebar.text_area("Input News Headlines:", 
                                     height=150, 
                                     value="OPEC confirms production cuts until next year. API reports massive inventory draw. Middle East tensions rising.")
    
    # --- PROCESSING ---
    ai_sentiment, triggers = engine.evaluate_news_impact(news_input)
    # Mocking price history
    history = [76.5, 76.8, 77.2, 77.5, 78.0, 78.4, 78.2, 78.5, 78.7, xti_price]
    
    z_score = engine.compute_z_score(history)
    arb_bias = engine.compute_arb_bias(dxy_delta, cad_delta)
    final_score = engine.calculate_final_confluence(ai_sentiment, arb_bias, z_score)

    # --- TOP METRICS ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SPOT PRICE", f"${xti_price}", f"{xti_price-78.0:.2f}")
    c2.metric("STATISTICAL BIAS (Z)", f"{z_score:.2f}", "EXPENSIVE" if z_score > 1.5 else "CHEAP")
    c3.metric("MACRO ARBITRAGE", f"{arb_bias:.2f}", "BULLISH" if arb_bias > 0 else "BEARISH")
    c4.metric("NEWS SENTIMENT", f"{ai_sentiment:.2f}", "STRENGTHENING" if ai_sentiment > 0 else "WEAKENING")

    st.markdown("---")

    # --- MAIN DASHBOARD LAYOUT ---
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("#### MARKET STRUCTURE & TREND PROJECTION")
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=history, mode='lines+markers', name='XTIUSD', line=dict(color='#00FF41', width=3)))
        fig.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                          margin=dict(l=0, r=0, t=0, b=0), height=350)
        st.plotly_chart(fig, use_container_width=True)
        
        # NEWS INTERPRETATION FEED
        st.markdown("#### AI NEWS INTERPRETATION & KEY IMPACTS")
        if triggers:
            for trigger, vector in triggers:
                color = "#00FF41" if vector == "BULLISH" else "#FF0000"
                st.markdown(f"""
                <div class="news-card" style="border-left-color: {color};">
                    <strong>EVENT DETECTED:</strong> {trigger} | <strong>VECTOR:</strong> {vector}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.write("No significant semantic triggers detected in current lexicons.")

    with col_right:
        st.markdown("#### FINAL COMMAND VERDICT")
        conf_pct = abs(final_score) * 100
        
        if final_score > engine.risk_threshold:
            st.markdown(f"<div class='status-box' style='color:#00FF41; border-color:#00FF41;'>BUY / LONG<br>{conf_pct:.1f}% CONFIDENCE</div>", unsafe_allow_html=True)
            st.write("**PROBABILITY TREND:** Bullish expansion confirmed by news fusion.")
        elif final_score < -engine.risk_threshold:
            st.markdown(f"<div class='status-box' style='color:#FF0000; border-color:#FF0000;'>SELL / SHORT<br>{conf_pct:.1f}% CONFIDENCE</div>", unsafe_allow_html=True)
            st.write("**PROBABILITY TREND:** Bearish trend accelerating via negative sentiment.")
        else:
            st.markdown(f"<div class='status-box' style='color:#FFFF00; border-color:#FFFF00;'>STANDBY / NEUTRAL<br>WAIT FOR CONFLUENCE</div>", unsafe_allow_html=True)
            st.write("**PROBABILITY TREND:** Noise dominant. Sentiment and Math are decoupled.")

        # SCORE BREAKDOWN
        st.markdown("---")
        st.markdown("#### WEIGHT DISTRIBUTION")
        st.write(f"Semantic Weight (News): {ai_sentiment * 45:.1f}%")
        st.write(f"Arbitrage Weight (DXY): {arb_bias * 30:.1f}%")
        st.write(f"Statistical Weight (Z): {(-z_score/3) * 25:.1f}%")

if __name__ == "__main__":
    main()
