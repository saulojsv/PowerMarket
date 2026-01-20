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
HALFLIFE_MINUTES = 60  # Tempo para o choque perder 50% da relevância
VOLATILITY_THRESHOLD = 12.0  # Alpha acima disso dispara ALERTA

RSS_FEEDS = {
    "OilPrice": "https://oilprice.com/rss/main",
    "Reuters Energy": "https://www.reutersagency.com/feed/?best-topics=energy&format=xml",
    "Energy Exch": "https://www.energyexch.com/news.php?do=newsrss",
    "Investing (Macro)": "https://www.investing.com/rss/news_11.rss",
    "Ground News": "https://ground.news/rss/interest/oil-and-gas-sector",
    "gCaptain (Logística)": "https://gcaptain.com/feed/"
}

# --- 1. LÉXICO BASE (TOPICS) ---
# Estrutura: Regex: [BaseScore, Direction, Category]
LEXICON_TOPICS = {
    # --- CHOQUES DE OFERTA (SUPPLY SIDE) ---
    r"war|attack|missile|drone|strike|conflict": [9.5, 1, "Geopolítica (War)"],
    r"opec|saudi|cut|quota|production curb": [9.0, 1, "Política OPEP"],
    r"force majeure|shut-in|outage|pipeline leak|fire": [9.5, 1, "Choque Físico (Supply)"],
    r"sanction|ban|embargo|price cap": [8.0, 1, "Geopolítica (Sanções)"],
    r"inventory|stockpile|draw|drawdown": [7.0, 1, "Dados de Estoque"],
    r"build|glut|oversupply": [7.0, -1, "Dados de Estoque"],
    
    # --- CHOQUES DE DEMANDA (DEMAND SIDE) ---
    r"china|stimulus|recovery|growth": [7.5, 1, "Demanda China"],
    r"recession|slowdown|weak|contracting|pmi miss": [8.0, -1, "Destruição de Demanda"],
    r"airline|travel|jet fuel|kerosene": [6.0, 1, "Consumo Físico"],
    
    # --- MACRO & ESTRUTURA (PAPER MARKET) ---
    r"fed|rate hike|hawkish|inflation|cpi": [6.5, -1, "Macro Monetário"],
    r"dovish|rate cut|powell|liquidity": [6.5, 1, "Macro Monetário"],
    r"dollar|dxy|greenback": [6.0, -1, "Correlação FX"],
    r"backwardation|premium": [7.0, 1, "Estrutura de Mercado"],
    r"contango|discount": [7.0, -1, "Estrutura de Mercado"]
}

# --- 2. MODIFICADORES DE IMPACTO (MULTIPLIERS) ---
# Aumentam ou diminuem o peso baseado na credibilidade/surpresa
LEXICON_MODIFIERS = {
    # Amplificadores (Surpresa/Magnitude)
    r"unexpected|surprise|shock|massive|surge|soar|jump|skyrocket": 1.5,
    r"plunge|crash|collapse|freefall|dump": 1.5,
    r"breakout|critical|pivotal|major": 1.25,
    
    # Atenuadores (Incerteza/Ruído)
    r"rumor|unconfirmed|reportedly|maybe|potential|possible|could": 0.5,
    r"muted|flat|steady|unchanged|considers|weighs": 0.6
}

def calculate_complex_alpha(title):
    """Calcula Alpha com base no Tópico * Modificador."""
    title_lower = title.lower()
    base_alpha = 0
    direction = 0
    category = "Geral"
    multiplier = 1.0
    
    # 1. Encontrar o Tópico Base
    for pattern, params in LEXICON_TOPICS.items():
        if re.search(pattern, title_lower):
            # Soma os scores se houver múltiplos tópicos (Confluência interna)
            base_alpha += params[0]
            # Direção domina (se já achou um trigger, mantém a direção ou soma)
            if direction == 0: 
                direction = params[1]
                category = params[2]
            elif direction != params[1]:
                # Conflito na mesma manchete (ex: Estoques caem mas produção sobe)
                direction = 0 
                
    # 2. Encontrar Modificadores (Multiplicadores)
    for pattern, mod_value in LEXICON_MODIFIERS.items():
        if re.search(pattern, title_lower):
            multiplier *= mod_value
            
    # Cálculo Final: Score * Direção * Multiplicador
    final_score = base_alpha * direction * multiplier
    
    return final_score, category

