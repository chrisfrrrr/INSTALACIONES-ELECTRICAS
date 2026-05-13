import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import math

st.set_page_config(
    page_title="Estudio de Instalaciones Eléctricas",
    page_icon="⚡",
    layout="wide"
)

st.markdown("""
<style>
.main-title {font-size: 2.2rem; font-weight: 800; color: #17365D;}
.subtitle {font-size: 1.05rem; color: #555;}
.warning-box {
    padding: 0.9rem; border-radius: 10px;
    background-color: #fff3cd; border: 1px solid #ffeeba; color: #664d03;
}
.ok-box {
    padding: 0.9rem; border-radius: 10px;
    background-color: #d1e7dd; border: 1px solid #badbcc; color: #0f5132;
}
.small-note {font-size: 0.85rem; color: #666;}
</style>
""", unsafe_allow_html=True)

BREAKER_STD = [15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 125, 150, 175, 200, 225, 250, 300, 350, 400]

CONDUCTORES = [
    (15, "#14 AWG"), (20, "#12 AWG"), (30, "#10 AWG"), (40, "#8 AWG"),
    (55, "#6 AWG"), (70, "#4 AWG"), (85, "#3 AWG"), (100, "#2 AWG"),
    (115, "#1 AWG"), (130, "1/0 AWG"), (150, "2/0 AWG"), (175, "3/0 AWG"),
    (200, "4/0 AWG"), (230, "250 kcmil"), (255, "300 kcmil"),
    (285, "350 kcmil"), (310, "400 kcmil"), (335, "500 kcmil"),
]

AREA_MM2_APROX = {
    "#14 AWG": 2.08, "#12 AWG": 3.31, "#10 AWG": 5.26, "#8 AWG": 8.37,
    "#6 AWG": 13.3, "#4 AWG": 21.2, "#3 AWG": 26.7, "#2 AWG": 33.6,
    "#1 AWG": 42.4, "1/0 AWG": 53.5, "2/0 AWG": 67.4, "3/0 AWG": 85.0,
    "4/0 AWG": 107.2, "250 kcmil": 126.7, "300 kcmil": 152.0,
    "350 kcmil": 177.3, "400 kcmil": 202.7, "500 kcmil": 253.4,
}

def next_standard_breaker(current_a: float, factor: float = 1.25):
    if pd.isna(current_a) or current_a <= 0:
        return np.nan
    target = current_a * factor
    for b in BREAKER_STD:
        if b >= target:
            return b
    return "Revisar >400 A"

def conductor_sugerido(breaker):
    if pd.isna(breaker):
        return ""
    if isinstance(breaker, str):
        return "Revisar"
    for amp, cond in CONDUCTORES:
        if breaker <= amp:
            return cond
    return "Revisar"

def corriente(pot_total_w, voltaje, fases, fp):
    if voltaje <= 0 or fp <= 0:
        return np.nan
    if fases == 3:
        return pot_total_w / (math.sqrt(3) * voltaje * fp)
    return pot_total_w / (voltaje * fp)

def caida_tension_pct(corriente_a, distancia_m, voltaje, fases, conductor):
    if pd.isna(corriente_a) or corriente_a <= 0 or voltaje <= 0:
        return np.nan
    area = AREA_MM2_APROX.get(conductor, None)
    if not area:
        return np.nan
    rho = 0.0175
    if fases == 3:
        delta_v = math.sqrt(3) * corriente_a * rho * distancia_m / area
    else:
        delta_v = 2 * corriente_a * rho * distancia_m / area
    return (delta_v / voltaje) * 100

def clasificar_observacion(row, limite_caida):
    obs = []
    if pd.notna(row.get("Caída de tensión (%)")) and row["Caída de tensión (%)"] > limite_caida:
        obs.append("Revisar caída de tensión")
    if row.get("Tipo de carga") == "No lineal":
        obs.append("Puede generar armónicos")
    if row.get("Tipo de carga") == "Inductiva":
        obs.append("Considerar corriente de arranque y FP")
    if pd.notna(row.get("FP")) and row["FP"] < 0.85:
        obs.append("Factor de potencia bajo")
    return " / ".join(obs) if obs else "OK"

