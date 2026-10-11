"""Generación del informe en PDF con ReportLab (+ gráficos con Matplotlib)."""
from __future__ import annotations

import io
from datetime import date
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem,  # noqa: E402
                                Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from procesador import fmt_num, fmt_pct, UMBRAL_SATISFACTORIO  # noqa: E402

# Paleta
AZUL = "#2a78d6"
NARANJA = "#eb6834"
TINTA = colors.HexColor("#1d1d1b")
TINTA_2 = colors.HexColor("#52514e")
PRINCIPAL = colors.HexColor("#1f4e79")
FONDO_CAB = colors.HexColor("#1f4e79")
FONDO_ALT = colors.HexColor("#f2f5f9")
LINEA = colors.HexColor("#c9d3df")
VERDE_TXT = colors.HexColor("#1b6e3a")
ROJO_TXT = colors.HexColor("#b3261e")

ANCHO = A4[0] - 4 * cm
# Nº de participante (orden del cuestionario en el .zip) de cada comentario.
_PARTICIPANTES: list[int] = []

_base = getSampleStyleSheet()
E = {
    "titulo": ParagraphStyle("titulo", parent=_base["Title"], fontSize=20, leading=25,
                             textColor=PRINCIPAL, spaceAfter=4),
    "subtitulo": ParagraphStyle("subtitulo", parent=_base["Normal"], fontSize=9.5,
                                textColor=TINTA_2, alignment=TA_CENTER, spaceAfter=14),
    "h1": ParagraphStyle("h1", parent=_base["Heading1"], fontSize=14, leading=18,
                         textColor=PRINCIPAL, spaceBefore=14, spaceAfter=6),
    "h2": ParagraphStyle("h2", parent=_base["Heading2"], fontSize=11.5, leading=15,
                         textColor=TINTA, spaceBefore=10, spaceAfter=4),
    "h3": ParagraphStyle("h3", parent=_base["Heading3"], fontSize=10, leading=13,
                         textColor=TINTA, spaceBefore=6, spaceAfter=3),
    "normal": ParagraphStyle("normal", parent=_base["Normal"], fontSize=9.5, leading=13.5,
                             textColor=TINTA),
    "celda": ParagraphStyle("celda", parent=_base["Normal"], fontSize=8.5, leading=11,
                            textColor=TINTA),
    "celda_cab": ParagraphStyle("celda_cab", parent=_base["Normal"], fontSize=8.5, leading=11,
                                textColor=colors.white, fontName="Helvetica-Bold"),
    "cita": ParagraphStyle("cita", parent=_base["Normal"], fontSize=8.8, leading=12,
                           textColor=TINTA_2, fontName="Helvetica-Oblique",
                           leftIndent=12, borderPadding=(2, 0, 2, 6), spaceAfter=4),
    "nota": ParagraphStyle("nota", parent=_base["Normal"], fontSize=7.8, leading=10,
                           textColor=TINTA_2),
    "kpi_valor": ParagraphStyle("kpi_valor", parent=_base["Normal"], fontSize=20, leading=24,
                                textColor=PRINCIPAL, fontName="Helvetica-Bold",
                                alignment=TA_CENTER),
    "kpi_etq": ParagraphStyle("kpi_etq", parent=_base["Normal"], fontSize=8.5, leading=11,
                              textColor=TINTA_2, alignment=TA_CENTER),
}


# --------------------------------------------------------------------------
def _txt(s) -> str:
    """Escapa texto para Paragraph y sustituye caracteres que Helvetica no tiene."""
    s = "" if s is None else str(s)
    for a, b in {"“": "«", "”": "»", "‘": "'", "’": "'", "…": "...", "​": ""}.items():
        s = s.replace(a, b)
    s = s.encode("cp1252", errors="ignore").decode("cp1252")
    return escape(s)


def _p(s, estilo="celda") -> Paragraph:
    return Paragraph(_txt(s), E[estilo])


