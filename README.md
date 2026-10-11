# Informe de evaluación de acciones formativas (Streamlit)

Procesa un `.zip` con los cuestionarios SEPE/FUNDAE de evaluación de la calidad
(PDF rellenables) y genera el informe **«Informe Curso – [Nombre del curso]»** en PDF con:

1. **Ficha del curso** – nombre, Nº expediente, Nº AAFF / grupo, Nº cuestionarios, modalidad.
2. **Análisis cuantitativo** – media y nivel de satisfacción por apartado (1-4; <3 No
   satisfactorio, ≥3 Satisfactorio, valores truncados sin redondear), detalle por sub-ítem,
   y % Sí/No de los ítems 8.1, 8.2 y 10.1.
3. **Análisis de comentarios** (ítem 11) – elemento, valor, frecuencia y 2 comentarios.
4. **Conclusiones y recomendaciones** – nota 0-10, resumen ejecutivo, nivel de
   satisfacción, fortalezas, áreas de mejora y recomendaciones con acción sugerida.

## Ejecutar en local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Desplegar en Streamlit Community Cloud
1. Sube esta carpeta a un repositorio de GitHub.
2. En share.streamlit.io → *New app* → elige el repo y `app.py`.
3. (Opcional) En *Settings → Secrets* pega el contenido de `.streamlit/secrets.toml.example`
   con tu API key para activar el análisis con IA.

## Archivos
| Archivo | Función |
|---|---|
| `app.py` | Interfaz Streamlit (carga del .zip, opciones laterales, descarga del PDF) |
| `procesador.py` | Lectura de los campos del formulario PDF y cálculos cuantitativos |
| `comentarios.py` | Análisis de comentarios (reglas o IA) y conclusiones |
| `informe_pdf.py` | Maquetación del informe PDF |
| `analisis.py` | Orquesta todo el proceso |

## Notas
- Los datos se leen de los **campos del formulario** PDF. Si un cuestionario está escaneado
  o "aplanado" (sin campos), se descarta y se avisa en pantalla.
- «No contesta» y respuestas en blanco se excluyen de los cálculos.
- Ítem 4: se agregan las columnas Formador y Tutor.
- Ítem 7: la barra lateral permite valorarlo automáticamente según la modalidad, forzarlo o excluirlo.
- Valoración global sobre 10 = (media global − 1) / 3 × 10.
- Para ajustar el análisis por reglas (palabras clave, acciones recomendadas), edita los
  diccionarios `ELEMENTOS`, `POSITIVOS`, `NEGATIVOS`, `SUGERENCIAS` y `ACCIONES` en `comentarios.py`.
