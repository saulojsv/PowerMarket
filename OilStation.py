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

# --- CONFIGURAÇÃO DE CHAVES ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")

# --- 1. CONFIGURAÇÃO ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v80_refresh") 

MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"

OIL_MANDATORY_TERMS = [
    "oil", "wti", "crude", "brent", "gasoline", "fuel", "opec", 
    "energy", "shale", "refinery", "inventory", "stockpile", 
    "petroleum", "diesel", "barrel", "rig count", "drilling", "tengiz"
]

# Inicialização automática do dicionário com os 22 Lexicons Estratégicos
if not os.path.exists(VERIFIED_FILE) or os.path.getsize(VERIFIED_FILE) == 0:
    initial_lexicons = {
        "tengiz": 1, "cpc blend": 1, "libya east": 1, "spr draw": -1,
        "novak": 1, "kharg island": 1, "cushing": 1, "permian": -1,
        "shale drag": -1, "refinery run": -1, "force majeure": 1,
        "export ban": 1, "supply glut": -1, "floating storage": -1,
        "bakken": -1, "ural crude": 1, "druzhba": 1, "houthis": 1,
        "strait of hormuz": 1, "strategic reserve": -1, "api draw": 1, "eia build": -1
    }
    with open(VERIFIED_FILE, 'w') as f:
        json.dump(initial_lexicons, f, indent=4)

