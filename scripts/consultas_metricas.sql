-- Consultas de análisis de métricas de uso de RutApp (PostgreSQL).
-- Ejecutar con:  psql -h localhost -U <usuario> -d rutapp_db -f scripts/consultas_metricas.sql
-- Todas miran los últimos 30 días. Para probarlas con datos de prueba: python scripts/simular_metricas.py

-- 1. Páginas más visitadas
-- Ranking de URLs (normalizadas: los identificadores se reemplazan por :id). Responde qué pantallas se usan más.
SELECT url, COUNT(*) AS visitas
FROM navegacion
WHERE fecha >= now() - interval '30 days'
GROUP BY url
ORDER BY visitas DESC
LIMIT 10;

-- 2. Tiempo promedio de sesión
-- Duración promedio y mediana en minutos. Si la sesión no se cerró con “Salir”, termina en su última actividad.
SELECT ROUND(AVG(EXTRACT(EPOCH FROM (COALESCE(fecha_fin, ultima_actividad) - fecha_inicio))) / 60) AS promedio_min,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (
              ORDER BY EXTRACT(EPOCH FROM (COALESCE(fecha_fin, ultima_actividad) - fecha_inicio))) / 60)::numeric) AS mediana_min
FROM sesiones_usuario
WHERE fecha_inicio >= now() - interval '30 days';

-- 3. Sesiones y duración por rol
-- Distingue el uso de escritorio del administrador del uso en ruta del chofer.
SELECT rol, COUNT(*) AS sesiones, COUNT(DISTINCT usuario_id) AS usuarios,
       ROUND(AVG(EXTRACT(EPOCH FROM (COALESCE(fecha_fin, ultima_actividad) - fecha_inicio))) / 60) AS duracion_prom_min
FROM sesiones_usuario
WHERE fecha_inicio >= now() - interval '30 days'
GROUP BY rol
ORDER BY sesiones DESC;

-- 4. Dispositivo y navegador
-- Tipo de dispositivo y navegador usado en cada sesión (se obtiene del encabezado User-Agent).
SELECT dispositivo, navegador, COUNT(*) AS sesiones
FROM sesiones_usuario
WHERE fecha_inicio >= now() - interval '30 days'
GROUP BY dispositivo, navegador
ORDER BY sesiones DESC
LIMIT 8;

-- 5. Horario de acceso (franjas pico)
-- Visitas por hora del día en hora argentina; sirve para elegir ventanas de mantenimiento y reforzar la atención.
SELECT EXTRACT(HOUR FROM fecha AT TIME ZONE 'America/Argentina/Buenos_Aires')::int AS hora, COUNT(*) AS visitas
FROM navegacion
WHERE fecha >= now() - interval '30 days'
GROUP BY hora
ORDER BY visitas DESC
LIMIT 6;

-- 6. Logins y usuarios activos por día
-- Cantidad de ingresos y de personas distintas que usaron el sistema cada día (últimos 7 días con actividad).
SELECT (fecha_inicio AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS dia,
       COUNT(*) AS logins, COUNT(DISTINCT usuario_id) AS usuarios_activos
FROM sesiones_usuario
WHERE fecha_inicio >= now() - interval '30 days'
GROUP BY dia
ORDER BY dia DESC
LIMIT 7;

-- 7. Registros creados, modificados y eliminados
-- Actividad de datos agrupada por tipo de operación.
SELECT tipo, COUNT(*) AS operaciones
FROM eventos_usuario
WHERE tipo IN ('crear', 'editar', 'eliminar', 'operacion') AND fecha >= now() - interval '30 days'
GROUP BY tipo
ORDER BY operaciones DESC;

-- 8. Eventos más frecuentes
-- Qué acciones se realizan más (bitácora de eventos).
SELECT evento, COUNT(*) AS cantidad
FROM eventos_usuario
WHERE fecha >= now() - interval '30 days'
GROUP BY evento
ORDER BY cantidad DESC
LIMIT 8;

-- 9. Conversión de entregas
-- De las entregas cargadas, cuántas se confirmaron y cuántas no se pudieron realizar.
SELECT COUNT(*) FILTER (WHERE evento = 'CREAR_ENTREGA')         AS creadas,
       COUNT(*) FILTER (WHERE evento = 'CONFIRMAR_ENTREGA')      AS confirmadas,
       COUNT(*) FILTER (WHERE evento = 'ENTREGA_NO_REALIZADA')   AS no_realizadas,
       ROUND(100.0 * COUNT(*) FILTER (WHERE evento = 'CONFIRMAR_ENTREGA')
             / NULLIF(COUNT(*) FILTER (WHERE evento = 'CREAR_ENTREGA'), 0), 1) AS conversion_pct
FROM eventos_usuario
WHERE fecha >= now() - interval '30 days';

-- 10. Abandono de formularios
-- Compara cuántas veces se abrió cada formulario de alta contra cuántas veces se completó la acción.
SELECT f.flujo,
       (SELECT COUNT(*) FROM navegacion n WHERE n.url = f.url AND n.fecha >= now() - interval '30 days') AS inicios,
       (SELECT COUNT(*) FROM eventos_usuario e WHERE e.evento = f.evento AND e.fecha >= now() - interval '30 days') AS completados
FROM (VALUES ('Nuevo cliente', '/admin/clientes/nuevo', 'CREAR_CLIENTE'),
             ('Nueva entrega', '/admin/entregas/nueva', 'CREAR_ENTREGA'),
             ('Nueva ruta',    '/admin/rutas/nueva',    'CREAR_RUTA')) AS f(flujo, url, evento);

-- 11. Operaciones más lentas (cuellos de botella)
-- Tiempo de respuesta promedio y percentil 95 por operación. El percentil 95 muestra lo que vive el usuario en sus peores momentos.
SELECT evento, COUNT(*) AS veces,
       ROUND(AVG(duracion_ms)) AS promedio_ms,
       ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duracion_ms)) AS p95_ms
