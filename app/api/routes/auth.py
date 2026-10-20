# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.usuario import Usuario, RolUsuario
from pydantic import BaseModel
from sqlalchemy import func
from app.schemas.auth import (
    LoginRequest, TokenResponse, UsuarioCreate, UsuarioResponse, CambiarPassword
)
from app.core.security import (
    verificar_password, hashear_password,
    crear_token, get_current_user, require_admin
)
import uuid
from datetime import timedelta
from app.core.config import settings

# El router agrupa todos los endpoints de auth bajo el mismo prefijo
router = APIRouter(prefix="/auth", tags=["Auth"])


def _admins_activos(db: Session) -> int:
    return db.query(Usuario).filter(
        Usuario.rol == RolUsuario.admin, Usuario.activo.is_(True)
    ).count()


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Autentica a un usuario y devuelve un token JWT.
    Verifica email, contraseña y rol.
    """
    # Buscar el usuario por email en la base de datos
    usuario = db.query(Usuario).filter(
        func.lower(Usuario.email) == request.email.strip().lower()
    ).first()

    # Si no existe el usuario o la contraseña no coincide → 401
    if not usuario or not verificar_password(request.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )

    # Verificar que el rol solicitado coincida con el rol del usuario
    if usuario.rol.value != request.rol.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Este usuario no tiene el rol '{request.rol.value}'"
        )

    # Verificar que el usuario esté activo
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo — contactá al administrador"
        )

    # Crear el token JWT con los datos del usuario
    # Estos datos van a estar disponibles en cada request protegido
    token = crear_token(data={
        "sub": str(usuario.id),   # subject: el ID del usuario
        "email": usuario.email,
        "rol": usuario.rol.value,
        "nombre": usuario.nombre
    }, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        rol=usuario.rol.value,
        nombre=usuario.nombre
    )


@router.get("/me", response_model=UsuarioResponse)
def get_me(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Devuelve los datos del usuario autenticado.
    El front lo usa para saber quién está logueado al cargar la app.
    """
    usuario = db.query(Usuario).filter(
        Usuario.id == current_user["sub"]
    ).first()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    return usuario


@router.post("/usuarios", response_model=UsuarioResponse, status_code=201)
def crear_usuario(
    datos: UsuarioCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Crea un nuevo usuario (admin o chofer). Solo un admin puede hacerlo.
    Puede haber varios administradores.
    La contraseña debe tener al menos 8 caracteres, con mayúscula, minúscula y número.
    """
    # Verificar que no exista otro usuario con el mismo email (sin distinguir mayúsculas)
    existente = db.query(Usuario).filter(
        func.lower(Usuario.email) == datos.email
    ).first()

    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese email"
        )

    # Crear el usuario hasheando la contraseña antes de guardar
    nuevo_usuario = Usuario(
        nombre=datos.nombre,
        email=datos.email,
        password_hash=hashear_password(datos.password),
        rol=RolUsuario[datos.rol.value],
        telefono=datos.telefono
    )

    db.add(nuevo_usuario)
    db.commit()          # Confirmar la transacción en la BD
    db.refresh(nuevo_usuario)  # Recargar para obtener el ID generado

    return nuevo_usuario

@router.post("/setup", response_model=UsuarioResponse, status_code=201)
def setup_inicial(
    datos: UsuarioCreate,
    db: Session = Depends(get_db)
):
    """
    Crea el primer usuario administrador del sistema.
    Solo funciona si no existe ningun usuario en la base de datos.
    Una vez que hay al menos un usuario, este endpoint queda
    bloqueado permanentemente devolviendo 403.
    """
    # Verificar que no exista ningun usuario — si hay uno, el sistema
    # ya fue inicializado y no se puede volver a usar este endpoint
    total_usuarios = db.query(Usuario).count()
    if total_usuarios > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El sistema ya fue configurado. Este endpoint esta deshabilitado."
        )

    # El primer usuario debe ser obligatoriamente admin
    if datos.rol.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El primer usuario debe ser administrador"
        )

    # Crear el admin inicial con la contrasena hasheada
    nuevo_usuario = Usuario(
        nombre=datos.nombre,
        email=datos.email,
        password_hash=hashear_password(datos.password),
        rol=RolUsuario[datos.rol.value],
        telefono=datos.telefono,
        activo=True
    )

    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return nuevo_usuario

@router.get("/usuarios", response_model=list[UsuarioResponse])
def listar_usuarios(
    rol: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Lista todos los usuarios del sistema.
    Solo puede hacerlo un admin.
    Filtro opcional por rol: ?rol=chofer o ?rol=admin
    """
    query = db.query(Usuario)

    if rol:
        try:
            query = query.filter(Usuario.rol == RolUsuario[rol])
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rol '{rol}' no válido. Opciones: admin, chofer"
            )

    usuarios = query.order_by(Usuario.nombre).all()
    return usuarios


@router.patch("/usuarios/{usuario_id}/desactivar", response_model=UsuarioResponse)
def desactivar_usuario(
    usuario_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Desactiva un usuario (borrado lógico).
    El usuario no puede desactivarse a sí mismo y no se puede desactivar
    al último administrador activo.
    Solo puede hacerlo un admin.
    """
    # No puede desactivarse a sí mismo
    if usuario_id == current_user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No podés desactivar tu propio usuario"
        )

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario ya está inactivo"
        )

    if usuario.rol == RolUsuario.admin and _admins_activos(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede desactivar al único administrador activo"
        )

    usuario.activo = False
    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/usuarios/{usuario_id}/reactivar", response_model=UsuarioResponse)
def reactivar_usuario(
    usuario_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Reactiva un usuario desactivado. Solo admin."""
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if usuario.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario ya está activo")
    usuario.activo = True
    db.commit()
    db.refresh(usuario)
    return usuario


class CambiarRol(BaseModel):
    rol: str


@router.patch("/usuarios/{usuario_id}/rol", response_model=UsuarioResponse)
def cambiar_rol(
    usuario_id: uuid.UUID,
    datos: CambiarRol,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Cambia el rol de un usuario (promover un chofer a admin o volver un admin chofer).
    No podés cambiar tu propio rol y siempre tiene que quedar al menos un admin activo.
    """
    if datos.rol not in ("admin", "chofer"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rol no válido. Opciones: admin, chofer"
        )
    if str(usuario_id) == current_user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No podés cambiar tu propio rol"
        )
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    nuevo = RolUsuario[datos.rol]
    if usuario.rol == nuevo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El usuario ya es {datos.rol}")
    if usuario.rol == RolUsuario.admin and usuario.activo and _admins_activos(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede quitar el rol al único administrador activo"
        )
    usuario.rol = nuevo
    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/me/password", status_code=204)
def cambiar_mi_password(
    datos: CambiarPassword,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Cambia la contraseña del usuario autenticado. Pide la actual y valida la política
    (mínimo 8 caracteres, con mayúscula, minúscula y número).
    """
    usuario = db.query(Usuario).filter(Usuario.id == uuid.UUID(current_user["sub"])).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if not verificar_password(datos.password_actual, usuario.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta")
    if verificar_password(datos.password_nueva, usuario.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña nueva tiene que ser distinta de la actual")
    usuario.password_hash = hashear_password(datos.password_nueva)
    db.commit()
