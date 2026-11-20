# -*- coding: utf-8 -*-
"""
Genera datos de prueba para las métricas de uso (sesiones, eventos y navegación).

Como en la etapa de desarrollo no hay usuarios reales, este script simula la actividad de un
negocio de reparto durante varios días: administradores que planifican y controlan, choferes
que recorren rutas desde el celular y clientes que miran el seguimiento público.
El comportamiento imita patrones reales: más actividad en días hábiles y a la mañana, pocos
domingos, algún formulario abandonado, entregas no realizadas y operaciones lentas (como el
cálculo de rutas, que depende de un servicio externo).

Todo lo que genera queda marcado con simulado = true, así que se puede borrar sin tocar datos reales.

Uso (desde la carpeta rutapp-back, con el entorno virtual activo y el .env configurado):
    python scripts/simular_metricas.py                 # 30 días hacia atrás, semilla fija
    python scripts/simular_metricas.py --dias 60 --semilla 7
    python scripts/simular_metricas.py --limpiar       # borra los datos simulados (y sus usuarios)
"""
import argparse
import math
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hashear_password  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models import usuario, cliente, entrega, ruta, vehiculo, punto_salida  # noqa: E402,F401  (registra todas las tablas)
from app.models.metricas import EventoUsuario, Navegacion, SesionUsuario  # noqa: E402
from app.models.usuario import RolUsuario, Usuario  # noqa: E402

DOMINIO = "@sim.rutapp.test"
ARG = timezone(timedelta(hours=-3))   # Argentina no usa horario de verano


def elegir(rng, opciones):
    """opciones: lista de (valor, peso)."""
    total = sum(p for _, p in opciones)
    x = rng.uniform(0, total)
    acum = 0
    for v, p in opciones:
        acum += p
        if x <= acum:
            return v
    return opciones[-1][0]


def dispositivo_admin(rng):
    disp = elegir(rng, [("escritorio", 85), ("movil", 11), ("tablet", 4)])
    if disp == "escritorio":
        nav, so = elegir(rng, [(("Chrome", "Windows"), 50), (("Edge", "Windows"), 20), (("Firefox", "Windows"), 8),
                                (("Safari", "macOS"), 9), (("Chrome", "macOS"), 7), (("Chrome", "Linux"), 6)])
    elif disp == "movil":
        nav, so = elegir(rng, [(("Chrome", "Android"), 70), (("Safari", "iOS"), 30)])
    else:
        nav, so = elegir(rng, [(("Chrome", "Android"), 40), (("Safari", "iOS"), 60)])
    return disp, nav, so


def dispositivo_chofer(rng):
    nav, so = elegir(rng, [(("Chrome", "Android"), 72), (("Safari", "iOS"), 20), (("Samsung Internet", "Android"), 8)])
    return elegir(rng, [("movil", 96), ("tablet", 4)]), nav, so


