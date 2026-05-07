/**
 * ReviewInterface — Interface de Revisão Médica (Human-in-the-Loop)
 *
 * Layout split-view:
 *   Esquerda: Transcrição com timestamps e labels médico/paciente
 *   Direita:  Nota SOAP com chips editáveis por seção
 *
 * Meta de UX: validação em < 5 segundos
 */
import React, { useState } from 'react'

interface Entity {
  entity_id: string
  type: 'symptom' | 'diagnosis' | 'medication' | 'vital_sign'
  value: string
  confidence: number
  negated: boolean
  linked_code?: { system: string; code: string; display: string }
}

interface SOAPNote {
  subjective: string
  objective: string
  assessment: string
  plan: string
}

interface TranscriptSegment {
  speaker: 'doctor' | 'patient'
  text: string
  timestamp: number
}

interface ReviewInterfaceProps {
  sessionId: string
  soap: SOAPNote
  entities: Entity[]
  transcript: TranscriptSegment[]
  onApprove: (sessionId: string) => void
  onDiscard: (sessionId: string) => void
  onCorrection: (entityId: string, newValue: string) => void
}

const CONFIDENCE_THRESHOLD = 0.85

const typeColors: Record<Entity['type'], string> = {
  symptom: 'bg-yellow-100 border-yellow-400 text-yellow-800',
  diagnosis: 'bg-red-100 border-red-400 text-red-800',
  medication: 'bg-blue-100 border-blue-400 text-blue-800',
  vital_sign: 'bg-green-100 border-green-400 text-green-800',
}

