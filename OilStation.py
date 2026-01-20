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

# --- PARÂMETROS ESTRUTURAIS ---
DB_FILE = "Oil_Station_PRO_v2.xlsx" # Nova versão para garantir estrutura correta
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

# --- LÉXICO AVANÇADO ---
LEXICON_TOPICS = {
    r"war|attack|missile|drone|strike|conflict": [9.5, 1, "Geopolítica (Risco)"],
    r"opec|saudi|cut|quota|production curb": [9.0, 1, "Política OPEP"],
    r"force majeure|shut-in|outage|pipeline leak|fire": [9.5, 1, "Choque Físico (Oferta)"],
    r"sanction|ban|embargo|price cap": [8.0, 1, "Geopolítica (Sanções)"],
    r"inventory|stockpile|draw|drawdown": [7.0, 1, "Dados de Estoque"],
    r"build|glut|oversupply": [7.0, -1, "Dados de Estoque"],
    r"china|stimulus|recovery|growth": [7.5, 1, "Demanda (China)"],
    r"recession|slowdown|weak|contracting|pmi miss": [8.0, -1, "Macro (Recessão)"],
    r"fed|rate hike|hawkish|inflation|cpi": [6.5, -1, "Macro (Monetário)"],
    r"dovish|rate cut|powell|liquidity": [6.5, 1, "Macro (Monetário)"],
    r"dollar|dxy|greenback": [6.0, -1, "Correlação FX"],
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

# --- MOTORES DE CÁLCULO ---

def calculate_complex_alpha(title):
    title_lower = title.lower()
    base_alpha = 0
    direction = 0
    category = "Geral"
    multiplier = 1.0
    
    # Detecção de Tópico
    for pattern, params in LEXICON_TOPICS.items():
        if re.search(pattern, title_lower):
            base_alpha += params[0]
            if direction == 0: 
                direction = params[1]
                category = params[2]
    
    # Detecção de Modificadores
    for pattern, mod_value in LEXICON_MODIFIERS.items():
        if re.search(pattern, title_lower):
            multiplier *= mod_value
            
    return (base_alpha * direction * multiplier), category

def apply_analytics(df):
    """Aplica Decaimento Temporal e Cálculo de Z-Score (Desvio da Média)"""
    try:
        if df.empty or 'Timestamp_Iso' not in df.columns: return pd.DataFrame()
        
        # Converter string ISO de volta para datetime
        df['dt_obj'] = pd.to_datetime(df['Timestamp_Iso'])
        now = datetime.now()
        
        # 1. Decaimento Temporal (Financeiro)
        lam = np.log(2) / HALFLIFE_MINUTES
        df['Minutes_Ago'] = (now - df['dt_obj']).dt.total_seconds() / 60
        df['Alpha_Decayed'] = df['Alpha'] * np.exp(-lam * df['Minutes_Ago'])
        
        # Filtrar dados irrelevantes (> 6 horas ou impacto nulo)
        active_df = df[(df['Minutes_Ago'] < 360) & (abs(df['Alpha_Decayed']) > 0.05)].copy()
        
        return active_df
    except Exception as e:
        print(f"Erro analytics: {e}")
        return pd.DataFrame()

def calculate_probability_and_regime(net_alpha):
    """
    Transforma Alpha Líquido em Probabilidade (0-100)
    e define o Regime de Mercado para Automação.
    """
    k = 0.15 # Suavização da curva sigmoide
    prob = 1 / (1 + np.exp(-k * net_alpha))
    prob_pct = round(prob * 100, 1)
    
    # Definição de Regime (Output para IA)
    if prob_pct > 70:
        regime = "COMPRA (BULL)"
        color = "#00FF00" # Verde Neon
    elif prob_pct < 30:
        regime = "VENDA (BEAR)"
        color = "#FF0033" # Vermelho Sangue
    else:
        regime = "NEUTRO (SIDEWAYS)"
        color = "#FFD700" # Amarelo Ouro
        
    return prob_pct, regime, color

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
                        if abs(alpha) > 0.5: # Apenas relevância mínima
                            save_data({
                                "Timestamp_Iso": datetime.now().isoformat(), # Essencial para precisão
                                "Data_Hora": datetime.now().strftime("%H:%M:%S"),
                                "Fonte": source,
                                "Manchete": title,
                                "Categoria": cat,
                                "Alpha": alpha
                            })
                        seen.add(title)
            except: pass
        time.sleep(60)

# --- INTERFACE (DASHBOARD) ---
def main():
    st.set_page_config(page_title="QUANT STATION PRO", layout="wide", page_icon="🛢️")

    # CSS HARMONIZADO (Dark Glassmorphism)
    st.markdown("""
        <style>
        /* Fundo Geral - Cinza Profundo Profissional (Não Preto Puro) */
        .stApp { background-color: #0E1117; color: #E0E0E0; }
        
        /* Cards (Vidro Escuro) */
        div.stMetric, div.stDataFrame {
            background-color: #161B22; 
            border: 1px solid #30363D; 
            padding: 15px; 
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        
        /* Fontes e Títulos */
        [data-testid="stMetricValue"] { font-family: 'Roboto Mono', monospace; font-weight: bold; }
        h1, h2, h3 { color: #FFFFFF; font-weight: 300; letter-spacing: 1px; }
        
        /* Ajuste do Plotly para fundir com o fundo */
        .js-plotly-plot .plotly .main-svg { background: rgba(0,0,0,0) !important; }
        </style>
        """, unsafe_allow_html=True)

    if st_autorefresh:
        st_autorefresh(interval=60000, key="pro_refresh")

    if 'monitor_active' not in st.session_state:
        threading.Thread(target=news_monitor, daemon=True).start()
        st.session_state['monitor_active'] = True

    # --- HEADER E KPI ---
    c_title, c_kpi = st.columns([3, 1])
    with c_title:
        st.title("OIL SENTIMENT: INSTITUTIONAL FEED")
        st.caption("AI-READY ANALYTICS ENGINE | REAL-TIME RSS PARSING")
    
    if os.path.exists(DB_FILE):
        try:
            df_raw = pd.read_excel(DB_FILE)
            active_df = apply_analytics(df_raw)
            
            if not active_df.empty:
                # Cálculos Principais
                net_alpha = active_df['Alpha_Decayed'].sum()
                prob_pct, regime, regime_color = calculate_probability_and_regime(net_alpha)
                news_velocity = len(active_df[active_df['Minutes_Ago'] < 60])

                # --- 1. O GAUGE (CONTADOR) SOLICITADO ---
                with c_kpi:
                    fig_gauge = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = prob_pct,
                        domain = {'x': [0, 1], 'y': [0, 1]},
                        title = {'text': "Probabilidade de Compra (%)", 'font': {'size': 14, 'color': "#888"}},
                        number = {'font': {'color': regime_color, 'size': 40}},
                        gauge = {
                            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#333"},
                            'bar': {'color': "rgba(0,0,0,0)"}, # Esconde a barra padrão
                            'bgcolor': "#161B22",
                            'steps': [
                                {'range': [0, 30], 'color': "#550000"},   # Zona Venda (Escuro)
                                {'range': [30, 70], 'color': "#444400"},  # Zona Neutra (Escuro)
                                {'range': [70, 100], 'color': "#003300"}  # Zona Compra (Escuro)
                            ],
                            'threshold': {
                                'line': {'color': regime_color, 'width': 4},
                                'thickness': 0.75,
                                'value': prob_pct
                            }
                        }
                    ))
                    fig_gauge.update_layout(height=160, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_gauge, use_container_width=True)

                # --- 2. PAINEL DE CONTROLE ---
                st.markdown(f"""
                <div style="background-color: {regime_color}20; border-left: 5px solid {regime_color}; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    <h3 style="margin:0; color:{regime_color};">REGIME ATUAL: {regime}</h3>
                    <small>Net Alpha: {net_alpha:.2f} | Velocidade (1h): {news_velocity} manchetes</small>
                </div>
                """, unsafe_allow_html=True)

                # --- 3. HEATMAP E GRÁFICO (ABAS) ---
                tab1, tab2 = st.tabs(["📡 HEATMAP (TREEMAP)", "CURVA DE ALPHA"])
                
                with tab1:
                    # HEATMAP HIERÁRQUICO
                    # Mostra Categoria -> Fonte. Tamanho = Relevância (Soma Absoluta do Alpha). Cor = Sentimento.
                    if not active_df.empty:
                        # Agrupamento para o Treemap
                        tree_df = active_df.groupby(['Categoria', 'Fonte']).agg(
                            Count=('Manchete', 'count'),
                            Total_Alpha=('Alpha_Decayed', 'sum'),
                            Abs_Alpha=('Alpha_Decayed', lambda x: x.abs().sum())
                        ).reset_index()
                        
                        fig_tree = px.treemap(
                            tree_df, 
                            path=[px.Constant("MERCADO"), 'Categoria', 'Fonte'], 
                            values='Abs_Alpha', # Tamanho baseado na intensidade (relevância)
                            color='Total_Alpha', # Cor baseada na direção (positivo/negativo)
                            color_continuous_scale=['#FF0000', '#111111', '#00FF00'], # Escala Vermelho-Preto-Verde
                            color_continuous_midpoint=0,
                            title="Mapa de Calor de Sentimento (Tamanho = Relevância | Cor = Viés)"
                        )
                        fig_tree.update_layout(
                            template="plotly_dark", 
                            paper_bgcolor='rgba(0,0,0,0)', 
                            plot_bgcolor='rgba(0,0,0,0)',
                            margin=dict(t=30, l=0, r=0, b=0),
                            height=400
                        )
                        # Melhorar hover
                        fig_tree.data[0].textinfo = 'label+text+value'
                        st.plotly_chart(fig_tree, use_container_width=True)
                    else:
                        st.warning("Dados insuficientes para gerar Heatmap.")

                with tab2:
                    # GRÁFICO DE ÁREA
                    df_chart = active_df.sort_values('dt_obj')
                    df_chart['Cumulative_Alpha'] = df_chart['Alpha_Decayed'].cumsum()
                    
                    fig_area = px.area(
                        df_chart, x="Data_Hora", y="Cumulative_Alpha", 
                        title="Acumulação de Pressão (Alpha Líquido)",
                        template="plotly_dark"
                    )
                    # Cor dinâmica da linha baseada no último valor
                    line_color = "#00FF00" if df_chart['Cumulative_Alpha'].iloc[-1] > 0 else "#FF0000"
                    fig_area.update_traces(line_color=line_color, fillcolor=f"{line_color}40") # 40% opacidade
                    fig_area.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_area, use_container_width=True)

                # --- 4. LEDGER (LOG) ---
                with st.expander("Dados Brutos", expanded=False):
                    st.dataframe(
                        active_df[['Data_Hora', 'Fonte', 'Categoria', 'Manchete', 'Alpha', 'Alpha_Decayed']]
                        .sort_values(by="Data_Hora", ascending=False), 
                        use_container_width=True
                    )

            else:
                st.info("Aguardando fluxo de notícias... (Calibrando)")
                
        except Exception as e:
            st.error(f"Erro de processamento: {e}")
            # Botão de pânico para limpar dados corrompidos se necessário
            if st.button("Hard Reset Database"):
                if os.path.exists(DB_FILE): os.remove(DB_FILE)
                st.rerun()

    else:
        st.warning("Inicializando banco de dados... Aguarde as primeiras manchetes.")

if __name__ == "__main__":
    main()

