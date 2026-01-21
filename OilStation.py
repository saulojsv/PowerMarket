import pandas as pd
import re
import feedparser
import os
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from google import genai 
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO IA (INTERPRETAÇÃO DE VIÉS) ---
client = genai.Client(api_key="AIzaSyCtQK_hLAM-mcihwnM0ER-hQzSt2bUMKWM")

st.set_page_config(page_title="TERMINAL XTIUSD - V79", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=300000, key="v79_refresh") 

# --- 2. OS 22 LEXICONS (FONTES RSS) ---
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
    "IEA News": "https://www.iea.org/news/rss",
    "BOC News": "https://www.bankofcanada.ca/feed/",
    "Fed News": "https://www.federalreserve.gov/feeds/press_all.xml"
}

# Tópicos Quantitativos para cálculo do Alpha
LEXICON_TOPICS = {
    r"war|attack|missile|conflict": [9.8, 1, "Geopolitics"],
    r"opec|saudi|russia|cut": [9.5, 1, "Supply"],
    r"inventory|draw|api|eia": [8.0, 1, "Stocks"],
    r"recession|slowdown|china": [8.8, -1, "Demand"],
    r"fed|rate|inflation": [7.5, -1, "Macro"]
}

# --- 3. PROCESSAMENTO DE DADOS ---
def fetch_news():
    news_list = []
    for source, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                score = 0.0
                for patt, (w, d, c) in LEXICON_TOPICS.items():
                    if re.search(patt, entry.title.lower()):
                        score = float(w * d)
                        break
                if score != 0:
                    news_list.append({
                        "Data": datetime.now().strftime("%H:%M"),
                        "Fonte": source,
                        "Manchete": entry.title[:100],
                        "Alpha": score,
                        "Link": entry.link
                    })
        except: continue
    
    if news_list:
        df = pd.DataFrame(news_list)
        if os.path.exists("Oil_Station_V54_Master.csv"):
            old = pd.read_csv("Oil_Station_V54_Master.csv")
            pd.concat([df, old]).drop_duplicates(subset=['Manchete']).head(200).to_csv("Oil_Station_V54_Master.csv", index=False)
        else:
            df.to_csv("Oil_Station_V54_Master.csv", index=False)

@st.cache_data(ttl=300)
def get_market_metrics():
    # Arbitragem Quantitativa WTI vs USDCAD
    tickers = {"WTI": "CL=F", "USDCAD": "USDCAD=X"}
    try:
        data = yf.download(list(tickers.values()), period="5d", interval="15m", progress=False)
        p_wti = data['Close']['CL=F'].iloc[-1]
        p_cad = data['Close']['USDCAD=X'].iloc[-1]
        
        # Z-Score do Spread Relativo
        ratio = data['Close']['CL=F'] / data['Close']['USDCAD=X']
        z_score = (ratio.iloc[-1] - ratio.mean()) / ratio.std()
        return {"WTI": p_wti, "USDCAD": p_cad, "Z": float(z_score)}
    except:
        return {"WTI": 75.0, "USDCAD": 1.35, "Z": 0.0}

# --- 4. INTERFACE PRINCIPAL ---
def main():
    fetch_news()
    mkt = get_market_metrics()
    df_news = pd.read_csv("Oil_Station_V54_Master.csv") if os.path.exists("Oil_Station_V54_Master.csv") else pd.DataFrame()
    
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0.0
    ica_val = (avg_alpha + (mkt['Z'] * -5)) / 2

    st.markdown(f'### TERMINAL XTIUSD | ICA: {ica_val:.2f}')

    tab1, tab2, tab3 = st.tabs(["📊 MONITOR QUANT", "🧠 IA LEARNING", "🤖 AI SITREP"])

    with tab1:
        # Colunas de métricas rápidas
        c1, c2, c3 = st.columns(3)
        c1.metric("WTI", f"$ {mkt['WTI']:.2f}")
        c2.metric("USDCAD", f"{mkt['USDCAD']:.4f}")
        c3.metric("Z-SCORE", f"{mkt['Z']:.2f}")

        # Tabela com Alpha e Manchetes (Conforme solicitado)
        if not df_news.empty:
            st.dataframe(df_news[['Data', 'Fonte', 'Manchete', 'Alpha', 'Link']], use_container_width=True)

    with tab3:
        # A IA interpreta o contexto das manchetes e do ICA matemático
        st.subheader("Análise de Viés e Contexto Atual")
        if not df_news.empty:
            contexto = ". ".join(df_news['Manchete'].head(10).tolist())
            prompt = f"""
            Como analista quant sênior, interprete o viés das seguintes notícias: {contexto}.
            O ICA matemático está em {ica_val:.2f}. 
            Determine se o viés é Positivo (Alta) ou Negativo (Baixa) e explique o que isso representa para o contexto atual do WTI.
            """
            try:
                analise = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                st.info(analise.text)
            except:
                st.warning("IA em calibração...")

if __name__ == "__main__":
    main()
