import pandas as pd
import re
import feedparser
import os
import json
import streamlit as st
import plotly.graph_objects as go
import requests
from google import genai 
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE CHAVES ---
AV_API_KEY = "UCT0N3Y3CEQ7EIWS" 
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")

# --- 1. CONFIGURAÇÃO ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD - V80 MAX", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v80_refresh") 

MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"

# CSS CORRIGIDO PARA VISIBILIDADE DAS CAIXAS
st.markdown("""
    <style>
    .stApp { background: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #111827; border-bottom: 2px solid #00FFC8; margin-bottom: 20px; font-family: monospace; }
    .scroll-container { height: 500px; overflow-y: auto; border: 1px solid #1E293B; background: #020617; font-family: monospace; }
    
    .match-tag { background: #064E3B; color: #34D399; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .veto-tag { background: #450a0a; color: #f87171; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    
    /* CORREÇÃO DAS CAIXAS DE TREINAMENTO */
    .learned-box { 
        border: 2px solid #00FFC8; 
        padding: 12px; 
        background: #0F172A !important; 
        color: #00FFC8 !important; 
        margin-bottom: 8px; 
        border-left: 8px solid #00FFC8;
        font-weight: bold;
        border-radius: 4px;
        text-align: center;
    }
    
    table { width: 100%; border-collapse: collapse; color: #CBD5E1; font-size: 12px; }
    th { background: #1E293B; color: #00FFC8; text-align: left; padding: 8px; border-bottom: 2px solid #00FFC8; position: sticky; top: 0; }
    td { padding: 8px; border-bottom: 1px solid #1E293B; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LEXICONS E FONTES ---
LEXICON_TOPICS = {
    r"war|attack|missile|conflict|escalation|invasion": [9.8, 1],
    r"iran|strait of hormuz|red sea|houthis|tehran": [9.8, 1],
    r"israel|gaza|hezbollah|lebanon|syria": [9.2, 1],
    r"opec|saudi|riyadh|production cut|quota": [9.5, 1],
    r"inventory|stockpile|draw|api|eia|cushing": [8.0, 1],
    r"fed|rate hike|hawkish|inflation|tightening": [7.5, -1],
    r"rate cut|dovish|powell|easing|liquidity": [7.5, 1],
    r"recession|slowdown|weak|china|demand worry": [8.8, -1],
    r"hurricane|storm|gulf coast|refinery shut": [7.5, 1],
    r"spr|emergency release|biden|strategic reserve": [8.5, -1]
}

NEWS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=business&post_type=best",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "Yahoo": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "EIA": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "FT": "https://www.ft.com/commodities?format=rss"
}

# --- 3. FUNÇÕES ---
def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)

def get_ai_val(title):
    try:
        prompt = f"Analise impacto WTI (1, -1 ou 0) e 2 termos técnicos: '{title}'. Responda APENAS JSON: {{\"alpha\": v, \"termos\": [\"t1\", \"t2\"]}}"
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res)
    except: return {"alpha": 0, "termos": []}

def fetch_news():
    news_list = []
    memory = load_json(MEMORY_FILE)
    verified = load_json(VERIFIED_FILE)
    
    for source, url in NEWS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]:
                title_low = entry.title.lower()
                lex_weight, lex_dir = 0, 0
                for patt, (w, d) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        lex_weight, lex_dir = w, d
                        break
                for term, val in verified.items():
                    if term in title_low:
                        lex_weight, lex_dir = 8.5, (1 if val > 0 else -1)
                        break
                ai_data = get_ai_val(entry.title)
                ai_dir = ai_data.get("alpha", 0)
                for t in ai_data.get("termos", []):
                    t = t.lower()
                    if t not in memory: memory[t] = {"alpha": ai_dir}
                alpha_final = (lex_weight * lex_dir) + (ai_dir * 2.0)
                status = "CONFLUÊNCIA" if (ai_dir == lex_dir and ai_dir != 0) else "DIVERGÊNCIA"
                if lex_dir == 0: status = "IA ANALYSING"
                news_list.append({
                    "Data": datetime.now().strftime("%d/%m/%Y"),
                    "Hora": datetime.now().strftime("%H:%M"),
                    "Fonte": source, "Manchete": entry.title[:100],
                    "Alpha": round(alpha_final, 2), "Status": status
                })
        except: continue
    save_json(MEMORY_FILE, memory)
    if news_list: pd.DataFrame(news_list).to_csv("Oil_Station_V80_Hybrid.csv", index=False)

@st.cache_data(ttl=600)
def get_market_metrics():
    try:
        url_fx = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=CAD&apikey={AV_API_KEY}"
        fx_data = requests.get(url_fx).json()
        cad = float(fx_data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
        url_wti = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=WTI&apikey={AV_API_KEY}"
        wti_data = requests.get(url_wti).json()
        wti = float(wti_data['Global Quote']['05. price'])
        change_pct = float(wti_data['Global Quote']['10. change percent'].replace('%', ''))
        return {"WTI": wti, "CAD": cad, "Z": round(change_pct/1.2, 2), "status": "AV_ONLINE"}
    except:
        return {"WTI": 75.0, "CAD": 1.38, "Z": 0.0, "status": "API_LIMIT"}

# --- 4. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    memory = load_json(MEMORY_FILE)
    verified = load_json(VERIFIED_FILE)
    df_news = pd.read_csv("Oil_Station_V80_Hybrid.csv") if os.path.exists("Oil_Station_V80_Hybrid.csv") else pd.DataFrame()
    avg_alpha = df_news['Alpha'].mean() if not df_news.empty else 0.0
    ica_val = (avg_alpha + (mkt['Z'] * -5)) / 2

    st.markdown(f'<div class="live-status"><div><b>XTIUSD TERMINAL</b> | V80 MAX</div><div>{mkt["status"]} ● {datetime.now().strftime("%H:%M")}</div></div>', unsafe_allow_html=True)
    t1, t2 = st.tabs(["📊 DASHBOARD", "🧠 TRAINING & DICTIONARY"])

    with t1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI", f"$ {mkt['WTI']:.2f}")
        c2.metric("USDCAD", f"{mkt['CAD']:.4f}")
        c3.metric("Z-SCORE", f"{mkt['Z']:.2f}")
        c4.metric("ICA SCORE", f"{ica_val:.2f}")

        cg, cn = st.columns([1, 2])
        with cg:
            fig = go.Figure(go.Indicator(
                mode = "gauge+number", value = ica_val,
                gauge = {'axis': {'range': [-15, 15]}, 'bar': {'color': "#00FFC8"},
                         'steps': [{'range': [-15, -5], 'color': '#450a0a'}, {'range': [5, 15], 'color': '#064E3B'}]}))
            fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, width='stretch')

        with cn:
            if not df_news.empty:
                html = "<table><tr><th>DATA</th><th>HORA</th><th>FONTE</th><th>MANCHETE</th><th>ALPHA</th><th>STATUS</th></tr>"
                for _, row in df_news.iterrows():
                    tag = "match-tag" if row["Status"] != "DIVERGÊNCIA" else "veto-tag"
                    html += f"<tr><td>{row['Data']}</td><td>{row['Hora']}</td><td>{row['Fonte']}</td><td>{row['Manchete']}</td><td style='color:#00FFC8'><b>{row['Alpha']}</b></td><td><span class='{tag}'>{row['Status']}</span></td></tr>"
                st.markdown(f'<div class="scroll-container">{html}</table></div>', unsafe_allow_html=True)

    with t2:
        st.subheader("🧠 Dicionário e Treino Ativo")
        cl, cr = st.columns(2)
        with cl:
            st.write("✅ **Termos Ensinados**")
            st.write(verified if verified else "Aguardando validação...")
        with cr:
            st.write("💡 **Clique para Validar (Agora Visível)**")
            for term in list(memory.keys())[:15]:
                with st.container():
                    col_txt, col_v = st.columns([4, 1])
                    # Texto agora em Neon Green sobre fundo azul marinho profundo
                    col_txt.markdown(f'<div class="learned-box">{term.upper()}</div>', unsafe_allow_html=True)
                    if col_v.button("✅", key=f"y_{term}"):
                        verified[term] = memory[term]["alpha"]
                        del memory[term]
                        save_json(VERIFIED_FILE, verified); save_json(MEMORY_FILE, memory); st.rerun()

if __name__ == "__main__": main()

