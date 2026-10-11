"""
App Streamlit · Informe de evaluación de acciones formativas
Ejecutar:  streamlit run app.py
"""
import os

import pandas as pd
import streamlit as st

from analisis import generar_informe
from procesador import fmt_num, fmt_pct

st.set_page_config(page_title="Informe de evaluación de cursos", page_icon="📊", layout="wide")


def _secreto(nombre: str) -> str:
    try:
        return st.secrets.get(nombre, "") or os.environ.get(nombre, "")
    except Exception:  # noqa: BLE001  (sin secrets.toml)
        return os.environ.get(nombre, "")


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header("⚙️ Opciones del informe")

    st.subheader("Ítem 7 · Modalidad telemática o mixta")
    opcion7 = st.radio(
        "¿Valorar el ítem 7?",
        ["Automático (según la modalidad del curso)", "Sí, valorarlo", "No valorarlo"],
        help="El ítem 7 solo procede cuando el curso se ha impartido en teleformación o "
             "modalidad mixta. En automático se decide según la modalidad indicada en los "
             "cuestionarios.",
    )
    modo_item7 = {"Automático": "auto", "Sí, valor": "si", "No valor": "no"}[
        next(k for k in ("Automático", "Sí, valor", "No valor") if opcion7.startswith(k))]

    st.divider()
    st.subheader("Análisis de comentarios")
    clave_defecto = _secreto("ANTHROPIC_API_KEY")
    usar_ia = st.toggle("Usar IA (Claude) para comentarios y conclusiones",
                        value=bool(clave_defecto),
                        help="Sin IA se aplica un análisis por reglas en castellano, gratuito "
                             "y sin conexión. Con IA el análisis de matices es más fino.")
    api_key, modelo = "", "claude-sonnet-5-5"
    if usar_ia:
        api_key = st.text_input("API key de Anthropic", value=clave_defecto, type="password")
        modelo = st.text_input("Modelo", value=_secreto("ANTHROPIC_MODEL") or "claude-sonnet-5-5")
        if not api_key:
            st.info("Introduce una API key o se usará el análisis por reglas.")

# ---------------------------------------------------------------- contenido
st.title("📊 Informe de evaluación de acciones formativas")
st.write(
    "Sube un archivo **.zip** con los cuestionarios de evaluación de la calidad "
    "(PDF rellenables SEPE/FUNDAE) de un mismo curso y grupo. La app calculará las "
    "valoraciones, analizará los comentarios y generará el informe en PDF."
)

archivo = st.file_uploader("Cuestionarios (.zip)", type=["zip"])

if archivo and st.button("Generar informe", type="primary"):
    with st.spinner("Procesando cuestionarios..."):
        try:
            st.session_state["informe"] = generar_informe(
                archivo, modo_item7=modo_item7, usar_ia=usar_ia and bool(api_key),
                api_key=api_key, modelo=modelo)
        except Exception as e:  # noqa: BLE001
            st.session_state.pop("informe", None)
            st.error(f"No se ha podido generar el informe: {e}")

inf = st.session_state.get("informe")
if inf:
    f = inf.ficha
    st.success(f"Informe generado a partir de {f['n_cuestionarios']} cuestionarios.")
    for aviso in inf.avisos:
        st.warning(aviso)
    if inf.descartados:
        with st.expander(f"⚠️ {len(inf.descartados)} archivo(s) no procesados"):
            st.dataframe(pd.DataFrame(inf.descartados, columns=["Archivo", "Motivo"]),
                         hide_index=True)

    st.download_button("⬇️ Descargar informe PDF", data=inf.pdf, file_name=inf.nombre_archivo,
                       mime="application/pdf", type="primary")

    st.subheader(f"Informe Curso – {f['curso']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valoración global", f"{fmt_num(inf.nota, 1)} / 10")
    c2.metric("Media global (1-4)", fmt_num(inf.media_global))
    c3.metric("Cuestionarios", f["n_cuestionarios"])
    c4.metric("Con comentarios", len(inf.comentarios))
    st.caption(f"Nivel de satisfacción general: **{inf.nivel_general}** · Modalidad: "
               f"{f['modalidad'] or '–'} · Ítem 7 {'incluido' if inf.incluir_item7 else 'excluido'} · "
               f"Comentarios analizados con {'IA' if inf.motor == 'ia' else 'reglas'}")

    t1, t2, t3, t4 = st.tabs(["Ficha", "Análisis cuantitativo", "Comentarios", "Conclusiones"])
    with t1:
        st.table(pd.DataFrame({
            "Campo": ["Nombre del curso", "Sociedad bonificada (Nº expediente)",
                      "Nº acción formativa / Grupo", "Nº cuestionarios", "Modalidad"],
            "Valor": [f["curso"], f["expediente"], f"{f['n_aaff']} / {f['n_grupo']}",
                      str(f["n_cuestionarios"]), f["modalidad"]],
        }).set_index("Campo"))
    with t2:
        st.dataframe(pd.DataFrame([{
            "Apartado": f"{a['numero']}. {a['nombre']}",
            "Puntuación media": fmt_num(a["media"]),
            "Nivel de satisfacción": a["nivel"]} for a in inf.apartados]),
            hide_index=True)
        st.dataframe(pd.DataFrame([{
            "Ítem": s["codigo"], "Descripción": s["texto"], "Sí": s["si"], "No": s["no"],
            "% Sí": fmt_pct(s["pct_si"]), "% No": fmt_pct(s["pct_no"])}
            for b in inf.sino for s in b["subitems"]]), hide_index=True)
    with t3:
        if inf.elementos:
            st.dataframe(pd.DataFrame([{
                "Elemento": e["elemento"], "Valor": e["valor"], "Frecuencia": e["frecuencia"],
                "Ejemplo": inf.comentarios[e["ejemplos"][0]] if e["ejemplos"] else ""}
                for e in inf.elementos]), hide_index=True)
        else:
            st.info("No hay comentarios.")
    with t4:
        st.markdown("**Resumen ejecutivo**")
        st.write(inf.conclusiones["resumen"])
        col_a, col_b = st.columns(2)
        col_a.markdown("**Fortalezas**\n\n" + "\n".join(f"- {x}" for x in inf.conclusiones["fortalezas"]))
        col_b.markdown("**Áreas de mejora**\n\n" + "\n".join(f"- {x}" for x in inf.conclusiones["mejoras"]))
        st.markdown("**Recomendaciones**")
        for r in inf.conclusiones["recomendaciones"]:
            st.markdown(f"- **{r['punto']}** → {r['accion']}")
