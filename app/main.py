from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import Base, engine
from app.api.routes import auth, clientes, entregas, rutas, usuarios

# Crea todas las tablas en la base de datos al arrancar la app
# En producción esto se reemplaza por migraciones con Alembic
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="rutapp API",
    description="Backend para el sistema de optimización de rutas de entrega",
    version="1.0.0"
)

# Configuración de CORS — permite que el front (React en localhost:3000)
# pueda hacer requests al back (FastAPI en localhost:8000)
# Sin esto el navegador bloquea todas las requests por seguridad
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # URL del front en desarrollo
    allow_credentials=True,
    allow_methods=["*"],   # Permite GET, POST, PUT, PATCH, DELETE
    allow_headers=["*"],   # Permite todos los headers incluyendo Authorization
)

# Registro de routers — cada archivo de routes maneja un grupo de endpoints
app.include_router(auth.router,      prefix="/api/v1", tags=["Auth"])
app.include_router(clientes.router,  prefix="/api/v1", tags=["Clientes"])
app.include_router(entregas.router,  prefix="/api/v1", tags=["Entregas"])
app.include_router(rutas.router,     prefix="/api/v1", tags=["Rutas"])
app.include_router(usuarios.router,  prefix="/api/v1", tags=["Usuarios"])

@app.get("/")
def root():
    """Endpoint de verificación — confirma que el servidor está corriendo"""
    return {"status": "ok", "mensaje": "rutapp API corriendo"}