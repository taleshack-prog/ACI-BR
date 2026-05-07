import { useState, useEffect } from 'react'

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
}

export function DashboardPage({ onStartConsultation, onLogout }: Props) {
  const [sessions, setSessions] = useState<any[]>([])
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const token = localStorage.getItem('aci_token')
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  useEffect(() => {
    const load = async () => {
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
    }
    load()
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🏥</span>
          <div>
            <h1 className="font-bold text-gray-800">ACI-BR</h1>
            <p className="text-xs text-gray-500">{user?.name ?? '...'} — {user?.specialty ?? ''}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onStartConsultation}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition-colors flex items-center gap-2"
          >
            🎙️ Nova Consulta
          </button>
          <button onClick={onLogout} className="text-gray-400 hover:text-gray-600 text-sm">Sair</button>
        </div>
      </header>

      {/* Stats */}
      <div className="px-6 py-4 grid grid-cols-3 gap-4 max-w-4xl mx-auto">
        {[
          { label: 'Aguardando Revisão', value: sessions.filter(s => s.review_status === 'AWAITING_REVIEW').length, color: 'text-yellow-600' },
          { label: 'Sincronizadas Hoje', value: sessions.filter(s => s.review_status === 'SYNCED').length, color: 'text-blue-600' },
          { label: 'Total de Sessões', value: sessions.length, color: 'text-gray-700' },
        ].map(stat => (
          <div key={stat.label} className="bg-white rounded-xl shadow p-4 text-center">
            <p className={`text-3xl font-bold ${stat.color}`}>{stat.value}</p>
            <p className="text-xs text-gray-500 mt-1">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Session list */}
      <div className="px-6 max-w-4xl mx-auto">
        <h2 className="font-semibold text-gray-700 mb-3">Sessões Recentes</h2>
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
              <div key={s.session_id} className="bg-white rounded-xl shadow p-4 flex items-center justify-between">
                <div>
                  <p className="font-medium text-sm text-gray-800">Paciente: {s.patient_id}</p>
                  <p className="text-xs text-gray-400">{s.specialty} · {new Date(s.created_at).toLocaleString('pt-BR')}</p>
                </div>
                <span className={`text-xs font-semibold px-2 py-1 rounded-full ${statusColors[s.review_status] ?? 'bg-gray-100'}`}>
                  {s.review_status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
