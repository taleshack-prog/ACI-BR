# 🏥 ACI-BR — Ambient Clinical Intelligence (Brasil)

Sistema de documentação clínica autônoma via captura de áudio ambiental, estruturação SOAP automática e interoperabilidade HL7 FHIR R4 com prontuários brasileiros (TASY, MV, PEPs).

---

## 🧠 Arquitetura (4 Camadas)

```
FRONTEND (React/Next.js + Web Audio API)
    ↕ HTTPS + OAuth2
BACKEND (FastAPI + Node.js)
    ├── Audio Pipeline (Diarization + ASR)
    ├── Clinical NLP (C-NER + Entity Linking)
    └── FHIR Bridge (SOAP → FHIR R4)
    ↕ FHIR R4 + TLS 1.3
DATA LAYER (MongoDB + PostgreSQL)
    ↕
EXTERNAL EHR (TASY, MV, ICP-Brasil)
```

## 📦 Stack Tecnológico

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Frontend | React 18 + Vite + TypeScript | HMR rápido, type safety |
| Backend | FastAPI (Python 3.11) | Async nativo, ML integration |
| DB Staging | MongoDB | Sessões temporárias, TTL, JSONB flexível |
| DB Production | PostgreSQL 15 | ACID, FHIR persistence, audit trail |
| ASR | Whisper V3 fine-tuned pt-BR | Léxico médico especializado |
| Diarização | pyannote.audio | Speaker embeddings, VAD |
| NLP | BioBERT + custom medical dict | C-NER, ICD-10/SNOMED-CT/LOINC |
| Padrão | HL7 FHIR R4 | Interop TASY, MV, Philips |
| Auth | OAuth2 + JWT + ICP-Brasil | LGPD compliance |
| Crypto | AES-256 + TLS 1.3 | PII protection |
| Deploy | Docker + Kubernetes | Escalabilidade horizontal |

---

## 🚀 Setup Rápido

### Pré-requisitos
- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- Git

### 1. Clone e configure

```bash
git clone https://github.com/taleshack-prog/ACI-BR.git
cd ACI-BR
cp .env.example .env
# Edite .env com suas credenciais
```

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Docker (recomendado)

```bash
docker-compose up --build
```

Acesse:
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs
- MongoDB: localhost:27017
- PostgreSQL: localhost:5432

---

## 📋 Fluxo Completo

```
1. Captura de Áudio (Web Audio API, PCM 16kHz mono)
2. Streaming via WebSocket (chunks 100ms)
3. VAD + Diarização (médico vs. paciente)
4. ASR pt-BR (Whisper V3 fine-tuned)
5. C-NER (BioBERT) → extração de entidades
6. Entity Linking (ICD-10, SNOMED-CT, LOINC, TUSS)
7. Negation Detection
8. Geração SOAP estruturado
9. Parser SOAP → FHIR R4 Bundle
10. Interface de revisão (human-in-the-loop < 5s)
11. Write-back ao PEP via FHIR R4
12. Auditoria + Persistência PostgreSQL
```

---

## 🗂️ Estrutura de Pastas

```
ACI-BR/
├── frontend/          # React + Vite + TypeScript
├── backend/           # FastAPI + ML pipeline
├── docs/              # Documentação técnica
├── infra/             # Terraform + Kubernetes
├── scripts/           # Utilitários de setup/deploy
└── .github/workflows/ # CI/CD GitHub Actions
```

---

## 🔐 Segurança & Compliance

- **LGPD**: Anonimização do áudio após extração de entidades
- **AES-256**: Dados em repouso (PII)
- **TLS 1.3**: Dados em trânsito
- **OAuth2 + ICP-Brasil**: Autenticação e assinatura digital
- **Audit Trail**: Registro imutável de todas as ações

---

## 📚 Documentação

- [Arquitetura](docs/ARCHITECTURE.md)
- [API FHIR](docs/API.md)
- [Segurança & LGPD](docs/SECURITY.md)
- [Guia FHIR R4](docs/FHIR_GUIDE.md)
- [Deploy](docs/DEPLOYMENT.md)

---

## 🗓️ Roadmap

- [x] Estrutura do projeto
- [x] Schema banco de dados
- [x] Especificação FHIR R4
- [ ] FastAPI core + OAuth2
- [ ] Pipeline de áudio (Diarization + ASR)
- [ ] Clinical NLP (C-NER + Entity Linking)
- [ ] Frontend Review Interface
- [ ] EHR Write-back (TASY/MV)
- [ ] CI/CD + Kubernetes deploy

---

## 📄 Licença

MIT — veja [LICENSE](LICENSE)
