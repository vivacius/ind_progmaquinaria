# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import timedelta

# -----------------------
# Configuración general
# -----------------------
st.set_page_config(
    page_title="📊 Control de Apuntamiento - Profesional",
    layout="wide"
)

st.title("📊 Control de Apuntamiento de Equipos — Profesional")
st.markdown(
    "Sube el archivo Excel despivotado (cada fila = Zona, Equipo, Turno, Día Apuntamiento). "
    "La app calcula KPIs, gráficos, seguimiento temporal y un resumen ejecutivo listo para gerencia."
)

# -----------------------
# Helper functions
# -----------------------
@st.cache_data
def read_excel(uploaded_file):
    return pd.read_excel(uploaded_file)

def find_date_column(cols):
    # heurístico para detectar columna de fecha
    for c in cols:
        lc = c.lower()
        if "dia" in lc or "fecha" in lc or "apunt" in lc:
            return c
    return None

def normalize_df(df, date_col):
    df = df.copy()
    # Normalizar nombres de columnas
    df.columns = df.columns.str.strip()
    # Columnas requeridas
    required = ["Equipo", "Turno", "Zona"]
    for r in required:
        if r not in df.columns:
            raise ValueError(f"Columna requerida no encontrada: '{r}'")
    # Columna de fecha
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    # Normalizar strings
    df["Turno"] = df["Turno"].astype(str).str.strip().str.lower().fillna("")
    df["Zona"] = df["Zona"].astype(str).str.strip().str.upper().fillna("SIN ZONA")
    df["Equipo"] = df["Equipo"].astype(str).str.strip()
    # Extraer número de turnos
    df["turnos_num"] = df["Turno"].str.extract(r"(\d+)").fillna(0).astype(float)
    df["is_taller"] = df["Turno"].str.contains("taller", na=False)
    df["is_disponible"] = df["Turno"].str.contains("disponible", na=False)
    # Estado textual derivado
    def estado(row):
        if row["is_taller"]:
            return "taller"
        if row["turnos_num"] >= 1:
            n = int(row["turnos_num"])
            return f"{n} turno" if n == 1 else f"{n} turnos"
        if row["is_disponible"]:
            return "disponible"
        return "sin dato"
    df["Estado"] = df.apply(estado, axis=1)
    return df

def summarize(grouped):
    """
    grouped: DataFrame con 1 fila por equipo (idealmente agrupado por Zona y Equipo)
    Devuelve métricas agregadas sobre ese conjunto.
    """
    total_teams = grouped["Equipo"].nunique()
    teams_in_taller = int(grouped[grouped["is_taller"]]["Equipo"].nunique())
    teams_available = max(total_teams - teams_in_taller, 0)
    total_turns = grouped["turnos_num"].sum()
    teams_with_turns = int(grouped[grouped["turnos_num"] >= 1]["Equipo"].nunique())
    avg_turns_per_available = (total_turns / teams_available) if teams_available else 0
    avg_turns_per_team = (total_turns / total_teams) if total_teams else 0
    pct_availability = (teams_available / total_teams * 100) if total_teams else 0
    pct_utilization = (teams_with_turns / teams_available * 100) if teams_available else 0
    pct_programacion = (total_turns / (total_teams * 3) * 100) if total_teams else 0
    ge1 = int(grouped[grouped["turnos_num"] >= 1]["Equipo"].nunique())
    ge2 = int(grouped[grouped["turnos_num"] >= 2]["Equipo"].nunique())
    ge3 = int(grouped[grouped["turnos_num"] >= 3]["Equipo"].nunique())
    return {
        "total_teams": int(total_teams),
        "teams_in_taller": int(teams_in_taller),
        "teams_available": int(teams_available),
        "total_turns": float(total_turns),
        "teams_with_turns": int(teams_with_turns),
        "avg_turns_per_available": float(round(avg_turns_per_available, 2)),
        "avg_turns_per_team": float(round(avg_turns_per_team, 2)),
        "pct_availability": round(pct_availability, 1),
        "pct_utilization": round(pct_utilization, 1),
        "pct_programacion": round(pct_programacion, 1),
        "ge1": ge1,
        "ge2": ge2,
        "ge3": ge3
    }

