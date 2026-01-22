import pandas as pd
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
# Chave de API extraída das suas configurações salvas
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")
SERVICE_ACCOUNT_FILE = 'oilstation-485112-ac2d104d1370.json' 
SCOPES = ['https://www.googleapis.com/auth/drive']

# --- 1. CONFIGURAÇÃO ESTÉTICA ---
st.set_page_config(page_title="TERMINAL XTIUSD", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v92_refresh") 

VERIFIED_FILE = "verified_lexicons.json"
AUDIT_CSV = "Oil_Station_Audit.csv"
REPORT_MARKER = "last_report_date.txt"

st.markdown("""
    <style>
    .stApp { background: #050A12; color: #FFFFFF; }
    header {visibility: hidden;}
    .live-status { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0F172A; border-bottom: 1px solid #00FFC8; margin-bottom: 20px; font-family: monospace; font-size: 12px; }
    .status-live { color: #00FFC8; font-weight: bold; }
    .stButton>button { background-color: transparent; color: #00FFC8; border: 1px solid #00FFC8; border-radius: 4px; font-family: monospace; font-weight: bold; width: 100%; transition: 0.3s; }
    .stButton>button:hover { background-color: #00FFC8; color: #050A12; box-shadow: 0 0 15px #00FFC8; }
    .driver-card { background: #111827; border-left: 3px solid #1E293B; padding: 12px; border-radius: 4px; }
    .driver-val { font-size: 20px; font-weight: bold; color: #F8FAFC; font-family: monospace; }
    .driver-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; }
    .terminal-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 13px; }
    .terminal-table th { background: #1E293B; color: #00FFC8; text-align: left; padding: 8px; border-bottom: 1px solid #334155; }
    .terminal-table td { padding: 8px; border-bottom: 1px solid #0F172A; }
    .ai-insight { background: #0F172A; border: 1px solid #00FFC8; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 13px; color: #00FFC8; margin-top: 10px; }
    .scroll-box { height: 400px; overflow-y: auto; background: #020617; border: 1px solid #1E293B; padding: 5px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. INTEGRAÇÃO GEMINI AI ---
def get_gemini_analysis(df):
    if df.empty: return "Aguardando dados para análise..."
    try:
        # Pegamos as 10 manchetes mais recentes para o Gemini analisar
        recent_headlines = "\n".join(df.head(10)['Manchete'].tolist())
        prompt = f"""
        Como analista expert em Petróleo WTI, analise estas manchetes recentes:
        {recent_headlines}
        
        Forneça um insight curto (máximo 3 linhas) sobre o viés predominante (BULLISH, BEARISH ou NEUTRAL) e o motivo principal.
        """
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return response.text
    except Exception as e:
        return f"IA Temporariamente indisponível: {str(e)}"

# --- 3. LÓGICA DE DRIVE ---
def upload_to_drive():
    if not os.path.exists(SERVICE_ACCOUNT_FILE): return False
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': f"Audit_Oil_{datetime.now().strftime('%Y-%m-%d')}.csv"}
        media = MediaFileUpload(AUDIT_CSV, mimetype='text/csv')
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return True
    except: return False

# --- 4. LÓGICA DE DADOS ---
OIL_MANDATORY_TERMS = ["oil", "wti", "crude", "brent", "opec", "inventory", "tengiz", "production", "shale"]
NEWS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Investing": "https://www.investing.com/rss/news_11.rss",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=energy",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15838907",
    "RigZone": "https://www.rigzone.com/news/rss/rigzone_latest.aspx"
}

def fetch_news():
    news_list = []
    verified = {}
    if os.path.exists(VERIFIED_FILE):
        try:
            with open(VERIFIED_FILE, 'r') as f: verified = json.load(f)
        except: pass
    
    for source, url in NEWS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.title
                title_low = title.lower()
                if not any(t in title_low for t in OIL_MANDATORY_TERMS): continue
                
                dt_parsed = entry.get('published_parsed', datetime.now().timetuple())
                dt_obj = datetime(*dt_parsed[:6])
                
                lex_dir = 0
                for expr, val in verified.items():
                    if expr.lower() in title_low:
                        lex_dir = val
                        break
                
                ai_dir = 1 if any(x in title_low for x in ["cut", "rise", "tight"]) else -1 if any(x in title_low for x in ["build", "fall", "glut"]) else 0
                
                news_list.append({
                    "Timestamp": dt_obj,
                    "Data": dt_obj.strftime("%d/%m %H:%M"),
                    "Fonte": source,
                    "Manchete": title,
                    "Link": entry.link,
                    "Lexicon_Bias": lex_dir,
                    "AI_Bias": ai_dir,
                    "Alpha": (lex_dir * 10.0) + (ai_dir * 4.0)
                })
        except: continue
    
    if news_list:
        new_df = pd.DataFrame(news_list)
        if os.path.exists(AUDIT_CSV):
            old_df = pd.read_csv(AUDIT_CSV)
            old_df['Timestamp'] = pd.to_datetime(old_df['Timestamp'])
            combined = pd.concat([old_df, new_df]).drop_duplicates(subset=['Manchete'], keep='last')
            combined = combined.sort_values(by="Timestamp", ascending=False)
            combined.to_csv(AUDIT_CSV, index=False)
        else:
            new_df.sort_values(by="Timestamp", ascending=False).to_csv(AUDIT_CSV, index=False)

def get_market_metrics():
    try:
        wti = yf.Ticker("CL=F").history(period="2d")
        wti_p = wti['Close'].iloc[-1]
        change_pct = ((wti_p - wti['Close'].iloc[-2]) / wti['Close'].iloc[-2]) * 100
        return {"WTI": wti_p, "Z": round(change_pct / 1.2, 2), "status": "LIVE"}
    except: return {"WTI": 0.0, "Z": 0.0, "status": "OFFLINE"}

# --- 5. INTERFACE ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df = pd.read_csv(AUDIT_CSV) if os.path.exists(AUDIT_CSV) else pd.DataFrame()
    
    st.markdown(f'<div class="live-status"><div><b>XTIUSD TERMINAL</b></div><div class="status-live">● {mkt["status"]} | {datetime.now().strftime("%H:%M:%S")}</div></div>', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📊 DASHBOARD", "🔍 AUDIT FEED", "🧠 TRAINING"])

    with t1:
        sentiment_val = df['Alpha'].mean() if not df.empty else 0.0
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="driver-card"><div class="driver-label">WTI</div><div class="driver-val">$ {mkt["WTI"]:.2f}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="driver-card"><div class="driver-label">SENTIMENT</div><div class="driver-val">{sentiment_val:.2f}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="driver-card"><div class="driver-label">Z-SCORE</div><div class="driver-val">{mkt["Z"]:.2f}</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="driver-card"><div class="driver-label">ICA SCORE</div><div class="driver-val" style="color:#00FFC8">{(sentiment_val + (mkt["Z"]*-5))/2:.2f}</div></div>', unsafe_allow_html=True)

        # Seção do Gemini Insight
        st.markdown("### 🤖 GEMINI STRATEGIC INSIGHT")
        insight = get_gemini_analysis(df)
        st.markdown(f'<div class="ai-insight">{insight}</div>', unsafe_allow_html=True)

        if not df.empty:
            st.markdown("<br>", unsafe_allow_html=True)
            n_html = '<div class="scroll-box"><table class="terminal-table"><tr><th>DATA</th><th>NOTÍCIA</th></tr>'
            for _, r in df.head(15).iterrows():
                n_html += f"<tr><td style='color:#64748B;'>{r['Data']}</td><td>{r['Manchete']}</td></tr>"
            st.markdown(n_html + "</table></div>", unsafe_allow_html=True)

    with t2:
        st.markdown("### 🔍 Audit Trail")
        if st.button("🚀 Backup Drive"):
            if upload_to_drive(): st.success("OK!")
            else: st.error("Erro!")
        st.dataframe(df, use_container_width=True)

    with t3:
        st.markdown("### 🧠 Lexicon Intelligence Training")
        col_in, col_list = st.columns([1, 1])
        with col_in:
            st.markdown("**Adicionar Nova Expressão**")
            new_expr = st.text_input("Expressão (ex: 'production cut')")
            new_val = st.slider("Peso do Viés (-1.0 a 1.0)", -1.0, 1.0, 0.0, 0.1)
            if st.button("Gravar na Memória"):
                if new_expr:
                    verified = {}
                    if os.path.exists(VERIFIED_FILE):
                        with open(VERIFIED_FILE, 'r') as f: verified = json.load(f)
                    verified[new_expr.lower()] = new_val
                    with open(VERIFIED_FILE, 'w') as f: json.dump(verified, f)
                    st.success(f"'{new_expr}' memorizado!")
                    st.rerun()
        with col_list:
            st.markdown("**Lexicons Ativos**")
            if os.path.exists(VERIFIED_FILE):
                with open(VERIFIED_FILE, 'r') as f: verified = json.load(f)
                for k, v in verified.items(): st.code(f"{k}: {v}")

if __name__ == "__main__": main()
