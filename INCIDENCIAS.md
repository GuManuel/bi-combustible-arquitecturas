# Incidencias de la ejecución final

Se conservó la ejecución final completa, sin descartar solicitudes fallidas:

- 18 casos de ingesta con totales correctos.
- 72 casos de API, 14 400 solicitudes medidas.
- 14 398 respuestas correctas y 2 errores de transporte `httpx.ReadError` (0,0139 %).
- Ambos errores: REST, proyección Kappa, consulta por placa y periodo, 30 clientes, repetición 2; solicitudes 24 y 75.
- El servidor API no registró una excepción de aplicación en su log. Esto no permite determinar la causa de los errores de transporte.
- Las cuatro pruebas funcionales pasaron, incluida la ingesta mediante el consumidor en segundo plano.

El benchmark termina con código 1 al detectar errores, después de guardar los CSV. Es un control deliberado: una ejecución con incidencias no se declara aprobada. El informe puede generarse para documentar los resultados, pero las incidencias deben revisarse antes de aprobar el despliegue.

En PostgreSQL, repite el ensayo completo siguiendo README.md y conserva los nuevos registros. No borres solo las filas con errores ni mezcles repeticiones de distintos motores. Si la incidencia reaparece, compara logs del servidor, código de error y configuración de conexiones; no se afirma que el origen esté en Kappa o en PostgreSQL.
