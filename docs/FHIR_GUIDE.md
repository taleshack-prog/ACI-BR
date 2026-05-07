# FHIR R4 Guide — ACI-BR

## Recursos Implementados

| Recurso FHIR | Endpoint | Origem no SOAP |
|---|---|---|
| `DocumentReference` | `POST /fhir/r4/DocumentReference` | Nota SOAP completa |
| `Condition` | `POST /fhir/r4/Condition` | Assessment (diagnósticos CID-10) |
| `Observation` | `POST /fhir/r4/Observation` | Objective (sinais vitais LOINC) |
| `MedicationRequest` | `POST /fhir/r4/MedicationRequest` | Plan (prescrições TUSS) |
| `Bundle` | `POST /fhir/r4/Bundle` | Write-back atômico ao PEP |

## Mapeamento SOAP → FHIR

```
S (Subjective)  → Condition (clinicalStatus: active, verificationStatus: provisional)
O (Objective)   → Observation (category: vital-signs, code: LOINC)
A (Assessment)  → Condition (code: ICD-10, verificationStatus: confirmed)
P (Plan)        → MedicationRequest (status: active, intent: order)
```

## Ontologias Utilizadas

- **ICD-10**: Diagnósticos (`http://hl7.org/fhir/sid/icd-10`)
- **SNOMED-CT**: Sintomas e procedimentos (`http://snomed.info/sct`)
- **LOINC**: Sinais vitais e exames (`http://loinc.org`)
- **TUSS**: Medicamentos brasileiros (`http://www.anvisa.gov.br/tuss`)

## Fluxo de Write-back

```
1. GET /Patient?identifier={CPF}  — valida paciente no PEP
2. POST /Encounter                 — abre atendimento
3. POST /Bundle (transaction)      — escrita atômica:
   ├── DocumentReference (SOAP)
   ├── Condition[] (diagnósticos)
   ├── Observation[] (sinais vitais)
   └── MedicationRequest[] (prescrições)
```

## Headers Obrigatórios

```http
Authorization: Bearer {JWT_TOKEN}
Content-Type: application/fhir+json
X-Correlation-ID: {UUID}           # rastreamento distribuído
X-Idempotency-Key: {UUID}          # retry seguro
```

## Erros (OperationOutcome)

```json
{
  "resourceType": "OperationOutcome",
  "issue": [{
    "severity": "error",
    "code": "invalid",
    "diagnostics": "Descrição do erro",
    "expression": ["Condition.code.coding"]
  }]
}
```

## Compatibilidade EHR Brasileiros

| Sistema | Protocolo | Status |
|---|---|---|
| TASY (Philips) | FHIR R4 nativo | ✅ Planejado |
| MV (Soul MV) | FHIR R4 + adaptador | ✅ Planejado |
| Prontuário Eletrônico (PEP) | FHIR R4 | ✅ Planejado |
| Sistemas legados (XML/SQL) | Adaptador de tradução | 🔄 Roadmap |
