"""notas del chofer por parada y paradas omitidas ("no se pudo entregar")

Agrega a paradas_ruta:
- nota_chofer / nota_chofer_en: nota libre del chofer sobre la parada.
- omitida / motivo_omision / omitida_en: el chofer avisó que no pudo entregar y siguió la ruta.

Revision ID: c4d8f1a7b3e9
Revises: b7c1e9a4d2f0
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8f1a7b3e9'
down_revision: Union[str, Sequence[str], None] = 'b7c1e9a4d2f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('paradas_ruta', sa.Column('nota_chofer', sa.Text(), nullable=True))
    op.add_column('paradas_ruta', sa.Column('nota_chofer_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('paradas_ruta', sa.Column('omitida', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('paradas_ruta', sa.Column('motivo_omision', sa.String(length=30), nullable=True))
    op.add_column('paradas_ruta', sa.Column('omitida_en', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('paradas_ruta', 'omitida_en')
    op.drop_column('paradas_ruta', 'motivo_omision')
    op.drop_column('paradas_ruta', 'omitida')
    op.drop_column('paradas_ruta', 'nota_chofer_en')
    op.drop_column('paradas_ruta', 'nota_chofer')