def _tabla(filas, anchos, cabecera=True, zebra=True) -> Table:
    datos = []
    for r, fila in enumerate(filas):
        estilo = "celda_cab" if (cabecera and r == 0) else "celda"
        datos.append([c if not isinstance(c, (str, int, float)) else _p(c, estilo) for c in fila])
    t = Table(datos, colWidths=anchos, repeatRows=1 if cabecera else 0)
    st = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if cabecera:
        st.append(("BACKGROUND", (0, 0), (-1, 0), FONDO_CAB))
    if zebra:
        for r in range(1 if cabecera else 0, len(filas)):
            if r % 2 == 0:
                st.append(("BACKGROUND", (0, r), (-1, r), FONDO_ALT))
    t.setStyle(TableStyle(st))
    return t


def _nivel_par(nivel: str) -> Paragraph:
    color = VERDE_TXT if nivel == "Satisfactorio" else ROJO_TXT if nivel == "No satisfactorio" else TINTA_2
    est = ParagraphStyle("niv", parent=E["celda"], textColor=color, fontName="Helvetica-Bold")
    return Paragraph(_txt(nivel), est)


def _cita(comentarios, idx, max_len=360) -> Paragraph:
    texto, num = comentarios[idx], _PARTICIPANTES[idx] if idx < len(_PARTICIPANTES) else idx + 1
    if len(texto) > max_len:
        texto = texto[:max_len].rsplit(" ", 1)[0] + "..."
    return Paragraph(f"«{_txt(texto)}» <font color='#8a8985'>(Participante {num})</font>",
                     E["cita"])


def _cita_celda(comentarios, idx, max_len=260) -> Paragraph:
    texto, num = comentarios[idx], _PARTICIPANTES[idx] if idx < len(_PARTICIPANTES) else idx + 1
    if len(texto) > max_len:
        texto = texto[:max_len].rsplit(" ", 1)[0] + "..."
    est = ParagraphStyle("citacelda", parent=E["celda"], fontName="Helvetica-Oblique",
                         textColor=TINTA_2)
    return Paragraph(f"«{_txt(texto)}» <font color='#8a8985' size='7.5'>(P{num})</font>", est)


def _figura(fig, ancho_cm) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = ancho_cm * cm
    img.drawHeight = ancho_cm * cm * ratio
    return img


def _estilo_ejes(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#b5b4ae")
    ax.tick_params(colors="#52514e", labelsize=8, length=0)


def _grafico_apartados(apartados) -> Image:
    datos = [a for a in apartados if a["media"] is not None][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(datos) + 0.9))
    y = range(len(datos))
    ax.barh(y, [a["media"] for a in datos], color=AZUL, height=0.55)
    ax.set_yticks(list(y), [a["nombre"] for a in datos], fontsize=8, color="#1d1d1b")
    ax.set_xlim(0, 4.35)
    ax.set_xticks([0, 1, 2, 3, 4])
    ax.axvline(UMBRAL_SATISFACTORIO, color="#52514e", lw=1, ls="--")
    ax.text(UMBRAL_SATISFACTORIO, len(datos) - 0.35, " umbral satisfactorio (3)",
            fontsize=7, color="#52514e", va="bottom")
    for i, a in enumerate(datos):
        ax.text(a["media"] - 0.05, i, fmt_num(a["media"]), va="center", ha="right",
                fontsize=7.5, color="white", fontweight="bold")
    ax.grid(axis="x", color="#e8e7e2", lw=0.6)
    ax.set_axisbelow(True)
    _estilo_ejes(ax)
    ax.set_xlabel("Puntuación media (escala 1-4)", fontsize=8, color="#52514e")
    return _figura(fig, 16)


