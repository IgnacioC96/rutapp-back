# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.usuario import Usuario, RolUsuario
from app.schemas.auth import LoginRequest, TokenResponse, UsuarioCreate, UsuarioResponse
from app.core.security import (
    verificar_password, hashear_password,
    crear_token, get_current_user, require_admin
)
from datetime import timedelta
from app.core.config import settings

# El router agrupa todos los endpoints de auth bajo el mismo prefijo
router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Autentica a un usuario y devuelve un token JWT.
    Verifica email, contraseÃ±a y rol.
    """
    # Buscar el usuario por email en la base de datos
    usuario = db.query(Usuario).filter(
        Usuario.email == request.email
    ).first()

    # Si no existe el usuario o la contraseÃ±a no coincide â†’ 401
    if not usuario or not verificar_password(request.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseÃ±a incorrectos"
        )

    # Verificar que el rol solicitado coincida con el rol del usuario
    if usuario.rol.value != request.rol.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Este usuario no tiene el rol '{request.rol.value}'"
        )

    # Verificar que el usuario estÃ© activo
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo â€” contactÃ¡ al administrador"
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
    El front lo usa para saber quiÃ©n estÃ¡ logueado al cargar la app.
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
    Crea un nuevo usuario (admin o chofer).
    Solo puede hacerlo un usuario autenticado (cualquier rol).
    En producciÃ³n esto deberÃ­a requerir rol admin.
    """
    # Verificar que no exista otro usuario con el mismo email
    existente = db.query(Usuario).filter(
        Usuario.email == datos.email
    ).first()

    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese email"
        )

    # Crear el usuario hasheando la contraseÃ±a antes de guardar
    nuevo_usuario = Usuario(
        nombre=datos.nombre,
        email=datos.email,
        password_hash=hashear_password(datos.password),
        rol=RolUsuario[datos.rol.value],
        telefono=datos.telefono
    )

    db.add(nuevo_usuario)
    db.commit()          # Confirmar la transacciÃ³n en la BD
    db.refresh(nuevo_usuario)  # Recargar para obtener el ID generado

    return nuevo_usuario
