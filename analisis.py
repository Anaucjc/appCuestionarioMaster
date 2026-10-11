"""Orquestación: del .zip de cuestionarios al PDF del informe."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import procesador as pr
from comentarios import analizar_comentarios_reglas, analizar_con_ia, conclusiones_reglas
from informe_pdf import generar_pdf


@dataclass
class Informe:
    pdf: bytes
    nombre_archivo: str
    ficha: dict
    apartados: list
    sino: list
    elementos: list
    conclusiones: dict
    comentarios: list
    media_global: float | None
    nota: float | None
    nivel_general: str
    incluir_item7: bool
    motor: str
    descartados: list
    avisos: list


def nombre_archivo(curso: str) -> str:
    s = unicodedata.normalize("NFKD", curso).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:80] or "curso"
    return f"Informe_Curso_{s}.pdf"


def generar_informe(archivo_zip, modo_item7: str = "auto", usar_ia: bool = False,
                    api_key: str | None = None, modelo: str = "claude-sonnet-5-5") -> Informe:
    """modo_item7: 'auto' (según modalidad), 'si' o 'no'."""
    lectura = pr.leer_zip(archivo_zip)
    cs = lectura.cuestionarios
    if not cs:
        raise ValueError("El .zip no contiene cuestionarios PDF válidos.")

    ficha = pr.ficha_curso(cs)
    avisos = list(ficha.pop("avisos"))
    if modo_item7 == "auto":
        incluir7 = pr.modalidad_requiere_item7(ficha["modalidad"])
    else:
        incluir7 = modo_item7 == "si"

    apartados = pr.analisis_cuantitativo(cs, incluir7)
    sino = pr.analisis_si_no(cs)
    media = pr.media_global(apartados)
    nota = pr.nota_sobre_10(media)
    nivel = pr.nivel_satisfaccion(media)
    if media is not None:
        nivel = f"{nivel} ({pr.grado_cualitativo(media).lower()})"

    con_comentario = [(n, c.comentario) for n, c in enumerate(cs, 1) if len(c.comentario) > 2]
    participantes = [n for n, _ in con_comentario]
    comentarios = [t for _, t in con_comentario]

    motor = "reglas"
    elementos = analizar_comentarios_reglas(comentarios)
    concl = conclusiones_reglas(apartados, sino, elementos, comentarios, ficha, media, nota)
    if usar_ia and api_key:
        try:
            elementos_ia, concl_ia = analizar_con_ia(comentarios, apartados, sino, api_key, modelo)
            if concl_ia.get("resumen"):
                elementos, concl, motor = elementos_ia, concl_ia, "ia"
        except Exception as e:  # noqa: BLE001
            avisos.append(f"No se pudo usar la IA ({e}); se ha aplicado el análisis por reglas.")

    pdf = generar_pdf(ficha, apartados, sino, elementos, concl, comentarios, media, nota,
                      nivel, incluir7, motor, participantes)
    return Informe(pdf, nombre_archivo(ficha["curso"]), ficha, apartados, sino, elementos,
                   concl, comentarios, media, nota, nivel, incluir7, motor,
                   lectura.descartados, avisos)