class Simulador:
    def __init__(self, db, rng, ahora):
        self.db, self.rng, self.ahora = db, rng, ahora
        self.sesiones, self.eventos, self.navegaciones = [], [], []

    # ── primitivas ───────────────────────────────────────────────────────────
    def ms(self, base, dispersion=0.35):
        return max(20, int(self.rng.lognormvariate(math.log(base), dispersion)))

    def sesion(self, usuario, rol, inicio, perfil):
        disp, nav, so = perfil
        s = SesionUsuario(id=uuid.uuid4(), usuario_id=usuario.id, rol=rol, fecha_inicio=inicio, ultima_actividad=inicio,
                          dispositivo=disp, navegador=nav, sistema_operativo=so, simulado=True)
        self.sesiones.append(s)
        self.evento(s, inicio, "LOGIN", "sesion", desc=f"Ingreso desde {disp} ({nav})")
        return s

    def evento(self, s, cuando, nombre, tipo, entidad=None, desc=None, dur=None, status=200, usuario=True):
        if cuando > self.ahora:
            return False
        self.eventos.append(EventoUsuario(
            id=uuid.uuid4(), usuario_id=s.usuario_id if (s is not None and usuario) else None,
            sesion_id=s.id if s is not None else None, rol=s.rol if s is not None else None, fecha=cuando,
            evento=nombre, tipo=tipo, entidad=entidad, descripcion=desc or nombre.replace("_", " ").capitalize(),
            http_status=status if tipo != "sesion" else None, duracion_ms=dur, simulado=True))
        if s is not None and cuando > s.ultima_actividad:
            s.ultima_actividad = cuando
        return True

    def ir(self, s, cuando, url, anterior):
        if cuando > self.ahora:
            return False
        self.navegaciones.append(Navegacion(id=uuid.uuid4(), usuario_id=s.usuario_id, sesion_id=s.id, fecha=cuando, url=url,
                                            url_anterior=anterior, dispositivo=s.dispositivo, navegador=s.navegador, simulado=True))
        if cuando > s.ultima_actividad:
            s.ultima_actividad = cuando
        return True

    def cerrar(self, s, cuando, prob_logout):
        if cuando > self.ahora:
            return
        if self.rng.random() < prob_logout:
            s.fecha_fin = max(cuando, s.ultima_actividad)
            self.evento(s, s.fecha_fin, "LOGOUT", "sesion", desc="Cierre de sesión")

    # ── una sesión de administrador ──────────────────────────────────────────
    def sesion_admin(self, usuario, inicio, creciente):
        r = self.rng
        s = self.sesion(usuario, "admin", inicio, dispositivo_admin(r))
        t = inicio + timedelta(seconds=r.randint(2, 6))
        actual = None

        def paso(url, pausa=(6, 70)):
            nonlocal t, actual
            t += timedelta(seconds=r.randint(*pausa))
            if self.ir(s, t, url, actual):
                actual = url

        paso("/admin", (1, 4))
        flujo = elegir(r, [("control", 56), ("gestion", 28), ("rapida", 16)])
        if flujo == "control":
            paso("/admin/rutas")
            for _ in range(r.choice([1, 2, 2, 3])):
                paso("/admin/rutas/:id", (10, 80))
            if r.random() < 0.5:
                paso("/admin/entregas")
                if r.random() < 0.5:
                    t += timedelta(seconds=r.randint(5, 40)); self.evento(s, t, "BUSCAR", "busqueda", "entrega", "Búsqueda en entregas", self.ms(110))
            if r.random() < 0.25:
                paso("/admin/clientes")
            if r.random() < 0.12:
                paso("/admin/entregas")
                t += timedelta(seconds=r.randint(10, 50)); self.evento(s, t, "CANCELAR_ENTREGA", "eliminar", "entrega", dur=self.ms(140))
        elif flujo == "gestion":
            destino = elegir(r, [("/admin/usuarios", 45), ("/admin/flota", 17), ("/admin/plantillas", 10), ("/admin/clientes", 28)])
            paso(destino)
            if destino == "/admin/usuarios" and r.random() < 0.3:
                t += timedelta(seconds=r.randint(60, 180)); self.evento(s, t, "CREAR_USUARIO", "crear", "usuario", dur=self.ms(380), status=201)
            if destino == "/admin/flota" and r.random() < 0.3:
                t += timedelta(seconds=r.randint(40, 120)); self.evento(s, t, "CREAR_VEHICULO", "crear", "vehiculo", dur=self.ms(130), status=201)
            if destino == "/admin/clientes" and r.random() < 0.3:
                t += timedelta(seconds=r.randint(30, 90)); self.evento(s, t, "EDITAR_CLIENTE", "editar", "cliente", dur=self.ms(140))
            if r.random() < 0.5:
                paso("/admin")
        else:  # consulta rápida
            paso("/admin/rutas")
        t += timedelta(seconds=r.randint(5, 25))
        self.cerrar(s, t, 0.72)


    # ── sesión de planificación: carga las entregas de cada ruta, arma la ruta y la asigna ──
    def sesion_planificacion(self, usuario, inicio, rutas):
        """rutas: lista con la cantidad de paradas de cada ruta que se arma en esta sesión."""
        r = self.rng
        s = self.sesion(usuario, "admin", inicio, dispositivo_admin(r))
        t = inicio + timedelta(seconds=r.randint(2, 6))
        actual = None

        def paso(url, pausa=(6, 40)):
            nonlocal t, actual
            t += timedelta(seconds=r.randint(*pausa))
            if self.ir(s, t, url, actual):
                actual = url

        paso("/admin", (1, 4))
        for paradas in rutas:
            for _ in range(paradas):
                if r.random() < 0.13:                       # cliente nuevo: se da de alta antes de la entrega
                    paso("/admin/clientes/nuevo")
                    if r.random() < 0.78:
                        t += timedelta(seconds=r.randint(40, 140)); self.evento(s, t, "CREAR_CLIENTE", "crear", "cliente", dur=self.ms(140), status=201)
                    else:
                        t += timedelta(seconds=r.randint(10, 40))
                if r.random() < 0.15:                       # formulario abandonado y vuelto a abrir
                    paso("/admin/entregas/nueva"); t += timedelta(seconds=r.randint(8, 30))
                paso("/admin/entregas/nueva")
                t += timedelta(seconds=r.randint(45, 150)); self.evento(s, t, "CREAR_ENTREGA", "crear", "entrega", dur=self.ms(160), status=201)
            if r.random() < 0.34:                           # un tercio abandona el armado de la ruta y vuelve a intentar
                paso("/admin/rutas/nueva"); t += timedelta(seconds=r.randint(20, 90))
            paso("/admin/rutas/nueva")
            lento = 2.6 if r.random() < 0.12 else 1.0       # a veces el servicio de mapas tarda más
            t += timedelta(seconds=r.randint(60, 200)); self.evento(s, t, "CREAR_RUTA", "crear", "ruta", dur=self.ms(2300 * lento, 0.3), status=201)
            paso("/admin/rutas/:id", (3, 12))
            t += timedelta(seconds=r.randint(8, 40)); self.evento(s, t, "ASIGNAR_RUTA", "operacion", "ruta", dur=self.ms(210))
            if r.random() < 0.12:
                t += timedelta(seconds=r.randint(10, 60)); self.evento(s, t, "REORDENAR_PARADAS", "editar", "ruta", dur=self.ms(260))
        t += timedelta(seconds=r.randint(5, 25))
        self.cerrar(s, t, 0.7)

    # ── una ruta completa del chofer + las visitas de los clientes ──────────
    def jornada_chofer(self, chofer, inicio, paradas):
        r = self.rng
        s = self.sesion(chofer, "chofer", inicio, dispositivo_chofer(r))
        t = inicio + timedelta(seconds=r.randint(2, 6))
        self.ir(s, t, "/chofer", None)
        t += timedelta(seconds=r.randint(20, 120))
        self.evento(s, t, "INICIAR_RUTA", "operacion", "ruta", dur=self.ms(180))
        inicio_visitas = t
        no_ent = 0
        for i in range(paradas):
            t += timedelta(minutes=r.uniform(7, 24))
            if r.random() < 0.12:
                self.evento(s, t, "ENTREGA_NO_REALIZADA", "operacion", "entrega", dur=self.ms(150)); no_ent += 1
            else:
                self.evento(s, t, "CONFIRMAR_ENTREGA", "operacion", "entrega", dur=self.ms(190))
            if r.random() < 0.15:
                self.evento(s, t + timedelta(seconds=20), "NOTA_PARADA", "editar", "parada", dur=self.ms(110))
        t += timedelta(seconds=3)
        self.evento(s, t, "RUTA_CERRADA", "operacion", "ruta",
                    desc="Ruta cerrada automáticamente (" + ("finalizada" if no_ent else "completada") + ")")
        self.cerrar(s, t + timedelta(minutes=r.randint(1, 12)), 0.4)
        # clientes que miran el enlace de seguimiento mientras dura el reparto (sin usuario ni sesión)
        for _ in range(int(paradas * r.uniform(1.0, 2.2))):
            cuando = inicio_visitas + (t - inicio_visitas) * r.random()
            if cuando > self.ahora:
                continue
            disp = elegir(r, [("movil", 88), ("escritorio", 12)])
            nav = elegir(r, [("Chrome", 62), ("Safari", 26), ("Samsung Internet", 7), ("Firefox", 3), ("Edge", 2)])
            self.navegaciones.append(Navegacion(id=uuid.uuid4(), usuario_id=None, fecha=cuando, url="/seguimiento/:codigo",
                                                dispositivo=disp, navegador=nav, simulado=True))

    def ingresos_fallidos(self, dia, factor):
        r = self.rng
        n = r.choice([0, 0, 0, 1]) if factor > 0.2 else 0
        if dia.day % 11 == 0:   # un día con varios intentos seguidos (olvido de contraseña)
            n = r.randint(4, 7)
        for _ in range(n):
            cuando = dia.replace(hour=r.choice([7, 8, 9, 13, 18]), minute=r.randint(0, 59), second=r.randint(0, 59))
            self.evento(None, cuando, "LOGIN_FALLIDO", "sesion", desc="Intento de ingreso rechazado (HTTP 401)", status=401, usuario=False)


