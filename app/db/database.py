import os
os.environ['PGCLIENTENCODING'] = 'utf8'

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# En local (Windows con mensajes en español) se fuerzan mensajes UTF-8 del servidor.
# En servicios gestionados (Neon, etc.) ese parámetro no está permitido, así que sólo se
# envía cuando la base es local.
_BASE_LOCAL = any(h in settings.DATABASE_URL for h in ("localhost", "127.0.0.1", "host=/"))
_connect_args = {"client_encoding": "utf8"}
if _BASE_LOCAL:
    _connect_args["options"] = "-c lc_messages=en_US.UTF-8"

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    # Neon suspende la base por inactividad: se verifica la conexión antes de usarla.
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()