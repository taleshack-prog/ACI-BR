/**
 * ConsultationPage — Fluxo completo de consulta.
 *
 * Estados:
 *   idle        → médico clica "Iniciar"
 *   recording   → gravando áudio via WebSocket
 *   processing  → pipeline Whisper + NLP + FHIR
 *   reviewing   → médico revisa SOAP + chips
 *   synced      → nota enviada ao PEP
 */
import { useState, useCallback } from 'react'
import { useAudioCapture } from '../hooks/useAudioCapture'
import { ReviewInterface } from '../components/ReviewInterface'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8001'

type Stage = 'idle' | 'recording' | 'processing' | 'reviewing' | 'synced' | 'error'

interface Props {
  token: string
  onBack: () => void
}

// Demo data for reviewing stage (simulates pipeline output)
const DEMO_SOAP = {
  subjective: 'Paciente relata dor no peito há 3 dias, com piora aos esforços. Nega febre e tosse.',
  objective: 'PA: 140/90 mmHg (LOINC: 85354-9), FC: 88 bpm (LOINC: 8867-4), SatO2: 97%.',
  assessment: '1. Dor torácica (R07.9 — Dor torácica não especificada)\n2. Hipertensão arterial (I10 — Hipertensão essencial)',
  plan: '1. Prescrever Losartan 50mg uma vez ao dia\n2. Solicitar eletrocardiograma\n3. Retorno em 15 dias',
}

const DEMO_ENTITIES = [
  { entity_id: 'e1', type: 'symptom' as const, value: 'dor no peito', confidence: 0.82, negated: false, linked_code: { system: 'SNOMED-CT', code: '29857009', display: 'Chest pain' } },
  { entity_id: 'e2', type: 'symptom' as const, value: 'febre', confidence: 0.82, negated: true, linked_code: { system: 'SNOMED-CT', code: '386661006', display: 'Fever' } },
  { entity_id: 'e3', type: 'vital_sign' as const, value: 'pressão arterial: 140/90', confidence: 0.91, negated: false, linked_code: { system: 'LOINC', code: '85354-9', display: 'Blood pressure panel' } },
  { entity_id: 'e4', type: 'vital_sign' as const, value: 'frequência cardíaca: 88', confidence: 0.91, negated: false, linked_code: { system: 'LOINC', code: '8867-4', display: 'Heart rate' } },
  { entity_id: 'e5', type: 'diagnosis' as const, value: 'hipertensão arterial', confidence: 0.85, negated: false, linked_code: { system: 'ICD-10', code: 'I10', display: 'Hipertensão essencial (primária)' } },
  { entity_id: 'e6', type: 'medication' as const, value: 'Losartan 50 mg', confidence: 0.88, negated: false, linked_code: null },
]

const DEMO_TRANSCRIPT = [
  { speaker: 'patient' as const, text: 'Estou com dor no peito há 3 dias, piora quando me esforço.', timestamp: 1000 },
  { speaker: 'doctor' as const, text: 'Tem febre ou tosse?', timestamp: 8000 },
  { speaker: 'patient' as const, text: 'Não, sem febre nem tosse.', timestamp: 10000 },
  { speaker: 'doctor' as const, text: 'Pressão 140/90, frequência 88 bpm, saturação 97%. Vou prescrever Losartan 50mg e solicitar ECG.', timestamp: 15000 },
]

