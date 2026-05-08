/**
 * useAudioCapture — Web Audio API + WebSocket com transcrição real via OpenAI Whisper.
 *
 * O backend acumula chunks de 3s e chama a API do Whisper a cada batch,
 * retornando transcrições parciais em tempo real via WebSocket.
 */
import { useState, useRef, useCallback } from 'react'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8001/audio/stream'
const SAMPLE_RATE = 16000
const CHUNK_SIZE = 1600  // 100ms @ 16kHz

export interface TranscriptSegment {
  speaker: 'doctor' | 'patient' | 'unknown'
  text: string
  timestamp: number
}

export interface AudioCaptureState {
  isRecording: boolean
  sessionId: string | null
  transcript: TranscriptSegment[]
  fullTranscript: string
  error: string | null
  status: 'idle' | 'recording' | 'processing' | 'ready' | 'error'
}

export function useAudioCapture(patientId: string, doctorId: string, specialty = 'general') {
  const [state, setState] = useState<AudioCaptureState>({
    isRecording: false,
    sessionId: null,
    transcript: [],
    fullTranscript: '',
    error: null,
    status: 'idle',
  })

  const audioContextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const sessionIdRef = useRef<string>(crypto.randomUUID())
  const fullTranscriptRef = useRef<string>('')

  const pcmToBase64 = (float32: Float32Array): string => {
    const int16 = new Int16Array(float32.length)
    for (let i = 0; i < float32.length; i++) {
      int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32768))
    }
    const bytes = new Uint8Array(int16.buffer)
    let binary = ''
    bytes.forEach(b => (binary += String.fromCharCode(b)))
    return btoa(binary)
  }

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      streamRef.current = stream
      fullTranscriptRef.current = ''

      const audioContext = new AudioContext({ sampleRate: SAMPLE_RATE })
      audioContextRef.current = audioContext
      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(CHUNK_SIZE, 1, 1)
      processorRef.current = processor

      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      const sessionId = sessionIdRef.current

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'start', sessionId, patientId, doctorId, specialty }))
        setState(s => ({ ...s, isRecording: true, sessionId, status: 'recording', error: null, transcript: [], fullTranscript: '' }))
      }

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)

        if (msg.type === 'transcript' && msg.text) {
          // Transcrição parcial real do Whisper
          fullTranscriptRef.current += ' ' + msg.text
          setState(s => ({
            ...s,
            fullTranscript: fullTranscriptRef.current.trim(),
            transcript: [...s.transcript, {
              speaker: msg.speaker ?? 'unknown',
              text: msg.text,
              timestamp: Date.now(),
            }],
          }))
        } else if (msg.type === 'status') {
          if (msg.fullTranscript) {
            fullTranscriptRef.current = msg.fullTranscript
            setState(s => ({ ...s, fullTranscript: msg.fullTranscript, status: msg.status }))
          } else {
            setState(s => ({ ...s, status: msg.status }))
          }
        } else if (msg.type === 'error') {
          setState(s => ({ ...s, error: msg.message, status: 'error' }))
        }
      }

      ws.onerror = () => setState(s => ({ ...s, error: 'Erro na conexão WebSocket', status: 'error' }))

      processor.onaudioprocess = (e) => {
        if (ws.readyState === WebSocket.OPEN) {
          const channelData = e.inputBuffer.getChannelData(0)
          const base64 = pcmToBase64(channelData)
          ws.send(JSON.stringify({ type: 'chunk', sessionId, audio: base64, timestamp: Date.now() }))
        }
      }

      source.connect(processor)
      processor.connect(audioContext.destination)

    } catch (err) {
      setState(s => ({ ...s, error: `Erro ao iniciar gravação: ${err}`, status: 'error' }))
    }
  }, [patientId, doctorId, specialty])

  const stopRecording = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop())
    processorRef.current?.disconnect()
    audioContextRef.current?.close()

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end', sessionId: sessionIdRef.current }))
      wsRef.current.close()
    }

    setState(s => ({ ...s, isRecording: false, status: 'processing' }))
    return fullTranscriptRef.current.trim()
  }, [])

  const reset = useCallback(() => {
    sessionIdRef.current = crypto.randomUUID()
    fullTranscriptRef.current = ''
    setState({ isRecording: false, sessionId: null, transcript: [], fullTranscript: '', error: null, status: 'idle' })
  }, [])

  const getFullTranscript = useCallback(() => fullTranscriptRef.current.trim(), [])

  return { ...state, startRecording, stopRecording, reset, getFullTranscript }
}
