"""
Extracción y análisis cuantitativo de los cuestionarios SEPE / FUNDAE
(Cuestionario para la evaluación de la calidad de las acciones formativas).

Los cuestionarios son PDF con formulario rellenable (AcroForm). Los datos se
leen directamente de los campos del formulario, sin OCR.
"""
from __future__ import annotations

import io
import math
import zipfile
from collections import Counter
from dataclasses import dataclass, field

from pypdf import PdfReader

# --------------------------------------------------------------------------
# Correspondencia de campos del formulario
# --------------------------------------------------------------------------
ESCALA = {
    "Completamente en desacuerdo": 1,
    "En desacuerdo": 2,
    "De acuerdo": 3,
    "Completamente de acuerdo": 4,
}
SI_NO = {"Si": "Sí", "Sí": "Sí", "No": "No"}

CAMPOS_FICHA = {
    "expediente": "D_NUM_EXPEDIENTE",
    "tipo_acceso": "D_EXPEDIENTE_DM",
    "cif": "D_CIF",
    "n_aaff": "D_COD_AAFF",
    "n_grupo": "D_COD_GRUPO",
    "curso": "D_ACCION_FORMATIVA",
    "modalidad": "ID_MODALIDAD",
}

# Apartados valorados en escala 1-4. Cada sub-ítem puede alimentarse de más de
# un campo (el ítem 4 tiene columna Formador y columna Tutor).
APARTADOS_ESCALA = [
    ("1", "Organización del curso", [
        ("1.1", "El curso ha estado bien organizado", ["ID_BUENA_ORGANIZACION"]),
        ("1.2", "El número de alumnos del grupo ha sido adecuado", ["ID_NUM_ALUMNOS_ADECUADO"]),
    ]),
    ("2", "Contenidos y metodología de impartición", [
        ("2.1", "Los contenidos han respondido a mis necesidades formativas", ["ID_CONTENIDOS_SEGUN_NECESIDADES"]),
        ("2.2", "Combinación adecuada de teoría y aplicación práctica", ["ID_CONTENIDOS_SEGUN_TEORIA_PRACTICA"]),
    ]),
    ("3", "Duración y horario", [
        ("3.1", "La duración ha sido suficiente según objetivos y contenidos", ["ID_DURACION_SUFICIENTE"]),
        ("3.2", "El horario ha favorecido la asistencia", ["ID_HORARIO_FAVORABLE"]),
    ]),
    ("4", "Formadores y tutores", [
        ("4.1", "La forma de impartir o tutorizar ha facilitado el aprendizaje",
         ["ID_FORMADOR_FACILITADOR", "ID_TUTOR_FACILITADOR"]),
        ("4.2", "Conocen los temas impartidos en profundidad",
         ["ID_FORMADOR_CONOCE_TEMA", "ID_TUTOR_CONOCE_TEMA"]),
    ]),
    ("5", "Medios didácticos", [
        ("5.1", "Documentación y materiales comprensibles y adecuados", ["ID_MEDIOS_COMPRENSIBLES"]),
        ("5.2", "Los medios didácticos están actualizados", ["ID_MEDIOS_ACTUALIZADOS"]),
    ]),
    ("6", "Instalaciones y medios técnicos", [
        ("6.1", "Aula, taller o instalaciones apropiadas", ["ID_INSTALACIONES_ADECUADAS"]),
        ("6.2", "Medios técnicos adecuados", ["ID_MEDIOS_TECNICOS_ADECUADOS"]),
    ]),
    ("7", "Modalidad telemática o mixta", [
        ("7.1", "Guías tutoriales y materiales han facilitado el curso", ["ID_TELEFORMACION_GUIA"]),
        ("7.2", "Medios de apoyo suficientes (tutorías, correo, videoconferencia...)", ["ID_TELEFORMACION_MEDIOS"]),
    ]),
    ("9", "Valoración general del curso", [
        ("9.1", "Puede contribuir a mi incorporación al mercado de trabajo", ["ID_INCORPORACION_MERCADO"]),
        ("9.2", "He adquirido habilidades aplicables al puesto de trabajo", ["Habilidades_trabajar_en_formado"]),
        ("9.3", "Ha mejorado mis posibilidades de cambiar de puesto", ["ID_CONOCIMIENTOS_PUESTO_TRABAJO"]),
        ("9.4", "He ampliado conocimientos para progresar en mi carrera", ["ID_PROGRESAR_CARRERA"]),
        ("9.5", "Ha favorecido mi desarrollo personal", ["ID_DESARROLLO_PERSONAL"]),
    ]),
    ("10", "Grado de satisfacción general con el curso", [
        ("10", "Grado de satisfacción general", ["ID_GRADO_SATISFACCION"]),
    ]),
]

