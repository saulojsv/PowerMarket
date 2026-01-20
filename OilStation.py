import pandas as pd
import re
import feedparser
import time
import os
import threading
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import yfinance as yf
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO DE AMBIENTE ---
st.set_page_config(page_title="V54 QUANT SIMULATOR PRO", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="v54_refresh_sim")

# Arquivos de Dados
DB_FILE = "Oil_Station_V54_Master.csv"
TRADE_LOG_FILE = "Simulation_Log_V54.csv"

# Inicialização de Cache
if 'last_oil_price' not in st.session_state:
    st.session_state.last_oil_price = 0.0

# --- ESTILO ORIGINAL SOLICITADO ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .stApp { background-color: #02060C; color: #E0E0E0; font-family: 'JetBrains Mono', monospace; }
        .trade-row { background: #0B121D; padding: 10px; border-radius: 5px; margin-bottom: 5px; border-left: 4px solid #39FF14; }
        .pnl-positive { color: #39FF14; font-weight: bold; }
        .pnl-negative { color: #FF4B4B; font-weight: bold; }
        .macro-tag { background: #1B2B48; color: #8a96a3; padding: 2px 6px; border-radius: 3px; font-size: 10px; }
        [data-testid="stMetricValue"] { color: #39FF14 !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURAÇÕES MASTER (FONTES & 22 LEXICONS) ---
RSS_SOURCES = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Investing Oil": "https://www.investing.com/rss/news_11.rss",
    "CNBC Energy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    "EIA Reports": "https://www.eia.gov/about/rss/todayinenergy.xml",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Yahoo Finance": "https://finance.yahoo.com/rss/headline?s=CL=F",
    "Bloomberg": "https://www.bloomberg.com/feeds/bview/energy.xml",
    "S&P Global": "https://www.spglobal.com/platts/en/rss-feed/news/oil",
    "Rigzone": "https://www.rigzone.com/news/rss/rigzone_latest.xml"
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

# --- 3. MOTOR DE DADOS ---

def get_live_market():
    try:
        data = yf.download(["CL=F", "USDCAD=X"], period="1d", interval="5m", progress=False)
        oil = data['Close']['CL=F'].iloc[-1]
        cad_open = data['Open']['USDCAD=X'].iloc[0]
        cad_now = data['Close']['USDCAD=X'].iloc[-1]
        cad_delta = ((cad_now / cad_open) - 1) * 100
        st.session_state.last_oil_price = oil
        return oil, cad_delta
    except:
        return st.session_state.last_oil_price, 0.0

def execute_simulated_trade(side, entry_price, reason):
    new_entry = pd.DataFrame([{
        "Data_Hora": datetime.now().strftime("%d/%m %H:%M:%S"),
        "Lote": 1.0,
        "Tipo": side,
        "Entrada": entry_price,
        "Macro_Context": reason,
        "Status": "ACTIVE",
        "TS": datetime.now().timestamp()
    }])
    if os.path.exists(TRADE_LOG_FILE):
        log = pd.read_csv(TRADE_LOG_FILE)
        if (datetime.now().timestamp() - log['TS'].iloc[-1]) > 900: # Proteção 15 min
            pd.concat([log, new_entry], ignore_index=True).to_csv(TRADE_LOG_FILE, index=False)
    else:
        new_entry.to_csv(TRADE_LOG_FILE, index=False)

# --- 4. INTERFACE PRINCIPAL ---

def main():
    oil_price, cad_delta = get_live_market()
    
    st.title("🛡️ QUANT SIMULATOR & MACRO ANALYSIS")
    
    tab_sim, tab_news, tab_lex = st.tabs(["🏦 SIMULATED PORTFOLIO", "📊 SENTIMENT FLOW", "🧠 22 LEXICONS"])

    with tab_news:
        if os.path.exists(DB_FILE):
            df_news = pd.read_csv(DB_FILE).sort_values('TS', ascending=False)
            avg_a = df_news.head(10)['Alpha'].mean()
            
            # Lógica de Decisão (Tese: Sentimento + Validação Câmbio)
            if avg_a > 1.5 and cad_delta < -0.05:
                execute_simulated_trade("BUY", oil_price, "Alpha Bullish + CAD Confirmation")
            elif avg_a < -1.5 and cad_delta > 0.05:
                execute_simulated_trade("SELL", oil_price, "Alpha Bearish + CAD Confirmation")
            
            st.dataframe(df_news[['Data', 'Fonte', 'Manchete', 'Alpha', 'Cat']].head(50), width='stretch', hide_index=True)

    with tab_sim:
        if os.path.exists(TRADE_LOG_FILE):
            trades = pd.read_csv(TRADE_LOG_FILE).sort_values('TS', ascending=False)
            trades['PnL_Points'] = trades.apply(lambda r: oil_price - r['Entrada'] if r['Tipo']=="BUY" else r['Entrada'] - oil_price, axis=1)
            trades['PnL_USD'] = trades['PnL_Points'] * 1000

            c1, c2, c3 = st.columns(3)
            total_pts = trades['PnL_Points'].sum()
            c1.metric("POSIÇÕES SIMULADAS", len(trades))
            c2.metric("ALPHA ACUMULADO", f"{total_pts:+.2f} pts")
            c3.metric("PNL ESTIMADO (1 LOTE)", f"${total_pts * 1000:,.2f}")

            st.markdown("### 📝 Journal de Execução")
            for _, row in trades.iterrows():
                pnl_color = "pnl-positive" if row['PnL_Points'] >= 0 else "pnl-negative"
                st.markdown(f"""
                    <div class="trade-row">
                        <span style="font-size:12px; color:#8a96a3;">{row['Data_Hora']}</span> | 
                        <b style="color:{'#39FF14' if row['Tipo']=='BUY' else '#FF4B4B'}">{row['Tipo']}</b> | 
                        Entrada: <b>${row['Entrada']:.2f}</b> | 
                        PnL: <span class="{pnl_color}">{row['PnL_Points']:+.2f} pts (${row['PnL_USD']:,.2f})</span><br>
                        <span class="macro-tag">MOTIVO: {row['Macro_Context']}</span>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Aguardando confluência macro para abrir posições.")

    with tab_lex:
        st.write("Configuração dos 22 Eixos de Análise:")
        lex_df = pd.DataFrame([{"Regex": k, "Força": v[0], "Bias": v[1], "Categoria": v[2]} for k,v in LEXICON_TOPICS.items()])
        st.dataframe(lex_df, width='stretch')

if __name__ == "__main__": main()