def _grafico_sino(sino) -> Image | None:
    filas = [s for b in sino for s in b["subitems"] if s["pct_si"] is not None][::-1]
    if not filas:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 0.45 * len(filas) + 0.9))
    y = list(range(len(filas)))
    si = [s["pct_si"] for s in filas]
    no = [s["pct_no"] for s in filas]
    ax.barh(y, si, color=AZUL, height=0.55, label="Sí", edgecolor="white", linewidth=1.5)
    ax.barh(y, no, left=si, color=NARANJA, height=0.55, label="No", edgecolor="white", linewidth=1.5)
    ax.set_yticks(y, [f"{s['codigo']} {s['texto'][:48]}" for s in filas], fontsize=8, color="#1d1d1b")
    for i, (a, b) in enumerate(zip(si, no)):
        if a >= 9:
            ax.text(a / 2, i, fmt_pct(a), ha="center", va="center", fontsize=7.5, color="white")
        if b >= 9:
            ax.text(a + b / 2, i, fmt_pct(b), ha="center", va="center", fontsize=7.5, color="white")
    ax.set_xlim(0, 100)
    ax.set_xlabel("% sobre respuestas válidas", fontsize=8, color="#52514e")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False, fontsize=8)
    _estilo_ejes(ax)
    return _figura(fig, 16)


