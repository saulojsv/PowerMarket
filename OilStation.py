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
AUDIT_CSV = "Oil_Station_Audit.csv"

# Estilização Profissional (Bloomberg/Reuters Style)
st.markdown("""
    <style>
    .stApp { background: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    
    /* Live Header */
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0F172A; border-bottom: 1px solid #1E293B; margin-bottom: 20px; font-family: 'Courier New', monospace; font-size: 12px; }
    .status-live { color: #00FFC8; font-weight: bold; }
    .status-off { color: #EF4444; font-weight: bold; }

    /* Dashboard Cards */
    .driver-card { background: #111827; border-left: 3px solid #1E293B; padding: 12px; border-radius: 4px; text-align: left; }
    .driver-val { font-size: 20px; font-weight: bold; color: #F8FAFC; font-family: monospace; }
    .driver-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; }

    /* Professional Audit Table (Bloomberg Style) */
    .terminal-table { width: 100%; border-collapse: collapse; font-family: 'Courier New', monospace; font-size: 13px; background: #020617; }
    .terminal-table th { background: #1E293B; color: #94A3B8; text-align: left; padding: 10px; text-transform: uppercase; font-size: 11px; border-bottom: 1px solid #334155; }
    .terminal-table td { padding: 12px 10px; border-bottom: 1px solid #0F172A; vertical-align: middle; }
    .terminal-table tr:hover { background: #0F172A; }
    
    /* Tags de Viés */
    .bias-tag { padding: 4px 8px; border-radius: 2px; font-weight: bold; font-size: 11px; text-align: center; display: inline-block; min-width: 70px; }
    .up { background: #064E3B; color: #34D399; }
    .down { background: #450A0A; color: #F87171; }
    .mid { background: #1E293B; color: #94A3B8; }
    
    .manchete-text { color: #CBD5E1; font-weight: 500; }
    .source-text { color: #64748B; font-size: 11px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LOGICA DE DADOS ---
OIL_MANDATORY_TERMS = ["oil", "wti", "crude", "brent", "opec", "inventory", "tengiz", "production"]

def load_json(p):
    if os.path.exists(p):
        with open(p, 'r') as f: return json.load(f)
    return {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, indent=4)

def get_market_metrics():
    try:
        wti = yf.Ticker("CL=F").history(period="2d")
        if wti.empty: raise Exception()
        wti_p, wti_prev = wti['Close'].iloc[-1], wti['Close'].iloc[-2]
        change_pct = ((wti_p - wti_prev) / wti_prev) * 100
        # Z-Score simplificado: variação normalizada
        return {"WTI": wti_p, "Z": round(change_pct / 1.2, 2), "status": "LIVE_YF", "is_live": True}
    except:
        return {"WTI": 0.0, "Z": 0.0, "status": "MKT_OFFLINE", "is_live": False}

def fetch_news():
    sources = {"OilPrice": "https://oilprice.com/rss/main", "Investing": "https://www.investing.com/rss/news_11.rss"}
    news_list = []
    verified = load_json(VERIFIED_FILE)
    
    for source, url in sources.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.title
                title_low = title.lower()
                if not any(t in title_low for t in OIL_MANDATORY_TERMS): continue

                lex_dir = 0
                for v_expr, v_dir in verified.items():
                    if v_expr.lower() in title_low:
                        lex_dir = v_dir
                        break

                # Simulação de IA para exemplo rápido (em produção usa Gemini)
                ai_dir = 1 if "jump" in title_low or "halt" in title_low else -1 if "fall" in title_low or "build" in title_low else 0
                alpha = (lex_dir * 10.0) + (ai_dir * 4.0)
                
                news_list.append({
                    "Hora": datetime.now().strftime("%H:%M:%S"),
                    "Fonte": source,
                    "Manchete": title[:110],
                    "Lexicon_Bias": lex_dir,
                    "AI_Bias": ai_dir,
                    "Alpha": alpha
                })
        except: continue
    if news_list: pd.DataFrame(news_list).to_csv(AUDIT_CSV, index=False)

# --- 3. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    
    # Header com correção de Status
    status_class = "status-live" if mkt["is_live"] else "status-off"
    st.markdown(f"""
        <div class="live-status">
            <div><b>XTIUSD TERMINAL</b> | V90 EVO</div>
            <div class="{status_class}">● {mkt["status"]} | {datetime.now().strftime("%H:%M:%S")}</div>
        </div>
    """, unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 AUDIT FEED", "🧠 TRAINING"])

    with t1:
        # Conteúdo da aba principal conforme solicitado
        c1, c2, c3, c4 = st.columns(4)
        sentiment_val = df['Alpha'].mean() if not df.empty else 0.0
        with c1: st.markdown(f'<div class="driver-card"><div class="driver-label">WTI Spot</div><div class="driver-val">$ {mkt["WTI"]:.2f}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="driver-card"><div class="driver-label">Sentiment Driver</div><div class="driver-val">{sentiment_val:.2f}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="driver-card"><div class="driver-label">Z-Score (Volatility)</div><div class="driver-val">{mkt["Z"]:.2f}</div></div>', unsafe_allow_html=True)
        
        ica_val = (sentiment_val + (mkt['Z'] * -5)) / 2
        with c4: st.markdown(f'<div class="driver-card"><div class="driver-label">ICA Score</div><div class="driver-val" style="color:#00FFC8">{ica_val:.2f}</div></div>', unsafe_allow_html=True)

        fig = go.Figure(go.Indicator(mode="gauge+number", value=ica_val, gauge={'axis': {'range': [-15, 15]}, 'bar': {'color': "#00FFC8"}}))
        fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
        st.plotly_chart(fig, width='stretch')

    with t2:
        # ABA AUDITORIA PADRÃO BLOOMBERG
        st.markdown("### 🔍 Professional Sentiment Audit")
        if not df.empty:
            html = """<table class="terminal-table">
                        <tr>
                            <th>Time</th>
                            <th>Source</th>
                            <th>Headline</th>
                            <th>Lexicon Bias</th>
                            <th>AI Bias</th>
                            <th>Alpha</th>
                        </tr>"""
            for _, r in df.iterrows():
                # Formatação de Tags
                l_bias = "UP" if r['Lexicon_Bias'] > 0 else "DOWN" if r['Lexicon_Bias'] < 0 else "MID"
                l_cls = "up" if l_bias == "UP" else "down" if l_bias == "DOWN" else "mid"
                
                a_bias = "UP" if r['AI_Bias'] > 0 else "DOWN" if r['AI_Bias'] < 0 else "MID"
                a_cls = "up" if a_bias == "UP" else "down" if a_bias == "DOWN" else "mid"
                
                html += f"""
                    <tr>
                        <td style="color:#64748B">{r['Hora']}</td>
                        <td class="source-text">{r['Fonte']}</td>
                        <td class="manchete-text">{r['Manchete']}</td>
                        <td><span class="bias-tag {l_cls}">{l_bias}</span></td>
                        <td><span class="bias-tag {a_cls}">{a_bias}</span></td>
                        <td style="font-weight:bold; color:{'#34D399' if r['Alpha'] > 0 else '#F87171' if r['Alpha'] < 0 else '#94A3B8'}">{r['Alpha']:.1f}</td>
                    </tr>
                """
            st.markdown(html + "</table>", unsafe_allow_html=True)

    with t3:
        st.info("Aba de treinamento conforme lógica de expressões de peso.")
        # ... (Manter lógica de treinamento anterior aqui)

if __name__ == "__main__": main()
