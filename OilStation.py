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

# Inicialização com Expressões de Peso (Exemplos)
if not os.path.exists(VERIFIED_FILE) or os.path.getsize(VERIFIED_FILE) == 0:
    initial_expressions = {
        "production cut": 1, "inventory draw": 1, "inventory build": -1,
        "supply disruption": 1, "refinery outage": 1, "export ban": 1,
        "demand weakness": -1, "economic slowdown": -1, "rate hike": -1,
        "rate cut": 1, "strategic reserve release": -1, "opec agreement": 1,
        "shale growth": -1, "geopolitical tension": 1, "tengiz production drop": 1
    }
    with open(VERIFIED_FILE, 'w') as f:
        json.dump(initial_expressions, f, indent=4)

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
        # Prompt focado estritamente em EXPRESSÕES DE PESO (N-grams)
        prompt = (
            f"Analise o impacto no Petróleo WTI: '{title}'. "
            "Extraia apenas EXPRESSÕES TÉCNICAS DE PESO (2 a 4 palavras) que justifiquem o movimento. "
            "Exemplos: 'Stronger dollar', 'OPEC production cut', 'EIA inventory draw'. "
            "Seja agressivo no viés: 1 (Alta), -1 (Baixa), 0 (Neutro). "
            "Responda APENAS JSON: {\"alpha\": 1/-1/0, \"expressoes\": [\"Expressão Técnica\"]}"
        )
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res)
    except: return {"alpha": 0, "expressoes": []}

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

                # Busca por expressões verificadas (prioridade máxima)
                lex_dir = 0
                for v_expr, v_dir in verified.items():
                    if v_expr.lower() in title_low:
                        lex_dir = v_dir
                        break

                ai_data = get_ai_val(entry.title)
                ai_dir = ai_data.get("alpha", 0)
                
                # Salva novas expressões na memória para treinamento
                for exp in ai_data.get("expressoes", []):
                    exp_low = exp.lower().strip()
                    if len(exp_low.split()) >= 2 and exp_low not in verified and exp_low not in memory:
                        memory[exp_low] = {"alpha": ai_dir, "news": entry.title[:60]}
                
                alpha_final = (lex_dir * 10.0) + (ai_dir * 4.0)
                status = "CONFLUÊNCIA" if (ai_dir == lex_dir and ai_dir != 0) else "NEUTRO" if (ai_dir == 0 and lex_dir == 0) else "DIVERGÊNCIA"
                
                news_list.append({
                    "Hora": datetime.now().strftime("%H:%M"), "Fonte": source, "Manchete": entry.title[:100],
                    "Lex_Expr": lex_dir, "IA_Dir": ai_dir, "Alpha": round(alpha_final, 2), "Status": status
                })
        except: continue
    
    save_json(MEMORY_FILE, memory)
    if news_list: pd.DataFrame(news_list).to_csv(AUDIT_CSV, index=False)

@st.cache_data(ttl=300)
def get_market_metrics():
    try:
        wti = yf.Ticker("CL=F").history(period="2d")
        wti_p, wti_prev = wti['Close'].iloc[-1], wti['Close'].iloc[-2]
        change_pct = ((wti_p - wti_prev) / wti_prev) * 100
        return {"WTI": wti_p, "Z": round(change_pct / 1.2, 2), "status": "LIVE_YF"}
    except:
        return {"WTI": 75.0, "Z": 0.0, "status": "MKT_OFFLINE"}

# --- 3. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df_audit = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    verified = load_json(VERIFIED_FILE)
    memory = load_json(MEMORY_FILE)
    
    sentiment_driver = df_audit['Alpha'].mean() if not df_audit.empty else 0.0
    technical_driver = mkt['Z'] * -5.0 
    ica_val = (sentiment_driver + technical_driver) / 2

    st.markdown(f'<div class="live-status"><div><b>XTIUSD TERMINAL</b> | EXPRESSION MODE</div><div>{mkt["status"]} ● {datetime.now().strftime("%H:%M")}</div></div>', unsafe_allow_html=True)
    
    # ICA DRIVERS
    c_dr1, c_dr2, c_dr3, c_dr4 = st.columns(4)
    with c_dr1: st.markdown(f'<div class="driver-card"><div class="driver-label">SENTIMENT (EXPRESSIONS)</div><div class="driver-val">{sentiment_driver:.2f}</div></div>', unsafe_allow_html=True)
    with c_dr2: st.markdown(f'<div class="driver-card"><div class="driver-label">TECHNICAL IMPACT</div><div class="driver-val">{technical_driver:.2f}</div></div>', unsafe_allow_html=True)
    with c_dr3: st.markdown(f'<div class="driver-card"><div class="driver-label">ICA SCORE</div><div class="driver-val">{ica_val:.2f}</div></div>', unsafe_allow_html=True)
    with c_dr4: st.markdown(f'<div class="driver-card"><div class="driver-label">CONFLUENCE</div><div class="driver-val">{"YES" if sentiment_driver*technical_driver > 0 else "NO"}</div></div>', unsafe_allow_html=True)

    st.divider()

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 EXPRESSION AUDIT", "🧠 EXPRESSION TRAINING"])

    with t1:
        col_metrics, col_table = st.columns([1, 2])
        with col_metrics:
            st.metric("WTI PRICE", f"$ {mkt['WTI']:.2f}")
            fig = go.Figure(go.Indicator(mode="gauge+number", value=ica_val, gauge={'axis': {'range': [-15, 15]}, 'bar': {'color': "#00FFC8"}}))
            fig.update_layout(height=280, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, width='stretch')

        with col_table:
            if not df_audit.empty:
                html = "<table><tr><th>HORA</th><th>MANCHETE</th><th>SENTIMENTO</th></tr>"
                for _, row in df_audit.iterrows():
                    tag = "match-tag" if row["Status"] == "CONFLUÊNCIA" else "neutro-tag" if row["Status"] == "NEUTRO" else "veto-tag"
                    html += f"<tr><td>{row['Hora']}</td><td>{row['Manchete']}</td><td><span class='{tag}'>{row['Status']}</span></td></tr>"
                st.markdown(f'<div class="scroll-container">{html}</table></div>', unsafe_allow_html=True)

    with t2:
        st.subheader("🕵️ Auditoria de Expressões Identificadas")
        if not df_audit.empty:
            st.table(df_audit[["Hora", "Manchete", "Status", "Alpha"]])

    with t3:
        st.subheader("🧠 Treinamento de Expressões de Peso")
        cl, cr = st.columns(2)
        with cl:
            st.markdown("✅ **Expressões Verificadas**")
            for exp, val in sorted(verified.items()):
                st.markdown(f'<div class="learned-box">{exp.upper()} ({val})</div>', unsafe_allow_html=True)
        with cr:
            st.markdown("💡 **Novas Expressões Sugeridas**")
            for exp, data in list(memory.items())[:10]:
                col_txt, col_v = st.columns([4, 1])
                col_txt.markdown(f'<div class="learned-box">{exp.upper()}<br><small>{data.get("news")}</small></div>', unsafe_allow_html=True)
                if col_v.button("Add", key=f"add_{exp}"):
                    verified[exp] = data["alpha"]
                    del memory[exp]
                    save_json(VERIFIED_FILE, verified); save_json(MEMORY_FILE, memory); st.rerun()

if __name__ == "__main__": main()