def apply_time_decay(df):
    """Aplica decaimento financeiro (Half-Life)."""
    if df.empty: return df
    
    df['Timestamp'] = pd.to_datetime(df['Data_Full'])
    now = datetime.now()
    lam = np.log(2) / HALFLIFE_MINUTES # Lambda de decaimento
    
    df['Minutes_Ago'] = (now - df['Timestamp']).dt.total_seconds() / 60
    
    # Fórmula: Alpha(t) = Alpha_0 * e^(-lambda * t)
    df['Alpha_Decayed'] = df['Alpha'] * np.exp(-lam * df['Minutes_Ago'])
    
    # Filtra ruído antigo (> 6h ou Alpha residual < 0.1)
    df = df[(df['Minutes_Ago'] < 360) & (abs(df['Alpha_Decayed']) > 0.1)].copy()
    return df

def calculate_probability(net_alpha):
    """Converte Net Alpha em Probabilidade (Sigmoid ajustada)."""
    k = 0.20 # Curva menos íngreme para acomodar scores altos (15+)
    prob_buy = 1 / (1 + np.exp(-k * net_alpha))
    return round(prob_buy * 100, 1)

def save_data(data):
    df_new = pd.DataFrame([data])
    try:
        if not os.path.exists(DB_FILE): 
            df_new.to_excel(DB_FILE, index=False)
        else:
            df_old = pd.read_excel(DB_FILE)
            if 'Fonte' not in df_old.columns: df_old['Fonte'] = 'System'
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
                        # Cálculo Otimizado
                        alpha, cat = calculate_complex_alpha(title)
                        
                        if abs(alpha) > 0.5: # Só salva se tiver impacto relevante
                            prob = calculate_probability(alpha)
                            save_data({
                                "Data/Full": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "Data/Hora": datetime.now().strftime("%H:%M:%S"),
                                "Fonte": source,
                                "Manchete": title,
                                "Categoria": cat,
                                "Alpha": alpha, # Alpha Original (puro)
                                "Probability": prob
                            })
                        seen.add(title)
            except: pass
        time.sleep(60)

