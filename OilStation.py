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
st_autorefresh(interval=60000, key="v90_refresh") 

MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"
BACKUP_FILE = "verified_lexicons_backup.json"
AUDIT_CSV = "Oil_Station_Audit.csv"

OIL_MANDATORY_TERMS = [
    "oil", "wti", "crude", "brent", "gasoline", "fuel", "opec", 
    "energy", "shale", "refinery", "inventory", "stockpile", 
    "petroleum", "diesel", "barrel", "rig count", "drilling", "tengiz"
]

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
    .driver-card { background: #111827; border: 1px solid #1E293B; padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 10px; }
    .driver-val { font-size: 22px; font-weight: bold; color: #00FFC8; font-family: monospace; }
    .driver-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .scroll-container { height: 400px; overflow-y: auto; border: 1px solid #1E293B; background: #020617; font-family: monospace; }
    .match-tag { background: #064E3B; color: #34D399; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .veto-tag { background: #450a0a; color: #f87171; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .neutro-tag { background: #1e293b; color: #94a3b8; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
    .learned-box { border: 1px solid #00FFC8; padding: 8px; background: #0F172A; color: #00FFC8; margin-bottom: 5px; border-radius: 4px; font-size: 12px; font-family: monospace; }
    table { width: 100%; border-collapse: collapse; color: #CBD5E1; font-size: 12px; margin-bottom: 20px; }
    th { background: #1E293B; color: #00FFC8; text-align: left; padding: 8px; border-bottom: 2px solid #00FFC8; }
    td { padding: 8px; border-bottom: 1px solid #1E293B; }
    .bias-up { color: #00FFC8; font-weight: bold; }
    .bias-down { color: #FF4B4B; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LOGICA DE DADOS ---
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
    "Yahoo": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "FT": "https://www.ft.com/commodities?format=rss"
}

def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)
    if p == VERIFIED_FILE: save_json(BACKUP_FILE, d)

def get_ai_val(title):
    try:
        prompt = (
            f"Analise impacto no WTI: '{title}'. "
            "1. Remova ruídos. 2. Extraia EXPRESSÕES técnicas. "
            "3. Viés: 1 (Alta), -1 (Baixa), 0 (Neutro). "
            "Responda APENAS JSON: {\"alpha\": 1/-1/0, \"termos\": [\"Expressão 1\"]}"
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

                lex_dir = 0
                for patt, (w, d) in LEXICON_TOPICS.items():
                    if re.search(patt, title_low):
                        lex_dir = d
                        break
                
                for v_term, v_dir in verified.items():
                    if v_term.lower() in title_low:
                        lex_dir = v_dir
                        break

                ai_data = get_ai_val(entry.title)
                ai_dir = ai_data.get("alpha", 0)
                
                for t in ai_data.get("termos", []):
                    t = t.lower().strip()
                    if len(t) > 3 and t not in verified and t not in memory:
                        memory[t] = {"alpha": ai_dir, "news": entry.title[:60]}
                
                alpha_final = (lex_dir * 10.0) + (ai_dir * 4.0)
                status = "CONFLUÊNCIA" if (ai_dir == lex_dir and ai_dir != 0) else "NEUTRO" if (ai_dir == 0 and lex_dir == 0) else "DIVERGÊNCIA"
                
                news_list.append({
                    "Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title[:100],
                    "Lexicon_Dir": lex_dir, "IA_Dir": ai_dir, "Alpha": round(alpha_final, 2), "Status": status
                })
        except: continue
    
    save_json(MEMORY_FILE, memory)
    if news_list: pd.DataFrame(news_list).to_csv(AUDIT_CSV, index=False)

@st.cache_data(ttl=300)
def get_market_metrics():
    try:
        wti = yf.Ticker("CL=F").history(period="2d")
        cad = yf.Ticker("USDCAD=X").history(period="1d")
        wti_p, wti_prev = wti['Close'].iloc[-1], wti['Close'].iloc[-2]
        change_pct = ((wti_p - wti_prev) / wti_prev) * 100
        return {"WTI": wti_p, "CAD": cad['Close'].iloc[-1], "Z": round(change_pct / 1.2, 2), "status": "LIVE_YF"}
    except:
        return {"WTI": 75.0, "CAD": 1.38, "Z": 0.0, "status": "MKT_OFFLINE"}

# --- 3. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df_audit = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    memory = load_json(MEMORY_FILE)
    verified = load_json(VERIFIED_FILE)
    
    # COMPONENTES DO ICA
    sentiment_driver = df_audit['Alpha'].mean() if not df_audit.empty else 0.0
    technical_driver = mkt['Z'] * -5.0 # Peso do desvio de preço
    ica_val = (sentiment_driver + technical_driver) / 2

    st.markdown(f'<div class="live-status"><div><b>XTIUSD TERMINAL</b> | V90 EVO</div><div>{mkt["status"]} ● {datetime.now().strftime("%H:%M")}</div></div>', unsafe_allow_html=True)
    
    # --- NOVA SEÇÃO: ICA DRIVERS (TRANSPARÊNCIA) ---
    c_dr1, c_dr2, c_dr3, c_dr4 = st.columns(4)
    with c_dr1:
        st.markdown(f'<div class="driver-card"><div class="driver-label">SENTIMENT ALPHA (NEWS)</div><div class="driver-val">{sentiment_driver:.2f}</div></div>', unsafe_allow_html=True)
    with c_dr2:
        st.markdown(f'<div class="driver-card"><div class="driver-label">TECHNICAL DRIVE (PRICE)</div><div class="driver-val">{technical_driver:.2f}</div></div>', unsafe_allow_html=True)
    with c_dr3:
        conf_status = "ALTA" if (sentiment_driver * technical_driver) > 0 else "CONFLITO"
        st.markdown(f'<div class="driver-card"><div class="driver-label">CONFLUÊNCIA GERAL</div><div class="driver-val">{conf_status}</div></div>', unsafe_allow_html=True)
    with c_dr4:
        st.markdown(f'<div class="driver-card"><div class="driver-label">Z-SCORE IMPACT</div><div class="driver-val">{mkt["Z"]:.2f}</div></div>', unsafe_allow_html=True)

    st.divider()

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 SENTIMENT AUDIT", "🧠 TRAINING"])

    with t1:
        col_metrics, col_table = st.columns([1, 2])
        with col_metrics:
            st.metric("WTI PRICE", f"$ {mkt['WTI']:.2f}")
            st.metric("USDCAD", f"{mkt['CAD']:.4f}")
            
            fig = go.Figure(go.Indicator(mode="gauge+number", value=ica_val, gauge={
                'axis': {'range': [-15, 15]}, 
                'bar': {'color': "#00FFC8"},
                'steps': [{'range': [-15, -5], 'color': '#450a0a'}, {'range': [5, 15], 'color': '#064E3B'}]}
            ))
            fig.update_layout(height=280, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)

        with col_table:
            if not df_audit.empty:
                html = "<table><tr><th>HORA</th><th>MANCHETE</th><th>STATUS</th></tr>"
                for _, row in df_audit.iterrows():
                    tag = "match-tag" if row["Status"] == "CONFLUÊNCIA" else "neutro-tag" if row["Status"] == "NEUTRO" else "veto-tag"
                    html += f"<tr><td>{row['Hora']}</td><td>{row['Manchete']}</td><td><span class='{tag}'>{row['Status']}</span></td></tr>"
                st.markdown(f'<div class="scroll-container">{html}</table></div>', unsafe_allow_html=True)

    with t2:
        st.subheader("🕵️ Auditoria de Viés (Sinalização)")
        if not df_audit.empty:
            col_lex, col_ai = st.columns(2)
            with col_lex:
                st.markdown("### 📘 Interpretação Lexicons")
                lex_html = "<table><tr><th>Manchete</th><th>Viés</th></tr>"
                for _, row in df_audit.iterrows():
                    bias = "ALTISTA" if row['Lexicon_Dir'] > 0 else "BAIXA" if row['Lexicon_Dir'] < 0 else "NEUTRO"
                    cls = "bias-up" if bias == "ALTISTA" else "bias-down" if bias == "BAIXA" else ""
                    lex_html += f"<tr><td>{row['Manchete'][:60]}...</td><td class='{cls}'>{bias}</td></tr>"
                st.markdown(lex_html + "</table>", unsafe_allow_html=True)
            with col_ai:
                st.markdown("### 🤖 Interpretação AI (Gemini)")
                ai_html = "<table><tr><th>Manchete</th><th>Viés</th></tr>"
                for _, row in df_audit.iterrows():
                    bias = "ALTISTA" if row['IA_Dir'] > 0 else "BAIXA" if row['IA_Dir'] < 0 else "NEUTRO"
                    cls = "bias-up" if bias == "ALTISTA" else "bias-down" if bias == "BAIXA" else ""
                    ai_html += f"<tr><td>{row['Manchete'][:60]}...</td><td class='{cls}'>{bias}</td></tr>"
                st.markdown(ai_html + "</table>", unsafe_allow_html=True)

    with t3:
        st.subheader("🧠 Treinamento Contínuo")
        st.info("Novas expressões capturadas automaticamente a cada minuto via RSS.")
        cl, cr = st.columns(2)
        with cl:
            st.markdown("✅ **Dicionário Validado**")
            for term, val in sorted(verified.items()):
                st.markdown(f'<div class="learned-box">{term.upper()} (Viés: {"Alta" if val>0 else "Baixa" if val<0 else "Neutro"})</div>', unsafe_allow_html=True)
        with cr:
            st.markdown("💡 **Sugestões da IA (Novos Fatos)**")
            for term, data in list(memory.items())[:15]:
                with st.container():
                    col_txt, col_v = st.columns([4, 1])
                    col_txt.markdown(f'<div class="learned-box">{term.upper()}<br><small style="color:#888">{data.get("news", "")}</small></div>', unsafe_allow_html=True)
                    if col_v.button("Aprovar", key=f"y_{term}"):
                        verified[term] = data["alpha"]
                        del memory[term]
                        save_json(VERIFIED_FILE, verified); save_json(MEMORY_FILE, memory); st.rerun()

if __name__ == "__main__": main()
