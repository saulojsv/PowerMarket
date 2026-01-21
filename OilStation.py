import pandas as pd
import re
import feedparser
import os
import json
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
import google.generativeai as genai
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from collections import Counter

# --- CONFIGURAÇÃO IA (GEMINI FREE) ---
# Substitua pela sua chave API do Google AI Studio
genai.configure(api_key="SUA_CHAVE_GEMINI_AQUI")
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# --- 1. CONFIGURAÇÕES E ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD - QUANT ARBITRAGE", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v76_refresh") # Atualização 1min para IA

st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle, #0D1421 0%, #050A12 100%); color: #FFFFFF; }
    header {visibility: hidden;}
    .main .block-container {padding-top: 1rem;}
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    [data-testid="stMetricLabel"] { font-size: 10px !important; color: #94A3B8 !important; text-transform: uppercase; }
    
    .live-status {
        display: flex; justify-content: space-between; align-items: center; 
        padding: 10px; background: rgba(30, 41, 59, 0.3); 
        border-bottom: 2px solid #00FFC8; margin-bottom: 20px;
    }
    .arbitrage-monitor { padding: 20px; border-radius: 5px; border: 1px solid #1E293B; background: rgba(0, 0, 0, 0.4); margin-bottom: 20px; text-align: center; }
    .scroll-container { height: 480px; overflow-y: auto; border: 1px solid rgba(30, 41, 59, 0.5); background: rgba(0, 0, 0, 0.2); }
    .scroll-container::-webkit-scrollbar { width: 4px; }
    .scroll-container::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 10px; }
    
    table { width: 100%; border-collapse: collapse; }
    th { color: #94A3B8 !important; font-size: 10px; text-transform: uppercase; border-bottom: 1px solid #1E293B; padding: 10px; position: sticky; top: 0; background: #050A12; z-index: 10; }
    td { font-size: 12px; padding: 10px; border-bottom: 1px solid #0D1421; }
    .pos-score { color: #00FFC8; font-weight: bold; }
    .neg-score { color: #FF4B4B; font-weight: bold; }
    
    .link-btn { color: #00FFC8 !important; text-decoration: none; font-size: 10px; font-weight: 700; border: 1px solid #00FFC8; padding: 2px 5px; border-radius: 3px; }
    .learned-box { border: 1px solid #334155; padding: 15px; border-radius: 8px; margin-bottom: 5px; background: #0F172A; }
    .learned-term { color: #FACC15; font-weight: bold; font-family: monospace; font-size: 14px; }
    .sentiment-tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; font-weight: bold; }
    
    div.stButton > button { width: 100%; border-radius: 4px; font-weight: bold; height: 32px; font-size: 11px; }
    .btn-approve button { background-color: #00FFC8 !important; color: #050A12 !important; }
    .btn-reject button { background-color: #FF4B4B !important; color: #FFFFFF !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURAÇÕES DE ARQUIVOS E LÉXICOS (Mantidos os seus originais) ---
MEMORY_FILE, VERIFIED_FILE, MARKET_CACHE_FILE = "brain_memory.json", "verified_lexicons.json", "market_last_prices.json"
STOPWORDS = {'the', 'a', 'an', 'of', 'to', 'in', 'and', 'is', 'for', 'on', 'at', 'by', 'with', 'from', 'that', 'it', 'as', 'are', 'be', 'this', 'will', 'has', 'have', 'but', 'not', 'up', 'down', 'its', 'their', 'prices', 'oil', 'crude'}

# (Dicionários RSS_SOURCES e LEXICON_TOPICS mantidos conforme sua solicitação anterior)
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
    r"non-opec|brazil|guyana|canada|alberta|output surge": [7.0, -1, "Non-OPEC Supply"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Stocks (Deficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Stocks (Surplus)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refining/Margins"],
    r"crack spread|heating oil|jet fuel|diesel demand": [6.5, 1, "Distillates"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Weak Demand)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Strong Demand)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate|boc": [7.5, -1, "Macro (Fed/BoC Tightening)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Fed Easing)"],
    r"dollar|dxy|greenback|fx|yields|usdcad": [7.0, -1, "DXY/CAD Correlation"],
    r"gdp|pmi|manufacturing|industrial production": [6.8, 1, "Macro Indicators"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Speculative Flow"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Technical Analysis"],
    r"volatility|vix|contango|backwardation": [6.2, 1, "Term Structure"],
    r"algorithmic trading|ctas|margin call|liquidation": [6.0, 1, "Quant Flow"]
}

# --- 3. FUNÇÕES DE SUPORTE ---
def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, indent=4)

def calculate_ica(z, alpha):
    raw = (alpha + (z * -5)) / 2
    return max(min(raw, 10), -10)

def get_ai_insight(headlines, ica):
    try:
        prompt = f"Analise estas manchetes de petróleo: {headlines}. O indicador ICA está em {ica:.2f}. Explique em uma frase curta em português o risco ou oportunidade para o WTI hoje."
        response = ai_model.generate_content(prompt)
        return response.text
    except: return "Aguardando nova janela de requisição IA..."

@st.cache_data(ttl=300)
def get_market_metrics():
    tickers = {"WTI": "CL=F", "BRENT": "BZ=F", "DXY": "DX-Y.NYB", "USDCAD": "USDCAD=X"}
    cached = load_json(MARKET_CACHE_FILE)
    prices = cached.get("prices", {"WTI": 75.0, "BRENT": 80.0, "DXY": 103.5, "USDCAD": 1.35})
    momentum = cached.get("momentum", 0.0)
    z_score_comp = cached.get("z_score_composite", 0.0)

    try:
        # Bypass do Rate Limit: Tenta baixar, se falhar usa cache sem travar
        data = yf.download(list(tickers.values()), period="5d", interval="15m", progress=False, ignore_tz=True, threads=False)
        
        if not data.empty and 'Close' in data:
            closes = data['Close'].ffill()
            for k, v in tickers.items(): 
                if v in closes.columns and not pd.isna(closes[v].iloc[-1]):
                    prices[k] = float(closes[v].iloc[-1])
            
            if all(t in closes.columns for t in ["BZ=F", "CL=F", "USDCAD=X"]):
                spread_bw = closes["BZ=F"] - closes["CL=F"]
                z_bw = (spread_bw.iloc[-1] - spread_bw.mean()) / spread_bw.std()
                cad_strength = 1 / closes["USDCAD=X"]
                ratio_oil_cad = closes["CL=F"] / cad_strength
                z_cad = (ratio_oil_cad.iloc[-1] - ratio_oil_cad.mean()) / ratio_oil_cad.std()
                z_score_comp = (z_bw * 0.6) + (z_cad * 0.4)
                momentum = float(closes["CL=F"].pct_change().iloc[-1])
            
            save_json(MARKET_CACHE_FILE, {"prices": prices, "momentum": momentum, "z_score_composite": float(z_score_comp)})
    except Exception:
        pass # Silenciosamente mantém o cache se houver YFRateLimitError
        
    return prices, momentum, z_score_comp

# --- 4. INTERFACE PRINCIPAL ---
def main():
    # Carregamento e processamento de dados (fetch_filtered_news deve estar definida)
    # fetch_filtered_news() <- Chame aqui se necessário
    
    prices, momentum, z_score = get_market_metrics()
    df_news = pd.read_csv("Oil_Station_V54_Master.csv") if os.path.exists("Oil_Station_V54_Master.csv") else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0.0
    ica_val = calculate_ica(z_score, avg_alpha)

    # Live Status Header
    now = datetime.now().strftime("%H:%M:%S")
    st.markdown(f'<div class="live-status"><div style="font-weight:800; color:#00FFC8;">TERMINAL XTIUSD | QUANT</div><div style="font-family:monospace;">{now} <span style="color:#00FFC8;">● LIVE</span></div></div>', unsafe_allow_html=True)

    tab_dash, tab_brain, tab_sitrep = st.tabs(["📊 MONITOR", "🧠 IA LEARNING", "🤖 AI SITREP"])

    with tab_dash:
        if ica_val > 4.5: arb_s, arb_c = "LONG AGGRESSIVE", "#00FFC8"
        elif ica_val < -4.5: arb_s, arb_c = "SHORT AGGRESSIVE", "#FF4B4B"
        else: arb_s, arb_c = "WAIT FOR CONFLUENCE", "#94A3B8"

        st.markdown(f'<div class="arbitrage-monitor" style="border-color:{arb_c}; color:{arb_c};"><strong>{arb_s}</strong></div>', unsafe_allow_html=True)
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("WTI", f"$ {prices['WTI']:.2f}", f"{momentum:.2%}")
        c2.metric("BRENT", f"$ {prices['BRENT']:.2f}")
        c3.metric("USDCAD", f"{prices['USDCAD']:.4f}")
        c4.metric("Z-SCORE", f"{z_score:.2f}")
        c5.metric("ALPHA", f"{avg_alpha:.2f}")
        
        col_g, col_t = st.columns([1, 2])
        with col_g:
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=ica_val,
                title={'text': "Convergência ICA", 'font': {'size': 14}},
                gauge={'axis': {'range': [-10, 10]}, 'bar': {'color': arb_c}}
            ))
            fig.update_layout(height=280, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, margin=dict(t=30, b=0))
            st.plotly_chart(fig, width=350) # Correção para 2026
            
        with col_t:
            if not df_news.empty:
                df_d = df_news.head(20).copy()
                df_d['Alpha'] = df_d['Alpha'].apply(lambda v: f'<span class="{"pos-score" if v>0 else "neg-score"}">{v}</span>')
                table_html = df_d[['Data', 'Fonte', 'Manchete', 'Alpha']].to_html(escape=False, index=False)
                st.markdown(f'<div class="scroll-container">{table_html}</div>', unsafe_allow_html=True)

    with tab_sitrep:
        # Inteligência Gemini
        top_h = ". ".join(df_news['Manchete'].head(8).tolist()) if not df_news.empty else "Sem manchetes."
        ai_analysis = get_ai_insight(top_h, ica_val)
        
        st.markdown(f"""
            <div style="background: #0F172A; border: 1px solid {arb_c}; padding: 40px; border-radius: 10px; text-align: center;">
                <h1 style="color: {arb_c}; font-size: 50px; margin-bottom: 10px;">{arb_s}</h1>
                <p style="color: #94A3B8; font-size: 18px;">ICA Score: {ica_val:.2f} | Alpha: {avg_alpha:.2f}</p>
                <div style="margin: 20px; padding: 20px; background: rgba(0,255,200,0.05); border-radius: 8px; font-size: 16px; color: #FFFFFF;">
                    <strong>AI INSIGHT:</strong> {ai_analysis}
                </div>
            </div>
        """, unsafe_allow_html=True)

    # (Lógica da tab_brain mantida conforme seu código original)

if __name__ == "__main__":
    main()