def to_csv_bytes(df):
    buff = BytesIO()
    df.to_csv(buff, index=False)
    buff.seek(0)
    return buff

# -----------------------
# Carga del archivo
# -----------------------
uploaded_file = st.file_uploader("Sube tu archivo Excel (.xlsx)", type=["xlsx"])

if not uploaded_file:
    st.info(
        "Sube un archivo Excel con columnas mínimas: `Dia Apuntamiento` (o equivalente), `Zona`, `Equipo`, `Turno`."
    )
    st.stop()

try:
    df_raw = read_excel(uploaded_file)
except Exception as e:
    st.error(f"Error leyendo el Excel: {e}")
    st.stop()

# Detectar columna de fecha automáticamente
date_col = find_date_column(df_raw.columns)
if date_col:
    df_raw[date_col] = pd.to_datetime(df_raw[date_col], errors="coerce").dt.date

try:
    df = normalize_df(df_raw, date_col)
except ValueError as e:
    st.error(str(e))
    st.stop()

# -----------------------
# Sidebar filtros (incluye selección de modo Día vs Rango consolidado)
# -----------------------
with st.expander("Filtros"):
    cols = st.columns([1,1,1])
    with cols[0]:
        zones_all = sorted(df["Zona"].unique().tolist())
        sel_zones = st.multiselect("Zona", options=zones_all, default=zones_all)
    with cols[1]:
        estados_all = sorted(df["Estado"].unique().tolist())
        sel_estados = st.multiselect("Estado (Turno)", options=estados_all, default=estados_all)
    with cols[2]:
        # Modo de análisis: Por Día (único) o Consolidado (rango)
        analysis_mode = st.selectbox("Modo de Análisis", options=["Por Día (single day)", "Consolidado (rango)"], index=0)
        if date_col:
            if analysis_mode == "Por Día (single day)":
                # Mostrar un selectbox con los días disponibles
                days = sorted(df[date_col].dropna().unique().tolist())
                if days:
                    sel_day = st.selectbox("Selecciona Día Apuntamiento", options=days, index=len(days)-1)
                    sel_date_range = [sel_day, sel_day]
                else:
                    sel_date_range = None
            else:
                min_date = df[date_col].min()
                max_date = df[date_col].max()
                sel_date_range = st.date_input("Rango Día Apuntamiento", value=[min_date, max_date], min_value=min_date, max_value=max_date)
        else:
            sel_date_range = None

# Aplicar filtros básicos (zona / estado)
mask = df["Zona"].isin(sel_zones) & df["Estado"].isin(sel_estados)

# Aplicar filtro de fecha (si existe)
if date_col and isinstance(sel_date_range, list) and len(sel_date_range) == 2:
    start_dt, end_dt = sel_date_range[0], sel_date_range[1]
    mask = mask & df[date_col].between(start_dt, end_dt)

df_f = df[mask].copy()

if df_f.empty:
    st.warning("No hay datos con los filtros aplicados. Ajusta filtros o sube otro archivo.")
    st.stop()

# -----------------------
# Preparar agregación por equipo (sin duplicar equipos entre días en modo consolidado)
# -----------------------
# Si el análisis es "Por Día", df_f ya contiene solo ese día (start==end). 
# En ambos casos vamos a consolidar por Zona+Equipo para el cálculo de KPIs (evita duplicados).
agg_team = df_f.groupby(["Zona","Equipo"], as_index=False).agg({
    "turnos_num":"sum",      # si hay varios registros por equipo (por ejemplo por encuestas repetidas), sumar
    "is_taller":"max",
    "is_disponible":"max"
})

# Recalcular Estado por equipo agregado
def agg_estado(row):
    if row["is_taller"]:
        return "taller"
    if row["turnos_num"] >= 1:
        n = int(row["turnos_num"])
        return f"{n} turno" if n == 1 else f"{n} turnos"
    if row["is_disponible"]:
        return "disponible"
    return "sin dato"

agg_team["Estado"] = agg_team.apply(agg_estado, axis=1)

# -----------------------
# Métricas globales y por zona (usando agg_team para evitar conteos duplicados)
# -----------------------
global_metrics = summarize(agg_team)

