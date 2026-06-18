# -*- coding: utf-8 -*-
import httpx
from app.core.config import settings

# URL base de la API de OpenRouteService
ORS_BASE_URL = "https://api.openrouteservice.org"


async def geocodificar_direccion(direccion: str) -> tuple[float, float] | None:
    """
    Convierte una direccion en texto a coordenadas (longitud, latitud).
    Usa la API de geocodificacion de OpenRouteService.
    Devuelve una tupla (longitud, latitud) o None si no encuentra la direccion.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ORS_BASE_URL}/geocode/search",
            params={
                "api_key": settings.ORS_API_KEY,
                "text": f"{direccion}, Argentina",
                "size": 1,                    # Solo queremos el resultado mas relevante
                "boundary.country": "AR",     # Limitamos a Argentina
            }
        )
        data = response.json()

        # La API devuelve una lista de features GeoJSON
        if not data.get("features"):
            return None

        # Las coordenadas vienen en formato [longitud, latitud]
        coords = data["features"][0]["geometry"]["coordinates"]
        return coords[0], coords[1]  # (longitud, latitud)


async def calcular_matriz_distancias(coordenadas: list[tuple[float, float]]) -> list[list[float]]:
    """
    Calcula una matriz de duraciones entre todos los puntos.
    Recibe una lista de coordenadas (longitud, latitud).
    Devuelve una matriz NxN con los tiempos en segundos entre cada par de puntos.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ORS_BASE_URL}/v2/matrix/driving-car",
            headers={
                "Authorization": settings.ORS_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "locations": [[lon, lat] for lon, lat in coordenadas],
                "metrics": ["duration", "distance"],  # Tiempo y distancia
                "units": "km"
            }
        )
        data = response.json()
        return data["durations"], data["distances"]


def algoritmo_nearest_neighbor(
    origen: int,
    matriz_duraciones: list[list[float]]
) -> list[int]:
    """
    Algoritmo del vecino mas cercano (Nearest Neighbor) para optimizar el orden de paradas.

    Como funciona:
    1. Arranca desde el punto de origen (deposito)
    2. Busca la parada no visitada mas cercana en tiempo
    3. La agrega al recorrido
    4. Repite hasta visitar todas las paradas

    Es un algoritmo greedy (codicioso) — no garantiza el optimo global
    pero es rapido y da buenos resultados para rutas pequenas (< 20 paradas).

    Recibe:
      - origen: indice del punto de origen en la matriz
      - matriz_duraciones: matriz NxN con tiempos entre puntos

    Devuelve:
      - Lista de indices en el orden optimo (sin incluir el origen al principio)
    """
    n = len(matriz_duraciones)
    visitados = [False] * n
    visitados[origen] = True  # El origen ya fue "visitado"
    ruta = []

    actual = origen
    while len(ruta) < n - 1:  # -1 porque el origen no cuenta como parada
        mejor_tiempo = float('inf')
        mejor_siguiente = -1

        # Buscar la parada no visitada mas cercana en tiempo
        for i in range(n):
            if not visitados[i] and matriz_duraciones[actual][i] < mejor_tiempo:
                mejor_tiempo = matriz_duraciones[actual][i]
                mejor_siguiente = i

        if mejor_siguiente == -1:
            break

        visitados[mejor_siguiente] = True
        ruta.append(mejor_siguiente)
        actual = mejor_siguiente

    return ruta


async def optimizar_ruta(
    origen_coords: tuple[float, float],
    entregas_coords: list[tuple[float, float]]
) -> tuple[list[int], float, int]:
    """
    Funcion principal que coordina el proceso de optimizacion.
    Devuelve:
      - orden_indices: lista de indices en orden optimo
      - total_km: distancia total del recorrido en km
      - tiempo_total_min: tiempo estimado total en minutos
    """
    todas_coords = [origen_coords] + entregas_coords
    duraciones, distancias = await calcular_matriz_distancias(todas_coords)
    orden_indices = algoritmo_nearest_neighbor(0, duraciones)

    # Calcular totales recorriendo el camino optimizado
    total_km = 0.0
    tiempo_total_seg = 0.0
    actual = 0  # Empezamos desde el origen (indice 0)
    for idx in orden_indices:
        total_km += distancias[actual][idx]
        tiempo_total_seg += duraciones[actual][idx]
        actual = idx

    tiempo_total_min = int(tiempo_total_seg / 60)

    return [i - 1 for i in orden_indices], round(total_km, 2), tiempo_total_min