"""vincular entregas con su ruta (backfill de entregas.ruta_id)

Hasta ahora la columna entregas.ruta_id nunca se completaba al crear una ruta, por lo que un chofer
no veía sus propias entregas (el filtro de visibilidad se apoya en esa columna). Esta migración
NO cambia el esquema: completa ruta_id con la ruta más reciente de cada entrega que está
en curso o completada, y deja en NULL las pendientes/canceladas.

Revision ID: b7c1e9a4d2f0
Revises: 1d204456c6f4
Create Date: 2026-10-27 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7c1e9a4d2f0'
down_revision: Union[str, Sequence[str], None] = '1d204456c6f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Completa entregas.ruta_id a partir de las paradas existentes."""
    op.execute("""
        UPDATE entregas e
        SET ruta_id = ultima.ruta_id
        FROM (
            SELECT DISTINCT ON (p.entrega_id) p.entrega_id, p.ruta_id
            FROM paradas_ruta p
            JOIN rutas r ON r.id = p.ruta_id
            WHERE p.entrega_id IS NOT NULL
            ORDER BY p.entrega_id, r.creada_en DESC
        ) ultima
        WHERE e.id = ultima.entrega_id
          AND e.ruta_id IS NULL
          AND e.estado IN ('en_curso', 'completada')
    """)


def downgrade() -> None:
    """Los datos completados son correctos aunque se baje de versión: no se revierten."""
    pass