by_zone = agg_team.groupby("Zona").apply(lambda g: pd.Series(summarize(g))).reset_index()

# Métricas por fecha para seguimiento temporal (por día)
if date_col:
    by_date = df_f.groupby(date_col).agg({
        "turnos_num":"sum",
        "Equipo":"nunique",
        "is_taller":"sum"
    }).reset_index().rename(columns={"turnos_num":"turnos_totales", "Equipo":"equipos_unicos", "is_taller":"taller_count"})
    # calcular pct_programacion por dia
    by_date["turnos_maximos"] = by_date["equipos_unicos"] * 3
    by_date["pct_programacion"] = (by_date["turnos_totales"] / by_date["turnos_maximos"] * 100).round(1)

# -----------------------
# Layout principal: KPIs y Resumen
# -----------------------
st.markdown("## 📊 KPIs principales")

kpi1, kpi2, kpi3, kpi4 = st.columns([1.2,1.2,1.2,1])
kpi1.metric("✅ Disponibilidad (%)", f"{global_metrics['pct_availability']:.1f}%")
kpi2.metric("⚡ Utilización (%)", f"{global_metrics['pct_utilization']:.1f}%")
kpi3.metric("📈 % Programación (turnos/capacidad)", f"{global_metrics['pct_programacion']:.1f}%")
kpi4.metric("⏱️ Carga promedio (turnos/equipo disponible)", f"{global_metrics['avg_turns_per_available']:.2f}")

scol1, scol2, scol3 = st.columns(3)
scol1.info(f"Total equipos (filtrados, consolidados): **{global_metrics['total_teams']}**")
scol2.info(f"Equipos en taller: **{global_metrics['teams_in_taller']}**")
scol3.info(f"Total turnos asignados: **{int(global_metrics['total_turns'])}**")

st.markdown("---")

# -----------------------
# Tabs: Dashboard / Seguimiento / Métricas
# -----------------------
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "⏱️ Seguimiento Temporal", "ℹ️ Métricas e Interpretación"])

with tab1:
    st.subheader("📊 Dashboard Compacto")
    # --- Dos columnas ---
    col1, col2 = st.columns([1,1])

    # --- Columna 1 ---
    with col1:
        st.markdown("### Estado de Equipos por Zona")
        chart_data = agg_team.groupby(["Zona","Estado"])["Equipo"].count().reset_index(name="conteo")
        fig1 = px.bar(
            chart_data.sort_values(["Zona","Estado"]),
            x="Zona", y="conteo", color="Estado",
            text="conteo", barmode="stack",
            color_discrete_map={"taller":"blue","disponible":"red","sin dato":"gray","1 turno":"green","2 turnos":"orange","3 turnos":"yellow"}
        )
        fig1.update_layout(height=350, margin=dict(t=30))
        st.plotly_chart(fig1, use_container_width=True)

     
    # --- Columna 2 ---
    with col2:
        st.markdown("### KPIs Globales")
        kpi_cols = st.columns(4)
        kpi_cols[0].metric("✅ Disponibilidad (%)", f"{global_metrics['pct_availability']:.1f}%")
        kpi_cols[1].metric("⚡ Utilización (%)", f"{global_metrics['pct_utilization']:.1f}%")
        kpi_cols[2].metric("📈 % Programación", f"{global_metrics['pct_programacion']:.1f}%")
        kpi_cols[3].metric("⏱️ Carga promedio", f"{global_metrics['avg_turns_per_available']:.2f}")

        st.markdown("### Resumen por Zona (con solidificación por equipo)")
        zone_summary = by_zone[[
            "Zona",
            "total_teams",
            "teams_available",
            "teams_in_taller",
            "pct_availability",
            "pct_utilization",
            "pct_programacion",
            "total_turns"
        ]].copy()

        # Renombrar columnas (legible, sin emojis en nombres internos)
        zone_summary.rename(columns={
            "total_teams": "Total Equipos",
            "teams_available": "Disponibles",
            "teams_in_taller": "Equipos en taller",
            "pct_availability":"Disponibilidad (%)",
            "pct_utilization":"Utilización (%)",
            "pct_programacion":"% Programación",
            "total_turns":"Turnos asignados"
        }, inplace=True)

        # Formatear columnas porcentuales como strings para visualización (mantener datos originales en by_zone)
        zone_summary_display = zone_summary.copy()
        zone_summary_display["Disponibilidad (%)"] = zone_summary_display["Disponibilidad (%)"].map(lambda x: f"{x:.1f}%")
        zone_summary_display["Utilización (%)"] = zone_summary_display["Utilización (%)"].map(lambda x: f"{x:.1f}%")
        zone_summary_display["% Programación"] = zone_summary_display["% Programación"].map(lambda x: f"{x:.1f}%")
        # Mostrar
        st.dataframe(zone_summary_display.set_index("Zona"), height=250)