st.markdown("""
    <style>
    .stApp { background: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00FFC8 !important; }
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #111827; border-bottom: 2px solid #00FFC8; margin-bottom: 20px; font-family: monospace; }
    .scroll-container { height: 500px; overflow-y: auto; border: 1px solid #1E293B; background: #020617; font-family: monospace; }
    .match-tag { background: #064E3B; color: #34D399; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .veto-tag { background: #450a0a; color: #f87171; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .neutro-tag { background: #1e293b; color: #94a3b8; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .learned-box { border: 1px solid #00FFC8; padding: 8px; background: #0F172A; color: #00FFC8; margin-bottom: 5px; border-radius: 4px; font-size: 12px; font-family: monospace; }
    div[data-testid="stJson"] { background-color: transparent !important; }
    table { width: 100%; border-collapse: collapse; color: #CBD5E1; font-size: 12px; }
    th { background: #1E293B; color: #00FFC8; text-align: left; padding: 8px; border-bottom: 2px solid #00FFC8; position: sticky; top: 0; }
    td { padding: 8px; border-bottom: 1px solid #1E293B; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LEXICONS ---
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
        prompt = (
            f"Manchete: '{title}'. "
            "Aja como especialista em Petróleo. Mesmo que a notícia pareça neutra, extraia 3 termos únicos "
            "(nomes de campos, cidades, CEOs, ou eventos técnicos) que sejam cruciais para o mercado. "
            "Responda APENAS JSON puro: {\"alpha\": 1/-1/0, \"termos\": [\"termo1\", \"termo2\", \"termo3\"]}"
        )
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
            for entry in feed.entries[:5]:
                title_low = entry.title.lower()
                if not any(term in title_low for term in OIL_MANDATORY_TERMS): continue

                lex_weight, lex_dir = 0, 0
                for patt, (w, d) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        lex_weight, lex_dir = w, d
                        break
                
                for v_term, v_dir in verified.items():
                    if v_term in title_low:
                        lex_weight, lex_dir = 9.0, v_dir
                        break

                ai_data = get_ai_val(entry.title)
                ai_dir = ai_data.get("alpha", 0)
                
                for t in ai_data.get("termos", []):
                    t = t.lower().strip()
                    if len(t) > 3 and t not in verified and t not in memory:
                        memory[t] = {"alpha": ai_dir, "news": entry.title[:50]}
                
                alpha_final = (lex_weight * lex_dir) + (ai_dir * 2.0)
                status = "CONFLUÊNCIA" if (ai_dir == lex_dir and ai_dir != 0) else "NEUTRO" if (ai_dir == 0 and lex_dir == 0) else "DIVERGÊNCIA"
                
                news_list.append({
                    "Hora": datetime.now().strftime("%H:%M"),
                    "Fonte": source, 
                    "Manchete": entry.title[:100],
                    "Lexicon_Dir": lex_dir,
                    "IA_Dir": ai_dir,
                    "Alpha": round(alpha_final, 2), 
                    "Status": status
                })
        except: continue
    
    save_json(MEMORY_FILE, memory)
    if news_list: pd.DataFrame(news_list).to_csv("Oil_Station_Audit.csv", index=False)

@st.cache_data(ttl=300)
def get_market_metrics():
    try:
        wti_ticker = yf.Ticker("CL=F")
        cad_ticker = yf.Ticker("USDCAD=X")
        wti_hist = wti_ticker.history(period="2d")
        cad_hist = cad_ticker.history(period="1d")
        wti_price = wti_hist['Close'].iloc[-1]
        wti_prev = wti_hist['Close'].iloc[-2]
        change_pct = ((wti_price - wti_prev) / wti_prev) * 100
        cad_price = cad_hist['Close'].iloc[-1]
        return {"WTI": wti_price, "CAD": cad_price, "Z": round(change_pct / 1.2, 2), "status": "LIVE_YF"}
    except:
        return {"WTI": 75.0, "CAD": 1.38, "Z": 0.0, "status": "MKT_OFFLINE"}

# --- 4. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df_audit = pd.read_csv("Oil_Station_Audit.csv") if os.path.exists("Oil_Station_Audit.csv") else pd.DataFrame()
    memory = load_json(MEMORY_FILE)
    verified = load_json(VERIFIED_FILE)
    
    avg_alpha = df_audit['Alpha'].mean() if not df_audit.empty else 0.0
    ica_val = (avg_alpha + (mkt['Z'] * -5)) / 2

    st.markdown(f'<div class="live-status"><div><b>XTIUSD TERMINAL</b> | V80 MAX</div><div>{mkt["status"]} ● {datetime.now().strftime("%H:%M")}</div></div>', unsafe_allow_html=True)
    
    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 SENTIMENT AUDIT", "🧠 TRAINING"])

    with t1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WTI", f"$ {mkt['WTI']:.2f}")
        c2.metric("USDCAD", f"{mkt['CAD']:.4f}")
        c3.metric("Z-SCORE", f"{mkt['Z']:.2f}")
        c4.metric("ICA SCORE", f"{ica_val:.2f}")

        cg, cn = st.columns([1, 2])
        with cg:
            fig = go.Figure(go.Indicator(mode="gauge+number", value=ica_val, gauge={'axis': {'range': [-15, 15]}, 'bar': {'color': "#00FFC8"}, 'steps': [{'range': [-15, -5], 'color': '#450a0a'}, {'range': [5, 15], 'color': '#064E3B'}]}))
            fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, margin=dict(l=20, r=20, t=50, b=20))
            # ATUALIZADO: width='stretch' substitui use_container_width=True
            st.plotly_chart(fig, width='stretch')

        with cn:
            if not df_audit.empty:
                html = "<table><tr><th>HORA</th><th>FONTE</th><th>MANCHETE</th><th>STATUS</th></tr>"
                for _, row in df_audit.iterrows():
                    tag = "match-tag" if row["Status"] == "CONFLUÊNCIA" else "neutro-tag" if row["Status"] == "NEUTRO" else "veto-tag"
                    html += f"<tr><td>{row['Hora']}</td><td>{row['Fonte']}</td><td>{row['Manchete']}</td><td><span class='{tag}'>{row['Status']}</span></td></tr>"
                st.markdown(f'<div class="scroll-container">{html}</table></div>', unsafe_allow_html=True)

    with t2:
        if not df_audit.empty:
            audit_html = "<table><tr><th>MANCHETE</th><th>LEXICON DIR</th><th>IA DIR</th><th>RESULTADO</th></tr>"
            for _, row in df_audit.iterrows():
                l_clr = "#00FFC8" if row['Lexicon_Dir'] > 0 else "#FF4B4B" if row['Lexicon_Dir'] < 0 else "#888"
                a_clr = "#00FFC8" if row['IA_Dir'] > 0 else "#FF4B4B" if row['IA_Dir'] < 0 else "#888"
                audit_html += f"<tr><td>{row['Manchete']}</td><td style='color:{l_clr}'>{row['Lexicon_Dir']}</td><td style='color:{a_clr}'>{row['IA_Dir']}</td><td>{'✅ CONFERE' if row['Lexicon_Dir'] == row['IA_Dir'] else '❌ DIVERGENTE'}</td></tr>"
            st.markdown(f'<div class="scroll-container">{audit_html}</table></div>', unsafe_allow_html=True)

    with t3:
        st.subheader("🧠 Treinamento de Inteligência")
        cl, cr = st.columns(2)
        with cl:
            st.markdown("✅ **Dicionário Validado**")
            for term, val in verified.items():
                st.markdown(f'<div class="learned-box">{term.upper()} (Impacto: {val})</div>', unsafe_allow_html=True)
                
        with cr:
            st.markdown("💡 **Sugestões para o Radar**")
            for term, data in list(memory.items())[:15]:
                with st.container():
                    col_txt, col_v = st.columns([4, 1])
                    col_txt.markdown(f'<div class="learned-box">{term.upper()}<br><small style="color:#888">{data.get("news", "")}</small></div>', unsafe_allow_html=True)
                    if col_v.button("Aprovar", key=f"y_{term}"):
                        verified[term] = data["alpha"]
                        del memory[term]
                        save_json(VERIFIED_FILE, verified); save_json(MEMORY_FILE, memory); st.rerun()

if __name__ == "__main__": main()