def procesar_cargas(df, factor_breaker, limite_caida):
    df = df.copy()
    required_cols = ["Carga", "Cantidad", "Potencia unitaria (W)", "Voltaje (V)", "Fases", "FP", "Tipo de carga", "¿UPS?", "¿Generador?", "Distancia (m)"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    for col in ["Cantidad", "Potencia unitaria (W)", "Voltaje (V)", "Fases", "FP", "Distancia (m)"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Cantidad"] = df["Cantidad"].fillna(0)
    df["Potencia unitaria (W)"] = df["Potencia unitaria (W)"].fillna(0)
    df["Voltaje (V)"] = df["Voltaje (V)"].fillna(120)
    df["Fases"] = df["Fases"].fillna(1).astype(int)
    df["FP"] = df["FP"].fillna(0.90)
    df["Distancia (m)"] = df["Distancia (m)"].fillna(0)
    df["Tipo de carga"] = df["Tipo de carga"].replace("", "Mixta").fillna("Mixta")
    df["¿UPS?"] = df["¿UPS?"].replace("", "No").fillna("No")
    df["¿Generador?"] = df["¿Generador?"].replace("", "No").fillna("No")

    df["Potencia total (W)"] = df["Cantidad"] * df["Potencia unitaria (W)"]
    df["Corriente (A)"] = df.apply(lambda r: corriente(r["Potencia total (W)"], r["Voltaje (V)"], r["Fases"], r["FP"]), axis=1)
    df["Breaker sugerido (A)"] = df["Corriente (A)"].apply(lambda x: next_standard_breaker(x, factor_breaker))
    df["Conductor sugerido"] = df["Breaker sugerido (A)"].apply(conductor_sugerido)
    df["Caída de tensión (%)"] = df.apply(lambda r: caida_tension_pct(r["Corriente (A)"], r["Distancia (m)"], r["Voltaje (V)"], r["Fases"], r["Conductor sugerido"]), axis=1)
    df["Observación"] = df.apply(lambda r: clasificar_observacion(r, limite_caida), axis=1)
    return df

def crear_excel(df_resultado, resumen, ups_gen):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_resultado.to_excel(writer, index=False, sheet_name="Cargas Calculadas")
        pd.DataFrame([resumen]).to_excel(writer, index=False, sheet_name="Resumen")
        pd.DataFrame([ups_gen]).to_excel(writer, index=False, sheet_name="UPS_Generador")
    return output.getvalue()

columnas = ["Carga", "Cantidad", "Potencia unitaria (W)", "Voltaje (V)", "Fases", "FP", "Tipo de carga", "¿UPS?", "¿Generador?", "Distancia (m)"]

ejemplo = pd.DataFrame([
    {"Carga": "Computadoras", "Cantidad": 12, "Potencia unitaria (W)": 300, "Voltaje (V)": 120, "Fases": 1, "FP": 0.90, "Tipo de carga": "No lineal", "¿UPS?": "Sí", "¿Generador?": "Sí", "Distancia (m)": 25},
    {"Carga": "Monitores", "Cantidad": 12, "Potencia unitaria (W)": 120, "Voltaje (V)": 120, "Fases": 1, "FP": 0.95, "Tipo de carga": "No lineal", "¿UPS?": "Sí", "¿Generador?": "Sí", "Distancia (m)": 25},
    {"Carga": "Servidor", "Cantidad": 1, "Potencia unitaria (W)": 1200, "Voltaje (V)": 120, "Fases": 1, "FP": 0.95, "Tipo de carga": "No lineal", "¿UPS?": "Sí", "¿Generador?": "Sí", "Distancia (m)": 15},
    {"Carga": "Switch de red", "Cantidad": 2, "Potencia unitaria (W)": 80, "Voltaje (V)": 120, "Fases": 1, "FP": 0.95, "Tipo de carga": "No lineal", "¿UPS?": "Sí", "¿Generador?": "Sí", "Distancia (m)": 15},
    {"Carga": "Cámaras", "Cantidad": 8, "Potencia unitaria (W)": 25, "Voltaje (V)": 120, "Fases": 1, "FP": 0.90, "Tipo de carga": "No lineal", "¿UPS?": "Sí", "¿Generador?": "Sí", "Distancia (m)": 30},
    {"Carga": "Iluminación LED", "Cantidad": 25, "Potencia unitaria (W)": 18, "Voltaje (V)": 120, "Fases": 1, "FP": 0.95, "Tipo de carga": "No lineal", "¿UPS?": "No", "¿Generador?": "Sí", "Distancia (m)": 30},
    {"Carga": "Aire acondicionado", "Cantidad": 2, "Potencia unitaria (W)": 2200, "Voltaje (V)": 240, "Fases": 1, "FP": 0.85, "Tipo de carga": "Inductiva", "¿UPS?": "No", "¿Generador?": "Sí", "Distancia (m)": 20},
    {"Carga": "Impresoras", "Cantidad": 3, "Potencia unitaria (W)": 600, "Voltaje (V)": 120, "Fases": 1, "FP": 0.90, "Tipo de carga": "No lineal", "¿UPS?": "Sí", "¿Generador?": "Sí", "Distancia (m)": 20},
    {"Carga": "Refrigeradora", "Cantidad": 1, "Potencia unitaria (W)": 500, "Voltaje (V)": 120, "Fases": 1, "FP": 0.85, "Tipo de carga": "Inductiva", "¿UPS?": "No", "¿Generador?": "Sí", "Distancia (m)": 18},
    {"Carga": "Microondas", "Cantidad": 1, "Potencia unitaria (W)": 1200, "Voltaje (V)": 120, "Fases": 1, "FP": 0.95, "Tipo de carga": "Resistiva", "¿UPS?": "No", "¿Generador?": "No", "Distancia (m)": 12},
])

st.sidebar.title("⚙️ Configuración")
factor_breaker = st.sidebar.slider("Factor para selección de breaker", 1.00, 1.50, 1.25, 0.05)
limite_caida = st.sidebar.slider("Límite máximo de caída de tensión (%)", 2.0, 8.0, 5.0, 0.5)
factor_seg_ups = st.sidebar.slider("Factor de seguridad UPS", 1.00, 1.50, 1.25, 0.05)
factor_seg_gen = st.sidebar.slider("Factor de seguridad generador", 1.00, 1.80, 1.30, 0.05)
fp_ups = st.sidebar.number_input("FP estimado UPS", min_value=0.5, max_value=1.0, value=0.90, step=0.05)
fp_gen = st.sidebar.number_input("FP estimado generador", min_value=0.5, max_value=1.0, value=0.90, step=0.05)
autonomia_min = st.sidebar.number_input("Autonomía UPS requerida (min)", min_value=5, max_value=240, value=20, step=5)

st.markdown('<div class="main-title">⚡ Estudio Básico de Instalaciones Eléctricas</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Herramienta educativa para ingresar cargas y obtener cálculos de corriente, protecciones, caída de tensión, UPS y generador.</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Herramienta desarrollada por Christian Pocol, Ingeniero Electronico.</div>', unsafe_allow_html=True)
tabs = st.tabs(["📘 Guía", "🧾 Ingreso de cargas", "📊 Resultados", "🔋 UPS y Generador", "📐 Diagrama", "📥 Exportar"])

with tabs[0]:
    st.header("📘 Guía para estudiantes")
    st.markdown("""
    ### ¿Qué resultados obtendrás?

    Esta aplicación calcula de forma educativa:

    - Potencia total instalada.
    - Corriente por cada carga.
    - Breaker sugerido.
    - Conductor sugerido.
    - Caída de tensión aproximada.
    - Capacidad estimada de UPS.
    - Capacidad estimada de generador.
    - Advertencias por caída de tensión, armónicos, bajo factor de potencia o cargas inductivas.

    ### Pasos de uso

    1. Ingresa o edita las cargas en la pestaña **Ingreso de cargas**.
    2. Revisa los cálculos en **Resultados**.
    3. Define qué cargas van con **UPS** y cuáles con **Generador**.
    4. Analiza advertencias técnicas.
    5. Descarga el reporte en Excel.

    ### Fórmulas usadas
    """)
    st.latex(r"I_{1\phi}=\frac{P}{V \cdot FP}")
    st.latex(r"I_{3\phi}=\frac{P}{\sqrt{3}\cdot V \cdot FP}")
    st.latex(r"UPS_{VA}=\frac{P_{critica}\cdot FS}{FP_{UPS}}")
    st.latex(r"Generador_{VA}=\frac{P_{respaldo}\cdot FS}{FP_{Gen}}")
    st.warning("Los cálculos son simplificados para fines académicos. Un diseño real requiere normativa vigente, canalización, temperatura, agrupamiento, puesta a tierra, cortocircuito y coordinación de protecciones.")

with tabs[1]:
    st.header("🧾 Ingreso de cargas")

    if "df_cargas" not in st.session_state:
        st.session_state.df_cargas = ejemplo.copy()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Cargar ejemplo de oficina"):
            st.session_state.df_cargas = ejemplo.copy()
    with c2:
        if st.button("🧹 Limpiar tabla"):
            st.session_state.df_cargas = pd.DataFrame(columns=columnas)

    df_editado = st.data_editor(
        st.session_state.df_cargas,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Tipo de carga": st.column_config.SelectboxColumn("Tipo de carga", options=["Lineal", "No lineal", "Inductiva", "Resistiva", "Mixta"]),
            "¿UPS?": st.column_config.SelectboxColumn("¿UPS?", options=["Sí", "No"]),
            "¿Generador?": st.column_config.SelectboxColumn("¿Generador?", options=["Sí", "No"]),
            "Fases": st.column_config.SelectboxColumn("Fases", options=[1, 3]),
        }
    )
    st.session_state.df_cargas = df_editado

df_resultado = procesar_cargas(st.session_state.get("df_cargas", ejemplo), factor_breaker, limite_caida)

pot_total = df_resultado["Potencia total (W)"].sum()
corriente_total = df_resultado["Corriente (A)"].sum()
pot_ups = df_resultado.loc[df_resultado["¿UPS?"] == "Sí", "Potencia total (W)"].sum()
pot_gen = df_resultado.loc[df_resultado["¿Generador?"] == "Sí", "Potencia total (W)"].sum()
cantidad_cargas = len(df_resultado[df_resultado["Carga"].astype(str).str.strip() != ""])

resumen = {
    "Cantidad de cargas": cantidad_cargas,
    "Potencia total (W)": pot_total,
    "Potencia total (kW)": pot_total / 1000,
    "Corriente total aproximada (A)": corriente_total,
    "Potencia en UPS (W)": pot_ups,
    "Potencia en Generador (W)": pot_gen,
}

ups_va = (pot_ups * factor_seg_ups / fp_ups) if fp_ups > 0 else np.nan
gen_va = (pot_gen * factor_seg_gen / fp_gen) if fp_gen > 0 else np.nan
energia_baterias_wh = pot_ups * (autonomia_min / 60)

ups_gen = {
    "Carga UPS (W)": pot_ups,
    "UPS recomendado (VA)": ups_va,
    "UPS recomendado (kVA)": ups_va / 1000,
    "Autonomía requerida (min)": autonomia_min,
    "Energía de baterías estimada (Wh)": energia_baterias_wh,
    "Carga Generador (W)": pot_gen,
    "Generador recomendado (VA)": gen_va,
    "Generador recomendado (kVA)": gen_va / 1000,
}

with tabs[2]:
    st.header("📊 Resultados del estudio")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Potencia total", f"{pot_total/1000:.2f} kW")
    m2.metric("Corriente total aprox.", f"{corriente_total:.2f} A")
    m3.metric("Cargas en UPS", f"{pot_ups/1000:.2f} kW")
    m4.metric("Cargas en generador", f"{pot_gen/1000:.2f} kW")

    st.subheader("Tabla calculada")
    st.dataframe(
        df_resultado.style.format({
            "Potencia total (W)": "{:,.0f}",
            "Corriente (A)": "{:,.2f}",
            "Caída de tensión (%)": "{:,.2f}",
            "FP": "{:.2f}",
        }),
        use_container_width=True
    )

    st.subheader("Potencia por tipo de carga")
    if not df_resultado.empty:
        graf = df_resultado.groupby("Tipo de carga", dropna=False)["Potencia total (W)"].sum().reset_index()
        st.bar_chart(graf, x="Tipo de carga", y="Potencia total (W)", use_container_width=True)

    advertencias = df_resultado[df_resultado["Observación"] != "OK"]
    if len(advertencias) > 0:
        st.markdown('<div class="warning-box"><b>Advertencias detectadas:</b> revisar cargas con caída de tensión alta, armónicos, bajo FP o cargas inductivas.</div>', unsafe_allow_html=True)
        st.dataframe(advertencias[["Carga", "Tipo de carga", "Corriente (A)", "Caída de tensión (%)", "Observación"]], use_container_width=True)
    else:
        st.markdown('<div class="ok-box"><b>Sin advertencias relevantes:</b> los resultados están dentro de los criterios educativos configurados.</div>', unsafe_allow_html=True)

with tabs[3]:
    st.header("🔋 Dimensionamiento de UPS y Generador")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("UPS")
        st.metric("Carga crítica UPS", f"{pot_ups/1000:.2f} kW")
        st.metric("UPS recomendado", f"{ups_va/1000:.2f} kVA")
        st.metric("Energía baterías estimada", f"{energia_baterias_wh:.0f} Wh")
        st.info("El UPS debe alimentar cargas críticas: servidores, red, cámaras, computadoras o equipos que no pueden apagarse repentinamente.")

    with col2:
        st.subheader("Generador")
        st.metric("Carga respaldada", f"{pot_gen/1000:.2f} kW")
        st.metric("Generador recomendado", f"{gen_va/1000:.2f} kVA")
        st.info("El generador debe considerar margen de seguridad y corriente de arranque de motores.")

    c1, c2 = st.columns(2)
    with c1:
        st.write("**Cargas en UPS**")
        st.dataframe(df_resultado[df_resultado["¿UPS?"] == "Sí"][["Carga", "Potencia total (W)", "Tipo de carga"]], use_container_width=True)
    with c2:
        st.write("**Cargas en Generador**")
        st.dataframe(df_resultado[df_resultado["¿Generador?"] == "Sí"][["Carga", "Potencia total (W)", "Tipo de carga"]], use_container_width=True)

with tabs[4]:
    st.header("📐 Diagrama unifilar conceptual")
    st.code("""
RED ELÉCTRICA / DISTRIBUIDOR
        │
        ▼
     MEDIDOR
        │
        ▼
BREAKER GENERAL + SPD
        │
        ▼
       ATS ◄────────── GENERADOR
        │
        ▼
TABLERO PRINCIPAL
        │
        ├────────── CARGAS NORMALES
        │
        ▼
       UPS
        │
        ▼
CARGAS CRÍTICAS
(servidor, red, cámaras, computadoras)
    """, language="text")

    st.markdown("""
    ### Preguntas para análisis

    1. ¿Por qué el UPS se coloca antes de las cargas críticas?
    2. ¿Qué cargas no deberían conectarse al UPS?
    3. ¿Por qué el generador debe considerar arranque de motores?
    4. ¿Qué función cumple el ATS?
    5. ¿Qué ocurriría si no existe una buena tierra física?
    """)

with tabs[5]:
    st.header("📥 Exportar resultados")
    excel_bytes = crear_excel(df_resultado, resumen, ups_gen)

    st.download_button(
        label="📄 Descargar reporte en Excel",
        data=excel_bytes,
        file_name="reporte_instalacion_electrica.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.subheader("Resumen")
    st.json(resumen)
    st.markdown('<div class="small-note">Recomendación: el estudiante debe entregar el archivo exportado junto con una breve explicación de sus decisiones técnicas.</div>', unsafe_allow_html=True)
