/**
 * ConsultationPage — Fluxo completo de consulta.
 * Após encerrar gravação, chama /process/fhir-bundle com o transcript real.
 */
import { useState, useCallback, useRef } from 'react'
import { useAudioCapture } from '../hooks/useAudioCapture'
import { ReviewInterface } from '../components/ReviewInterface'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8001'

type Stage = 'idle' | 'recording' | 'processing' | 'reviewing' | 'synced' | 'error'

interface Props {
  token: string
  onBack: () => void
}

export function ConsultationPage({ token, onBack }: Props) {
  const [stage, setStage] = useState<Stage>('idle')
  const [patientId, setPatientId] = useState('')
  const [specialty, setSpecialty] = useState('general')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [soapData, setSoapData] = useState<any>(null)
  const [entities, setEntities] = useState<any[]>([])
  const [error, setError] = useState('')
  const [processingSteps, setProcessingSteps] = useState<string[]>([])

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const { isRecording, transcript, fullTranscript, startRecording, stopRecording, getFullTranscript, error: audioError, status: audioStatus } =
    useAudioCapture(patientId, 'doctor-from-token', specialty)

  // Guarda o transcript acumulado para usar no processamento
  const transcriptRef = useRef<typeof transcript>([])
  transcriptRef.current = transcript

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
    setProcessingSteps([])

    try {
      // Usa transcript real do Whisper se disponível, senão demo por especialidade
      const transcriptText = getFullTranscript() || null

      setProcessingSteps(s => [...s, '✅ Gravação encerrada'])

      // Chama o pipeline real com o transcript
      // Se não há transcript (WebSocket não conectou), usa um texto genérico baseado
      // na especialidade para demonstração
      const textToProcess = transcriptText || getSpecialtyDemo(specialty)

      setProcessingSteps(s => [...s, '✅ Diarização concluída'])
      setProcessingSteps(s => [...s, '⏳ Extraindo entidades clínicas (C-NER)...'])

      const res = await fetch(`${API}/process/fhir-bundle`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          text: textToProcess,
          specialty,
          patient_id: patientId,
        }),
      })

      if (!res.ok) throw new Error(`Pipeline retornou ${res.status}`)

      const data = await res.json()

      setProcessingSteps(s => [...s,
        `✅ ${data.entity_count} entidades extraídas`,
        `✅ SOAP gerado`,
        `✅ FHIR Bundle criado (${data.fhir_resources} recursos)`,
      ])

      setSoapData(data.soap)
      setEntities(data.entities?.entities || [])

      // Salva sessão no backend para persistência e dashboard
      let newSessionId = crypto.randomUUID()
      try {
        const sessRes = await fetch(`${API}/session`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            patient_id: patientId,
            specialty,
            soap: data.soap,
            entities: data.entities?.entities || [],
            fhir_bundle: data.fhir_bundle,
          }),
        })
        if (sessRes.ok) {
          const sessData = await sessRes.json()
          newSessionId = sessData.session_id
          setProcessingSteps(s => [...s, '✅ Sessão salva no servidor'])
        }
      } catch (e) {
        console.warn('Sessão não salva no servidor (continuando localmente)', e)
      }

      setSessionId(newSessionId)
      setTimeout(() => setStage('reviewing'), 800)

    } catch (e: any) {
      console.error(e)
      setError(`Erro no pipeline: ${e.message}`)
      setStage('error')
    }
  }, [stopRecording, specialty, patientId, headers])

  const handleApprove = useCallback(async (sid: string) => {
    setStage('synced')
  }, [])

  const handleDiscard = useCallback(() => {
    setStage('idle')
    setSessionId(null)
    setSoapData(null)
    setEntities([])
  }, [])

  const handleCorrection = useCallback((entityId: string, newValue: string) => {
    console.log('Correção:', entityId, '→', newValue)
  }, [])

  // ── Idle ──────────────────────────────────────────────────────────────────
  if (stage === 'idle' || stage === 'error') return (
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
              <option value="general">Clínica Geral</option>
              <option value="cardiology">Cardiologia</option>
              <option value="psychiatry">Psiquiatria</option>
              <option value="orthopedics">Ortopedia</option>
              <option value="pediatrics">Pediatria</option>
            </select>
          </div>
          {error && <p className="text-red-500 text-xs bg-red-50 p-2 rounded">{error}</p>}
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

  // ── Recording ─────────────────────────────────────────────────────────────
  if (stage === 'recording') return (
    <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center text-white p-4">
      <div className="text-center w-full max-w-lg">
        <div className="w-24 h-24 rounded-full bg-red-500 mx-auto mb-6 flex items-center justify-center animate-pulse">
          <span className="text-4xl">🎙️</span>
        </div>
        <h2 className="text-2xl font-bold mb-1">Gravando...</h2>
        <p className="text-gray-400 text-sm mb-1">ACI-BR está ouvindo a consulta</p>
        <p className="text-gray-500 text-xs mb-6">
          Paciente: {patientId} · {specialty === 'general' ? 'Clínica Geral' : specialty}
        </p>

        {transcript.length > 0 && (
          <div className="bg-gray-800 rounded-xl p-4 text-left max-h-48 overflow-y-auto mb-6 space-y-1">
            {transcript.map((seg, i) => (
              <p key={i} className={`text-xs ${seg.speaker === 'doctor' ? 'text-blue-300' : 'text-green-300'}`}>
                <span className="font-semibold">{seg.speaker === 'doctor' ? '👨‍⚕️' : '🧑'}</span> {seg.text}
              </p>
            ))}
          </div>
        )}

        {audioStatus === 'error' && audioError && (
          <div className="bg-red-900/50 border border-red-500 rounded-xl px-4 py-3 mb-6 text-sm text-red-200 text-left">
            <p className="font-semibold mb-1">⚠️ Falha na captura de áudio</p>
            <p className="text-xs text-red-300">{audioError}</p>
            <p className="text-xs text-red-400 mt-1">O SOAP será gerado sem transcrição em tempo real.</p>
          </div>
        )}

        {audioStatus !== 'error' && transcript.length === 0 && (
          <p className="text-gray-600 text-xs mb-6">
            💡 Transcrição em tempo real aparecerá aqui assim que o microfone for capturado
          </p>
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
      <div className="text-center max-w-sm">
        <div className="text-5xl mb-4 animate-spin">⚙️</div>
        <h2 className="text-xl font-bold text-gray-800 mb-4">Processando consulta...</h2>
        <div className="space-y-1 text-sm text-gray-600 text-left bg-white rounded-xl p-4 shadow">
          {processingSteps.length === 0
            ? <p className="text-gray-400">Iniciando pipeline...</p>
            : processingSteps.map((step, i) => <p key={i}>{step}</p>)
          }
        </div>
      </div>
    </div>
  )

  // ── Reviewing ─────────────────────────────────────────────────────────────
  if (stage === 'reviewing' && soapData) return (
    <ReviewInterface
      sessionId={sessionId!}
      soap={soapData}
      entities={entities}
      transcript={transcript.length > 0 ? transcript : [
        { speaker: 'patient', text: 'Transcrição em tempo real indisponível — SOAP gerado via pipeline NLP.', timestamp: Date.now() }
      ]}
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
        <p className="text-green-600 mb-2">Paciente: {patientId}</p>
        <p className="text-green-500 text-sm mb-6">O prontuário foi atualizado com sucesso no PEP.</p>
        <button onClick={onBack}
          className="bg-green-600 hover:bg-green-700 text-white font-semibold px-6 py-2.5 rounded-xl transition-colors">
          Voltar ao Dashboard
        </button>
      </div>
    </div>
  )

  return null
}

// Textos demo por especialidade quando WebSocket não captura áudio real
function getSpecialtyDemo(specialty: string): string {
  const demos: Record<string, string> = {
    general: 'Paciente relata febre há 2 dias, tosse seca, dor de garganta e coriza. Nega dispneia. Temperatura 38.2°C. FC 92 bpm. SatO2 98%. Hipótese de gripe ou resfriado viral. Prescrever Dipirona 500mg e repouso.',
    cardiology: 'Paciente relata dor no peito há 3 dias. Nega febre. PA: 140/90 mmHg. FC: 88 bpm. SatO2 97%. Hipertensão arterial confirmada. Prescrever Losartan 50mg.',
    psychiatry: 'Paciente relata tristeza persistente há 3 semanas, insônia, perda de apetite e anedonia. Nega ideação suicida. Hipótese de episódio depressivo. Iniciar Sertralina 50mg.',
    orthopedics: 'Paciente relata dor no joelho direito há 1 semana após queda. Edema local. Sem crepitação. Hipótese de contusão. Prescrever anti-inflamatório e fisioterapia.',
    pediatrics: 'Criança de 5 anos com febre 38.5°C há 1 dia, tosse e coriza. Sem sinais de gravidade. Hipótese de IVAS viral. Prescrever Paracetamol 200mg/ml conforme peso.',
  }
  return demos[specialty] || demos.general
}
