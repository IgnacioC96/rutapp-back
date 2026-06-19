# rutapp — Back-End

API REST para el sistema de optimización de rutas de entrega logística.

## Stack tecnológico

- **Python 3.12** + **FastAPI** — framework web
- **PostgreSQL 16** — base de datos
- **SQLAlchemy** — ORM
- **JWT + bcrypt** — autenticación y seguridad
- **OpenRouteService API** — geocodificación y cálculo de distancias
- **Uvicorn** — servidor ASGI

## Requisitos previos

- Python 3.12+
- PostgreSQL 16
- Cuenta en [OpenRouteService](https://openrouteservice.org) (gratuita)

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/IgnacioC96/rutapp-back.git
cd rutapp-back

# 2. Crear y activar el entorno virtual
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

## Configuración

Crear un archivo `.env` en la raíz del proyecto con las siguientes variables:

DATABASE_URL=postgresql://postgres:TU_PASSWORD@localhost:5432/rutapp_db

SECRET_KEY=tu_clave_secreta

ALGORITHM=HS256

ACCESS_TOKEN_EXPIRE_MINUTES=1440

ORS_API_KEY=tu_api_key_de_openrouteservice

## Base de datos

1. Crear la base de datos en PostgreSQL:
```sql
CREATE DATABASE rutapp_db;
```

2. Las tablas se crean automáticamente al levantar el servidor.

3. Crear el primer usuario admin desde el endpoint de setup (ver abajo).

## Levantar el servidor

```bash
uvicorn app.main:app --reload
```

El servidor corre en `http://127.0.0.1:8000`

La documentación interactiva de la API está disponible en `http://127.0.0.1:8000/docs`

## Primer uso — Setup inicial

Al instalar el sistema por primera vez, crear el usuario administrador inicial:

```bash
POST http://127.0.0.1:8000/api/v1/auth/setup
Content-Type: application/json

{
  "nombre": "Admin",
  "email": "admin@rutapp.com",
  "password": "tu_password",
  "rol": "admin"
}
```

Este endpoint se desactiva automáticamente una vez creado el primer usuario.

## Endpoints principales

| Módulo | Prefijo | Descripción |
|--------|---------|-------------|
| Auth | `/api/v1/auth` | Login, setup, gestión de usuarios |
| Clientes | `/api/v1/clientes` | ABM de clientes con múltiples direcciones |
| Entregas | `/api/v1/entregas` | ABM de entregas con estados |
| Rutas | `/api/v1/rutas` | Crear, optimizar y ejecutar rutas |

## Estructura del proyecto

rutapp-back/

├── app/

│   ├── api/routes/      # Endpoints de la API

│   │   ├── auth.py      # Login, setup, usuarios

│   │   ├── clientes.py  # CRUD clientes

│   │   ├── entregas.py  # CRUD entregas

│   │   └── rutas.py     # Rutas + optimización

│   ├── core/

│   │   ├── config.py    # Variables de entorno

│   │   └── security.py  # JWT, bcrypt, roles

│   ├── db/

│   │   └── database.py  # Conexión a PostgreSQL

│   ├── models/          # Tablas de la BD (SQLAlchemy)

│   ├── schemas/         # Validación de datos (Pydantic)

│   ├── services/

│   │   └── optimizacion.py  # Algoritmo Nearest Neighbor

│   └── main.py          # App principal + CORS

├── requirements.txt

└── .env                 # No incluido en el repo

## Equipo

**Geonexusar** — Instituto Técnico Leopoldo Marechal · PP3 · 2026

- Ignacio Campaniello — Back-End
- Raúl Gilmar Rodriguez — Front-End  
- Soledad Albornoz — Testing
