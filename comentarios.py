"""
Análisis de los comentarios abiertos (ítem 11) y elaboración de conclusiones.

Dos motores:
  * "reglas": análisis léxico en castellano, sin dependencias externas ni coste.
  * "ia": usa la API de Claude (Anthropic) si se facilita una API key. Ofrece
    una lectura más fina de los matices; si falla, se vuelve a "reglas".

Ambos devuelven la misma estructura, de modo que el informe no depende del motor.
Los comentarios se referencian siempre por su índice, así las citas del informe
son siempre literales (nunca inventadas).
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict

from procesador import fmt_num, nivel_satisfaccion, UMBRAL_SATISFACTORIO

# --------------------------------------------------------------------------
# Diccionarios
# --------------------------------------------------------------------------
# Palabra terminada en * = prefijo; con espacios = expresión; resto = palabra exacta.
ELEMENTOS = {
    "Formador/a y forma de impartir": [
        "profesor*", "profe", "profes", "docente*", "formador*", "ponente*", "tutor*",
        "instructor*", "explicacion*", "explica*", "imparti*", "ameno", "amena", "ensena*",
    ],
    "Duración y ritmo del curso": [
        "tiempo", "duracion", "dura", "horas", "ritmo", "despacio", "deprisa", "rapido*",
        "intensiv*", "condensad*", "corto", "corta", "largo", "larga", "sesiones", "dias",
        "semanas", "mas tiempo",
    ],
    "Horario": [
        "horario*", "franja*", "jornada*", "tarde", "tardes", "manana", "mananas",
        "viernes", "fin de semana",
    ],
    "Contenidos": [
        "contenido*", "temario*", "tema", "temas", "teoria*", "teoric*", "nivel", "concepto*",
        "materia", "programa", "enfoque",
    ],
    "Parte práctica y ejemplos": [
        "practic*", "ejercicio*", "caso", "casos", "ejemplo*", "dinamica*", "simulacion*",
        "role play",
    ],
    "Materiales y documentación": [
        "material*", "documentacion", "manual*", "apunte*", "presentacion*", "diapositiva*",
        "guia*", "recurso*", "bibliografia",
    ],
    "Instalaciones y medios técnicos": [
        "aula*", "sala*", "instalacion*", "proyector*", "ordenador*", "wifi", "pantalla*",
        "sonido", "climatizacion", "aire acondicionado", "frio", "calor", "silla*",
        "pizarra*", "equipos",
    ],
    "Plataforma y formación online": [
        "plataforma*", "campus", "online", "virtual*", "zoom", "teams", "videoconferencia*",
        "conexion*", "internet", "grabacion*", "telematic*",
    ],
    "Organización y grupo": [
        "organiz*", "coordinac*", "informacion", "grupo*", "alumnos", "companer*",
        "convocatoria*", "fechas", "gestion", "comunicacion", "inscripcion",
    ],
    "Evaluación y acreditación": [
        "evaluac*", "examen*", "test", "certificad*", "diploma*", "acreditac*",
    ],
    "Utilidad y aplicación al puesto": [
        "util", "utiles", "utilidad", "aplicab*", "aplicar", "dia a dia", "puesto*",
        "trabajo", "herramienta*",
    ],
}
ELEMENTO_GENERAL = "Valoración general del curso"

POSITIVOS = [
    "buen*", "bien", "excelent*", "estupend*", "genial*", "ameno", "amena", "claro", "clara",
    "claridad", "util", "utiles", "interesant*", "recomend*", "perfect*", "encant*", "gust*",
    "fantastic*", "profesional*", "dinamic*", "complet*", "adecuad*", "satisf*",
    "aprendid*", "magnific*", "cercan*", "domin*", "agradable*", "motivad*", "didactic*",
    "facil", "ayud*", "enriquecedor*", "valios*", "aprovech*", "maravill*", "atent*",
    "pacien*", "mucha experiencia", "muy bien", "de diez", "acert*", "felicit*", "gracias",
]
NEGATIVOS = [
    "mal", "mala", "malo", "malas", "malos", "escas*", "insuficient*", "falt*", "costad*",
    "costo", "dificil*", "lento", "lenta", "aburrid*", "denso", "densa", "problema*",
    "fallo*", "fallab*", "desorganiz*", "confus*", "pesad*", "cansad*", "caotic*",
    "incomod*", "ruido*", "complicad*", "repetitiv*", "obsolet*", "desactualiz*", "pobre*",
    "deficien*", "molest*", "perdid*", "agobi*", "demasiad*", "lio", "lioso", "liosa",
    "mejorable*", "mejorar", "decepcion*", "superficial*", "corto", "corta", "frio", "calor",
]
# Expresiones de sugerencia / carencia: se tratan como aspecto a mejorar.
SUGERENCIAS = [
    "seria mejor", "habria sido mejor", "hubiera sido mejor", "seria conveniente",
    "convendria", "deberia", "deberian", "me gustaria", "nos gustaria", "estaria bien",
    "echo en falta", "eche en falta", "echamos en falta", "mas tiempo", "mas practic",
    "mas ejemplo", "mas ejercicio", "mas caso", "mas despacio", "mas horas", "mas dias",
    "poco tiempo", "no funcion", "no se entend", "se queda corto", "se hace largo",
    "se hizo largo", "se hizo corto", "a mejorar", "habria que", "hubiera estado bien",
    "seria interesante", "seria util", "se podria",
]
NEGADORES = {"no", "nada", "ningun", "ninguna", "ninguno", "nunca", "tampoco", "sin", "ni"}
CONTRASTE = r"\b(?:pero|aunque|sin embargo|no obstante|salvo|excepto|si bien)\b"

# Correspondencia entre apartados del cuestionario y elementos de comentarios
APARTADO_A_ELEMENTO = {
    "1": "Organización y grupo",
    "2": "Contenidos",
    "3": "Duración y ritmo del curso",
    "4": "Formador/a y forma de impartir",
    "5": "Materiales y documentación",
    "6": "Instalaciones y medios técnicos",
    "7": "Plataforma y formación online",
    "9": "Utilidad y aplicación al puesto",
    "10": ELEMENTO_GENERAL,
}

ACCIONES = {
    "Formador/a y forma de impartir":
        "Revisar con el equipo docente la metodología: más interacción, comprobaciones de "
        "comprensión periódicas y adaptación del discurso al nivel del grupo.",
    "Duración y ritmo del curso":
        "Ajustar la duración a los objetivos (ampliar horas o reducir contenidos) y planificar "
        "un ritmo progresivo con pausas de consolidación y repaso.",
    "Horario":
        "Consultar disponibilidad de los participantes antes de programar y ofrecer franjas "
        "alternativas o sesiones más cortas y repartidas.",
    "Contenidos":
        "Realizar un diagnóstico previo del nivel y las necesidades del grupo para adaptar el "
        "temario, e incluir un módulo introductorio para quien parta de cero.",
    "Parte práctica y ejemplos":
        "Aumentar el peso de la práctica: casos reales del sector, ejercicios guiados y "
        "talleres aplicados al puesto de trabajo.",
    "Materiales y documentación":
        "Actualizar y revisar los materiales, entregarlos con antelación y añadir guías de "
        "consulta rápida y recursos complementarios.",
    "Instalaciones y medios técnicos":
        "Verificar aula y equipos antes de cada sesión (proyector, conexión, climatización, "
        "puestos) y disponer de un plan alternativo ante incidencias.",
    "Plataforma y formación online":
        "Probar la plataforma y la conexión antes del curso, facilitar una guía de acceso y "
        "reforzar los canales de tutoría y soporte técnico.",
    "Organización y grupo":
        "Mejorar la comunicación previa (fechas, horarios, materiales) y dimensionar el grupo "
        "para favorecer la participación.",
    "Evaluación y acreditación":
        "Incorporar pruebas de evaluación y autoevaluación y comunicar desde el inicio qué "
        "acreditación o certificado se obtiene.",
    "Utilidad y aplicación al puesto":
        "Vincular los contenidos a situaciones reales del puesto y cerrar cada módulo con un "
        "plan de transferencia al trabajo.",
    ELEMENTO_GENERAL:
        "Recoger feedback intermedio durante el curso para corregir desajustes antes de su "
        "finalización.",
}


# --------------------------------------------------------------------------
# Motor por reglas
# --------------------------------------------------------------------------
def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ\s]", " ", t)


def _coincide(tokens: list[str], texto_norm: str, patron: str) -> list[int]:
    """Devuelve las posiciones (índices de token) donde aparece el patrón."""
    if " " in patron:
        pos = []
        for m in re.finditer(r"\b" + re.escape(patron), texto_norm):
            pos.append(len(texto_norm[: m.start()].split()))
        return pos
    if patron.endswith("*"):
        raiz = patron[:-1]
        return [i for i, t in enumerate(tokens) if t.startswith(raiz)]
    return [i for i, t in enumerate(tokens) if t == patron]


def _polaridad(fragmento: str) -> int:
    texto = " " + _norm(fragmento) + " "
    tokens = texto.split()
    puntuacion, ocupados = 0, set()
    for p in SUGERENCIAS:
        for i in _coincide(tokens, texto, p):
            puntuacion -= 1
            ocupados.update(range(i, i + len(p.split())))
    for lista, signo in ((POSITIVOS, 1), (NEGATIVOS, -1)):
        for p in lista:
            for i in _coincide(tokens, texto, p):
                if i in ocupados:
                    continue
                ocupados.add(i)
                negado = any(t in NEGADORES for t in tokens[max(0, i - 3): i])
                puntuacion += -signo if negado else signo
    return puntuacion


def _elementos(fragmento: str) -> set[str]:
    texto = " " + _norm(fragmento) + " "
    tokens = texto.split()
    return {el for el, pats in ELEMENTOS.items() if any(_coincide(tokens, texto, p) for p in pats)}


def _menciones_comentario(comentario: str) -> set[tuple[str, str]]:
    """Pares (elemento, valor) presentes en un comentario."""
    menciones: set[tuple[str, str]] = set()
    for frase in re.split(r"[.;!?\n]+", comentario):
        for clausula in re.split(CONTRASTE, frase, flags=re.I):
            frags = [f for f in re.split(r",|:|\(|\)", clausula) if f.strip()]
            datos = [(_elementos(f), _polaridad(f)) for f in frags]
            pol_clausula = sum(p for _, p in datos)
            ultimo_el: set[str] = set()
            for idx, (els, pol) in enumerate(datos):
                if not els and pol != 0:
                    # Opinión sin elemento explícito: hereda el del fragmento anterior
                    # o siguiente dentro de la misma cláusula.
                    siguientes = [e for e, _ in datos[idx + 1:] if e]
                    els = ultimo_el or (siguientes[0] if siguientes else {ELEMENTO_GENERAL})
                if els and pol == 0:
                    pol = pol_clausula
                for el in els:
                    valor = "Positivo" if pol > 0 else "Negativo" if pol < 0 else "Neutro"
                    menciones.add((el, valor))
                if els:
                    ultimo_el = els
    # Si un elemento tiene valoración positiva o negativa, se descarta su "Neutro".
    con_valor = {e for e, v in menciones if v != "Neutro"}
    return {(e, v) for e, v in menciones if v != "Neutro" or e not in con_valor}


def analizar_comentarios_reglas(comentarios: list[str]) -> list[dict]:
    menciones = defaultdict(list)  # (elemento, valor) -> [idx comentario]
    for i, c in enumerate(comentarios):
        for par in _menciones_comentario(c):
            menciones[par].append(i)
    elementos = []
    for (el, valor), ids in menciones.items():
        # Ejemplos: priorizar comentarios más cortos y explícitos (se leen mejor)
        ejemplos = sorted(ids, key=lambda k: abs(len(comentarios[k]) - 140))[:2]
        elementos.append({"elemento": el, "valor": valor, "frecuencia": len(ids),
                          "ids": ids, "ejemplos": ejemplos})
    # Agrupados por elemento (los más mencionados primero) y, dentro, por valor.
    orden_valor = {"Positivo": 0, "Negativo": 1, "Neutro": 2}
    total = defaultdict(int)
    for e in elementos:
        total[e["elemento"]] += e["frecuencia"]
    elementos.sort(key=lambda e: (-total[e["elemento"]], e["elemento"], orden_valor[e["valor"]]))
    return elementos


# --------------------------------------------------------------------------
# Conclusiones (motor por reglas)
# --------------------------------------------------------------------------
def _ejemplos_de(elementos: list[dict], valor: str, n: int) -> list[int]:
    """Elige n comentarios de distintos elementos, priorizando los que no mezclan
    valoraciones de signo contrario (ilustran mejor la idea)."""
    contrario = "Negativo" if valor == "Positivo" else "Positivo"
    mixtos = {i for e in elementos if e["valor"] == contrario for i in e["ids"]}
    elegidos: list[int] = []
    for e in [x for x in elementos if x["valor"] == valor]:
        candidatos = sorted(dict.fromkeys(e["ejemplos"] + e["ids"]), key=lambda i: i in mixtos)
        for i in candidatos:
            if i not in elegidos:
                elegidos.append(i)
                break
        if len(elegidos) >= n:
            break
    return elegidos


def conclusiones_reglas(apartados, sino, elementos, comentarios, ficha, media_glob, nota) -> dict:
    validos = [a for a in apartados if a["media"] is not None]
    orden = sorted(validos, key=lambda a: a["media"], reverse=True)
    elementos = sorted(elementos, key=lambda e: -e["frecuencia"])
    pos = [e for e in elementos if e["valor"] == "Positivo"]
    neg = [e for e in elementos if e["valor"] == "Negativo"]

    # Fortalezas
    fortalezas = []
    for a in [a for a in orden if a["media"] >= 3.5][:3] or orden[:2]:
        if a["media"] >= UMBRAL_SATISFACTORIO:
            fortalezas.append(f"{a['nombre']}: media {fmt_num(a['media'])} sobre 4.")
    for e in pos[:3]:
        fortalezas.append(f"{e['elemento']}: valorado positivamente en los comentarios "
                          f"de {e['frecuencia']} participante(s).")
    recomend = next((b for b in sino if b["numero"] == "10"), None)
    if recomend and recomend["pct_si"] is not None and recomend["pct_si"] >= 75:
        fortalezas.append(f"El {fmt_num(recomend['pct_si'], 1)} % recomendaría el curso.")

    # Áreas de mejora
    mejoras = []
    bajos = [a for a in orden[::-1] if a["media"] < UMBRAL_SATISFACTORIO]
    if not bajos:
        bajos = [a for a in orden[::-1] if a["media"] < 3.5][:2]
    for a in bajos:
        mejoras.append(f"{a['nombre']}: media {fmt_num(a['media'])} sobre 4 "
                       f"({a['nivel'].lower()}).")
    for e in neg[:3]:
        mejoras.append(f"{e['elemento']}: señalado como aspecto a mejorar por "
                       f"{e['frecuencia']} participante(s).")
    for b in sino:
        if b["numero"] == "8" and b["pct_no"] is not None and b["pct_no"] >= 50:
            mejoras.append(f"Mecanismos de evaluación: el {fmt_num(b['pct_no'], 1)} % de las "
                           f"respuestas indica que no se dispuso de ellos.")

    ej_fort = _ejemplos_de(elementos, "Positivo", 2)
    ej_mej = _ejemplos_de(elementos, "Negativo", 2)

    # Recomendaciones: una por elemento negativo y por apartado no satisfactorio
    recomendaciones, cubiertos = [], set()
    for e in neg:
        if e["elemento"] in cubiertos:
            continue
        cubiertos.add(e["elemento"])
        recomendaciones.append({
            "punto": f"{e['elemento']} ({e['frecuencia']} mención/es negativas)",
            "ejemplo": e["ejemplos"][0] if e["ejemplos"] else None,
            "accion": ACCIONES.get(e["elemento"], ACCIONES[ELEMENTO_GENERAL]),
        })
    for a in validos:
        el = APARTADO_A_ELEMENTO.get(a["numero"], ELEMENTO_GENERAL)
        if a["media"] < UMBRAL_SATISFACTORIO and el not in cubiertos:
            cubiertos.add(el)
            recomendaciones.append({
                "punto": f"{a['nombre']} (media {fmt_num(a['media'])}, no satisfactorio)",
                "ejemplo": None,
                "accion": ACCIONES.get(el, ACCIONES[ELEMENTO_GENERAL]),
            })
    for b in sino:
        if b["numero"] == "8" and b["pct_no"] is not None and b["pct_no"] >= 50 \
                and "Evaluación y acreditación" not in cubiertos:
            recomendaciones.append({
                "punto": f"Mecanismos de evaluación del aprendizaje ({fmt_num(b['pct_no'], 1)} % «No»)",
                "ejemplo": None,
                "accion": ACCIONES["Evaluación y acreditación"],
            })

    # Resumen ejecutivo
    lineas = [
        f"Se han analizado {ficha['n_cuestionarios']} cuestionarios de la acción formativa "
        f"«{ficha['curso']}».",
        f"La puntuación media global es {fmt_num(media_glob)} sobre 4, equivalente a "
        f"{fmt_num(nota, 1)} sobre 10, lo que supone un nivel de satisfacción "
        f"{nivel_satisfaccion(media_glob).lower()}.",
    ]
    if orden:
        lineas.append(f"El apartado mejor valorado es «{orden[0]['nombre']}» "
                      f"({fmt_num(orden[0]['media'])}) y el peor valorado, "
                      f"«{orden[-1]['nombre']}» ({fmt_num(orden[-1]['media'])}).")
    no_sat = [a["nombre"] for a in validos if a["media"] < UMBRAL_SATISFACTORIO]
    lineas.append("Todos los apartados alcanzan el nivel satisfactorio." if not no_sat else
                  f"No alcanzan el nivel satisfactorio: {', '.join(no_sat)}.")
    if recomend and recomend["pct_si"] is not None:
        lineas.append(f"El {fmt_num(recomend['pct_si'], 1)} % de quienes responden "
                      f"recomendaría el curso.")
    n_com = len(comentarios)
    if n_com:
        txt = f"{n_com} participante(s) dejaron comentarios"
        if pos:
            txt += f"; destacan positivamente «{pos[0]['elemento'].lower()}»"
        if neg:
            txt += f" y como aspecto a mejorar «{neg[0]['elemento'].lower()}»"
        lineas.append(txt + ".")
    else:
        lineas.append("Ningún participante dejó comentarios en el apartado de observaciones.")

    return {
        "resumen": " ".join(lineas),
        "fortalezas": fortalezas or ["No se identifican fortalezas destacables."],
        "ejemplos_fortalezas": ej_fort,
        "mejoras": mejoras or ["No se identifican áreas de mejora relevantes."],
        "ejemplos_mejoras": ej_mej,
        "recomendaciones": recomendaciones,
    }


# --------------------------------------------------------------------------
# Motor con IA (API de Claude)
# --------------------------------------------------------------------------
PROMPT_IA = """Eres técnico/a de formación y analizas los cuestionarios de evaluación de \
calidad de una acción formativa (cuestionario SEPE/FUNDAE). Responde SOLO con un JSON válido.

