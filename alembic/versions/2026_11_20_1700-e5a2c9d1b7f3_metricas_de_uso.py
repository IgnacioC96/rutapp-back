"""metricas de uso: sesiones, eventos y navegacion

Revision ID: e5a2c9d1b7f3
Revises: c4d8f1a7b3e9
Create Date: 2026-11-20 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a2c9d1b7f3'
down_revision: Union[str, Sequence[str], None] = 'c4d8f1a7b3e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sesiones_usuario',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=True),
    sa.Column('rol', sa.String(length=10), nullable=True),
    sa.Column('fecha_inicio', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('fecha_fin', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ultima_actividad', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('dispositivo', sa.String(length=15), nullable=True),
    sa.Column('navegador', sa.String(length=30), nullable=True),
    sa.Column('sistema_operativo', sa.String(length=30), nullable=True),
    sa.Column('simulado', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sesiones_usuario_usuario_id'), 'sesiones_usuario', ['usuario_id'], unique=False)
    op.create_index(op.f('ix_sesiones_usuario_fecha_inicio'), 'sesiones_usuario', ['fecha_inicio'], unique=False)

    op.create_table('eventos_usuario',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=True),
    sa.Column('sesion_id', sa.UUID(), nullable=True),
    sa.Column('rol', sa.String(length=10), nullable=True),
    sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('evento', sa.String(length=50), nullable=False),
    sa.Column('tipo', sa.String(length=15), nullable=False),
    sa.Column('entidad', sa.String(length=30), nullable=True),
    sa.Column('entidad_id', sa.String(length=40), nullable=True),
    sa.Column('descripcion', sa.String(length=500), nullable=True),
    sa.Column('http_status', sa.SmallInteger(), nullable=True),
    sa.Column('duracion_ms', sa.Integer(), nullable=True),
    sa.Column('simulado', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['sesion_id'], ['sesiones_usuario.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_eventos_usuario_usuario_id'), 'eventos_usuario', ['usuario_id'], unique=False)
    op.create_index(op.f('ix_eventos_usuario_fecha'), 'eventos_usuario', ['fecha'], unique=False)
    op.create_index(op.f('ix_eventos_usuario_evento'), 'eventos_usuario', ['evento'], unique=False)

    op.create_table('navegacion',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=True),
    sa.Column('sesion_id', sa.UUID(), nullable=True),
    sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('url', sa.String(length=300), nullable=False),
    sa.Column('url_anterior', sa.String(length=300), nullable=True),
    sa.Column('dispositivo', sa.String(length=15), nullable=True),
    sa.Column('navegador', sa.String(length=30), nullable=True),
    sa.Column('simulado', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['sesion_id'], ['sesiones_usuario.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_navegacion_usuario_id'), 'navegacion', ['usuario_id'], unique=False)
    op.create_index(op.f('ix_navegacion_fecha'), 'navegacion', ['fecha'], unique=False)
    op.create_index(op.f('ix_navegacion_url'), 'navegacion', ['url'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('navegacion')
    op.drop_table('eventos_usuario')
    op.drop_table('sesiones_usuario')
