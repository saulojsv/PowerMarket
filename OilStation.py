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
from datetime import datetime

# Importação para o Auto-Update (Sem F5)
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

# --- CONFIGURAÇÕES ---
# Ajustado para "Oil_Chaos_Master_Log.xlsx" sem caminho fixo para funcionar no Deploy do GitHub
DB_FILE = "Oil_Chaos_Master_Log.xlsx"

RSS_FEEDS = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Energy Exchange": "https://www.energyexch.com/news.php?do=newsrss",
    "Investing.com (Macro)": "https://www.investing.com/rss/news_11.rss",
    "Ground News (Oil)": "https://ground.news/rss/interest/oil-and-gas-sector",
    "gCaptain Marine": "https://gcaptain.com/feed/"
}

LEXICON = {
    r"oil|crude|brent|wti|petróleo": [2.0, 'Day', 1, "Atividade Geral"],
    r"energy|fuel|gasoline|diesel": [1.0, 'Day', 0, "Energia"],
    r"market|price|trading|surge|slump": [1.5, 'Day', 0, "Price Action"],
    r"war|attack|missile|drone|strike|explosion": [9.5, 'Swing', 1, "Risco Geopolítico"],
    r"red sea|houthis|strait|suez|hormuz": [9.0, 'Swing', 1, "Gargalo Logístico"],
    r"iran|israel|russia|ukraine": [8.5, 'Swing', 1, "Tensão Geopolítica"],
    r"opec|saudi|production cut": [9.5, 'Swing', 1, "OPEP+ Corte"],
    r"inventory|stockpile|eia|drawdown": [7.5, 'Day', 1, "Queda Estoques"],
    r"build": [6.5, 'Day', -1, "Aumento Estoques"],
    r"china|demand|slowdown": [7.0, 'Day', -1, "Demanda China"],
    r"fed|inflation|interest rate|hawkish|dollar|dxy": [6.5, 'Day', -1, "Macro/Forex"],
    r"breakout|resistance|support|bullish|bearish": [5.0, 'Day', 0, "Análise Técnica"]
}

def calculate_probability(alpha_score):
    k = 0.25
    prob_buy = 1 / (1 + np.exp(-k * alpha_score))
    return round(prob_buy * 100, 2)

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
        logs_list = []
        for name, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    title = entry.title
                    logs_list.append(f"{name}: {title[:45]}...")
                    if title not in seen:
                        total_alpha, rationales = 0, []
                        for pattern, params in LEXICON.items():
                            if re.search(pattern, title.lower()):
                                total_alpha += (params[0] * params[2])
                                rationales.append(params[3])
                        
                        if rationales:
                            prob_c = calculate_probability(total_alpha)
                            save_data({
                                "Data_Hora": datetime.now().strftime("%H:%M:%S"),
                                "Manchete": title,
                                "Alpha": total_alpha,
                                "Prob_Compra": prob_c,
                                "Prob_Venda": round(100 - prob_c, 2),
                                "Rationale": " | ".join(set(rationales))
                            })
                        seen.add(title)
            except: pass
        st.session_state['live_feeds'] = logs_list
        time.sleep(30)

def main():
    st.set_page_config(page_title="QUANT STATION CUMULATIVE", layout="wide")

    # --- AUTO REFRESH ATUALIZADO PARA 1 MINUTO (60.000 ms) ---
    if st_autorefresh:
        st_autorefresh(interval=60000, key="auto_refresh_minute")

    if 'monitor_active' not in st.session_state:
        st.session_state['live_feeds'] = []
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    st.title("🛢️ Quant Station: Sentimento Global (Auto-Refresh 1min)")

    if os.path.exists(DB_FILE):
        df = pd.read_excel(DB_FILE)
        if not df.empty:
            # Cálculo de Sentimento Global (últimas 10 notícias)
            window = 10
            global_buy = df['Prob_Compra'].tail(window).mean()
            global_sell = df['Prob_Venda'].tail(window).mean()
            
            # Gauge e Métricas
            col1, col2 = st.columns([1, 2])
            with col1:
                fig_gauge = go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = global_buy,
                    title = {'text': "SENTIMENTO GLOBAL (%)"},
                    gauge = {
                        'axis': {'range': [0, 100]},
                        'bar': {'color': "#00FF00" if global_buy > 50 else "#FF0000"},
                        'steps': [
                            {'range': [0, 40], 'color': "#330000"},
                            {'range': [60, 100], 'color': "#002200"}]}))
                st.plotly_chart(fig_gauge, use_container_width=True)

            with col2:
                st.subheader("📊 Momentum Adaptativo")
                c_buy, c_sell = st.columns(2)
                c_buy.metric("FORÇA COMPRA", f"{global_buy:.1f}%")
                c_sell.metric("FORÇA VENDA", f"{global_sell:.1f}%")
                
                sinal = "🔥 COMPRA" if global_buy > 60 else "❄️ VENDA" if global_sell > 60 else "⚖️ NEUTRO"
                st.info(f"Análise: **{sinal}**")

            # Gráfico de Área
            fig_area = px.area(df, x="Data_Hora", y=["Prob_Compra", "Prob_Venda"], 
                              title="Curva de Probabilidade Acumulada",
                              color_discrete_map={"Prob_Compra": "#00FF00", "Prob_Venda": "#FF0000"},
                              template="plotly_dark")
            st.plotly_chart(fig_area, use_container_width=True)

            # Sidebar
            with st.sidebar:
                st.header("🌐 Status das Fontes")
                for f_name in RSS_FEEDS.keys():
                    st.success(f"Online: {f_name}")
                st.divider()
                st.subheader("📡 Varredura RSS")
                for log in st.session_state.get('live_feeds', []):
                    st.caption(log)

            st.subheader("📋 Ledger: Inteligência Quantitativa")
            st.dataframe(df.sort_values(by="Data_Hora", ascending=False), use_container_width=True)
    else:
        st.info("Aguardando varredura inicial (Reuters, Energy Exch, Ground News)...")

if __name__ == "__main__":
    main()