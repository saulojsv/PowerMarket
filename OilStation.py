import pandas as pd
import re
import feedparser
import time
import os
import streamlit as st
import plotly.graph_objects as go
import numpy as np
import yfinance as yf
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. PARÂMETROS DE BANCA E RISCO (300€) ---
BANCA_INICIAL = 300.00
MULTIPLICADOR_MICRO = 10.0  # 1.00 USD no Petróleo = 10.00€ (Contrato Micro)
IA_STOP_LOSS = 50.0        
IA_TAKE_PROFIT = 100.00     

st.set_page_config(page_title="V54 | BANCA 300€ IA", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_pro")

DB_FILE = "Oil_Station_V54_Master.csv"
TRADE_LOG_FILE = "Trade_Simulation_V54.csv"

# --- 2. CONFIGURAÇÕES (SITES E LEXICONS) ---
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
    "IEA News": "https://www.iea.org/news/rss"
}

LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict|escalation|invasion": [9.8, 1, "Geopolítica (Conflito)"],
    r"sanction|embargo|ban|price cap|seizure|blockade|nuclear": [9.0, 1, "Geopolítica (Sanções)"],
    r"iran|strait of hormuz|red sea|houthis|bab al-mandab|suez": [9.8, 1, "Risco de Chokepoint"],
    r"israel|gaza|hezbollah|lebanon|tehran|kremlin|ukraine": [9.2, 1, "Tensões Regionais"],
    r"opec|saudi|russia|novak|bin salman|cut|quota|output curb": [9.5, 1, "Política OPEP+"],
    r"voluntary cut|unwinding|compliance|production target": [8.5, 1, "Oferta OPEP+"],
    r"shale|fracking|permian|rig count|drilling|bakken|spr": [7.5, -1, "Oferta EUA (Shale)"],
    r"non-opec|brazil|guyana|canada|output surge": [7.0, -1, "Oferta Extra-OPEP"],
    r"inventory|stockpile|draw|drawdown|depletion|api|eia": [8.0, 1, "Estoques (Déficit)"],
    r"build|glut|oversupply|surplus|storage full": [8.0, -1, "Estoques (Excesso)"],
    r"refinery|outage|maintenance|gasoline|distillates": [7.0, 1, "Refino/Margens"],
    r"crack spread|heating oil|jet fuel|diesel demand": [6.5, 1, "Derivados"],
    r"recession|slowdown|weak|contracting|hard landing|china": [8.8, -1, "Macro (Demanda Fraca)"],
    r"demand surge|recovery|consumption|growth|stimulus": [8.2, 1, "Macro (Demanda Forte)"],
    r"fed|rate hike|hawkish|inflation|cpi|interest rate": [7.5, -1, "Macro (Aperto Fed)"],
    r"dovish|rate cut|powell|liquidity|easing|soft landing": [7.5, 1, "Macro (Estímulo Fed)"],
    r"dollar|dxy|greenback|fx|yields": [7.0, -1, "Correlação DXY"],
    r"gdp|pmi|manufacturing|industrial production": [6.8, 1, "Indicadores Macro"],
    r"hedge funds|bullish|bearish|short covering|positioning": [6.5, 1, "Fluxo Especulativo"],
    r"technical break|resistance|support|moving average": [6.0, 1, "Análise Técnica"],
    r"volatility|vix|contango|backwardation": [6.2, 1, "Estrutura de Termo"],
    r"algorithmic trading|ctas|margin call|liquidation": [6.0, 1, "Fluxo Quant"]
}

# --- 3. MOTOR DE GESTÃO IA (EXECUÇÃO E RISCO) ---

