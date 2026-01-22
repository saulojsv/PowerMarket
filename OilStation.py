import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import feedparser
from datetime import datetime

# --- CONFIGURAÇÃO DE INTERFACE PROFISSIONAL ---
st.set_page_config(page_title="XTI NEURAL | TERMINAL", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    
    .main { background-color: #000000 !important; }
    [data-testid="stAppViewContainer"] { background-color: #000000; }
    header, [data-testid="stHeader"] { background-color: #000000; }
    
    html, body, [class*="css"] { 
        background-color: #000000; 
        color: #00FF41; 
        font-family: 'JetBrains Mono', monospace; 
    }

    .news-card { 
        background-color: #050505; 
        border: 1px solid #1a1a1a;
        border-left: 4px solid #00FF41; 
        padding: 15px; 
        margin-bottom: 10px; 
        border-radius: 4px;
    }
    .news-title { font-weight: bold; font-size: 0.9rem; color: #ffffff; margin-bottom: 5px; }
    .news-ai { font-size: 0.75rem; color: #00FF41; text-transform: uppercase; letter-spacing: 1px; }
    .news-ai-bear { color: #FF3131; }

    div[data-testid="stMetric"] { 
        background-color: #050505 !important; 
        border: 1px solid #1a1a1a !important; 
        padding: 20px !important; 
        border-radius: 5px !important;
    }
    
    .status-box { 
        border: 1px solid #00FF41; 
        padding: 30px; 
        text-align: center; 
        font-weight: bold; 
        text-transform: uppercase; 
        font-size: 1.5rem; 
        background-color: #050505;
        box-shadow: inset 0 0 15px #00FF4115;
    }
    </style>
    """, unsafe_allow_html=True)

class XTINeuralEngine:
    def __init__(self):
        self.risk_threshold = 0.70
        self.bullish_keywords = {'cut': 0.4, 'sanction': 0.45, 'war': 0.6, 'tension': 0.3, 'draw': 0.3, 'unrest': 0.35, 'opec': 0.25}
        self.bearish_keywords = {'increase': -0.3, 'glut': -0.5, 'build': -0.3, 'recession': -0.6, 'surplus': -0.4, 'slowdown': -0.4}

    def analyze_single_news(self, title):
        title_low = title.lower()
        impact = 0.0
        sentiment = "NEUTRAL / STABLE"
        css_class = ""

        for word, val in {**self.bullish_keywords, **self.bearish_keywords}.items():
            if word in title_low:
                impact += val
        
        if impact > 0:
            sentiment = f"BULLISH | IMPACT: +{impact:.2f}"
        elif impact < 0:
            sentiment = f"BEARISH | IMPACT: {impact:.2f}"
            css_class = "news-ai-bear"
            
        return sentiment, css_class, impact

@st.cache_data(ttl=600)
def fetch_headlines():
    feeds = ["https://oilprice.com/rss/main", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"]
    headlines = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:6]: headlines.append(entry.title)
        except: continue
    return headlines if headlines else ["Sincronizando feeds globais..."]

@st.cache_data(ttl=300)
def get_market_intelligence():
    try:
        xti = yf.download("CL=F", period="5d", interval="1h", progress=False)
        dxy = yf.download("DX-Y.NYB", period="2d", interval="1h", progress=False)
        
        # Tratamento para garantir que extraímos valores numéricos simples
        prices = xti['Close'].iloc[:, 0].tolist() if isinstance(xti['Close'], pd.DataFrame) else xti['Close'].tolist()
        
        # Cálculo seguro do delta DXY
        dxy_close = dxy['Close'].iloc[:, 0] if isinstance(dxy['Close'], pd.DataFrame) else dxy['Close']
        dxy_pct = dxy_close.pct_change().iloc[-1]
        
        # Se dxy_pct for NaN, define como 0
        if np.isnan(dxy_pct): dxy_pct = 0.0
            
        return [float(p) for p in prices], float(dxy_pct)
    except:
        return [75.0]*10, 0.0

def main():
    engine = XTINeuralEngine()
    
    st.markdown("### < XTI/USD NEURAL TERMINAL v9.1 >")
    st.write(f"CORE: ACTIVE // {datetime.now().strftime('%H:%M:%S')} // UPLINK: STABLE")
    st.markdown("---")

    headlines = fetch_headlines()
    prices, dxy_delta = get_market_intelligence()
    
    # Processamento individualizado
    news_impact_sum = 0.0
    interpreted_news = []
    for h in headlines:
        sentiment, css_class, impact = engine.analyze_single_news(h)
        interpreted_news.append({"title": h, "ai_desc": sentiment, "class": css_class})
        news_impact_sum += impact

    # Cálculos Finais
    ai_sentiment = float(np.clip(news_impact_sum / 2, -1, 1))
    z_score = float((pd.Series(prices).iloc[-1] - pd.Series(prices).mean()) / pd.Series(prices).std())
    arb_bias = float(np.clip(-dxy_delta * 10, -1, 1))
    
    final_score = (ai_sentiment * 0.45) + (arb_bias * 0.35) + (-np.clip(z_score/3, -1, 1) * 0.20)

    # MÉTRICAS
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("WTI CRUDE", f"${prices[-1]:.2f}", f"{prices[-1]-prices[-2]:.2f}")
    c2.metric("SENTIMENT", f"{ai_sentiment:+.2f}")
    c3.metric("DXY ARB", f"{arb_bias:+.2f}") # Corrigido para garantir float
    c4.metric("MATH BIAS", f"{z_score:+.2f}")

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_news, col_verdict = st.columns([1.8, 1])

    with col_news:
        st.markdown("#### IA LEXICON INTERPRETATION")
        for item in interpreted_news[:10]:
            st.markdown(f"""
                <div class="news-card">
                    <div class="news-title">{item['title']}</div>
                    <div class="news-ai {item['class']}">AI DECODER >> {item['ai_desc']}</div>
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
                <span style="font-size: 0.8rem; opacity: 0.8;">CONFIDENCE: {conf:.1f}%</span>
            </div>
        """, unsafe_allow_html=True)

        fig = go.Figure(go.Scatter(y=prices, line=dict(color='#00FF41', width=2), fill='tozeroy', fillcolor='rgba(0,255,65,0.05)'))
        fig.update_layout(
            template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(visible=False), yaxis=dict(showgrid=True, gridcolor='#1a1a1a', side="right")
        )
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

if __name__ == "__main__":
    main()
