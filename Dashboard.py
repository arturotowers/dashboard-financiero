import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN E INICIALIZACIÓN
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Dashboard Financiero Pro", page_icon="📊", layout="wide")

# Listas de Activos
BIG_SEVEN = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'TSLA', 'AMZN']
# 5 Empresas de Libre Elección (Diversificadas)
CHOSEN_FIVE = ['JPM', 'KO', 'DIS', 'XOM', 'PFE']  # JP Morgan, Coca-Cola, Disney, Exxon, Pfizer
MACRO_TICKERS = ['^TNX', 'MXN=X', 'EURUSD=X']  # Bonos 10Y, USD/MXN, EUR/USD

ALL_STOCKS = BIG_SEVEN + CHOSEN_FIVE
ALL_TICKERS = ALL_STOCKS + MACRO_TICKERS


# -----------------------------------------------------------------------------
# 2. ETL: EXTRACCIÓN Y TRANSFORMACIÓN
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_data():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2 años de historia

    try:
        # Descarga masiva
        raw_data = yf.download(ALL_TICKERS, start=start_date, end=end_date, progress=False)

        if raw_data.empty:
            st.error("Error: Yahoo Finance no devolvió datos. Revisa tu conexión.")
            return pd.DataFrame()

        # Aplanamiento de MultiIndex (Corrección para versiones nuevas de yfinance)
        if isinstance(raw_data.columns, pd.MultiIndex):
            # Prioridad: Close > Adj Close
            if 'Close' in raw_data.columns.levels[0]:
                df = raw_data['Close']
            elif 'Adj Close' in raw_data.columns.levels[0]:
                df = raw_data['Adj Close']
            else:
                df = raw_data.xs('Close', axis=1, level=0, drop_level=True)
        else:
            df = raw_data['Close'] if 'Close' in raw_data.columns else raw_data

        # Renombrar para claridad
        rename_map = {
            '^TNX': 'US_Treasury_10Y',
            'MXN=X': 'USD_MXN',
            'EURUSD=X': 'EUR_USD_Exchange'
            # Esto es Euros por Dólar o Dólares por Euro dependiendo la convención, Yahoo da USD per EUR
        }
        df.rename(columns=rename_map, inplace=True)

        # --- TRANSFORMACIONES ADICIONALES ---

        # 1. Calcular USD/EUR (Inverso de EUR/USD si Yahoo da precio del Euro en Dólares)
        # Yahoo 'EURUSD=X' suele ser 1.08 (1 Euro = 1.08 USD).
        # Si queremos USD/EUR (cuántos euros vale 1 dólar), invertimos:
        df['USD_EUR'] = 1 / df['EUR_USD_Exchange']

        # 2. Simulación de CETES (Ya que no tenemos API Key de Banxico)
        # Tendencia alcista ligera + ruido aleatorio sobre base de 11%
        dates = df.index
        np.random.seed(42)
        trend = np.linspace(10.5, 11.25, len(dates))
        noise = np.random.normal(0, 0.05, len(dates))
        df['CETES_28'] = trend + noise

        # Limpieza final
        df = df.ffill().bfill()
        return df

    except Exception as e:
        st.error(f"Error crítico en ETL: {e}")
        return pd.DataFrame()


# Carga de datos
df = load_data()

# Si falla la carga, detener app
if df.empty:
    st.stop()

# -----------------------------------------------------------------------------
# 3. BARRA LATERAL (FILTROS Y ALERTAS)
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Panel de Control")

st.sidebar.subheader("📅 Periodo de Análisis")
days_window = st.sidebar.slider("Días de historia", 30, 700, 365)
df_filtered = df.iloc[-days_window:]

st.sidebar.subheader("🔔 Configuración de Alertas")
limit_usd_mxn = st.sidebar.number_input("Techo USD/MXN", value=20.5, step=0.1)
limit_treasury = st.sidebar.number_input("Techo Bonos US (%)", value=4.5, step=0.1)
limit_usd_eur = st.sidebar.number_input("Piso USD/EUR (Debilidad Dólar)", value=0.90, step=0.01)

