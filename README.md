# Comparación de arquitecturas para registros de combustible

Actividad 1 de Business Intelligence. Prototipo educativo reproducible de dos patrones de ingesta (Lambda y Kappa) y dos estilos de API (REST y GraphQL). Datos ficticios; no contiene información operativa de una empresa.

**Estado de esta entrega:** código y pruebas funcionales ejecutados con SQLite; benchmark local real incluido. La última ejecución registró 2 errores de lectura HTTP de 14 400 intentos (0,014 %); los otros 14 398 devolvieron el contenido esperado. Consulta docs/INCIDENCIAS.md. PostgreSQL y Docker están preparados, pero no se pudieron ejecutar en el entorno de elaboración. Las cifras incluidas NO son resultados de PostgreSQL. La URL de GitHub todavía debe generarse en la cuenta del estudiante. No entregar el informe preliminar como si demostrara el despliegue PostgreSQL.

## Correspondencia con la consigna

| Lo solicitado | Implementación o evidencia | Estado |
|---|---|---|
| Dos arquitecturas de ingesta | Lambda con batch + speed + serving; Kappa con proyección incremental y replay | Ejecutadas localmente |
| Dos arquitecturas de API | REST y GraphQL con el mismo servicio de consulta SQL | Ejecutadas por HTTP |
| Servidor DB + API | PostgreSQL en `db` y FastAPI en `api`, con Docker Compose | Preparado; validar en tu PC |
| Plataforma de ingesta | `POST /events`, log persistente y consumidor de ambas rutas | Código y controles incluidos |
| Benchmark | `benchmark.py`, CSV de ejecuciones y solicitudes, metadatos y logs | SQLite medido; PostgreSQL pendiente |
| Repositorio GitHub URL | Este directorio se puede subir como repositorio | Publicación pendiente |
| Informe de 2 páginas | `docs/Informe_Benchmark_Preliminar.docx` y PDF | Preliminar con resultados medidos |
| Bibliografía Scopus y ScienceDirect | `docs/REFERENCIAS.md`, referencias en informe | Identificadas y verificadas |

La consigna usa “Lambda o Kappa”, pero exige dos arquitecturas de ingesta en el entregable. Se implementan ambas para cubrir ese requisito. REST y GraphQL se tratan como estilos de API; no se comparan directamente con Lambda/Kappa porque resuelven capas diferentes.

## 1 Ejecutar con PostgreSQL en Windows

Instala Docker Desktop desde https://docs.docker.com/desktop/setup/install/windows-install/ y abre Docker Desktop. Extrae el ZIP. Entra a la carpeta que contiene `compose.yaml`, haz clic en la barra de ruta del Explorador, escribe `powershell` y pulsa Enter.

Ejecuta, uno por uno:

```powershell
docker compose version
docker compose build
docker compose up -d db
docker compose run --rm lab python -m unittest discover -s tests -v
docker compose run --rm lab python benchmark.py
```

El test borra SOLO las tablas del laboratorio; el benchmark también. Usa exclusivamente la base `bi_lab` de este proyecto. Mantén `api` detenida durante ambos. Si la habías abierto, ejecuta primero `docker compose stop api`. No ejecutes dos benchmarks a la vez.

Éxito esperado: cuatro pruebas `OK` y al final `BENCHMARK OK`. Si aparecen errores, el benchmark guarda la evidencia y termina con código 1; revisa requests.csv antes de aprobar la ejecución. Esto ocurrió en el último ensayo SQLite adjunto (2 errores de transporte). En `results/environment.json` debe figurar `"database": "postgresql"`. Los CSV nuevos reemplazan los resultados SQLite. Los resultados originales también quedan preservados en `results_sqlite_reference/`.

Después levanta la demostración:

```powershell
docker compose up -d api
```

Abre http://localhost:8000, luego http://localhost:8000/health. Debe indicar `postgresql`. La consola interactiva está en http://localhost:8000/docs. El benchmark deja 100 000 registros y ambas proyecciones disponibles.

Si algo falla:

```powershell
docker compose ps
docker compose logs db api
```

Si el puerto 8000 está ocupado, detén el servicio que lo usa o cambia solo el puerto izquierdo en `compose.yaml` a `127.0.0.1:8001:8000`, y abre localhost:8001.

Detener conservando datos: `docker compose down`. Reiniciar: `docker compose up -d api`. No uses `down -v` salvo que quieras borrar el volumen del laboratorio.

## 2 Demostrar ingesta y consultas

Abre la consola `/docs`. En `POST /events` pulsa **Try it out** y pega el contenido de `data/ejemplo_eventos.json`. Pulsa **Execute**. La respuesta indica recibidos e insertados; es 202 porque los consumidores procesan después. Si envías el mismo ID de nuevo, se conserva el primer registro y no se vuelve a sumar. Para corregir registros este prototipo requeriría diseñar eventos compensatorios; no modifica el pasado.

En `GET /rest/summary`, prueba `mode=lambda` y `mode=kappa`, con `plate=TST-999`. Cuando termine el consumidor, ambas respuestas deben mostrar 2 registros, `gallonsMilli=30000` y `costCents=54000` (30 galones, S/ 540).

En `POST /graphql` usa este cuerpo:

```json
{"query":"{ summary(mode: kappa, plate: \"TST-999\") { plate records gallonsMilli costCents } }"}
```

Repite cambiando `kappa` por `lambda`. Después pide solo `{ plate costCents }` para demostrar selección de campos. Esa selección parcial es demostrativa; el benchmark principal exige campos equivalentes para una comparación justa.