# Ítems de respuesta Sí / No
APARTADOS_SINO = [
    ("8", "Mecanismos para la evaluación del aprendizaje", [
        ("8.1", "Pruebas de evaluación y autoevaluación del nivel alcanzado", "ID_PRUEBAS_EVALUACION"),
        ("8.2", "El curso permite obtener una acreditación de la cualificación", "ID_ACREDITACION"),
    ]),
    ("10", "Grado de satisfacción general con el curso", [
        ("10.1", "¿Recomendaría este curso?", "ID_RECOMENDARIA_CURSO"),
    ]),
]

CAMPO_COMENTARIO = "D_OBSERVACION"
UMBRAL_SATISFACTORIO = 3.0


# --------------------------------------------------------------------------
# Utilidades numéricas
# --------------------------------------------------------------------------
def truncar(valor: float, decimales: int = 2) -> float:
    """Trunca (no redondea) para que 2,999 se muestre como 2,99 y no como 3,00."""
    f = 10 ** decimales
    return math.floor(valor * f + 1e-9) / f


def fmt_num(valor: float | None, decimales: int = 2) -> str:
    if valor is None:
        return "–"
    return f"{truncar(valor, decimales):.{decimales}f}".replace(".", ",")


def fmt_pct(valor: float | None) -> str:
    if valor is None:
        return "–"
    return f"{valor:.1f} %".replace(".", ",")


def nivel_satisfaccion(media: float | None) -> str:
    if media is None:
        return "Sin datos"
    # Se usa el valor exacto (sin redondear) para clasificar.
    return "Satisfactorio" if media >= UMBRAL_SATISFACTORIO else "No satisfactorio"


# --------------------------------------------------------------------------
# Lectura de cuestionarios
# --------------------------------------------------------------------------
@dataclass
class Cuestionario:
    archivo: str
    campos: dict

    def texto(self, nombre: str) -> str:
        v = self.campos.get(nombre)
        return str(v).strip() if v is not None else ""

    def opcion(self, nombre: str) -> str:
        """Valor de un botón de opción, sin la barra inicial de los nombres PDF."""
        v = self.texto(nombre)
        return v[1:] if v.startswith("/") else v

    def puntuacion(self, nombre: str) -> int | None:
        return ESCALA.get(self.opcion(nombre))

    def si_no(self, nombre: str) -> str | None:
        return SI_NO.get(self.opcion(nombre))

    @property
    def comentario(self) -> str:
        return " ".join(self.texto(CAMPO_COMENTARIO).split())


@dataclass
class ResultadoLectura:
    cuestionarios: list[Cuestionario] = field(default_factory=list)
    descartados: list[tuple[str, str]] = field(default_factory=list)


def _leer_pdf(nombre: str, datos: bytes) -> Cuestionario:
    lector = PdfReader(io.BytesIO(datos))
    campos_pdf = lector.get_fields() or {}
    if not campos_pdf:
        raise ValueError("el PDF no contiene campos de formulario (¿escaneado o aplanado?)")
    campos = {k: v.get("/V") for k, v in campos_pdf.items()}
    if "D_ACCION_FORMATIVA" not in campos and "ID_BUENA_ORGANIZACION" not in campos:
        raise ValueError("no parece un cuestionario de evaluación de la calidad")
    return Cuestionario(archivo=nombre, campos=campos)


def leer_zip(archivo_zip) -> ResultadoLectura:
    """Lee todos los PDF de un .zip (incluidas subcarpetas)."""
    res = ResultadoLectura()
    with zipfile.ZipFile(archivo_zip) as zf:
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            nombre = info.filename
            base = nombre.rsplit("/", 1)[-1]
            if info.is_dir() or nombre.startswith("__MACOSX") or base.startswith("."):
                continue
            if not base.lower().endswith(".pdf"):
                res.descartados.append((base, "no es un archivo PDF"))
                continue
            try:
                res.cuestionarios.append(_leer_pdf(base, zf.read(info)))
            except Exception as e:  # noqa: BLE001
                res.descartados.append((base, str(e)))
    return res