# Botón de actualización manual
if st.sidebar.button("Forzar Actualización de Datos"):
    st.cache_data.clear()
    st.rerun()


# -----------------------------------------------------------------------------
# 4. LÓGICA DE ALERTAS
# -----------------------------------------------------------------------------
def get_alerts(current_data):
    alerts = []
    last = current_data.iloc[-1]

    if last['USD_MXN'] > limit_usd_mxn:
        alerts.append(f"🔴 **CRÍTICO:** Dólar supera {limit_usd_mxn} MXN (Actual: {last['USD_MXN']:.2f})")

    if last['US_Treasury_10Y'] > limit_treasury:
        alerts.append(f"🟠 **ALERTA:** Bonos US superan {limit_treasury}% (Actual: {last['US_Treasury_10Y']:.2f}%)")

    if last['USD_EUR'] < limit_usd_eur:
        alerts.append(f"🟡 **AVISO:** Dólar se debilita frente al Euro (Actual: {last['USD_EUR']:.2f} €)")

    return alerts


active_alerts = get_alerts(df_filtered)

# -----------------------------------------------------------------------------
# 5. LAYOUT PRINCIPAL
# -----------------------------------------------------------------------------
st.title("📈 Tablero de Control Financiero Integral")
st.markdown("Integración de **Big Seven**, **Empresas Tradicionales** y **Variables Macro**.")

# Sección de Alertas
if active_alerts:
    with st.expander("⚠️ Alertas del Sistema Activas", expanded=True):
        for alert in active_alerts:
            st.markdown(alert)
else:
    st.success("✅ Todos los indicadores operan dentro de los umbrales normales.")

# KPIs Principales
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
current = df_filtered.iloc[-1]
prev = df_filtered.iloc[-2]


def show_kpi(col, title, key, format_str="%.2f"):
    val = current[key]
    delta = val - prev[key]
    col.metric(title, format_str % val, f"{delta:.2f}")


show_kpi(kpi1, "USD / MXN", 'USD_MXN')
show_kpi(kpi2, "USD / EUR", 'USD_EUR', "%.3f €")  # Mostramos con 3 decimales
show_kpi(kpi3, "CETES 28D", 'CETES_28')
show_kpi(kpi4, "Bonos US 10Y", 'US_Treasury_10Y')

# -----------------------------------------------------------------------------
# 6. PESTAÑAS DE CONTENIDO
# -----------------------------------------------------------------------------
tab_market, tab_macro, tab_insights = st.tabs(
    ["🏢 Acciones (Big 7 vs Tradicionales)", "🌎 Divisas y Bonos", "💡 Descubrimientos (Preguntas)"])

# --- TAB 1: MERCADO DE ACCIONES ---
with tab_market:
    st.subheader("Análisis de Precios Históricos")

    # Selector unificado
    selected_stocks = st.multiselect("Selecciona empresas para comparar:", ALL_STOCKS,
                                     default=['NVDA', 'KO', 'TSLA', 'JPM'])

    if selected_stocks:
        # Gráfico de Línea Normalizado (Base 100) para comparar rendimiento real
        df_norm = df_filtered[selected_stocks] / df_filtered[selected_stocks].iloc[0] * 100
        fig_stocks = px.line(df_norm, x=df_norm.index, y=selected_stocks,
                             title="Rendimiento Relativo (Base 100 = Inicio del Periodo)",
                             labels={"value": "Rendimiento Base 100", "variable": "Empresa"})
        st.plotly_chart(fig_stocks, use_container_width=True)

        # Tabla de últimos precios
        st.markdown("**Últimos Precios de Cierre:**")
        st.dataframe(df_filtered[selected_stocks].tail(), use_container_width=True)
    else:
        st.info("Selecciona al menos una empresa para visualizar.")

