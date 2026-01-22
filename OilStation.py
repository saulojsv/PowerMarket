import pandas as pd
import feedparser
import os
import json
import streamlit as st
import yfinance as yf
from google import genai 
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DE CHAVES ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")
VERIFIED_FILE = "verified_lexicons.json"
AUDIT_CSV = "Oil_Station_Audit.csv"

# --- CONFIGURAÇÃO ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v100_refresh") 

# CSS Unificado: Forçando tabelas a saírem do branco para o Dark/Neon
st.markdown("""
    <style>
    .stApp { background: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0F172A; border-bottom: 1px solid #00FFC8; margin-bottom: 20px; font-family: monospace; font-size: 12px; }
    .status-live { color: #00FFC8; font-weight: bold; }
    .driver-card { background: #111827; border-left: 3px solid #1E293B; padding: 12px; border-radius: 4px; }
    .driver-val { font-size: 20px; font-weight: bold; color: #F8FAFC; font-family: monospace; }
    .driver-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; }
    
    /* CORREÇÃO DO FUNDO BRANCO NAS TABELAS */
    div[data-testid="stDataFrame"] {
        background-color: #020617;
        border: 1px solid #1E293B;
        border-radius: 4px;
    }
    
    /* Estilo para as abas (Tabs) */
    .stTabs [data-baseweb="tab-list"] { background-color: #050A12; }
    .stTabs [data-baseweb="tab"] { color: #94A3B8; }
    .stTabs [data-baseweb="tab-highlight"] { background-color: #00FFC8; }

    .ai-insight { background: #0F172A; border: 1px solid #00FFC8; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 13px; color: #00FFC8; margin-top: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- NÚCLEO DE INTELIGÊNCIA AUTOMÁTICA ---
def auto_train_lexicon(headline):
    try:
        prompt = f"""Analise a manchete: '{headline}'. 
        1. Extraia a expressão técnica principal.
        2. Atribua um peso de impacto no WTI (-1.0 a 1.0).
        Responda apenas JSON: {{"termo": "expressao", "peso": 0.0, "analise": "motivo"}}"""
        
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        data = json.loads(response.text)
        
        verified = {}
        if os.path.exists(VERIFIED_FILE):
            with open(VERIFIED_FILE, 'r') as f: verified = json.load(f)
        
        verified[data['termo'].lower()] = data['peso']
        with open(VERIFIED_FILE, 'w') as f: json.dump(verified, f)
        
        return data['peso'], data['analise']
    except:
        return 0.0, "Análise offline"

def get_strategic_analysis(df):
    if df.empty: return "Aguardando dados..."
    try:
        headlines = "\n".join(df.head(5)['Manchete'].tolist())
        prompt = f"Baseado nas notícias recentes de petróleo:\n{headlines}\nForneça viés e impacto esperado."
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return response.text
    except: return "IA em processamento..."

# --- LÓGICA DE DADOS ---
NEWS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "RigZone": "https://www.rigzone.com/news/rss/rigzone_latest.aspx"
}

def fetch_news():
    news_list = []
    for source, url in NEWS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.title
                if not any(x in title.lower() for x in ["oil", "wti", "crude"]): continue
                
                peso_ia, analise_ia = auto_train_lexicon(title)
                
                news_list.append({
                    "Timestamp": datetime.now(),
                    "Data": datetime.now().strftime("%d/%m %H:%M"),
                    "Fonte": source,
                    "Manchete": title,
                    "Lexicon_Peso": peso_ia,
                    "Interpretacao": analise_ia,
                    "Match": "YES" if abs(peso_ia) > 0.3 else "MID",
                    "Alpha": peso_ia * 10
                })
        except: continue
    
    if news_list:
        new_df = pd.DataFrame(news_list)
        if os.path.exists(AUDIT_CSV):
            old_df = pd.read_csv(AUDIT_CSV)
            combined = pd.concat([old_df, new_df]).drop_duplicates(subset=['Manchete']).sort_values(by="Timestamp", ascending=False)
            combined.to_csv(AUDIT_CSV, index=False)
        else: new_df.to_csv(AUDIT_CSV, index=False)

def get_market_metrics():
    try:
        wti = yf.Ticker("CL=F").history(period="2d")
        wti_p = wti['Close'].iloc[-1]
        change = ((wti_p - wti['Close'].iloc[-2]) / wti['Close'].iloc[-2]) * 100
        return {"WTI": wti_p, "Z": round(change / 1.2, 2), "status": "LIVE"}
    except: return {"WTI": 0.0, "Z": 0.0, "status": "OFFLINE"}

# --- INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    
    st.markdown(f'<div class="live-status"><div><b>XTIUSD TERMINAL</b></div><div class="status-live">● {mkt["status"]} | {datetime.now().strftime("%H:%M:%S")}</div></div>', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 AUDIT FEED", "🧠 BRAIN"])

    with t1:
        sentiment_val = df['Alpha'].mean() if not df.empty else 0.0
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="driver-card"><div class="driver-label">WTI</div><div class="driver-val">$ {mkt["WTI"]:.2f}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="driver-card"><div class="driver-label">SENTIMENT</div><div class="driver-val">{sentiment_val:.2f}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="driver-card"><div class="driver-label">Z-SCORE</div><div class="driver-val">{mkt["Z"]:.2f}</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="driver-card"><div class="driver-label">ICA SCORE</div><div class="driver-val" style="color:#00FFC8">{(sentiment_val + (mkt["Z"]*-5))/2:.2f}</div></div>', unsafe_allow_html=True)

        st.markdown("### 🤖 GEMINI STRATEGIC INSIGHT")
        st.markdown(f'<div class="ai-insight">{get_strategic_analysis(df)}</div>', unsafe_allow_html=True)

        if not df.empty:
            st.markdown("<br>", unsafe_allow_html=True)
            # Aplicando largura corrigida e tema dark forçado via CSS
            st.dataframe(df.head(15)[["Data", "Match", "Manchete"]], width=None, use_container_width=True, hide_index=True)

    with t2:
        st.markdown("### 🔍 Professional Audit Trail")
        if not df.empty:
            st.dataframe(df, width=None, use_container_width=True, hide_index=True)

    with t3:
        st.markdown("### 🧠 Autonomous Intelligence Training")
        if os.path.exists(VERIFIED_FILE):
            with open(VERIFIED_FILE, 'r') as f: verified = json.load(f)
            st.json(verified)

if __name__ == "__main__": main()
