# Segurança & Compliance — ACI-BR

## LGPD (Lei Geral de Proteção de Dados)

### Princípios Implementados

1. **Minimização**: Coletamos apenas dados necessários para o prontuário.
2. **Finalidade**: Áudio processado exclusivamente para documentação clínica.
3. **Anonimização**: Arquivo de áudio descartado após extração de entidades.
4. **Consentimento**: Paciente ciente da gravação no início da consulta.
5. **Segurança**: AES-256 + TLS 1.3 em todas as camadas.

### Ciclo de Vida do Dado

```
Áudio bruto (PCM)
    ↓ [processamento em memória]
Transcrição + Entidades clínicas
    ↓ [LGPD: descarte do áudio em até 24h]
Nota SOAP (sem áudio)
    ↓ [revisão médica + aprovação]
FHIR Bundle → PEP (prontuário)
    ↓ [MongoDB TTL: 30 dias]
PostgreSQL (permanente, criptografado)
```

### Dados Protegidos (PII)

| Campo | Proteção |
|---|---|
| `contact_phone` | AES-256 (PostgreSQL `encrypted_pii`) |
| `contact_email` | AES-256 |
| `address` | AES-256 |
| Áudio original | Descarte automático em 24h |
| Transcrição bruta | TTL MongoDB 30 dias |

## Criptografia

### Em Repouso
- PostgreSQL PII: **AES-256-GCM**
- Chaves: AWS Secrets Manager (rotação automática 90 dias)
- MongoDB: criptografia em nível de campo (MongoDB CSFLE)

### Em Trânsito
- API HTTPS: **TLS 1.3**
- WebSocket: **WSS (TLS 1.3)**
- Certificados: Let's Encrypt + renovação automática

## Autenticação & Autorização

```
OAuth2 Client Credentials Flow
    ↓
JWT (RS256, exp: 1h)
    ↓
RBAC: DOCTOR | ADMIN | AUDITOR
    ↓
ICP-Brasil (para assinatura digital de prescrições)
```

## Audit Trail

Todo acesso e modificação é registrado em `audit_logs` (PostgreSQL, imutável):

```sql
entity_type | entity_id | action | actor_id | old_values | new_values | timestamp
```

Ações auditadas: `CREATE`, `UPDATE`, `DELETE`, `REVIEW_APPROVED`, `SYNC`, `ACCESS`.

## ISO 27001 Controles Relevantes

- A.9: Controle de acesso
- A.10: Criptografia
- A.12: Segurança operacional (logs, monitoramento)
- A.14: Desenvolvimento seguro
- A.17: Continuidade do negócio (backup, retry logic)
- A.18: Conformidade (LGPD, CFM, CRM)
