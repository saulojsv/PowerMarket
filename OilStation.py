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
from datetime import datetime, timedelta

# Importação para Auto-Update
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

# --- PARÂMETROS ECONOMÉTRICOS ---
DB_FILE = "Oil_Chaos_Master_Log.xlsx"
HALFLIFE_MINUTES = 60  
VOLATILITY_THRESHOLD = 12.0  

RSS_FEEDS = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Energy Exch": "https://www.energyexch.com/news.php?do=newsrss",
    "Investing (Macro)": "https://www.investing.com/rss/news_11.rss",
    "Ground News": "https://ground.news/rss/interest/oil-and-gas-sector",
    "gCaptain (Logistica)": "https://gcaptain.com/feed/"
}

LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict": [9.5, 1, "Geopolitica (War)"],
    r"opec|saudi|cut|quota|production curb": [9.0, 1, "Politica OPEP"],
    r"force majeure|shut-in|outage|pipeline leak|fire": [9.5, 1, "Choque Fisico (Supply)"],
    r"sanction|ban|embargo|price cap": [8.0, 1, "Geopolitica (Sancoes)"],
    r"inventory|stockpile|draw|drawdown": [7.0, 1, "Dados de Estoque"],
    r"build|glut|oversupply": [7.0, -1, "Dados de Estoque"],
    r"china|stimulus|recovery|growth": [7.5, 1, "Demanda China"],
    r"recession|slowdown|weak|contracting|pmi miss": [8.0, -1, "Destruicao de Demanda"],
    r"fed|rate hike|hawkish|inflation|cpi": [6.5, -1, "Macro Monetario"],
    r"dovish|rate cut|powell|liquidity": [6.5, 1, "Macro Monetario"],
    r"dollar|dxy|greenback": [6.0, -1, "Correlacao FX"],
    r"backwardation|premium": [7.0, 1, "Estrutura de Mercado"],
    r"contango|discount": [7.0, -1, "Estrutura de Mercado"]
}

LEXICON_MODIFIERS = {
    r"unexpected|surprise|shock|massive|surge|soar|jump|skyrocket": 1.5,
    r"plunge|crash|collapse|freefall|dump": 1.5,
    r"breakout|critical|pivotal|major": 1.25,
    r"rumor|unconfirmed|reportedly|maybe|potential|possible|could": 0.5,
    r"muted|flat|steady|unchanged|considers|weighs": 0.6
}

def calculate_complex_alpha(title):
    title_lower = title.lower()
    base_alpha = 0
    direction = 0
    category = "Geral"
    multiplier = 1.0
    
    for pattern, params in LEXICON_TOPICS.items():
        if re.search(pattern, title_lower):
            base_alpha += params[0]
            if direction == 0: 
                direction = params[1]
                category = params[2]
            
    for pattern, mod_value in LEXICON_MODIFIERS.items():
        if re.search(pattern, title_lower):
            multiplier *= mod_value
            
    return (base_alpha * direction * multiplier), category

def apply_time_decay(df):
    if df.empty: return df
    df['Timestamp'] = pd.to_datetime(df['Data_Full'])
    now = datetime.now()
    lam = np.log(2) / HALFLIFE_MINUTES
    df['Minutes_Ago'] = (now - df['Timestamp']).dt.total_seconds() / 60
    df['Alpha_Decayed'] = df['Alpha'] * np.exp(-lam * df['Minutes_Ago'])
    return df[(df['Minutes_Ago'] < 360) & (abs(df['Alpha_Decayed']) > 0.05)].copy()

def calculate_probability(net_alpha):
    k = 0.20
    prob_buy = 1 / (1 + np.exp(-k * net_alpha))
    return round(prob_buy * 100, 1)

def save_data(data):
    df_new = pd.DataFrame([data])
    try:
        if not os.path.exists(DB_FILE): 
            df_new.to_excel(DB_FILE, index=False)
        else:
            df_old = pd.read_excel(DB_FILE)
            pd.concat([df_old, df_new], ignore_index=True).to_excel(DB_FILE, index=False)
    except: pass

