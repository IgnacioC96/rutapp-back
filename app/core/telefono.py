# -*- coding: utf-8 -*-
"""
Normalización de teléfonos para WhatsApp.

El usuario puede escribir el número como lo conoce (con 0, con 15, con guiones,
con espacios, con +54 9...). Se guarda siempre en formato internacional E.164,
que es lo que necesitan las APIs de WhatsApp: +54 9 <área><número> (14 caracteres).
"""
import re

MENSAJE_INVALIDO = (
    "Teléfono inválido. Ingresá código de área y número, por ejemplo 11 2345-6789"
)


def _quitar_15(nacional: str) -> str:
    """
    'Número nacional' con el 15 del celular (12 dígitos: área + 15 + abonado)
    -> 10 dígitos (área + abonado). El 15 va justo después del código de área
    (2 dígitos para AMBA '11', 3 o 4 para el resto del país).
    """
    if len(nacional) != 12:
        return nacional
    for largo_area in (2, 3, 4):
        if largo_area == 2 and not nacional.startswith("11"):
            continue
        if nacional[largo_area:largo_area + 2] == "15":
            return nacional[:largo_area] + nacional[largo_area + 2:]
    return nacional


def normalizar_telefono_ar(valor: str) -> str:
    """
    Devuelve el teléfono en formato +549XXXXXXXXXX (celular argentino) o, si
    el usuario escribió explícitamente otro país con '+', ese número en E.164.
    Lanza ValueError con un mensaje legible si no se puede interpretar.
    """
    texto = (valor or "").strip()
    if not texto:
        raise ValueError(MENSAJE_INVALIDO)

    empieza_con_mas = texto.startswith("+") or texto.startswith("00")
    digitos = re.sub(r"\D", "", texto)
    if texto.startswith("00"):
        digitos = digitos[2:]

    # Otro país indicado explícitamente: se respeta (E.164: hasta 15 dígitos)
    if empieza_con_mas and not digitos.startswith("54"):
        if 8 <= len(digitos) <= 15:
            return "+" + digitos
        raise ValueError(MENSAJE_INVALIDO)

    resto = digitos[2:] if digitos.startswith("54") else digitos
    resto = resto.lstrip("0") if resto.startswith("0") else resto

    # Prefijo de celular internacional '9' (+54 9 ...)
    if len(resto) == 11 and resto.startswith("9"):
        resto = resto[1:]
    elif len(resto) == 13 and resto.startswith("9"):
        resto = _quitar_15(resto[1:])
    else:
        resto = _quitar_15(resto)

    if len(resto) != 10:
        raise ValueError(MENSAJE_INVALIDO)

    return "+549" + resto
