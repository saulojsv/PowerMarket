import pandas as pd
import re
import feedparser
import os
import json
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from collections import Counter

# --- 1. CONFIGURAÇÕES E ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD - ARBITRAGE", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v69_refresh")

st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle, #0D1421 0%, #050A12 100%); color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1rem;}
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    [data-testid="stMetricLabel"] { font-size: 10px !important; color: #94A3B8 !important; text-transform: uppercase; }
    
    .arbitrage-monitor {
        padding: 20px;
        border-radius: 5px;
        border: 1px solid #1E293B;
        background: rgba(0, 0, 0, 0.4);
        margin-bottom: 20px;
        text-align: center;
    }

    .scroll-container {
        height: 480px;
        overflow-y: auto;
        border: 1px solid rgba(30, 41, 59, 0.5);
        background: rgba(0, 0, 0, 0.2);
    }
    .scroll-container::-webkit-scrollbar { width: 4px; }
    .scroll-container::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 10px; }
    
    table { width: 100%; border-collapse: collapse; }
    th { color: #94A3B8 !important; font-size: 10px; text-transform: uppercase; border-bottom: 1px solid #1E293B; padding: 10px; position: sticky; top: 0; background: #050A12; z-index: 10; }
    td { font-size: 12px; padding: 10px; border-bottom: 1px solid #0D1421; }
    .pos-score { color: #00FFC8; font-weight: bold; }
    .neg-score { color: #FF4B4B; font-weight: bold; }
    
    .link-btn { 
        color: #00FFC8 !important; 
        text-decoration: none; 
        font-size: 10px; 
        font-weight: 700; 
        border: 1px solid #00FFC8; 
        padding: 2px 5px; 
        border-radius: 3px;
    }
    .link-btn:hover { background: #00FFC8; color: #050A12 !important; }

    .learned-box { border: 1px solid #334155; padding: 15px; border-radius: 8px; margin-bottom: 5px; background: #0F172A; }
    .learned-term { color: #FACC15; font-weight: bold; font-family: monospace; font-size: 14px; }
    .learned-count { color: #94A3B8; font-size: 11px; float: right; }
    .sentiment-tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; font-weight: bold; }

    div.stButton > button {
        width: 100%;
        border-radius: 4px;
        font-weight: bold;
        border: none;
        height: 32px;
        font-size: 11px;
    }
    .btn-approve button { background-color: #00FFC8 !important; color: #050A12 !important; }
    .btn-reject button { background-color: #FF4B4B !important; color: #FFFFFF !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURAÇÕES DE ARQUIVOS ---
MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"
MARKET_CACHE_FILE = "market_last_prices.json"
STOPWORDS = {'the', 'a', 'an', 'of', 'to', 'in', 'and', 'is', 'for', 'on', 'at', 'by', 'with', 'from', 'that', 'it', 'as', 'are', 'be', 'this', 'will', 'has', 'have', 'but', 'not', 'up', 'down', 'its', 'their', 'prices', 'oil', 'crude'}

RSS_SOURCES = {
    "Bloomberg Energy": "https://www.bloomberg.com/feeds/bview/energy.xml",
    "Reuters Oil": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "CNBC Commodities": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "FT Commodities": "https://www.ft.com/commodities?format=rss",
    "WSJ Energy": "https://feeds.a.dj.com/rss/RSSWSJ.xml",
    "OilPrice Main": "https://oilprice.com/rss/main",
    "Rigzone": "https://www.rigzone.com/news/rss/rigzone_latest.xml",
    "S&P Global Platts": "https://www.spglobal.com/platts/en/rss-feed/news/oil",
    "Energy Voice": "https://www.energyvoice.com/category/oil-and-gas/feed/",
    "EIA Today": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "Investing.com": "https://www.investing.com/rss/news_11.rss",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Yahoo Finance Oil": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Foreign Policy": "https://foreignpolicy.com/feed/",
    "Lloyds List": "https://lloydslist.maritimeintelligence.informa.com/RSS/News",
    "Marine Insight": "https://www.marineinsight.com/feed/",
    "Splash 247": "https://splash247.com/feed/",
    "OPEC Press": "https://www.opec.org/opec_web/en/press_room/311.xml",
    "IEA News": "https://www.iea.org/news/rss"
}

LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation|invasion": [9.8, 1, "Geopolitics (Conflict)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolitics (Sanctions)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Chokepoint Risk"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Regional Tensions"],
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "OPEC+ Policy"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "OPEC+ Supply"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "US Supply"],
    r"non-opec|brazil|guyana|canada|output surge": [7.0, -1, "Non-OPEC Supply"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Stocks (Deficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Stocks (Surplus)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refining/Margins"],
    r"crack spread|heating oil|jet fuel|diesel demand": [6.5, 1, "Distillates"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Weak Demand)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Strong Demand)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate": [7.5, -1, "Macro (Fed Tightening)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Fed Easing)"],
    r"dollar|dxy|greenback|fx|yields": [7.0, -1, "DXY Correlation"],
    r"gdp|pmi|manufacturing|industrial production": [6.8, 1, "Macro Indicators"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Speculative Flow"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Technical Analysis"],
    r"volatility|vix|contango|backwardation": [6.2, 1, "Term Structure"],
    r"algorithmic trading|ctas|margin call|liquidation": [6.0, 1, "Quant Flow"]
}

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r') as f: return json.load(f)
    return {}

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, indent=4)

def learn_patterns(text, category, score, current_memory):
    text = text.lower()
    text = re.sub(r'[^a-z\s-]', '', text)
    tokens = text.split()
    if category not in current_memory: current_memory[category] = {}
    ngrams = []
    if len(tokens) >= 2: ngrams.extend([' '.join(tokens[i:i+2]) for i in range(len(tokens)-1)])
    if len(tokens) >= 3: ngrams.extend([' '.join(tokens[i:i+3]) for i in range(len(tokens)-2)])
    for ph in ngrams:
        if set(ph.split()).issubset(STOPWORDS): continue
        if ph not in current_memory[category]: current_memory[category][ph] = {"count": 0, "sentiment_sum": 0.0}
        current_memory[category][ph]["count"] += 1
        current_memory[category][ph]["sentiment_sum"] += score
    return current_memory

def fetch_filtered_news():
    news_data = []
    DB_FILE = "Oil_Station_V54_Master.csv"
    brain_memory = load_json(MEMORY_FILE)
    verified_lex = load_json(VERIFIED_FILE)
    memory_updated = False
    
    for name, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                score, cat = 0.0, None
                title_low = entry.title.lower()
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        score = float(w * d)
                        cat = c
                        break
                for v_cat, v_phrases in verified_lex.items():
                    for phrase, weight in v_phrases.items():
                        if phrase in title_low:
                            score += weight
                            if not cat: cat = v_cat
                if score != 0:
                    news_data.append({
                        "Data": datetime.now().strftime("%H:%M:%S"),
                        "Fonte": name,
                        "Manchete": entry.title[:90],
                        "Alpha": score,
                        "Cat": cat,
                        "Link": entry.link
                    })
                    if cat:
                        brain_memory = learn_patterns(entry.title, cat, score, brain_memory)
                        memory_updated = True
        except: continue
            
    if memory_updated: save_json(MEMORY_FILE, brain_memory)
    if news_data:
        df_new = pd.DataFrame(news_data)
        if os.path.exists(DB_FILE):
            df_old = pd.read_csv(DB_FILE)
            pd.concat([df_new, df_old]).drop_duplicates(subset=['Manchete']).head(300).to_csv(DB_FILE, index=False)
        else: df_new.to_csv(DB_FILE, index=False)

@st.cache_data(ttl=120)
def get_market_metrics():
    tickers = {"WTI": "CL=F", "BRENT": "BZ=F", "DXY": "DX-Y.NYB"}
    
    # Fallback/Cache Inicial
    cached = load_json(MARKET_CACHE_FILE)
    prices = cached.get("prices", {"WTI": 0.0, "BRENT": 0.0, "DXY": 0.0})
    momentum = cached.get("momentum", 0.0)
    z_score = cached.get("z_score", 0.0)

    try:
        data = yf.download(list(tickers.values()), period="5d", interval="15m", progress=False, ignore_tz=True)
        if not data.empty and 'Close' in data:
            closes = data['Close'].ffill()
            for k, v in tickers.items(): 
                if v in closes.columns: prices[k] = float(closes[v].iloc[-1])
            if "BZ=F" in closes.columns and "CL=F" in closes.columns:
                spread = closes["BZ=F"] - closes["CL=F"]
                z_score = (spread.iloc[-1] - spread.mean()) / spread.std()
                momentum = float(closes["CL=F"].pct_change().iloc[-1])
            
            # Salva o sucesso no cache
            save_json(MARKET_CACHE_FILE, {"prices": prices, "momentum": momentum, "z_score": z_score})
    except Exception as e:
        st.toast(f"Usando Dados em Cache: API Limitada", icon="⚠️")
        
    return prices, momentum, z_score

def main():
    fetch_filtered_news()
    prices, momentum, z_score = get_market_metrics()
    df_news = pd.read_csv("Oil_Station_V54_Master.csv") if os.path.exists("Oil_Station_V54_Master.csv") else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0.0

    tab_dash, tab_brain = st.tabs(["📊 MONITOR DE ARBITRAGEM", "🧠 IA LEARNING CENTER"])

    with tab_dash:
        if avg_alpha > 6.0 and z_score < -1.5: arb_s, arb_c = "COMPRA AGRESSIVA", "#00FFC8"
        elif avg_alpha < -6.0 and z_score > 1.5: arb_s, arb_c = "VENDA AGRESSIVA", "#FF4B4B"
        else: arb_s, arb_c = "EQUILÍBRIO", "#94A3B8"

        st.markdown(f'<div class="arbitrage-monitor" style="border-color:{arb_c}; color:{arb_c};"><strong>{arb_s}</strong></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI", f"$ {prices['WTI']:.2f}", f"{momentum:.2%}")
        c2.metric("Z-SCORE", f"{z_score:.2f}")
        c3.metric("ALPHA", f"{avg_alpha:.2f}")
        c4.metric("DXY", f"{prices['DXY']:.2f}")
        
        col_g, col_t = st.columns([1, 2])
        with col_g:
            fig = go.Figure(go.Indicator(mode="gauge+number", value=avg_alpha, gauge={'axis': {'range': [-10, 10]}, 'bar': {'color': arb_c}}))
            fig.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, margin=dict(t=50, b=20))
            st.plotly_chart(fig, width='stretch')
        with col_t:
            if not df_news.empty:
                df_d = df_news.copy()
                df_d['Alpha'] = df_d['Alpha'].apply(lambda v: f'<span class="{"pos-score" if v>0 else "neg-score"}">{v}</span>')
                df_d['Link'] = df_d['Link'].apply(lambda x: f'<a href="{x}" target="_blank" class="link-btn">DETALHES</a>')
                table_html = df_d[['Data', 'Fonte', 'Manchete', 'Alpha', 'Link']].to_html(escape=False, index=False)
                st.markdown(f'<div class="scroll-container">{table_html}</div>', unsafe_allow_html=True)

    with tab_brain:
        st.header("Novas Expressões Detectadas (N-Grams)")
        memory = load_json(MEMORY_FILE)
        verified = load_json(VERIFIED_FILE)
        
        if not memory: st.info("Processando padrões...")
        else:
            cols = st.columns(3)
            for idx, (cat, phrases) in enumerate(memory.items()):
                valid = {k: v for k, v in phrases.items() if v['count'] >= 3 and k not in verified.get(cat, {})}
                if not valid: continue
                with cols[idx % 3]:
                    st.markdown(f"#### 📂 {cat}")
                    for phrase, data in sorted(valid.items(), key=lambda x: x[1]['count'], reverse=True)[:8]:
                        avg_sent = data['sentiment_sum'] / data['count']
                        sent_label = "Positivo" if avg_sent > 0 else "Negativo"
                        sent_color = "#00FFC8" if avg_sent > 0 else "#FF4B4B"
                        
                        st.markdown(f"""
                            <div class="learned-box">
                                <span class="learned-term">"{phrase}"</span>
                                <span class="learned-count">Freq: {data['count']}</span><br>
                                <span class="sentiment-tag" style="background:{sent_color}33; color:{sent_color};">Sugerido: {sent_label}</span>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        w_input = st.number_input("Peso", value=round(avg_sent, 1), key=f"w_{cat}_{phrase}", label_visibility="collapsed")
                        
                        b_col1, b_col2 = st.columns(2)
                        with b_col1:
                            st.markdown('<div class="btn-approve">', unsafe_allow_html=True)
                            if st.button("APROVAR", key=f"app_{cat}_{phrase}"):
                                if cat not in verified: verified[cat] = {}
                                verified[cat][phrase] = w_input
                                save_json(VERIFIED_FILE, verified)
                                st.rerun()
                            st.markdown('</div>', unsafe_allow_html=True)
                        
                        with b_col2:
                            st.markdown('<div class="btn-reject">', unsafe_allow_html=True)
                            if st.button("REPROVAR", key=f"rej_{cat}_{phrase}"):
                                if phrase in memory[cat]:
                                    del memory[cat][phrase]
                                    save_json(MEMORY_FILE, memory)
                                    st.rerun()
                            st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