st.subheader("📊 Dashboard por Zona (KPIs)")

with tab2:
    st.subheader("⏱️ Seguimiento Temporal de Turnos")
    if date_col:
        if not by_date.empty:
            fig_time = px.line(
                by_date, x=date_col, y="pct_programacion",
                markers=True, title="Porcentaje de Programación (%) a través del tiempo"
            )
            fig_time.update_traces(line=dict(width=3, color="royalblue"))
            st.plotly_chart(fig_time, use_container_width=True)

            st.subheader("🔎 Evolución de equipos en taller")
            fig_taller = px.line(
                by_date, x=date_col, y="taller_count",
                markers=True, title="Cantidad de equipos en taller a través del tiempo"
            )
            fig_taller.update_traces(line=dict(width=3, color="firebrick"))
            st.plotly_chart(fig_taller, use_container_width=True)

            st.subheader("📈 Tendencia de Turnos (por Día)")
            fig2 = px.line(by_date, x=date_col, y="turnos_totales", markers=True, title="Turnos totales por Día")
            fig2.update_traces(line=dict(width=3))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No hay datos de fecha para generar series temporales con el rango/selección actual.")
    else:
        st.info("No hay columna de fecha para mostrar seguimiento temporal.")

    st.subheader("🔥 Heatmap: Turnos por Zona y Día")
    if date_col:
        heat = df_f.groupby([date_col, "Zona"])["turnos_num"].sum().reset_index()
        if not heat.empty:
            pivot_heat = heat.pivot(index="Zona", columns=date_col, values="turnos_num").fillna(0)
            fig3 = go.Figure(data=go.Heatmap(
                z=pivot_heat.values,
                x=[str(d) for d in pivot_heat.columns],
                y=pivot_heat.index,
                colorscale="Viridis",
                hovertemplate="Zona: %{y}<br>Dia: %{x}<br>Turnos: %{z}<extra></extra>"
            ))
            fig3.update_layout(height=400, margin=dict(l=100, r=10, t=40, b=40))
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No hay datos para el heatmap con los filtros actuales.")
    else:
        st.info("Heatmap requiere columna de fecha.")

with tab3:
    st.markdown("""
    ## Definiciones y fórmulas

    - **Disponibilidad (%)** = (Equipos disponibles) / (Total equipos) × 100  
      - *Equipos disponibles* = Total equipos - Equipos en taller.

    - **Utilización (%)** = (Equipos con ≥1 turno) / (Equipos disponibles) × 100  
      - **Nota:** Esta métrica mide la proporción de equipos disponibles que tuvieron al menos 1 turno. Con la consolidación por equipo, **no** debe pasar de 100%.

    - **Índice de Intensidad de Uso (opcional)** = (Turnos asignados / Equipos disponibles) × 100  
      - Puede ser >100% si equipos cubren más de 1 turno (p. ej. 200% = 2 turnos por equipo disponible en promedio).

    - **% Programación (turnos / capacidad)** = (Turnos asignados) / (Equipos totales × 3) × 100

    - **Carga promedio (turnos/equipo disponible)** = (Turnos asignados) / (Equipos disponibles)

    - **Equipos en taller** = cantidad de equipos con estado 'taller'

    ## Interpretación

    - **Alta disponibilidad** (>85%) es deseable.  
    - **Alta utilización** (70–90%) indica buen balance (proporción de equipos activos).  
    - **Si quieres medir intensidad de uso** (cuántos turnos por equipo), usa el Índice de Intensidad de Uso (puede superar 100%).  
    - **% programación bajo** indica subutilización o baja demanda; revisar programación y reasignación.  
    - **Carga promedio alta en pocos equipos** puede indicar riesgo de sobreuso y mayor probabilidad de fallas.
    """)