def main():
    st.set_page_config(page_title="QUANT STATION PRO", layout="wide", page_icon="🛢️")

    # CSS "War Room" (Dark High Contrast)
    st.markdown("""
        <style>
        .stApp { background-color: #000000; color: #E0E0E0; }
        [data-testid="stMetricValue"] { font-family: 'Roboto Mono', monospace; font-size: 42px; font-weight: bold; }
        .stAlert { background-color: #1A1A1A; border: 1px solid #555; }
        h1, h2, h3 { letter-spacing: 1px; text-transform: uppercase; }
        </style>
        """, unsafe_allow_index=True)

    if st_autorefresh:
        st_autorefresh(interval=60000, key="pro_refresh")

    if 'monitor_active' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    st.title("QUANT STATION: INSTITUTIONAL")
    
    if os.path.exists(DB_FILE):
        df_raw = pd.read_excel(DB_FILE)
        if not df_raw.empty:
            # Aplica a Econometria (Decaimento)
            df = apply_time_decay(df_raw)
            
            # Métricas Principais
            net_alpha = df['Alpha_Decayed'].sum()
            sentiment_buy = calculate_probability(net_alpha)
            sentiment_sell = 100 - sentiment_buy
            
            # --- ÁREA DE ALERTA DE CISNE NEGRO ---
            # Verifica a notícia mais recente (não decaída) para alerta imediato
            last_entry = df_raw.iloc[-1]
            if abs(last_entry['Alpha']) >= VOLATILITY_THRESHOLD:
                color = "#FF0000" if last_entry['Alpha'] < 0 else "#00FF00"
                st.markdown(f"""
                <div style="border: 3px solid {color}; padding: 15px; background-color: #111; text-align: center; margin-bottom: 20px;">
                    <h2 style="color: {color}; margin:0;">ALERTA DE ALTA VOLATILIDADE⚠️</h2>
                    <p style="font-size: 18px;">EVENTO: {last_entry['Manchete']} ({last_entry['Alpha']:.1f} ALPHA)</p>
                </div>
                """, unsafe_allow_html=True)

            # --- PAINEL DE COMANDO ---
            c1, c2, c3 = st.columns([1, 1, 2])
            
            with c1:
                color_s = "#00FF00" if sentiment_buy > 50 else "#FF0000"
                st.markdown(f"<span style='color:{color_s}; font-size:16px'>SENTIMENTO LÍQUIDO</span>", unsafe_allow_html=True)
                st.metric("PROB. COMPRA", f"{sentiment_buy:.1f}%", f"{net_alpha:.2f} Net Alpha")

            with c2:
                # Indicador de Velocidade (Quantas notícias relevantes na última hora)
                news_velocity = len(df[df['Minutes_Ago'] < 60])
                st.metric("VELOCIDADE (1H)", f"{news_velocity} news", "Fluxo Recente")

            with c3:
                # Gráfico Alpha Accumulado (Decaído)
                # Mostra a pressão real de compra/venda ao longo do tempo
                df_chart = df.sort_values('Timestamp')
                df_chart['Cumulative_Decayed'] = df_chart['Alpha_Decayed'].cumsum()
                
                fig = px.area(df_chart, x="Data_Hora", y="Cumulative_Decayed",
                              title="Pressão de Mercado (Alpha Ajustado p/ Tempo)",
                              template="plotly_dark")
                fig.update_traces(line_color='#00FF00' if net_alpha > 0 else '#FF0000')
                fig.update_yaxes(title="Net Alpha Impact")
                fig.update_layout(height=250, margin=dict(l=0,r=0,t=30,b=0))
                st.plotly_chart(fig, use_container_width=True)

            # --- HEATMAP & CATEGORIAS ---
            c_heat, c_cat = st.columns([2, 1])
            
            with c_heat:
                st.subheader("Radar de Fontes (Sentimento)")
                if 'Fonte' in df.columns:
                    src_grp = df.groupby('Fonte')['Alpha_Decayed'].sum().reset_index()
                    cols = st.columns(len(src_grp)) if len(src_grp) > 0 else [st]
                    for idx, row in src_grp.iterrows():
                        color = "#44FF44" if row['Alpha_Decayed'] > 0 else "#FF4444"
                        with cols[idx % 4]: # Max 4 colunas
                            st.markdown(f"""
                            <div style="border:1px solid #333; padding:10px; text-align:center; margin-bottom:10px;">
                                <div style="font-size:12px; color:#888;">{row['Fonte'][:10]}</div>
                                <div style="font-size:20px; font-weight:bold; color:{color};">{row['Alpha_Decayed']:.1f}</div>
                            </div>
                            """, unsafe_allow_html=True)

            with c_cat:
                st.subheader("Drivers Atuais")
                if 'Categoria' in df.columns:
                    cat_grp = df.groupby('Categoria')['Alpha_Decayed'].abs().sum().sort_values(ascending=False).head(3)
                    for cat, val in cat_grp.items():
                        st.progress(min(val/20, 1.0), text=f"{cat} (Impacto: {val:.1f})")

            # Ledger Profissional
            with st.expander("Ledger Institucional (Detalhado)", expanded=True):
                st.dataframe(
                    df[['Data_Hora', 'Fonte', 'Categoria', 'Manchete', 'Alpha', 'Alpha_Decayed']]
                    .sort_values(by="Data_Hora", ascending=False)
                    .style.applymap(lambda x: 'color: #44FF44' if x > 0 else 'color: #FF4444', subset=['Alpha']),
                    use_container_width=True
                )
    else:
        st.info("Inicializando modelos econométricos... Aguardando fluxo de dados.")

if __name__ == "__main__":
    main()