DATOS CUANTITATIVOS (escala 1-4; satisfactorio si media >= 3):
{cuantitativo}

COMENTARIOS DE LOS PARTICIPANTES (ítem 11), numerados:
{comentarios}

Devuelve este JSON (en castellano):
{{
  "elementos": [
    {{"elemento": "aspecto valorado (p. ej. 'Formador/a', 'Duración y ritmo', 'Parte práctica')",
      "valor": "Positivo" | "Negativo" | "Neutro",
      "ids": [números de TODOS los comentarios que mencionan ese aspecto con ese valor],
      "ejemplos": [los 2 números de comentario que mejor lo ilustran]}}
  ],
  "resumen": "resumen ejecutivo de 5 a 8 líneas que integre datos cuantitativos y comentarios",
  "fortalezas": ["fortaleza 1", "..."],
  "ejemplos_fortalezas": [2 números de comentario que demuestren las fortalezas],
  "mejoras": ["área de mejora 1", "..."],
  "ejemplos_mejoras": [2 números de comentario que demuestren las áreas de mejora],
  "recomendaciones": [
    {{"punto": "punto de mejora", "ejemplo": número de comentario que lo demuestra o null,
      "accion": "una acción concreta recomendada para corregirlo en futuras ediciones"}}
  ]
}}
Reglas: un mismo aspecto puede aparecer como Positivo y como Negativo si hay opiniones de \
ambos tipos. Las sugerencias ("sería mejor...", "faltó...") cuentan como Negativo. \
Usa solo números de comentario existentes. No inventes citas. Apoya fortalezas, mejoras y \
recomendaciones también en los apartados con puntuación baja aunque no tengan comentarios."""


def _resumen_cuantitativo(apartados, sino) -> str:
    lineas = [f"- {a['numero']}. {a['nombre']}: {fmt_num(a['media'])}" for a in apartados]
    for b in sino:
        for s in b["subitems"]:
            lineas.append(f"- {s['codigo']} {s['texto']}: Sí {s['si']}, No {s['no']}")
    return "\n".join(lineas)


def _ids_validos(valores, n) -> list[int]:
    out = []
    for v in valores or []:
        try:
            i = int(v) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= i < n and i not in out:
            out.append(i)
    return out


def analizar_con_ia(comentarios, apartados, sino, api_key: str, modelo: str) -> tuple[list, dict]:
    import anthropic  # importación diferida: solo se necesita en modo IA

    cliente = anthropic.Anthropic(api_key=api_key)
    texto_com = "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(comentarios)) or "(sin comentarios)"
    prompt = PROMPT_IA.format(cuantitativo=_resumen_cuantitativo(apartados, sino),
                              comentarios=texto_com)
    resp = cliente.messages.create(model=modelo, max_tokens=8000,
                                   messages=[{"role": "user", "content": prompt}])
    texto = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    datos = json.loads(texto[texto.find("{"): texto.rfind("}") + 1])

    n = len(comentarios)
    elementos = []
    for e in datos.get("elementos", []):
        ids = _ids_validos(e.get("ids"), n)
        if not ids:
            continue
        ejemplos = [i for i in _ids_validos(e.get("ejemplos"), n) if i in ids][:2] or ids[:2]
        valor = str(e.get("valor", "Neutro")).capitalize()
        elementos.append({"elemento": str(e.get("elemento", "")).strip(),
                          "valor": valor if valor in ("Positivo", "Negativo", "Neutro") else "Neutro",
                          "frecuencia": len(ids), "ids": ids, "ejemplos": ejemplos})
    total = defaultdict(int)
    for e in elementos:
        total[e["elemento"].lower()] += e["frecuencia"]
    elementos.sort(key=lambda e: (-total[e["elemento"].lower()], e["elemento"].lower(), e["valor"]))

    recomendaciones = []
    for r in datos.get("recomendaciones", []):
        ej = _ids_validos([r.get("ejemplo")], n)
        recomendaciones.append({"punto": str(r.get("punto", "")), "accion": str(r.get("accion", "")),
                                "ejemplo": ej[0] if ej else None})
    concl = {
        "resumen": str(datos.get("resumen", "")),
        "fortalezas": [str(x) for x in datos.get("fortalezas", [])],
        "ejemplos_fortalezas": _ids_validos(datos.get("ejemplos_fortalezas"), n)[:2],
        "mejoras": [str(x) for x in datos.get("mejoras", [])],
        "ejemplos_mejoras": _ids_validos(datos.get("ejemplos_mejoras"), n)[:2],
        "recomendaciones": recomendaciones,
    }
    return elementos, concl
