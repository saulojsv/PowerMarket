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
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIGURAÇÃO DE CHAVES ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")
SERVICE_ACCOUNT_FILE = 'oilstation-485112-ac2d104d1370.json' # Arquivo para o Drive
SCOPES = ['https://www.googleapis.com/auth/drive']

# --- 1. CONFIGURAÇÃO ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v92_refresh") 

MEMORY_FILE = "brain_memory.json"
VERIFIED_FILE = "verified_lexicons.json"
AUDIT_CSV = "Oil_Station_Audit.csv"

# Fontes Expandidas
NEWS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15838907"
}

st.markdown("""
    <style>
    .stApp { background: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0F172A; border-bottom: 1px solid #00FFC8; margin-bottom: 20px; font-family: monospace; font-size: 12px; }
    .status-live { color: #00FFC8; font-weight: bold; }
    .status-off { color: #EF4444; font-weight: bold; }
    .driver-card { background: #111827; border-left: 3px solid #1E293B; padding: 12px; border-radius: 4px; }
    .driver-val { font-size: 20px; font-weight: bold; color: #F8FAFC; font-family: monospace; }
    .driver-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; }
    .terminal-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 13px; margin-top: 10px; }
    .terminal-table th { background: #1E293B; color: #00FFC8; text-align: left; padding: 8px; text-transform: uppercase; border-bottom: 1px solid #334155; }
    .terminal-table td { padding: 10px 8px; border-bottom: 1px solid #0F172A; }
    .bias-tag { padding: 3px 6px; border-radius: 2px; font-weight: bold; font-size: 10px; }
    .up { background: #064E3B; color: #34D399; }
    .down { background: #450A0A; color: #F87171; }
    .mid { background: #1E293B; color: #94A3B8; }
    .scroll-box { height: 400px; overflow-y: auto; background: #020617; border: 1px solid #1E293B; padding: 5px; }
    .link-btn { color: #00FFC8 !important; text-decoration: none; border: 1px solid #00FFC8; padding: 2px 5px; border-radius: 3px; font-size: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LOGICA DE DRIVE ---
def upload_to_drive():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        st.error("Arquivo JSON do Google Drive não encontrado.")
        return
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': f"Audit_Oil_{datetime.now().strftime('%Y-%m-%d')}.csv"}
        media = MediaFileUpload(AUDIT_CSV, mimetype='text/csv')
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        st.success("Relatório salvo no Drive!")
    except Exception as e: st.error(f"Erro no Drive: {e}")

# --- 3. LOGICA DE DADOS ---
OIL_MANDATORY_TERMS = ["oil", "wti", "crude", "brent", "opec", "inventory", "tengiz", "production"]

def get_market_metrics():
    try:
        wti = yf.Ticker("CL=F").history(period="2d")
        wti_p, wti_prev = wti['Close'].iloc[-1], wti['Close'].iloc[-2]
        change_pct = ((wti_p - wti_prev) / wti_prev) * 100
        return {"WTI": wti_p, "Z": round(change_pct / 1.2, 2), "status": "LIVE_YF", "is_live": True}
    except: return {"WTI": 0.0, "Z": 0.0, "status": "MKT_OFFLINE", "is_live": False}

def fetch_news():
    news_list = []
    verified = {} # Carregaria do JSON (load_json)
    
    for source, url in NEWS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                title = entry.title
                title_low = title.lower()
                if not any(t in title_low for t in OIL_MANDATORY_TERMS): continue
                
                # Data da Notícia
                dt_parsed = entry.get('published_parsed', datetime.now().timetuple())
                dt_str = datetime(*dt_parsed[:6]).strftime("%d/%m %H:%M")

                # Lógica simplificada de Viés (Integrar com Gemini conforme anterior)
                ai_dir = 1 if "cut" in title_low else -1 if "build" in title_low else 0
                
                news_list.append({
                    "Data": dt_str,
                    "Fonte": source,
                    "Manchete": title,
                    "Link": entry.link,
                    "Lexicon_Bias": 0,
                    "AI_Bias": ai_dir,
                    "Alpha": ai_dir * 4.0
                })
        except: continue
    if news_list: pd.DataFrame(news_list).to_csv(AUDIT_CSV, index=False)

# --- 4. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    
    status_color = "status-live" if mkt["is_live"] else "status-off"
    st.markdown(f'<div class="live-status"><div><b>XTIUSD TERMINAL</b> | V92 EVO</div><div class="{status_color}">● {mkt["status"]} | {datetime.now().strftime("%H:%M:%S")}</div></div>', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 AUDIT FEED", "🧠 TRAINING"])

    with t1:
        sentiment_val = df['Alpha'].mean() if not df.empty else 0.0
        ica_val = (sentiment_val + (mkt['Z'] * -5)) / 2
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="driver-card"><div class="driver-label">WTI PRICE</div><div class="driver-val">$ {mkt["WTI"]:.2f}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="driver-card"><div class="driver-label">SENTIMENT</div><div class="driver-val">{sentiment_val:.2f}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="driver-card"><div class="driver-label">Z-SCORE</div><div class="driver-val">{mkt["Z"]:.2f}</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="driver-card"><div class="driver-label">ICA SCORE</div><div class="driver-val" style="color:#00FFC8">{ica_val:.2f}</div></div>', unsafe_allow_html=True)

        cl, cr = st.columns([1, 2])
        with cl:
            fig = go.Figure(go.Indicator(mode="gauge+number", value=ica_val, gauge={'axis': {'range': [-15, 15]}, 'bar': {'color': "#00FFC8"}}))
            fig.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, margin=dict(l=20,r=20,t=40,b=20))
            st.plotly_chart(fig, width='stretch')
        
        with cr:
            st.markdown("**LIVE NEWS FEED**")
            if not df.empty:
                n_html = '<div class="scroll-box"><table class="terminal-table">'
                for _, r in df.iterrows():
                    n_html += f"<tr><td style='color:#64748B; font-size:10px;'>{r['Data']}</td><td>{r['Manchete']}</td><td><a href='{r['Link']}' class='link-btn' target='_blank'>LINK</a></td></tr>"
                st.markdown(n_html + "</table></div>", unsafe_allow_html=True)

    with t2:
        st.markdown("### 🔍 Professional Sentiment Audit")
        if st.button("🚀 Backup Audit to Google Drive"): upload_to_drive()
        if not df.empty:
            audit_html = """<table class="terminal-table"><tr><th>DATA</th><th>FONTE</th><th>MANCHETE</th><th>LEXICON</th><th>AI</th><th>ALPHA</th></tr>"""
            for _, r in df.iterrows():
                l_cls = "up" if r['Lexicon_Bias'] > 0 else "down" if r['Lexicon_Bias'] < 0 else "mid"
                a_cls = "up" if r['AI_Bias'] > 0 else "down" if r['AI_Bias'] < 0 else "mid"
                audit_html += f"""<tr>
                    <td><small>{r['Data']}</small></td>
                    <td style="color:#94A3B8">{r['Fonte']}</td>
                    <td>{r['Manchete']}</td>
                    <td><span class="bias-tag {l_cls}">BIAS</span></td>
                    <td><span class="bias-tag {a_cls}">BIAS</span></td>
                    <td style="color:#00FFC8; font-weight:bold;">{r['Alpha']:.1f}</td>
                </tr>"""
            st.markdown(audit_html + "</table>", unsafe_allow_html=True)

if __name__ == "__main__": main()