Filtros disponibles: placa, inicio y fin (fechas ISO `AAAA-MM-DD`, inclusive). En GraphQL son `plate`, `start`, `end`. No se calcula consumo por km: el kilometraje se conserva como dato, pero comparar odómetros de cargas aisladas sin reglas de llenado no justificaría ese indicador.

## 3 Leer los resultados

- `results/ingestion.csv`: 18 ejecuciones (3 tamaños × 2 patrones × 3 repeticiones).
- `results/api.csv`: 72 ejecuciones (2 API × 2 proyecciones × 2 consultas × 3 concurrencias × 3 repeticiones).
- `results/requests.csv`: 14 400 solicitudes medidas; los calentamientos no se incluyen.
- `results/environment.json`: fecha UTC, motor, versiones, CPU/RAM visibles y parámetros.
- `results/run.log`: registro de la ejecución original; para guardar otra ejecución en PowerShell usa `docker compose run --rm lab python benchmark.py 2>&1 | Tee-Object results/run_postgresql.log`.
- `results/api_server.log`: arranque y cierre del servidor HTTP del benchmark.

Tiempo de ingesta: desde la primera escritura del log hasta terminar la proyección del último bloque. Incluye la reconstrucción periódica de Lambda. No incluye generar datos ni validar los totales. El tiempo de disponibilidad p95 corresponde a bloques de 1000 eventos, no a eventos individuales ni a latencia de red de POST /events. La prueba de ingesta llama al motor directamente para aislar el procesamiento.

El benchmark de API sí utiliza HTTP real por loopback. Mide consultas de resumen de toda la flota y de una placa en un periodo. Usa 100 000 registros, 1 proceso servidor, 1/10/30 clientes simultáneos, 200 solicitudes por caso y 10 calentamientos antes de cada caso. Orden aleatorio con semilla fija. La latencia se mide hasta recibir la respuesta; después se valida cada resultado contra un cálculo Python independiente. Throughput exitoso = solicitudes correctas / duración total; el ciclo del generador incluye la validación. p95 usa rango más cercano, no promedios de latencias. Las latencias registran todos los intentos, incluidos los fallidos; requests.csv permite separarlos. No se reintentan silenciosamente las solicitudes fallidas.

CPU: segundos de CPU del proceso de aplicación y porcentaje equivalente de un núcleo. En los casos de API, las métricas de recursos incluyen los 10 calentamientos; latencias y throughput los excluyen. Memoria: máximo RSS histórico del proceso, NO máximo independiente por caso. En PostgreSQL estas métricas excluyen el servidor de BD; en SQLite incluyen el motor embebido. No compares recursos entre motores como si tuvieran el mismo alcance. Este ensayo es corto, en una sola máquina, con cachés calientes; no demuestra escalabilidad distribuida ni tolerancia a fallos.

## 4 Actualizar el informe tras ejecutar PostgreSQL

`make_report.py` lee los CSV actuales y genera un DOCX de dos páginas. El informe cambia de “preliminar SQLite” a “PostgreSQL” según los metadatos. Para regenerarlo sin instalar Python en Windows:

```powershell
docker compose run --rm -v "${PWD}/docs:/lab/docs" lab sh -c "pip install python-docx==1.2.0 && python make_report.py"
```

Abre el Word generado, verifica que sean dos páginas, añade la URL real del repositorio en el párrafo indicado y exporta a PDF desde Word. No reutilices el PDF preliminar después de cambiar los resultados.

## 5 Subir a GitHub

Crea en https://github.com/new un repositorio llamado `bi-combustible-arquitecturas`. Usa datos ficticios como los incluidos. Sube el contenido de ESTA carpeta, conservando los subdirectorios. No subas `data/lab.db`, `.venv`, cachés ni contraseñas reales. El usuario/contraseña de Compose son únicamente credenciales de esta base de demostración, sin publicación del puerto de BD.

Si tienes Git instalado, dentro de esta carpeta y después de crear un repositorio vacío:

```powershell
git init
git add .
git commit -m "Laboratorio BI Lambda Kappa REST GraphQL"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/bi-combustible-arquitecturas.git
git push -u origin main
```

Sustituye `TU_USUARIO` por tu usuario real. Autentícate mediante GitHub; no incluyas tokens en archivos. Copia la URL real al informe y al aula virtual. Comprueba que el docente pueda acceder; si el repositorio es privado, dale acceso según las indicaciones del curso.

## Ejecución local alternativa con SQLite

Requiere Python 3.12 y acceso a internet para instalar dependencias. Se usa para aprender y reproducir los resultados preliminares; no acredita un servidor PostgreSQL.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python benchmark.py
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Usa siempre un solo proceso API porque también contiene al consumidor. El prototipo no implementa autenticación ni cuotas de GraphQL y está limitado a localhost: no publicarlo como servicio de producción.

## Archivos principales

`core.py`: log, checkpoints, Lambda, Kappa, reconstrucción y consulta común.
`app.py`: ingreso HTTP, consumidor, REST y motor GraphQL real.
`benchmark.py`: experimentos, comprobación de respuestas y exportación de evidencia.
`tests/test_correctness.py`: pruebas de duplicados, datos tardíos, cambio batch/speed, replay y paridad API.
`make_report.py`: informe a partir de CSV.
`docs/GUIA_PASO_A_PASO.md`: explicación para exposición.
`docs/ARQUITECTURA.md`: decisiones y límites.
`docs/REFERENCIAS.md`: bibliografía y trazabilidad.

## Criterio de entrega final

Antes de entregar: pruebas PostgreSQL OK; benchmark PostgreSQL sin errores; informe actualizado de dos páginas; URL real de GitHub; acceso del docente comprobado. Esos pasos no están sustituidos por los resultados SQLite incluidos.