# -----------------------
# Resumen Ejecutivo Automático
# -----------------------
st.markdown("---")
st.subheader("🧾 Resumen ejecutivo (automático)")

def gen_insights(metrics, by_zone_df):
    insights = []
    # availability
    if metrics["pct_availability"] < 80:
        insights.append(f"⚠️ **Disponibilidad baja**: {metrics['pct_availability']:.1f}% de equipos disponibles. Revisar plan de mantenimiento o redistribución de equipos.")
    else:
        insights.append(f"✅ **Disponibilidad saludable**: {metrics['pct_availability']:.1f}% de equipos disponibles.")
    # utilization
    if metrics["pct_utilization"] < 50:
        insights.append(f"🔎 **Baja utilización**: sólo {metrics['pct_utilization']:.1f}% de los equipos disponibles tienen al menos 1 turno. Podría existir subprogramación o baja demanda operativa.")
    else:
        insights.append(f"📈 **Buena utilización**: {metrics['pct_utilization']:.1f}% de equipos disponibles con turnos.")
    # programacion
    if metrics["pct_programacion"] < 50:
        insights.append(f"📉 **Programación débil**: solo {metrics['pct_programacion']:.1f}% de la capacidad teórica (3 turnos/equipo) está siendo utilizada.")
    else:
        insights.append(f"🔄 **Programación adecuada**: {metrics['pct_programacion']:.1f}% de la capacidad teórica utilizada.")
    # taller
    if metrics["teams_in_taller"] > 0:
        insights.append(f"🛠️ {metrics['teams_in_taller']} equipos en taller. Verificar tiempos de reparación y prioridad de retorno a servicio.")
    # top/bottom zones
    if not by_zone_df.empty:
        best = by_zone_df.sort_values("pct_programacion", ascending=False).head(3)
        worst = by_zone_df.sort_values("pct_programacion", ascending=True).head(3)
        insights.append("🔎 Zonas con mejor programación: " + ", ".join(best["Zona"].tolist()))
        insights.append("🔻 Zonas con menor programación: " + ", ".join(worst["Zona"].tolist()))
    # action suggestions
    suggestions = "Recomendaciones: 1) Rebalancear turnos entre zonas con baja programación; 2) Priorizar equipos en taller con mayor impacto operacional; 3) Revisar demanda operacional y ajustar plantilla/supertturnos."
    return insights, suggestions

# Asegurar pct_programacion en by_zone
if "pct_programacion" not in by_zone.columns:
    def zone_pct_program(df_zone):
        tot_teams = df_zone["Equipo"].nunique()
        tot_turns = df_zone["turnos_num"].sum()
        return round(tot_turns / (tot_teams*3) * 100, 1) if tot_teams else 0
    by_zone["pct_programacion"] = agg_team.groupby("Zona").apply(zone_pct_program).values

insights, suggestions = gen_insights(global_metrics, by_zone)
for i in insights:
    st.markdown(f"- {i}")
st.markdown(f"**Sugerencias principales:** {suggestions}")

# -----------------------
# Descargas
# -----------------------
st.markdown("---")
st.subheader("⬇️ Descargas CSV")

csv_summary = to_csv_bytes(pd.DataFrame([global_metrics]))
st.download_button("Descargar resumen general (CSV)", data=csv_summary, file_name="resumen_general.csv", mime="text/csv")

csv_by_zone = to_csv_bytes(by_zone)
st.download_button("Descargar resumen por zona (CSV)", data=csv_by_zone, file_name="resumen_por_zona.csv", mime="text/csv")

csv_pivot = to_csv_bytes(agg_team)
st.download_button("Descargar pivot (CSV)", data=csv_pivot, file_name="pivot_detalle.csv", mime="text/csv")

st.success("App cargada correctamente. Powered By Santiago Correa")