def news_monitor():
    seen = set()
    while True:
        for source, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    title = entry.title
                    if title not in seen:
                        alpha, cat = calculate_complex_alpha(title)
                        if abs(alpha) > 0.5:
                            save_data({
                                "Data": datetime.now().strftime("%Y-%m-%d"),
                                "Hora": datetime.now().strftime("%H:%M:%S"),
                                "Fonte": source,
                                "Manchete": title,
                                "Categoria": cat,
                                "Taxa Alpha": alpha
                            })
                        seen.add(title)
            except: pass
        time.sleep(60)

def main():
    st.set_page_config(page_title="QUANT STATION PRO", layout="wide", page_icon="🛢️")

    # CORREÇÃO DO CSS (unsafe_allow_html=True)
    st.markdown("""
        <style>
        .stApp { background-color: #000000; color: #E0E0E0; }
        [data-testid="stMetricValue"] { font-family: 'Roboto Mono', monospace; font-size: 42px; font-weight: bold; }
        h1, h2, h3 { letter-spacing: 1px; text-transform: uppercase; }
        </style>
        """, unsafe_allow_html=True)

    if st_autorefresh:
        st_autorefresh(interval=60000, key="pro_refresh")

    if 'monitor_active' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    st.title("STATION: INSTITUTIONAL FEED")
    
    if os.path.exists(DB_FILE):
        df_raw = pd.read_excel(DB_FILE)
        if not df_raw.empty:
            df = apply_time_decay(df_raw)
            net_alpha = df['Alpha_Decayed'].sum()
            sentiment_buy = calculate_probability(net_alpha)
            
            # --- ALERTA CISNE NEGRO ---
            last_entry = df_raw.iloc[-1]
            if abs(last_entry['Alpha']) >= VOLATILITY_THRESHOLD:
                color = "#FF0000" if last_entry['Alpha'] < 0 else "#00FF00"
                st.markdown(f'<div style="border:3px solid {color};padding:15px;text-align:center;">'
                            f'<h2 style="color:{color};">⚠️ IMPACTO MUITO ALTO: {last_entry["Alpha"]:.1f} ALPHA</h2>'
                            f'</div>', unsafe_allow_html=True)

            # --- DASHBOARD ---
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                st.metric("PROB. COMPRA", f"{sentiment_buy:.1f}%", f"{net_alpha:.2f} Net Alpha")
            with c2:
                st.metric("VELOCIDADE (1H)", f"{len(df[df['Minutes_Ago'] < 60])} news")
            with c3:
                df_chart = df.sort_values('Timestamp')
                df_chart['Cumulative_Decayed'] = df_chart['Alpha_Decayed'].cumsum()
                fig = px.area(df_chart, x="Data_Hora", y="Cumulative_Decayed", template="plotly_dark")
                fig.update_layout(height=250, margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig, use_container_width=True)

            # --- HEATMAP ---
            st.divider()
            src_grp = df.groupby('Fonte')['Alpha_Decayed'].sum().reset_index()
            cols = st.columns(len(src_grp)) if not src_grp.empty else [st]
            for idx, row in src_grp.iterrows():
                color = "#44FF44" if row['Alpha_Decayed'] > 0 else "#FF4444"
                cols[idx % 4].markdown(f'<div style="border:1px solid #333;text-align:center;padding:5px;">'
                                       f'<small>{row["Fonte"]}</small><br><b style="color:{color};">{row["Alpha_Decayed"]:.1f}</b>'
                                       f'</div>', unsafe_allow_html=True)

            st.dataframe(df[['Data_Hora', 'Fonte', 'Categoria', 'Manchete', 'Alpha']].sort_values(by="Data_Hora", ascending=False), use_container_width=True)
    else:
        st.info("Aguardando fluxo de dados...")

if __name__ == "__main__":
    main()