def usuarios_simulados(db):
    existentes = db.query(Usuario).filter(Usuario.email.like(f"%{DOMINIO}")).all()
    if existentes:
        return [u for u in existentes if u.rol == RolUsuario.admin], [u for u in existentes if u.rol == RolUsuario.chofer]
    nuevos = []
    for nombre, rol in [("Admin Simulado 1", RolUsuario.admin), ("Admin Simulado 2", RolUsuario.admin),
                        ("Chofer Simulado 1", RolUsuario.chofer), ("Chofer Simulado 2", RolUsuario.chofer),
                        ("Chofer Simulado 3", RolUsuario.chofer), ("Chofer Simulado 4", RolUsuario.chofer)]:
        slug = nombre.lower().replace(" ", ".")
        nuevos.append(Usuario(nombre=nombre, email=slug + DOMINIO, rol=rol, activo=True,
                              password_hash=hashear_password(uuid.uuid4().hex + "Aa1")))
    db.add_all(nuevos)
    db.commit()
    return [u for u in nuevos if u.rol == RolUsuario.admin], [u for u in nuevos if u.rol == RolUsuario.chofer]


def limpiar(db):
    n = {}
    for modelo in (EventoUsuario, Navegacion, SesionUsuario):
        n[modelo.__tablename__] = db.query(modelo).filter(modelo.simulado.is_(True)).delete(synchronize_session=False)
    n["usuarios"] = db.query(Usuario).filter(Usuario.email.like(f"%{DOMINIO}")).delete(synchronize_session=False)
    db.commit()
    return n


