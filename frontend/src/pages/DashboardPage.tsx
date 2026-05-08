import { useState, useEffect, useCallback } from 'react'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8001'

interface Props {
  onStartConsultation: () => void
  onLogout: () => void
}

const statusColors: Record<string, string> = {
  AWAITING_REVIEW: 'bg-yellow-100 text-yellow-800',
  APPROVED: 'bg-green-100 text-green-800',
  SYNCED: 'bg-blue-100 text-blue-800',
  DISCARDED: 'bg-gray-100 text-gray-500',
  FAILED: 'bg-red-100 text-red-800',
  REJECTED: 'bg-red-100 text-red-700',
}

const statusLabels: Record<string, string> = {
  AWAITING_REVIEW: '⏳ Aguardando Revisão',
  APPROVED: '✅ Aprovado',
  SYNCED: '🔵 Sincronizado',
  DISCARDED: '🗑️ Descartado',
  FAILED: '❌ Falhou',
  REJECTED: '✗ Rejeitado',
}

const specialtyLabels: Record<string, string> = {
  general: 'Clínica Geral',
  cardiology: 'Cardiologia',
  psychiatry: 'Psiquiatria',
  orthopedics: 'Ortopedia',
  pediatrics: 'Pediatria',
}

export function DashboardPage({ onStartConsultation, onLogout }: Props) {
  const [sessions, setSessions] = useState<any[]>([])
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [selectedSession, setSelectedSession] = useState<any>(null)

  const token = localStorage.getItem('aci_token')
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const loadData = useCallback(async () => {
    try {
      const [meRes, sessRes] = await Promise.all([
        fetch(`${API}/auth/me`, { headers }),
        fetch(`${API}/session`, { headers }),
      ])
      if (meRes.ok) setUser(await meRes.json())
      if (sessRes.ok) {
        const data = await sessRes.json()
        setSessions(data.sessions || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleSync = async (sessionId: string) => {
    try {
      // Primeiro aprova
      await fetch(`${API}/session/${sessionId}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ review_status: 'APPROVED' }),
      })
      // Depois sincroniza
      const res = await fetch(`${API}/session/${sessionId}/sync?ehr_target=simulator`, {
        method: 'POST', headers,
      })
      if (res.ok) {
        await loadData()
        setSelectedSession(null)
      }
    } catch (e) { console.error(e) }
  }

  const handleDiscard = async (sessionId: string) => {
    await fetch(`${API}/session/${sessionId}`, { method: 'DELETE', headers })
    await loadData()
    setSelectedSession(null)
  }

  const awaitingCount = sessions.filter(s => s.review_status === 'AWAITING_REVIEW').length
  const syncedCount = sessions.filter(s => s.review_status === 'SYNCED').length

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🏥</span>
          <div>
            <h1 className="font-bold text-gray-800">ACI-BR</h1>
            <p className="text-xs text-gray-500">
              {user?.name ?? '...'} · {user?.crm ?? ''} · {specialtyLabels[user?.specialty] ?? user?.specialty ?? ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={loadData} className="text-gray-400 hover:text-gray-600 text-sm" title="Atualizar">🔄</button>
          <button onClick={onStartConsultation}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition-colors flex items-center gap-2">
            🎙️ Nova Consulta
          </button>
          <button onClick={onLogout} className="text-gray-400 hover:text-gray-600 text-sm">Sair</button>
        </div>
      </header>

      {/* Stats */}
      <div className="px-6 py-4 grid grid-cols-3 gap-4 max-w-4xl mx-auto">
        {[
          { label: 'Aguardando Revisão', value: awaitingCount, color: 'text-yellow-600', bg: 'bg-yellow-50' },
          { label: 'Sincronizadas', value: syncedCount, color: 'text-blue-600', bg: 'bg-blue-50' },
          { label: 'Total de Sessões', value: sessions.length, color: 'text-gray-700', bg: 'bg-gray-50' },
        ].map(stat => (
          <div key={stat.label} className={`${stat.bg} rounded-xl shadow-sm border p-4 text-center`}>
            <p className={`text-3xl font-bold ${stat.color}`}>{stat.value}</p>
            <p className="text-xs text-gray-500 mt-1">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="px-6 max-w-4xl mx-auto flex gap-4">
        {/* Session list */}
        <div className="flex-1">
          <h2 className="font-semibold text-gray-700 mb-3 flex items-center justify-between">
            Sessões Recentes
            {awaitingCount > 0 && (
              <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">
                {awaitingCount} pendente{awaitingCount > 1 ? 's' : ''}
              </span>
            )}
          </h2>

          {loading ? (
            <p className="text-gray-400 text-center py-8">Carregando...</p>
          ) : sessions.length === 0 ? (
            <div className="bg-white rounded-xl shadow p-8 text-center text-gray-400">
              <p className="text-4xl mb-2">🎙️</p>
              <p>Nenhuma sessão ainda. Inicie uma nova consulta.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {sessions.map(s => (
                <div
                  key={s.session_id}
                  onClick={() => setSelectedSession(s)}
                  className={`bg-white rounded-xl shadow p-4 flex items-center justify-between cursor-pointer hover:shadow-md transition-shadow
                    ${selectedSession?.session_id === s.session_id ? 'ring-2 ring-blue-400' : ''}`}
                >
                  <div>
                    <p className="font-medium text-sm text-gray-800">
                      Paciente: <span className="font-mono">{s.patient_id}</span>
                    </p>
                    <p className="text-xs text-gray-400">
                      {specialtyLabels[s.specialty] ?? s.specialty} · {new Date(s.created_at).toLocaleString('pt-BR')}
                    </p>
                    {s.soap && (
                      <p className="text-xs text-gray-500 mt-1 truncate max-w-xs">
                        {s.soap.assessment?.split('\n')[0] ?? ''}
                      </p>
                    )}
                  </div>
                  <span className={`text-xs font-semibold px-2 py-1 rounded-full whitespace-nowrap ${statusColors[s.review_status] ?? 'bg-gray-100'}`}>
                    {statusLabels[s.review_status] ?? s.review_status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Session detail panel */}
        {selectedSession && (
          <div className="w-80 bg-white rounded-xl shadow p-4 h-fit sticky top-4">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-bold text-gray-800 text-sm">Detalhes da Sessão</h3>
              <button onClick={() => setSelectedSession(null)} className="text-gray-400 hover:text-gray-600">✕</button>
            </div>

            <div className="space-y-2 text-xs text-gray-600 mb-4">
              <p><span className="font-medium">Paciente:</span> {selectedSession.patient_id}</p>
              <p><span className="font-medium">Especialidade:</span> {specialtyLabels[selectedSession.specialty]}</p>
              <p><span className="font-medium">Status:</span> {statusLabels[selectedSession.review_status]}</p>
              <p><span className="font-medium">Criada:</span> {new Date(selectedSession.created_at).toLocaleString('pt-BR')}</p>
            </div>

            {selectedSession.soap && (
              <div className="mb-4 space-y-1">
                <p className="font-medium text-xs text-gray-700">SOAP resumido:</p>
                {['assessment', 'plan'].map(key => selectedSession.soap[key] && (
                  <div key={key} className="bg-gray-50 rounded p-2">
                    <p className="text-xs font-semibold text-gray-500 uppercase">{key === 'assessment' ? 'Avaliação' : 'Plano'}</p>
                    <p className="text-xs text-gray-700">{selectedSession.soap[key]}</p>
                  </div>
                ))}
              </div>
            )}

            {selectedSession.review_status === 'AWAITING_REVIEW' && (
              <div className="flex gap-2">
                <button
                  onClick={() => handleSync(selectedSession.session_id)}
                  className="flex-1 bg-green-600 hover:bg-green-700 text-white text-xs font-bold py-2 rounded-lg"
                >
                  ✅ Aprovar e Sincronizar
                </button>
                <button
                  onClick={() => handleDiscard(selectedSession.session_id)}
                  className="px-3 bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs font-medium py-2 rounded-lg"
                >
                  🗑️
                </button>
              </div>
            )}

            {selectedSession.review_status === 'SYNCED' && selectedSession.fhir_ids && (
              <div className="bg-blue-50 rounded p-2">
                <p className="text-xs font-semibold text-blue-700 mb-1">FHIR IDs no PEP:</p>
                {Object.entries(selectedSession.fhir_ids).map(([type, ids]: any) => (
                  <p key={type} className="text-xs text-blue-600">{type}: {Array.isArray(ids) ? ids.length : 1} recurso(s)</p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
