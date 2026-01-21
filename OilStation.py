import pandas as pd
import re
import feedparser
import os
import json
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from google import genai 
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO IA & ESTÉTICA ---
# Chave integrada conforme sua solicitação
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")

st.set_page_config(page_title="TERMINAL XTIUSD - V80 HYBRID", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=300000, key="v80_refresh") 

# Arquivos de Memória e Logs
MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"
CROSS_VAL_FILE = "cross_validation_log.json"

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
    
    .match-tag { background: #064E3B; color: #34D399; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .veto-tag { background: #450a0a; color: #f87171; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    
    .learned-box { border: 1px solid #334155; padding: 15px; border-radius: 8px; margin-bottom: 10px; background: #0F172A; }
    .learned-term { color: #FACC15; font-weight: bold; font-family: monospace; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LEXICONS ---
RSS_SOURCES = {
    "Bloomberg Energy": "https://www.bloomberg.com/feeds/bview/energy.xml", "Reuters Oil": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "CNBC Commodities": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135", "FT Commodities": "https://www.ft.com/commodities?format=rss",
    "WSJ Energy": "https://feeds.a.dj.com/rss/RSSWSJ.xml", "OilPrice Main": "https://oilprice.com/rss/main",
    "Rigzone": "https://www.rigzone.com/news/rss/rigzone_latest.xml", "S&P Global Platts": "https://www.spglobal.com/platts/en/rss-feed/news/oil",
    "Energy Voice": "https://www.energyvoice.com/category/oil-and-gas/feed/", "EIA Today": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "Investing.com": "https://www.investing.com/rss/news_11.rss", "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Yahoo Finance Oil": "https://finance.yahoo.com/rss/headline?s=CL=F", "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Foreign Policy": "https://foreignpolicy.com/feed/", "Lloyds List": "https://lloydslist.maritimeintelligence.informa.com/RSS/News",
    "Marine Insight": "https://www.marineinsight.com/feed/", "Splash 247": "https://splash247.com/feed/",
    "OPEC Press": "https://www.opec.org/opec_web/en/press_room/311.xml", "IEA News": "https://www.iea.org/news/rss",
    "BOC News": "https://www.bankofcanada.ca/feed/", "Fed News": "https://www.federalreserve.gov/feeds/press_all.xml"
}

LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation": [9.8, 1, "Geopolitics"],
    r"sanction|embargo|ban|price cap": [9.0, 1, "Sanctions"],
    r"iran|strait of hormuz|red sea|houthis": [9.8, 1, "Chokepoints"],
    r"israel|gaza|hezbollah|lebanon|tehran": [9.2, 1, "Middle East"],
    r"opec|saudi|russia|cut|quota": [9.5, 1, "OPEC+"],
    r"shale|fracking|permian|rig count": [7.5, -1, "US Supply"],
    r"inventory|stockpile|draw|api|eia": [8.0, 1, "Stocks"],
    r"build|glut|oversupply|surplus": [8.0, -1, "Surplus"],
    r"recession|slowdown|weak|china": [8.8, -1, "Demand"],
    r"fed|rate hike|hawkish|inflation|boc": [7.5, -1, "Macro Tightening"],
    r"dovish|rate cut|powell|easing": [7.5, 1, "Macro Easing"],
    r"dollar|dxy|greenback|usdcad": [7.0, -1, "FX Correl"]
}

# --- 3. FUNÇÕES DE SUPORTE ---
def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return [] if "log" in p else {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)

def get_ai_val(title):
    """Auditoria Independente com prompt otimizado para reduzir divergências."""
    try:
        prompt = f"""
        Como especialista em commodities, analise o impacto para o Petróleo (WTI):
        Notícia: '{title}'
        
        Considere: 
        - Decisões do Fed/Economia Forte/Cortes de Juros = Alta (+1)
        - Tensões Geopolíticas/Guerra/Ataques = Alta (+1)
        - Aumento de Estoques/Recessão/China fraca = Baixa (-1)
        
        Responda APENAS em JSON: {{"alpha": valor, "termos": ["termo1", "termo2"]}}
        Alpha deve ser 1, -1 ou 0.
        """
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        clean_res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_res)
    except: return {"alpha": 0, "termos": []}

# --- 4. ENGINE DE CONSENSO E EXTRAÇÃO ---
def fetch_news():
    news_list = []
    memory = load_json(MEMORY_FILE)
    logs = load_json(CROSS_VAL_FILE)
    MIN_LEX_TERMS = 2 

    for source, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                lex_score, cat, lex_match_count = 0.0, "General", 0
                title_low = entry.title.lower()
                
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    matches = re.findall(patt, title_low)
                    if matches:
                        lex_match_count += len(matches)
                        lex_score, cat = float(w * d), c
                
                lex_dir = 1 if lex_score > 0 else -1 if lex_score < 0 else 0
                ai_data = get_ai_val(entry.title)
                ai_dir = ai_data.get("alpha", 0)
                termos_sugeridos = ai_data.get("termos", [])

                # Consenso ajustado para ser mais flexível se o impacto for alto
                consenso = (ai_dir == lex_dir) and (lex_match_count >= MIN_LEX_TERMS or abs(lex_score) >= 9.0)
                status = "CONFLUÊNCIA" if consenso else "DIVERGÊNCIA"
                final_alpha = lex_score if consenso else 0.0

                if ai_dir != 0:
                    if cat not in memory: memory[cat] = {}
                    for t in termos_sugeridos:
                        t = t.lower().strip()
                        if t not in memory[cat]:
                            memory[cat][t] = {"count": 1, "sum": float(ai_dir * 9), "origin": "IA_SUGGESTION"}
                        else:
                            memory[cat][t]["count"] += 1

                if final_alpha != 0:
                    news_list.append({"Data": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title[:100], "Alpha": final_alpha, "Status": status})
                
                logs.insert(0, {"Data": datetime.now().strftime("%H:%M"), "Manchete": entry.title[:65], "Lex": lex_dir, "AI": ai_dir, "Result": status})
        except: continue
    
    save_json(MEMORY_FILE, memory)
    save_json(CROSS_VAL_FILE, logs[:100])
    if news_list: 
        pd.DataFrame(news_list).to_csv("Oil_Station_V80_Hybrid.csv", index=False)

@st.cache_data(ttl=900) # Cache de 15 min para evitar YFRateLimitError
def get_market_metrics():
    try:
        data = yf.download(["CL=F", "USDCAD=X"], period="5d", interval="15m", progress=False)
        if data.empty or 'CL=F' not in data['Close'] or data['Close']['CL=F'].isnull().all():
            return {"WTI": 0.0, "USDCAD": 1.37, "Z": 0.0, "status": "Rate Limited"}
            
        p_wti = data['Close']['CL=F'].dropna().iloc[-1]
        p_cad = data['Close']['USDCAD=X'].dropna().iloc[-1]
        
        ratio = data['Close']['CL=F'] / data['Close']['USDCAD=X']
        z = (ratio.iloc[-1] - ratio.mean()) / ratio.std() if ratio.std() != 0 else 0.0
        
        return {"WTI": float(p_wti), "USDCAD": float(p_cad), "Z": float(z), "status": "Online"}
    except: 
        return {"WTI": 0.0, "USDCAD": 1.37, "Z": 0.0, "status": "Offline"}

# --- 5. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df_news = pd.read_csv("Oil_Station_V80_Hybrid.csv") if os.path.exists("Oil_Station_V80_Hybrid.csv") else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0.0
    
    # Cálculo do ICA Score com proteção contra NaN
    z_val = mkt['Z'] if not pd.isna(mkt['Z']) else 0.0
    ica_val = (avg_alpha + (z_val * -5)) / 2

    st.markdown(f'<div class="live-status"><div style="font-weight:800; color:#00FFC8;">TERMINAL XTIUSD | QUANT V80 HYBRID</div><div style="font-family:monospace;">{datetime.now().strftime("%H:%M:%S")} <span style="color:#00FFC8;">● {mkt["status"]}</span></div></div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["📊 DASHBOARD", "🧠 IA LEARNING", "🤖 AI SITREP", "⚖️ VALIDAÇÃO"])

    with tab1:
        color = "#00FFC8" if ica_val > 4 else "#FF4B4B" if ica_val < -4 else "#94A3B8"
        st.markdown(f'<div class="arbitrage-monitor" style="border-color:{color}; color:{color};"><strong>ICA SCORE: {ica_val:.2f}</strong></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI", f"$ {mkt['WTI']:.2f}" if mkt['WTI'] > 0 else "LIMIT")
        c2.metric("USDCAD", f"{mkt['USDCAD']:.4f}")
        c3.metric("Z-SCORE", f"{mkt['Z']:.2f}")
        c4.metric("ALPHA", f"{avg_alpha:.2f}")
        
        if not df_news.empty:
            df_disp = df_news.copy()
            df_disp['Status'] = df_disp['Status'].apply(lambda x: f'<span class="match-tag">{x}</span>' if x=="CONFLUÊNCIA" else f'<span class="veto-tag">{x}</span>')
            st.markdown(f'<div class="scroll-container">{df_disp[["Data", "Fonte", "Manchete", "Alpha", "Status"]].to_html(escape=False, index=False)}</div>', unsafe_allow_html=True)
        else:
            st.info("Aguardando confluência de notícias para atualizar o Dashboard.")

    with tab2:
        st.subheader("🧠 Centro de Aprendizado Híbrido")
        memory = load_json(MEMORY_FILE)
        verified = load_json(VERIFIED_FILE)
        for cat, phrases in memory.items():
            with st.expander(f"📂 Categoria: {cat}"):
                for ph, data in phrases.items():
                    is_ia = data.get("origin") == "IA_SUGGESTION"
                    tag = "🤖 [SUGESTÃO IA]" if is_ia else "📊 [FREQ. LÉXICA]"
                    color = "#FACC15" if is_ia else "#94A3B8"
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f'<div class="learned-box" style="border-left:4px solid {color};"><small style="color:{color};">{tag}</small><br><span class="learned-term">"{ph}"</span> (Visto {data["count"]}x)</div>', unsafe_allow_html=True)
                    if c2.button(f"Aprovar", key=f"app_{ph}_{cat}"):
                        if cat not in verified: verified[cat] = {}
                        verified[cat][ph] = data['sum'] / data['count']
                        save_json(VERIFIED_FILE, verified)
                        st.success("Léxico Atualizado!")

    with tab4:
        st.subheader("⚖️ Log de Validação Cruzada")
        logs = load_json(CROSS_VAL_FILE)
        if logs: st.table(pd.DataFrame(logs).head(20))

if __name__ == "__main__": main()