FROM eventos_usuario
WHERE duracion_ms IS NOT NULL AND fecha >= now() - interval '30 days'
GROUP BY evento
ORDER BY p95_ms DESC
LIMIT 5;

-- 12. Flujo de navegación
-- Recorridos más frecuentes de una pantalla a la siguiente. Permite detectar vueltas atrás y rutas poco naturales.
SELECT url_anterior AS desde, url AS hacia, COUNT(*) AS veces
FROM navegacion
WHERE url_anterior IS NOT NULL AND url_anterior <> url AND fecha >= now() - interval '30 days'
GROUP BY url_anterior, url
ORDER BY veces DESC
LIMIT 6;

-- 13. Funcionalidades poco utilizadas
-- Secciones del menú ordenadas de menor a mayor uso.
SELECT CASE
         WHEN url = '/admin'                    THEN 'Panel principal'
         WHEN url LIKE '/admin/clientes%'       THEN 'Clientes'
         WHEN url LIKE '/admin/entregas%'       THEN 'Entregas'
         WHEN url LIKE '/admin/usuarios%'       THEN 'Choferes'
         WHEN url LIKE '/admin/rutas%'          THEN 'Rutas'
         WHEN url LIKE '/admin/flota%'          THEN 'Flota'
         WHEN url LIKE '/admin/plantillas%'     THEN 'Plantillas'
         WHEN url LIKE '/chofer%'               THEN 'Vista del chofer'
         WHEN url LIKE '/seguimiento%'          THEN 'Seguimiento público'
         ELSE 'Otras' END AS seccion,
       COUNT(*) AS visitas
FROM navegacion
WHERE fecha >= now() - interval '30 days'
GROUP BY seccion
ORDER BY visitas ASC
LIMIT 5;

-- 14. Duración promedio de un reparto
-- Métrica de negocio: tiempo entre que el chofer inicia la ruta y la ruta se cierra, y paradas por ruta.
SELECT COUNT(*) AS rutas,
       ROUND(AVG(EXTRACT(EPOCH FROM (c.fecha - i.fecha)) / 60)) AS minutos_promedio,
       ROUND(AVG(EXTRACT(EPOCH FROM (c.fecha - i.fecha)) / 3600)::numeric, 1) AS horas_promedio
FROM eventos_usuario i
JOIN eventos_usuario c ON c.sesion_id = i.sesion_id
                      AND c.evento = 'RUTA_CERRADA' AND i.evento = 'INICIAR_RUTA'
WHERE i.fecha >= now() - interval '30 days';

-- 15. Usuarios más activos
-- Cantidad de acciones realizadas por cada usuario (sin contar ingresos y salidas).
SELECT u.nombre, e.rol, COUNT(*) AS acciones
FROM eventos_usuario e
JOIN usuarios u ON u.id = e.usuario_id
WHERE e.tipo <> 'sesion' AND e.fecha >= now() - interval '30 days'
GROUP BY u.nombre, e.rol
ORDER BY acciones DESC
LIMIT 5;