def run_ia_management(current_oil, avg_alpha):
    """IA decide entradas e monitora saídas para proteger os 300€"""
    if not os.path.exists(TRADE_LOG_FILE):
        pd.DataFrame(columns=["Data", "Tipo", "Entrada", "Status", "PnL", "Motivo"]).to_csv(TRADE_LOG_FILE, index=False)
    
    df = pd.read_csv(TRADE_LOG_FILE)
    
    # 1. Verificar Saídas (Take Profit / Stop Loss)
    if not df.empty and (df['Status'] == 'OPEN').any():
        idx = df[df['Status'] == 'OPEN'].index[0]
        row = df.iloc[idx]
        
        # Cálculo de lucro/perda real
        pnl_float = (current_oil - row['Entrada']) * MULTIPLICADOR_MICRO if row['Tipo'] == 'BUY' else (row['Entrada'] - current_oil) * MULTIPLICADOR_MICRO
        
        exit_trigger = None
        if pnl_float >= IA_TAKE_PROFIT: exit_trigger = "IA_TP_REACHED"
        elif pnl_float <= -IA_STOP_LOSS: exit_trigger = "IA_SL_PROTECTION"
        
        if exit_trigger:
            df.at[idx, 'Status'] = 'CLOSED'
            df.at[idx, 'PnL'] = pnl_float
            df.at[idx, 'Motivo'] = exit_trigger
            df.to_csv(TRADE_LOG_FILE, index=False)
            st.toast(f"Trade encerrado pela IA: {exit_trigger}")

    # 2. Verificar Entradas (Apenas se não houver trade aberto)
    else:
        side = None
        if avg_alpha >= 3.0: side = "BUY"
        elif avg_alpha <= -3.0: side = "SELL"
        
        if side:
            new_row = {"Data": datetime.now().strftime("%H:%M"), "Tipo": side, 
                       "Entrada": current_oil, "Status": "OPEN", "PnL": 0, "Motivo": "ALPHA_SIGNAL"}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_csv(TRADE_LOG_FILE, index=False)
            st.toast(f"IA entrou em {side} no Petróleo", icon="🚀")

# --- 4. FUNÇÕES DE SUPORTE (MANTIDAS) ---
def run_global_scrap():
    news_data = []
    for name, url in RSS_SOURCES.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            title = entry.title
            score, cat = 0, "Neutral"
            for patt, (w, d, c) in LEXICON_TOPICS.items():
                if re.search(patt, title.lower()):
                    score = w * d
                    cat = c
                    break
            news_data.append({"TS": time.time(), "Data": datetime.now().strftime("%H:%M"), 
                              "Fonte": name, "Manchete": title[:80], "Alpha": score, "Cat": cat})
    df = pd.DataFrame(news_data)
    if os.path.exists(DB_FILE):
        df = pd.concat([df, pd.read_csv(DB_FILE)]).drop_duplicates(subset=['Manchete']).head(100)
    df.to_csv(DB_FILE, index=False)

def get_market_intel():
    try:
        tickers = ["CL=F", "DX-Y.NYB", "USDCAD=X", "GC=F"]
        data = yf.download(tickers, period="2d", interval="15m", progress=False)['Close']
        return data.iloc[-1], ((data.iloc[-1]/data.iloc[0])-1)*100, data.corr()
    except: return None

# --- 5. INTERFACE ---
def main():
    st.markdown("""<style> .stApp { background-color: #02060C; color: #E0E0E0; } </style>""", unsafe_allow_html=True)
    
    # Execução do Motor
    run_global_scrap()
    market = get_market_intel()
    if not market: return
    prices, deltas, corr = market
    
    df_news = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()
    avg_alpha = df_news['Alpha'].head(15).mean() if not df_news.empty else 0
    
    # IA Rodando em background
    run_ia_management(prices['CL=F'], avg_alpha)

    # UI BANNER
    st.markdown(f"""<div style="background:#0B121D; padding:15px; border-radius:5px; border-left:5px solid #39FF14;">
        <span style="color:#39FF14; font-weight:bold;"> IA MANAGER ATIVO</span> | 
        Banca Inicial: 300€ | Risco: {IA_STOP_LOSS}€ | Alvo: {IA_TAKE_PROFIT}€
    </div>""", unsafe_allow_html=True)

    # MÉTRICAS E VELOCÍMETRO
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("WTI OIL", f"${prices['CL=F']:.2f}", f"{deltas['CL=F']:.2f}%")
    c2.metric("DXY INDEX", f"{prices['DX-Y.NYB']:.2f}")
    
    # Saldo Real-Time
    df_trades = pd.read_csv(TRADE_LOG_FILE) if os.path.exists(TRADE_LOG_FILE) else pd.DataFrame()
    lucro_acumulado = df_trades['PnL'].sum() if not df_trades.empty else 0
    c3.metric("BANCA ATUAL", f"€{BANCA_INICIAL + lucro_acumulado:.2f}", f"€{lucro_acumulado:+.2f}")
    c4.metric("ALPHA SENTIMENT", f"{avg_alpha:.2f}")

    tab_news, tab_trades = st.tabs(["GLOBAL NEWS FLOW", "IA TRADE LOG"])
    
    with tab_news:
        st.dataframe(df_news.head(50), use_container_width=True, hide_index=True)
    
    with tab_trades:
        st.subheader("Histórico de Operações Gerenciadas")
        st.table(df_trades.sort_index(ascending=False).head(20))

if __name__ == "__main__":
    main()