# --------------------------------------------------------------------------
# Análisis
# --------------------------------------------------------------------------
def _valor_mayoritario(valores: list[str]) -> tuple[str, list[str]]:
    vals = [v for v in valores if v]
    if not vals:
        return "", []
    conteo = Counter(vals)
    return conteo.most_common(1)[0][0], sorted(conteo)


def ficha_curso(cs: list[Cuestionario]) -> dict:
    ficha, avisos = {}, []
    for clave, campo in CAMPOS_FICHA.items():
        lector = Cuestionario.opcion if clave == "modalidad" else Cuestionario.texto
        principal, distintos = _valor_mayoritario([lector(c, campo) for c in cs])
        ficha[clave] = principal
        if len(distintos) > 1:
            avisos.append(f"Hay valores distintos en '{clave}': {', '.join(distintos)}")
    ficha["modalidad"] = {"Teleformacion": "Teleformación"}.get(ficha["modalidad"], ficha["modalidad"])
    ficha["n_cuestionarios"] = len(cs)
    ficha["avisos"] = avisos
    return ficha


def modalidad_requiere_item7(modalidad: str) -> bool:
    m = modalidad.lower()
    return m.startswith("tele") or m.startswith("mixt")


def analisis_cuantitativo(cs: list[Cuestionario], incluir_item7: bool) -> list[dict]:
    apartados = []
    for num, nombre, subitems in APARTADOS_ESCALA:
        if num == "7" and not incluir_item7:
            continue
        detalle = []
        for cod, texto, campos in subitems:
            puntos = [p for c in cs for campo in campos if (p := c.puntuacion(campo)) is not None]
            media = sum(puntos) / len(puntos) if puntos else None
            dist = Counter(puntos)
            detalle.append({
                "codigo": cod, "texto": texto, "media": media, "n": len(puntos),
                "distribucion": {k: dist.get(k, 0) for k in (1, 2, 3, 4)},
            })
        medias = [d["media"] for d in detalle if d["media"] is not None]
        media_ap = sum(medias) / len(medias) if medias else None
        apartados.append({
            "numero": num, "nombre": nombre, "subitems": detalle,
            "media": media_ap, "nivel": nivel_satisfaccion(media_ap),
        })
    return apartados


def analisis_si_no(cs: list[Cuestionario]) -> list[dict]:
    bloques = []
    for num, nombre, subitems in APARTADOS_SINO:
        detalle, tot_si, tot_no = [], 0, 0
        for cod, texto, campo in subitems:
            resp = [c.si_no(campo) for c in cs]
            si, no = resp.count("Sí"), resp.count("No")
            sin = len(resp) - si - no
            validas = si + no
            detalle.append({
                "codigo": cod, "texto": texto, "si": si, "no": no, "sin_respuesta": sin,
                "pct_si": 100 * si / validas if validas else None,
                "pct_no": 100 * no / validas if validas else None,
            })
            tot_si, tot_no = tot_si + si, tot_no + no
        tot = tot_si + tot_no
        bloques.append({
            "numero": num, "nombre": nombre, "subitems": detalle,
            "pct_si": 100 * tot_si / tot if tot else None,
            "pct_no": 100 * tot_no / tot if tot else None,
        })
    return bloques


def media_global(apartados: list[dict]) -> float | None:
    medias = [a["media"] for a in apartados if a["media"] is not None]
    return sum(medias) / len(medias) if medias else None


def nota_sobre_10(media_1a4: float | None) -> float | None:
    """Convierte la escala 1-4 a 0-10 de forma lineal: 1 -> 0, 4 -> 10."""
    if media_1a4 is None:
        return None
    return (media_1a4 - 1) / 3 * 10


def grado_cualitativo(media: float | None) -> str:
    if media is None:
        return "Sin datos"
    if media >= 3.5:
        return "Muy alto"
    if media >= 3.0:
        return "Alto"
    if media >= 2.0:
        return "Bajo"
    return "Muy bajo"