# --------------------------------------------------------------------------
def generar_pdf(ficha, apartados, sino, elementos, concl, comentarios, media_glob, nota,
                nivel_general, incluir_item7, motor, participantes=None) -> bytes:
    _PARTICIPANTES[:] = participantes or range(1, len(comentarios) + 1)
    buf = io.BytesIO()
    titulo = f"Informe Curso – {ficha['curso'] or 'Sin nombre'}"
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm, title=titulo,
                            author="Informe automático de evaluación de la formación")

    def pie(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(TINTA_2)
        canvas.drawString(2 * cm, 1.1 * cm, _txt(titulo)[:110].replace("&amp;", "&"))
        canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Página {d.page}")
        canvas.setStrokeColor(LINEA)
        canvas.line(2 * cm, 1.4 * cm, A4[0] - 2 * cm, 1.4 * cm)
        canvas.restoreState()

    h = []
    h.append(Paragraph(_txt(titulo), E["titulo"]))
    h.append(Paragraph(f"Análisis de los cuestionarios de evaluación de la calidad · "
                       f"Generado el {date.today().strftime('%d/%m/%Y')}", E["subtitulo"]))

    # 1. FICHA ---------------------------------------------------------------
    h.append(Paragraph("1. Ficha del curso", E["h1"]))
    filas = [
        ["Nombre del curso", ficha["curso"] or "–"],
        ["Sociedad bonificada (Nº expediente)", ficha["expediente"] or "–"],
        ["Nº acción formativa / Grupo", f"{ficha['n_aaff'] or '–'} / {ficha['n_grupo'] or '–'}"],
        ["Nº cuestionarios", str(ficha["n_cuestionarios"])],
        ["Modalidad", ficha["modalidad"] or "–"],
    ]
    t = _tabla(filas, [6 * cm, ANCHO - 6 * cm], cabecera=False)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), FONDO_ALT),
                           ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
    h.append(t)

    # 2. CUANTITATIVO ---------------------------------------------------------
    h.append(Paragraph("2. Análisis cuantitativo", E["h1"]))
    h.append(Paragraph(
        "Escala de 1 (completamente en desacuerdo) a 4 (completamente de acuerdo). "
        "Medias entre 1,00 y 2,99: <b>No satisfactorio</b>; entre 3,00 y 4,00: "
        "<b>Satisfactorio</b>. Las puntuaciones se muestran truncadas a dos decimales, "
        "sin redondear." + ("" if incluir_item7 else
                            " El ítem 7 (modalidad telemática o mixta) no se ha valorado."),
        E["normal"]))
    h.append(Paragraph("2.1 Puntuación media por apartado", E["h2"]))
    filas = [["Apartado", "Puntuación media", "Nivel de satisfacción"]]
    for a in apartados:
        filas.append([f"{a['numero']}. {a['nombre']}", fmt_num(a["media"]), _nivel_par(a["nivel"])])
    h.append(_tabla(filas, [9.5 * cm, 3 * cm, ANCHO - 12.5 * cm]))
    h.append(Spacer(1, 8))
    h.append(_grafico_apartados(apartados))

    h.append(Paragraph("2.2 Detalle por apartado", E["h2"]))
    for a in apartados:
        filas = [["Ítem", "Descripción", "Media", "Resp.", "1", "2", "3", "4"]]
        for s in a["subitems"]:
            d = s["distribucion"]
            filas.append([s["codigo"], s["texto"], fmt_num(s["media"]), str(s["n"]),
                          str(d[1]), str(d[2]), str(d[3]), str(d[4])])
        filas.append(["", "Media del apartado", fmt_num(a["media"]), "", "", "", "", ""])
        t = _tabla(filas, [1.2 * cm, ANCHO - 9.2 * cm, 1.6 * cm, 1.4 * cm] + [1.25 * cm] * 4)
        t.setStyle(TableStyle([("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e3eaf3")),
                               ("SPAN", (3, -1), (-1, -1))]))
        bloque = [Paragraph(_txt(f"{a['numero']}. {a['nombre']} — media {fmt_num(a['media'])} "
                                 f"· {a['nivel']}"), E["h3"]), t]
        h.append(KeepTogether(bloque))
    h.append(Paragraph("Columnas 1-4: número de respuestas en cada valor de la escala. "
                       "En el ítem 4 se agregan las respuestas de las columnas Formador y Tutor.",
                       E["nota"]))

    h.append(Paragraph("2.3 Ítems de respuesta Sí / No", E["h2"]))
    filas = [["Ítem", "Descripción", "Sí", "No", "% Sí", "% No", "Sin resp."]]
    for b in sino:
        for s in b["subitems"]:
            filas.append([s["codigo"], s["texto"], str(s["si"]), str(s["no"]),
                          fmt_pct(s["pct_si"]), fmt_pct(s["pct_no"]), str(s["sin_respuesta"])])
        if len(b["subitems"]) > 1:
            filas.append(["", f"Total apartado {b['numero']}. {b['nombre']}", "", "",
                          fmt_pct(b["pct_si"]), fmt_pct(b["pct_no"]), ""])
    h.append(_tabla(filas, [1.2 * cm, ANCHO - 9.4 * cm, 1.2 * cm, 1.2 * cm, 1.8 * cm, 1.8 * cm, 2.2 * cm]))
    h.append(Paragraph("Los porcentajes se calculan sobre las respuestas válidas (Sí + No).",
                       E["nota"]))
    g = _grafico_sino(sino)
    if g:
        h.append(Spacer(1, 6))
        h.append(g)

    # 3. COMENTARIOS -----------------------------------------------------------
    h.append(Paragraph("3. Análisis de comentarios", E["h1"]))
    n_part = len(comentarios)
    h.append(Paragraph(
        f"{n_part} de {ficha['n_cuestionarios']} participantes han realizado comentarios en el "
        f"ítem 11 (sugerencias u observaciones). La frecuencia indica cuántos participantes "
        f"mencionan cada elemento con esa valoración.", E["normal"]))
    h.append(Spacer(1, 6))
    if elementos:
        filas = [["Elemento valorado", "Valor", "Frec.", "Comentarios ilustrativos"]]
        for e in elementos:
            citas = [_cita_celda(comentarios, i) for i in e["ejemplos"][:2]]
            color = {"Positivo": VERDE_TXT, "Negativo": ROJO_TXT}.get(e["valor"], TINTA_2)
            est = ParagraphStyle("v", parent=E["celda"], textColor=color, fontName="Helvetica-Bold")
            filas.append([e["elemento"], Paragraph(_txt(e["valor"]), est), str(e["frecuencia"]),
                          citas or "–"])
        h.append(_tabla(filas, [4 * cm, 1.9 * cm, 1.2 * cm, ANCHO - 7.1 * cm]))
    else:
        h.append(Paragraph("No hay comentarios que analizar.", E["normal"]))

    # 4. CONCLUSIONES ----------------------------------------------------------
    h.append(Paragraph("4. Conclusiones y recomendaciones", E["h1"]))
    kpis = [
        [Paragraph(f"{fmt_num(nota, 1)} / 10", E["kpi_valor"]),
         Paragraph(_txt(nivel_general), ParagraphStyle(
             "kpi_txt", parent=E["kpi_valor"], fontSize=13, leading=16)),
         Paragraph(f"{fmt_num(media_glob)} / 4", E["kpi_valor"])],
        [Paragraph("Valoración global del curso", E["kpi_etq"]),
         Paragraph("Nivel de satisfacción general", E["kpi_etq"]),
         Paragraph("Puntuación media global", E["kpi_etq"])],
    ]
    t = Table(kpis, colWidths=[ANCHO / 3] * 3)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (0, -1), 0.6, LINEA), ("BOX", (1, 0), (1, -1), 0.6, LINEA),
                           ("BOX", (2, 0), (2, -1), 0.6, LINEA),
                           ("BACKGROUND", (0, 0), (-1, -1), FONDO_ALT),
                           ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, -1), (-1, -1), 8)]))
    h.append(t)
    h.append(Paragraph("La valoración global sobre 10 transforma linealmente la media global "
                       "de la escala 1-4 (1 = 0; 4 = 10).", E["nota"]))

    h.append(Paragraph("Resumen ejecutivo", E["h2"]))
    h.append(Paragraph(_txt(concl["resumen"]), E["normal"]))

    def bloque_lista(titulo_b, items, ejemplos):
        h.append(Paragraph(titulo_b, E["h2"]))
        h.append(ListFlowable([ListItem(Paragraph(_txt(x), E["normal"]), leftIndent=12)
                               for x in items], bulletType="bullet", start="•", leftIndent=12))
        if ejemplos:
            h.append(Spacer(1, 3))
            h.append(Paragraph("<b>Comentarios de los participantes:</b>", E["normal"]))
            for i in ejemplos[:2]:
                h.append(_cita(comentarios, i))

    bloque_lista("Principales fortalezas", concl["fortalezas"], concl["ejemplos_fortalezas"])
    bloque_lista("Principales áreas de mejora", concl["mejoras"], concl["ejemplos_mejoras"])

    h.append(Paragraph("Recomendaciones de ajuste", E["h2"]))
    if concl["recomendaciones"]:
        filas = [["Punto de mejora", "Comentario que lo evidencia", "Acción recomendada"]]
        for r in concl["recomendaciones"]:
            cita = _cita_celda(comentarios, r["ejemplo"]) if r.get("ejemplo") is not None \
                else "Sin comentario asociado (detectado en la valoración cuantitativa)."
            filas.append([r["punto"], cita, r["accion"]])
        h.append(_tabla(filas, [4.2 * cm, (ANCHO - 4.2 * cm) / 2, (ANCHO - 4.2 * cm) / 2]))
    else:
        h.append(Paragraph("No se detectan puntos de mejora que requieran ajustes.", E["normal"]))

    h.append(Spacer(1, 14))
    h.append(Paragraph(
        "Nota metodológica: datos extraídos automáticamente de los campos de formulario de "
        "los cuestionarios. Las respuestas «No contesta» o en blanco se excluyen de los "
        "cálculos. Análisis de comentarios realizado con " +
        ("inteligencia artificial (Claude, Anthropic)." if motor == "ia"
         else "un motor de reglas léxicas en castellano.") +
        " Se recomienda revisión por el técnico de formación antes de su difusión.", E["nota"]))

    doc.build(h, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()