function EntityChip({ entity, onEdit, onDelete }: {
  entity: Entity
  onEdit: (id: string, val: string) => void
  onDelete: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(entity.value)
  const isLowConfidence = entity.confidence < CONFIDENCE_THRESHOLD

  const colorClass = typeColors[entity.type]

  const handleSave = () => {
    onEdit(entity.entity_id, value)
    setEditing(false)
  }

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1 m-1">
        <input
          autoFocus
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSave()}
          className="border rounded px-2 py-0.5 text-sm w-40"
        />
        <button onClick={handleSave} className="text-green-600 text-xs font-bold">✓</button>
        <button onClick={() => setEditing(false)} className="text-gray-400 text-xs">✕</button>
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1 border rounded-full px-2 py-0.5 text-xs font-medium m-1 cursor-pointer
        ${colorClass}
        ${isLowConfidence ? 'ring-2 ring-amber-400 ring-offset-1' : ''}
        ${entity.negated ? 'line-through opacity-60' : ''}
      `}
      title={`${entity.type} | ${entity.linked_code?.system}: ${entity.linked_code?.code ?? 'N/A'} | Conf: ${(entity.confidence * 100).toFixed(0)}%`}
    >
      {isLowConfidence && <span title="Baixa confiança — revisar">⚠️</span>}
      <span onClick={() => setEditing(true)}>{entity.value}</span>
      <button
        onClick={() => onDelete(entity.entity_id)}
        className="ml-1 text-current opacity-50 hover:opacity-100 font-bold"
      >×</button>
    </span>
  )
}

export function ReviewInterface({
  sessionId, soap, entities, transcript, onApprove, onDiscard, onCorrection
}: ReviewInterfaceProps) {
  const [localEntities, setLocalEntities] = useState(entities)
  const [localSoap, setLocalSoap] = useState(soap)
  const [approved, setApproved] = useState(false)

  const handleEdit = (entityId: string, newValue: string) => {
    setLocalEntities(es => es.map(e => e.entity_id === entityId ? { ...e, value: newValue } : e))
    onCorrection(entityId, newValue)
  }

  const handleDelete = (entityId: string) => {
    setLocalEntities(es => es.filter(e => e.entity_id !== entityId))
    onCorrection(entityId, '__DELETED__')
  }

  const handleApprove = () => {
    setApproved(true)
    onApprove(sessionId)
  }

  const entitiesByType = (type: Entity['type']) => localEntities.filter(e => e.type === type)
  const lowConfidenceCount = localEntities.filter(e => e.confidence < CONFIDENCE_THRESHOLD).length

  return (
    <div className="flex h-full gap-4 p-4 bg-gray-50 min-h-screen font-sans text-sm">

      {/* ── Esquerda: Transcrição ── */}
      <div className="w-1/2 bg-white rounded-xl shadow p-4 overflow-y-auto">
        <h2 className="text-base font-bold text-gray-700 mb-3 flex items-center gap-2">
          🎙️ Transcrição
          <span className="ml-auto text-xs text-gray-400">Sessão: {sessionId.slice(0, 8)}…</span>
        </h2>
        <div className="space-y-2">
          {transcript.map((seg, i) => (
            <div key={i} className={`flex gap-2 ${seg.speaker === 'doctor' ? 'flex-row-reverse' : ''}`}>
              <span className={`flex-shrink-0 w-16 text-xs font-semibold pt-1
                ${seg.speaker === 'doctor' ? 'text-blue-600 text-right' : 'text-green-600'}`}>
                {seg.speaker === 'doctor' ? '👨‍⚕️ Med.' : '🧑 Pac.'}
              </span>
              <div className={`rounded-lg px-3 py-2 max-w-xs
                ${seg.speaker === 'doctor' ? 'bg-blue-50 text-blue-900' : 'bg-green-50 text-green-900'}`}>
                {seg.text}
              </div>
            </div>
          ))}
          {transcript.length === 0 && (
            <p className="text-gray-400 text-center py-8">Transcrição aparecerá aqui durante a consulta.</p>
          )}
        </div>
      </div>

      {/* ── Direita: SOAP + Chips ── */}
      <div className="w-1/2 flex flex-col gap-3">

        {/* Alerta de baixa confiança */}
        {lowConfidenceCount > 0 && (
          <div className="bg-amber-50 border border-amber-300 rounded-lg px-3 py-2 flex items-center gap-2 text-amber-800 text-xs">
            ⚠️ <strong>{lowConfidenceCount}</strong> item(ns) com baixa confiança destacados em amarelo — revise antes de aprovar.
          </div>
        )}

        {/* Seções SOAP */}
        {[
          { key: 'subjective', label: 'S — Subjetivo', icon: '🗣️', entityTypes: ['symptom'] as Entity['type'][] },
          { key: 'objective', label: 'O — Objetivo', icon: '📊', entityTypes: ['vital_sign'] as Entity['type'][] },
          { key: 'assessment', label: 'A — Avaliação', icon: '🔍', entityTypes: ['diagnosis'] as Entity['type'][] },
          { key: 'plan', label: 'P — Plano', icon: '💊', entityTypes: ['medication'] as Entity['type'][] },
        ].map(section => (
          <div key={section.key} className="bg-white rounded-xl shadow p-3">
            <h3 className="font-bold text-gray-700 mb-2">{section.icon} {section.label}</h3>

            {/* Chips de entidades */}
            <div className="flex flex-wrap mb-2">
              {section.entityTypes.flatMap(type => entitiesByType(type)).map(entity => (
                <EntityChip
                  key={entity.entity_id}
                  entity={entity}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                />
              ))}
            </div>

            {/* Texto SOAP editável */}
            <textarea
              className="w-full border border-gray-200 rounded-lg p-2 text-xs text-gray-700 resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
              rows={2}
              value={localSoap[section.key as keyof SOAPNote]}
              onChange={e => setLocalSoap(s => ({ ...s, [section.key]: e.target.value }))}
            />
          </div>
        ))}

        {/* Botões de ação */}
        <div className="flex gap-3 mt-2">
          <button
            onClick={handleApprove}
            disabled={approved}
            className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-bold py-3 rounded-xl transition-colors text-sm"
          >
            {approved ? '✅ Aprovado!' : '✅ Aprovar e Sincronizar'}
          </button>
          <button
            onClick={() => onDiscard(sessionId)}
            className="px-4 bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium py-3 rounded-xl transition-colors text-sm"
          >
            🗑️ Descartar
          </button>
        </div>
      </div>
    </div>
  )
}