# --- TAB 2: MACROECONOMÍA ---
with tab_macro:
    col_mxn, col_eur = st.columns(2)

    with col_mxn:
        st.subheader("USD / MXN")
        fig_mxn = px.area(df_filtered, y='USD_MXN', title="Tendencia Peso Mexicano")
        fig_mxn.add_hline(y=limit_usd_mxn, line_dash="dash", line_color="red", annotation_text="Umbral")
        st.plotly_chart(fig_mxn, use_container_width=True)

    with col_eur:
        st.subheader("USD / EUR")
        fig_eur = px.line(df_filtered, y='USD_EUR', title="Tendencia Euro (Euros por Dólar)")
        fig_eur.update_traces(line_color='#2ECC71')
        st.plotly_chart(fig_eur, use_container_width=True)

    st.subheader("Comparativa de Tasas: CETES vs US Treasury")
    fig_rates = px.line(df_filtered, y=['CETES_28', 'US_Treasury_10Y'],
                        title="Diferencial de Tasas (Spread)",
                        color_discrete_map={'CETES_28': 'blue', 'US_Treasury_10Y': 'orange'})
    st.plotly_chart(fig_rates, use_container_width=True)

# --- TAB 3: INSIGHTS (PREGUNTAS VISUALES) ---
with tab_insights:
    st.markdown("### 🔍 Análisis Guiado por Datos")
    st.markdown("A continuación se presentan las respuestas visuales a las preguntas de negocio planteadas.")
    st.divider()

    # --- PREGUNTA 1 ---
    st.subheader("1. ¿Qué grupo de inversión presenta mayor riesgo: Big Tech o Tradicionales?")
    st.caption("Respuesta visual basada en la volatilidad anualizada (Desviación Estándar).")

    # Cálculo
    volatility = df_filtered[ALL_STOCKS].pct_change().std() * (252 ** 0.5) * 100
    vol_df = pd.DataFrame({'Ticker': volatility.index, 'Volatilidad_Anual_%': volatility.values})
    vol_df['Sector'] = vol_df['Ticker'].apply(lambda x: 'Big Tech' if x in BIG_SEVEN else 'Tradicional')

    fig_q1 = px.bar(vol_df.sort_values('Volatilidad_Anual_%', ascending=False),
                    x='Ticker', y='Volatilidad_Anual_%', color='Sector',
                    title="Riesgo por Activo: Volatilidad Anualizada",
                    color_discrete_map={'Big Tech': '#8E44AD', 'Tradicional': '#27AE60'})
    st.plotly_chart(fig_q1, use_container_width=True)

    st.divider()

    # --- PREGUNTA 2 ---
    st.subheader("2. ¿La fortaleza del Dólar frente al Euro depende de los Bonos del Tesoro?")
    st.caption("Respuesta visual basada en correlación lineal.")

    fig_q2 = px.scatter(df_filtered, x='US_Treasury_10Y', y='USD_EUR', trendline='ols',
                        title="Correlación: Rendimiento Bonos US vs Tipo de Cambio USD/EUR",
                        labels={'US_Treasury_10Y': 'Tasa Bonos 10Y (%)', 'USD_EUR': 'Precio USD en Euros'})
    st.plotly_chart(fig_q2, use_container_width=True)

    st.divider()

    # --- PREGUNTA 3 ---
    st.subheader("3. ¿Ha sido la inversión en NVIDIA superior a la suma de las 5 empresas tradicionales juntas?")
    st.caption("Respuesta visual comparativa de crecimiento acumulado.")

    # Crear un índice sintético de las "Chosen Five" (Promedio de sus rendimientos)
    chosen_norm = df_filtered[CHOSEN_FIVE] / df_filtered[CHOSEN_FIVE].iloc[0] * 100
    df_filtered['Index_Tradicional'] = chosen_norm.mean(axis=1)

    # Normalizar NVIDIA
    df_filtered['Index_NVDA'] = df_filtered['NVDA'] / df_filtered['NVDA'].iloc[0] * 100

    fig_q3 = px.line(df_filtered, y=['Index_NVDA', 'Index_Tradicional'],
                     title="Crecimiento: NVIDIA vs Portafolio Tradicional Promedio",
                     color_discrete_map={'Index_NVDA': '#76D7C4', 'Index_Tradicional': '#85929E'})
    st.plotly_chart(fig_q3, use_container_width=True)

# Pie de página
st.markdown("---")
st.caption("Dashboard generado con Python y Streamlit. Datos de Yahoo Finance.")