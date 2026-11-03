# Cómo contribuir

¡Gracias por querer mejorar el proyecto! Es Open Source (licencia [MIT](LICENSE)) y lo mantiene su autor, que revisa y aprueba cada cambio antes de fusionarlo.

## Qué tipo de contribución

| Tipo | Cómo |
|---|---|
| Corrección de errores (bugs) | Abre un PR directamente. Si el error no es obvio, describe cómo reproducirlo. |
| Mejoras del código sin cambiar el comportamiento (rendimiento, limpieza, pruebas, documentación, precisión del OCR) | Abre un PR directamente. |
| Funcionalidades nuevas o cambios de comportamiento (nuevas pantallas, cambios en el cálculo de rentabilidad o del precio objetivo, nuevas fuentes de datos, cambios en la base de datos) | **Abre primero un issue** y coméntalo con el autor. Empieza a programar cuando la idea esté acordada. |

Todos los PR se fusionan **solo con la aprobación del autor**, que puede pedir cambios o rechazar los que no encajen con el proyecto.

## Normas que no se negocian

- **Nunca automatizar el juego.** Nada de clics o teclas simuladas, lectura o escritura de memoria, modificación del cliente, captura de tráfico de red ni nada que interactúe con el proceso o el anticheat. La app solo lee imágenes de la pantalla que el usuario genera navegando a mano. Esto protege las cuentas de los usuarios frente a baneos.
- **Sin datos ni assets de terceros en el repositorio.** No subas iconos, imágenes ni datos del juego (son de NCSOFT) ni el catálogo o la caché de metabot.gg. Se generan en local con `tools/importar_metabot.py`.
- **Sin secretos.** Nunca subas un `.env`, claves de Supabase ni datos personales (bases de datos, capturas, inventarios).
- **Respeta las condiciones de metabot.gg.** Mantén la atribución y el ritmo pausado de descargas del importador.

## Pasos

1. Haz un fork y crea una rama con un nombre descriptivo (`arreglo-ocr-precios`, `mejora-cola-offline`…).
2. Prepara el entorno: `iniciar.bat` crea `.venv` e instala las dependencias (Windows, Python 3.14).
3. Haz tus cambios. La interfaz y los mensajes van en **español**, con los nombres oficiales del cliente en español.
4. Pasa las pruebas y añade las que cubran tu cambio:
   ```bash
   .\.venv\Scripts\python.exe -m pytest
   ```
5. Abre el PR contra `main` explicando qué cambia y por qué, y enlaza el issue si lo hay.

## Dudas

Abre un issue. Para cualquier cambio que no sea una corrección o una mejora pequeña, coméntalo antes en un issue.
