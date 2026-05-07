"""
Alembic Migration: 001_initial_schema
Schema PostgreSQL FHIR Persistence — ACI-BR
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, BYTEA, JSONB
import uuid


def upgrade():
    # Patients
    op.create_table(
        'patients',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('fhir_id', sa.String(255), unique=True),
        sa.Column('mrn', sa.String(255), unique=True),
        sa.Column('given_name', sa.String(255)),
        sa.Column('family_name', sa.String(255)),
        sa.Column('dob', sa.Date),
        sa.Column('gender', sa.String(10)),
        sa.Column('contact_phone', sa.String(20)),
        sa.Column('contact_email', sa.String(255)),
        sa.Column('address_line1', sa.String(255)),
        sa.Column('address_city', sa.String(100)),
        sa.Column('address_state', sa.String(2)),
        sa.Column('address_postal_code', sa.String(10)),
        sa.Column('encrypted_pii', BYTEA),  # AES-256
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now()),
    )

    # Encounters
    op.create_table(
        'encounters',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('fhir_id', sa.String(255), unique=True),
        sa.Column('patient_id', UUID(as_uuid=True), sa.ForeignKey('patients.id')),
        sa.Column('doctor_id', UUID(as_uuid=True)),
        sa.Column('specialty', sa.String(100)),
        sa.Column('status', sa.String(50)),
        sa.Column('encounter_type', sa.String(100)),
        sa.Column('start_time', sa.TIMESTAMP),
        sa.Column('end_time', sa.TIMESTAMP),
        sa.Column('reason_code', sa.String(50)),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now()),
    )

    # Conditions (Diagnósticos)
    op.create_table(
        'conditions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('fhir_id', sa.String(255), unique=True),
        sa.Column('encounter_id', UUID(as_uuid=True), sa.ForeignKey('encounters.id')),
        sa.Column('patient_id', UUID(as_uuid=True), sa.ForeignKey('patients.id')),
        sa.Column('icd10_code', sa.String(10)),
        sa.Column('icd10_display', sa.String(255)),
        sa.Column('snomed_code', sa.String(20)),
        sa.Column('clinical_status', sa.String(50)),
        sa.Column('verification_status', sa.String(50)),
        sa.Column('onset_date', sa.Date),
        sa.Column('abatement_date', sa.Date),
        sa.Column('negated', sa.Boolean, server_default='FALSE'),
        sa.Column('confidence', sa.Float),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now()),
    )

    # Observations (Sinais Vitais, Sintomas)
    op.create_table(
        'observations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('fhir_id', sa.String(255), unique=True),
        sa.Column('encounter_id', UUID(as_uuid=True), sa.ForeignKey('encounters.id')),
        sa.Column('patient_id', UUID(as_uuid=True), sa.ForeignKey('patients.id')),
        sa.Column('observation_type', sa.String(100)),
        sa.Column('loinc_code', sa.String(20)),
        sa.Column('loinc_display', sa.String(255)),
        sa.Column('value_quantity', sa.Float),
        sa.Column('value_unit', sa.String(50)),
        sa.Column('value_string', sa.String(255)),
        sa.Column('status', sa.String(50)),
        sa.Column('effective_datetime', sa.TIMESTAMP),
        sa.Column('confidence', sa.Float),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now()),
    )

    # MedicationRequests
    op.create_table(
        'medication_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('fhir_id', sa.String(255), unique=True),
        sa.Column('encounter_id', UUID(as_uuid=True), sa.ForeignKey('encounters.id')),
        sa.Column('patient_id', UUID(as_uuid=True), sa.ForeignKey('patients.id')),
        sa.Column('medication_code', sa.String(50)),
        sa.Column('medication_name', sa.String(255)),
        sa.Column('dosage_value', sa.Float),
        sa.Column('dosage_unit', sa.String(50)),
        sa.Column('frequency', sa.String(100)),
        sa.Column('route', sa.String(50)),
        sa.Column('duration_days', sa.Integer),
        sa.Column('status', sa.String(50)),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now()),
    )

    # DocumentReferences (SOAP Notes)
    op.create_table(
        'document_references',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('fhir_id', sa.String(255), unique=True),
        sa.Column('encounter_id', UUID(as_uuid=True), sa.ForeignKey('encounters.id')),
        sa.Column('patient_id', UUID(as_uuid=True), sa.ForeignKey('patients.id')),
        sa.Column('document_type', sa.String(100)),
        sa.Column('title', sa.String(255)),
        sa.Column('content_text', sa.Text),
        sa.Column('content_format', sa.String(50)),
        sa.Column('status', sa.String(50)),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now()),
    )

    # Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('entity_type', sa.String(100)),
        sa.Column('entity_id', UUID(as_uuid=True)),
        sa.Column('action', sa.String(50)),
        sa.Column('actor_id', UUID(as_uuid=True)),
        sa.Column('old_values', JSONB),
        sa.Column('new_values', JSONB),
        sa.Column('timestamp', sa.TIMESTAMP, server_default=sa.func.now()),
    )

    # Indexes
    op.create_index('idx_patients_mrn', 'patients', ['mrn'])
    op.create_index('idx_encounters_patient_id', 'encounters', ['patient_id'])
    op.create_index('idx_conditions_patient_id', 'conditions', ['patient_id'])
    op.create_index('idx_observations_encounter_id', 'observations', ['encounter_id'])
    op.create_index('idx_audit_logs_entity', 'audit_logs', ['entity_type', 'entity_id'])


def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('document_references')
    op.drop_table('medication_requests')
    op.drop_table('observations')
    op.drop_table('conditions')
    op.drop_table('encounters')
    op.drop_table('patients')