export function ConsultationPage({ token, onBack }: Props) {
  const [stage, setStage] = useState<Stage>('idle')
  const [patientId, setPatientId] = useState('')
  const [specialty, setSpecialty] = useState('cardiology')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [soapData, setSoapData] = useState(DEMO_SOAP)
  const [error, setError] = useState('')

  const headers = { Authorization: `Bearer ${token}` }

  const { isRecording, transcript, startRecording, stopRecording, status: audioStatus } =
    useAudioCapture(patientId, 'doctor-from-token', specialty)

  const handleStart = useCallback(async () => {
    if (!patientId.trim()) {
      setError('Informe o ID do paciente antes de iniciar.')
      return
    }
    setError('')
    setStage('recording')
    await startRecording()
  }, [patientId, startRecording])

  const handleStop = useCallback(async () => {
    stopRecording()
    setStage('processing')

    // Simula delay de processamento (~3s) e vai direto para review com demo data
    // Em produção: polling do status via GET /audio/status/{session_id}
    setTimeout(() => {
      setSessionId(crypto.randomUUID())
      setStage('reviewing')
    }, 2500)
  }, [stopRecording])

  const handleApprove = useCallback(async (sid: string) => {
    try {
      // Em produção: PUT /session/{sid} com review_status: APPROVED
      await new Promise(r => setTimeout(r, 500)) // simula API call
      setStage('synced')
    } catch {
      setError('Erro ao sincronizar com o PEP.')
    }
  }, [])

  const handleDiscard = useCallback((sid: string) => {
    setStage('idle')
    setSessionId(null)
  }, [])

  const handleCorrection = useCallback((entityId: string, newValue: string) => {
    // POST /session/{sessionId}/corrections para active learning
    console.log('Correção registrada:', entityId, '→', newValue)
  }, [])

  // ── Idle ──────────────────────────────────────────────────────────────────
  if (stage === 'idle') return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-md">
        <button onClick={onBack} className="text-gray-400 hover:text-gray-600 text-sm mb-4">← Voltar</button>
        <h2 className="text-xl font-bold text-gray-800 mb-6">🎙️ Nova Consulta</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">ID do Paciente / CPF</label>
            <input value={patientId} onChange={e => setPatientId(e.target.value)}
              placeholder="Ex: CPF-12345678900"
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Especialidade</label>
            <select value={specialty} onChange={e => setSpecialty(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
              <option value="cardiology">Cardiologia</option>
              <option value="general">Clínica Geral</option>
              <option value="psychiatry">Psiquiatria</option>
              <option value="orthopedics">Ortopedia</option>
              <option value="pediatrics">Pediatria</option>
            </select>
          </div>
          {error && <p className="text-red-500 text-xs">{error}</p>}
          <button onClick={handleStart}
            className="w-full bg-red-500 hover:bg-red-600 text-white font-bold py-3 rounded-xl transition-colors">
            🔴 Iniciar Gravação
          </button>
        </div>
        <p className="text-xs text-gray-400 text-center mt-4">
          O paciente será informado sobre a gravação antes de iniciar.
        </p>
      </div>
    </div>
  )

  // ── Recording ──────────────────────────────────────────────────────────────
  if (stage === 'recording') return (
    <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center text-white p-4">
      <div className="text-center">
        <div className="w-24 h-24 rounded-full bg-red-500 mx-auto mb-6 flex items-center justify-center animate-pulse">
          <span className="text-4xl">🎙️</span>
        </div>
        <h2 className="text-2xl font-bold mb-2">Gravando...</h2>
        <p className="text-gray-400 text-sm mb-2">ACI-BR está ouvindo a consulta</p>
        <p className="text-gray-500 text-xs mb-8">Paciente: {patientId} · {specialty}</p>

        {/* Transcrição em tempo real */}
        {transcript.length > 0 && (
          <div className="bg-gray-800 rounded-xl p-4 max-w-md text-left max-h-40 overflow-y-auto mb-6">
            {transcript.map((seg, i) => (
              <p key={i} className={`text-xs mb-1 ${seg.speaker === 'doctor' ? 'text-blue-300' : 'text-green-300'}`}>
                <span className="font-semibold">{seg.speaker === 'doctor' ? '👨‍⚕️' : '🧑'}</span> {seg.text}
              </p>
            ))}
          </div>
        )}

        <button onClick={handleStop}
          className="bg-white text-gray-900 font-bold px-8 py-3 rounded-xl hover:bg-gray-100 transition-colors">
          ⏹ Encerrar Consulta
        </button>
      </div>
    </div>
  )

  // ── Processing ────────────────────────────────────────────────────────────
  if (stage === 'processing') return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center">
      <div className="text-center">
        <div className="text-5xl mb-4 animate-spin">⚙️</div>
        <h2 className="text-xl font-bold text-gray-800 mb-2">Processando consulta...</h2>
        <div className="space-y-1 text-sm text-gray-500">
          <p>✅ Diarização de locutores</p>
          <p>✅ Transcrição ASR (Whisper pt-BR)</p>
          <p>⏳ Extração de entidades clínicas (C-NER)</p>
          <p>⏳ Geração do SOAP + FHIR Bundle</p>
        </div>
      </div>
    </div>
  )

  // ── Reviewing ─────────────────────────────────────────────────────────────
  if (stage === 'reviewing') return (
    <ReviewInterface
      sessionId={sessionId!}
      soap={soapData}
      entities={DEMO_ENTITIES}
      transcript={DEMO_TRANSCRIPT}
      onApprove={handleApprove}
      onDiscard={handleDiscard}
      onCorrection={handleCorrection}
    />
  )

  // ── Synced ────────────────────────────────────────────────────────────────
  if (stage === 'synced') return (
    <div className="min-h-screen bg-green-50 flex flex-col items-center justify-center">
      <div className="text-center">
        <div className="text-6xl mb-4">✅</div>
        <h2 className="text-2xl font-bold text-green-800 mb-2">Nota Sincronizada!</h2>
        <p className="text-green-600 mb-6">O prontuário foi atualizado com sucesso no PEP.</p>
        <button onClick={onBack}
          className="bg-green-600 hover:bg-green-700 text-white font-semibold px-6 py-2.5 rounded-xl transition-colors">
          Voltar ao Dashboard
        </button>
      </div>
    </div>
  )

  return null
}
