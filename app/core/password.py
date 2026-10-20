# -*- coding: utf-8 -*-
"""Política de contraseñas de RutApp.

Una sola función, así la regla se cambia en un único lugar.
Se aplica al crear usuarios y al cambiar la contraseña, NO al login
(las cuentas existentes con contraseñas viejas deben poder entrar).
"""

MIN_LARGO = 8
MAX_LARGO = 72  # bcrypt ignora (o rechaza) lo que pasa de 72 bytes


def validar_fortaleza_password(password: str) -> str:
    """Devuelve la contraseña si cumple la política; si no, ValueError con un mensaje en español."""
    if len(password) < MIN_LARGO:
        raise ValueError(f"La contraseña debe tener al menos {MIN_LARGO} caracteres")
    if len(password.encode("utf-8")) > MAX_LARGO:
        raise ValueError(f"La contraseña no puede superar los {MAX_LARGO} caracteres")
    faltan = []
    if not any(c.islower() for c in password):
        faltan.append("una minúscula")
    if not any(c.isupper() for c in password):
        faltan.append("una mayúscula")
    if not any(c.isdigit() for c in password):
        faltan.append("un número")
    if faltan:
        raise ValueError("La contraseña debe tener al menos " + ", ".join(faltan[:-1]) + (" y " if len(faltan) > 1 else "") + faltan[-1])
    return password
