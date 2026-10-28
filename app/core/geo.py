# -*- coding: utf-8 -*-
"""Utilidades geográficas simples."""
import math

RADIO_TIERRA_M = 6_371_000


def distancia_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos puntos (fórmula de haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(a))


def coordenadas_validas(latitud, longitud) -> None:
    """
    Valida un par de coordenadas que llega desde la API. Lanza ValueError si:
    - falta una de las dos (tienen que venir juntas),
    - alguna está fuera de rango (latitud ±90, longitud ±180),
    - es el punto (0, 0): es el valor "vacío" típico de un GPS o un mapa que no cargó,
      no una ubicación real.
    Si no viene ninguna de las dos, no hace nada (las coordenadas son opcionales).
    """
    if latitud is None and longitud is None:
        return
    if latitud is None or longitud is None:
        raise ValueError("Mandá latitud y longitud juntas, o ninguna de las dos")
    if not (-90 <= latitud <= 90) or not (-180 <= longitud <= 180):
        raise ValueError("Las coordenadas están fuera de rango (latitud ±90, longitud ±180)")
    if abs(latitud) < 1e-6 and abs(longitud) < 1e-6:
        raise ValueError("Las coordenadas (0, 0) no son una ubicación válida")