def main():
    ap = argparse.ArgumentParser(description="Genera datos de prueba para las métricas de uso de RutApp")
    ap.add_argument("--dias", type=int, default=30, help="cuántos días hacia atrás simular (por defecto 30)")
    ap.add_argument("--semilla", type=int, default=2026, help="semilla del generador: misma semilla, mismos datos")
    ap.add_argument("--limpiar", action="store_true", help="borra los datos simulados y termina")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.limpiar:
            print("Borrado:", limpiar(db))
            return
        limpiar(db)                       # re-ejecutar no duplica datos
        rng = random.Random(args.semilla)
        ahora = datetime.now(ARG)
        admins, choferes = usuarios_simulados(db)
        sim = Simulador(db, rng, ahora)
        for k in range(args.dias - 1, -1, -1):
            dia = (ahora - timedelta(days=k)).replace(hour=0, minute=0, second=0, microsecond=0)
            factor = {5: 0.35, 6: 0.08}.get(dia.weekday(), 1.0)
            creciente = 1 + 0.5 * (args.dias - 1 - k) / max(1, args.dias - 1)     # el uso crece a lo largo del período
            sim.ingresos_fallidos(dia, factor)
            n_rutas = min(max(0, round(rng.gauss(2.6 * factor * creciente, 0.8))), len(choferes))
            jornadas = []                      # (chofer, inicio, paradas)
            for i in range(n_rutas):
                inicio = dia.replace(hour=rng.choice([7, 8, 8, 9, 9, 10]), minute=rng.randint(0, 59), second=rng.randint(0, 59))
                jornadas.append((choferes[i], inicio, rng.randint(3, 9)))
            # La planificación se hace a la tarde anterior o a primera hora, agrupando 1 o 2 rutas por sesión
            pendientes = list(jornadas)
            while pendientes:
                k = rng.choice([1, 2])
                grupo, pendientes = pendientes[:k], pendientes[k:]
                rutas = [g[2] for g in grupo]
                previa = rng.random() < 0.5
                if previa:
                    cuando = (dia - timedelta(days=1)).replace(hour=rng.choice([17, 17, 18, 18, 19]), minute=rng.randint(0, 59), second=rng.randint(0, 59))
                else:
                    cuando = dia.replace(hour=6, minute=rng.randint(10, 59), second=rng.randint(0, 59))
                sim.sesion_planificacion(rng.choice(admins), cuando, rutas)
            for chofer, inicio, paradas in jornadas:
                sim.jornada_chofer(chofer, inicio, paradas)
            n_admin = max(0, round(rng.gauss(2.0 * factor * creciente, 0.8)))
            for _ in range(n_admin):
                hora = elegir(rng, [(8, 20), (9, 16), (10, 10), (12, 6), (13, 6), (16, 9), (17, 12), (18, 10), (19, 4)])
                inicio = dia.replace(hour=hora, minute=rng.randint(0, 59), second=rng.randint(0, 59))
                sim.sesion_admin(rng.choice(admins), inicio, creciente)
        db.add_all(sim.sesiones)
        db.flush()
        db.add_all(sim.eventos)
        db.add_all(sim.navegaciones)
        db.commit()
        print(f"Simulación lista ({args.dias} días, semilla {args.semilla}):")
        print(f"  sesiones_usuario : {len(sim.sesiones)}")
        print(f"  eventos_usuario  : {len(sim.eventos)}")
        print(f"  navegacion       : {len(sim.navegaciones)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
