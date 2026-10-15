"""esquema inicial

Revision ID: 0f69f8fece01
Revises: 
Create Date: 2026-10-07 12:38:36.583283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f69f8fece01'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Esquema inicial: refleja el estado de la base creada con create_all hasta el MVP 3 + codigo_confirmacion."""
    op.create_table('clientes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('nombre', sa.String(length=150), nullable=False),
    sa.Column('telefono_whatsapp', sa.String(length=20), nullable=False),
    sa.Column('cuit', sa.String(length=15), nullable=True),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('usuarios',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=150), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('rol', sa.Enum('admin', 'chofer', name='rolusuario'), nullable=False),
    sa.Column('telefono', sa.String(length=20), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usuarios_email'), 'usuarios', ['email'], unique=True)
    op.create_table('direcciones_cliente',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('cliente_id', sa.UUID(), nullable=False),
    sa.Column('descripcion', sa.String(length=255), nullable=False),
    sa.Column('referencia', sa.String(length=255), nullable=True),
    sa.Column('es_principal', sa.Boolean(), nullable=True),
    sa.Column('latitud', sa.Float(), nullable=True),
    sa.Column('longitud', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('rutas',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('origen_descripcion', sa.String(length=255), nullable=True),
    sa.Column('origen_latitud', sa.Float(), nullable=True),
    sa.Column('origen_longitud', sa.Float(), nullable=True),
    sa.Column('chofer_id', sa.UUID(), nullable=True),
    sa.Column('estado', sa.Enum('pendiente', 'asignada', 'en_curso', 'completada', 'finalizada', name='estadoruta'), nullable=True),
    sa.Column('total_km', sa.Float(), nullable=True),
    sa.Column('tiempo_estimado_min', sa.Integer(), nullable=True),
    sa.Column('es_plantilla', sa.Boolean(), nullable=True),
    sa.Column('fecha_programada', sa.Date(), nullable=True),
    sa.Column('codigo_seguimiento', sa.String(length=12), nullable=True),
    sa.Column('creada_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('iniciada_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finalizada_en', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['chofer_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo_seguimiento')
    )
    op.create_table('vehiculos',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('patente', sa.String(length=10), nullable=False),
    sa.Column('marca_modelo', sa.String(length=100), nullable=False),
    sa.Column('capacidad_kg', sa.Float(), nullable=False),
    sa.Column('estado', sa.Enum('disponible', 'en_ruta', 'mantenimiento', name='estadovehiculo'), nullable=False),
    sa.Column('chofer_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['chofer_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('patente')
    )
    op.create_table('entregas',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('cliente_id', sa.UUID(), nullable=False),
    sa.Column('direccion_id', sa.UUID(), nullable=False),
    sa.Column('ruta_id', sa.UUID(), nullable=True),
    sa.Column('descripcion', sa.String(length=255), nullable=False),
    sa.Column('bultos', sa.Integer(), nullable=True),
    sa.Column('peso_kg', sa.Float(), nullable=True),
    sa.Column('fecha_estimada', sa.Date(), nullable=True),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('observaciones_chofer', sa.Text(), nullable=True),
    sa.Column('estado', sa.Enum('pendiente', 'en_curso', 'completada', 'cancelada', name='estadoentrega'), nullable=True),
    sa.Column('codigo_confirmacion', sa.String(length=16), nullable=True),
    sa.Column('creada_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('actualizada_en', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
    sa.ForeignKeyConstraint(['direccion_id'], ['direcciones_cliente.id'], ),
    sa.ForeignKeyConstraint(['ruta_id'], ['rutas.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('paradas_ruta',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('ruta_id', sa.UUID(), nullable=False),
    sa.Column('entrega_id', sa.UUID(), nullable=True),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('tiempo_desde_anterior_min', sa.Integer(), nullable=True),
    sa.Column('distancia_desde_anterior_km', sa.Float(), nullable=True),
    sa.Column('completada', sa.Boolean(), nullable=True),
    sa.Column('latitud', sa.Float(), nullable=True),
    sa.Column('longitud', sa.Float(), nullable=True),
    sa.Column('es_parada_extra', sa.Boolean(), nullable=True),
    sa.Column('descripcion_extra', sa.String(length=200), nullable=True),
    sa.Column('direccion_extra', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['entrega_id'], ['entregas.id'], ),
    sa.ForeignKeyConstraint(['ruta_id'], ['rutas.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('paradas_ruta')
    op.drop_table('entregas')
    op.drop_table('vehiculos')
    op.drop_table('rutas')
    op.drop_table('direcciones_cliente')
    op.drop_index(op.f('ix_usuarios_email'), table_name='usuarios')
    op.drop_table('usuarios')
    op.drop_table('clientes')
    # PostgreSQL no borra los tipos ENUM al borrar las tablas
    for enum_name in ('estadoentrega', 'estadovehiculo', 'estadoruta', 'rolusuario'):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
    # ### end Alembic commands ###
