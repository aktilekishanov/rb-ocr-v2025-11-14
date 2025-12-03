# RB OCR System Architecture

> **Document Purpose**: This document provides comprehensive visual representations of the RB OCR system architecture, including data flow, component interactions, and infrastructure layout.

---

## Table of Contents
1. [High-Level Data Flow](#1-high-level-data-flow)
2. [Sequence Diagram](#2-sequence-diagram)
3. [Component Architecture](#3-component-architecture)
4. [Infrastructure Layout](#4-infrastructure-layout)
5. [Integration Details](#5-integration-details)

---

## 1. High-Level Data Flow

This diagram illustrates the complete journey of a document through the system, from user upload to final processing.

```mermaid
flowchart TB
    %% User and Mobile
    User([User])
    MobileApp[Mobile Application]
    
    %% Messaging Layer
    Kafka{{Kafka Topic<br/>dl-loan-delay.event.docs-uploaded}}
    
    %% Core Services
    IDPService[RB Loan Deferment IDP Service<br/>10.0.97.164]
    MinIO[(MinIO Object Storage<br/>s3-dev.fortebank.com:9000<br/>Bucket: loan-statements-dev)]
    
    FastAPI[FastAPI Service<br/>10.0.94.226<br/>rb-ocr-dev-app-uv01]
    
    %% External Services
    Tesseract[Tesseract OCR Service<br/>10.0.84.144<br/>ocr.fortebank.com]
    LLM[LLM Service GPT-4o<br/>10.0.84.144<br/>dl-ai-dev-app01-uv01]
    
    %% Database
    PostgreSQL[(PostgreSQL Database<br/>10.0.94.227<br/>rb-ocr-dev-pgsql-uv01)]
    
    %% Unknown Component
    Unknown[Unknown Service<br/>TBD]
    
    %% Flow
    User -->|1. Upload Document| MobileApp
    MobileApp -->|2. Upload to Storage| MinIO
    MobileApp -->|3. Publish Event| Kafka
    
    Kafka -->|4. Consume Event| IDPService
    IDPService -->|5. Download File| MinIO
    
    IDPService -->|6. POST /v1/verify<br/>Document + Metadata| FastAPI
    
    FastAPI -->|7a. Extract Text| Tesseract
    Tesseract -->|7b. OCR Result| FastAPI
    
    FastAPI -->|8a. Analyze Content| LLM
    LLM -->|8b. Analysis Result| FastAPI
    
    FastAPI -->|9. Store Results| PostgreSQL
    FastAPI -->|10. Verification Response| IDPService
    
    IDPService -->|11. POST Request| Unknown
    
    style User fill:#e1f5ff,stroke:#01579b
    style MobileApp fill:#b3e5fc,stroke:#0277bd
    style Kafka fill:#fff9c4,stroke:#f57f17
    style IDPService fill:#c8e6c9,stroke:#388e3c
    style MinIO fill:#f8bbd0,stroke:#c2185b
    style FastAPI fill:#ffccbc,stroke:#d84315
    style Tesseract fill:#d1c4e9,stroke:#512da8
    style LLM fill:#d1c4e9,stroke:#512da8
    style PostgreSQL fill:#b2dfdb,stroke:#00695c
    style Unknown fill:#eeeeee,stroke:#757575,stroke-dasharray: 5 5
```

---

## 2. Sequence Diagram

This diagram shows the detailed interaction timeline between all system components.

```mermaid
sequenceDiagram
    participant User
    participant Mobile as Mobile App
    participant MinIO as MinIO Storage
    participant Kafka
    participant IDP as RB Loan Deferment<br/>IDP Service
    participant FastAPI as FastAPI Service<br/>/v1/verify
    participant Tesseract as Tesseract OCR
    participant LLM as LLM Service<br/>GPT-4o
    participant DB as PostgreSQL
    participant Unknown as Unknown Service
    
    User->>Mobile: Upload Document
    Mobile->>MinIO: Store Document
    MinIO-->>Mobile: Storage Path (s3_path)
    
    Mobile->>Kafka: Publish Event<br/>Topic: dl-loan-delay.event.docs-uploaded
    Note over Kafka: Event Body:<br/>{request_id, document_type,<br/>s3_path, iin, first_name,<br/>last_name, second_name}
    
    Kafka->>IDP: Consume Event
    IDP->>MinIO: Download Document<br/>(using s3_path)
    MinIO-->>IDP: Document File
    
    IDP->>FastAPI: POST /v1/verify<br/>(file + metadata)
    
    activate FastAPI
    FastAPI->>Tesseract: POST /v2/pdf<br/>(document file)
    Tesseract-->>FastAPI: UUID
    FastAPI->>Tesseract: GET /v2/result/{uuid}
    Tesseract-->>FastAPI: OCR Text Result
    
    FastAPI->>LLM: POST /openai/payment/out/completions<br/>(extracted text + prompts)
    Note over LLM: Model: gpt-4o<br/>Temperature: 0.1<br/>MaxTokens: 100
    LLM-->>FastAPI: Analysis Result
    
    FastAPI->>DB: Store Verification Results
    DB-->>FastAPI: Confirmation
    
    FastAPI-->>IDP: Verification Response<br/>(JSON result)
    deactivate FastAPI
    
    IDP->>Unknown: POST Request<br/>(TBD)
    Unknown-->>IDP: Response (TBD)
```

---

## 3. Component Architecture

This diagram illustrates the system's component organization and dependencies.

```mermaid
graph TB
    subgraph "Client Layer"
        Mobile[Mobile Application]
    end
    
    subgraph "Message Queue Layer"
        Kafka[Kafka<br/>dl-loan-delay.event.docs-uploaded]
    end
    
    subgraph "Storage Layer"
        MinIO[MinIO Object Storage<br/>10.0.99.212<br/>s3-dev.fortebank.com:9000]
    end
    
    subgraph "Application Layer - Current Server (10.0.97.164)"
        IDP[RB Loan Deferment IDP Service<br/>Consumer & Orchestrator]
    end
    
    subgraph "Application Layer - FastAPI Server (10.0.94.226)"
        FastAPI[FastAPI Service<br/>Document Verification Engine]
        subgraph "FastAPI Components"
            Endpoint["/v1/verify Endpoint"]
            Pipeline[Processing Pipeline]
            Integration[External Service Integration]
        end
        FastAPI --> Endpoint
        Endpoint --> Pipeline
        Pipeline --> Integration
    end
    
    subgraph "External Services Layer (10.0.84.144)"
        Tesseract[Tesseract OCR Service<br/>ocr.fortebank.com]
        LLM[LLM Service<br/>dl-ai-dev-app01-uv01<br/>GPT-4o Model]
    end
    
    subgraph "Database Layer (10.0.94.227)"
        PostgreSQL[PostgreSQL Database<br/>rb-ocr-dev-pgsql-uv01]
    end
    
    subgraph "Unknown Integration"
        Unknown[Unknown Service<br/>TBD]
    end
    
    Mobile -->|Upload| MinIO
    Mobile -->|Event| Kafka
    Kafka -->|Consume| IDP
    IDP -->|Download| MinIO
    IDP -->|Verify Request| FastAPI
    Integration -->|OCR| Tesseract
    Integration -->|AI Analysis| LLM
    Pipeline -->|Store| PostgreSQL
    IDP -->|POST| Unknown
    
    style Mobile fill:#b3e5fc,stroke:#0277bd
    style Kafka fill:#fff9c4,stroke:#f57f17
    style MinIO fill:#f8bbd0,stroke:#c2185b
    style IDP fill:#c8e6c9,stroke:#388e3c
    style FastAPI fill:#ffccbc,stroke:#d84315
    style Tesseract fill:#d1c4e9,stroke:#512da8
    style LLM fill:#d1c4e9,stroke:#512da8
    style PostgreSQL fill:#b2dfdb,stroke:#00695c
    style Unknown fill:#eeeeee,stroke:#757575,stroke-dasharray: 5 5
```

---

## 4. Infrastructure Layout

This diagram shows the physical/network infrastructure distribution.

```mermaid
graph TB
    subgraph Internet["Internet / Mobile Network"]
        Mobile[Mobile Application]
    end
    
    subgraph DevInfra["Development Infrastructure - ForteBank Network"]
        
        subgraph MinIOServer["MinIO Server<br/>10.0.99.212<br/>s3-dev.fortebank.com"]
            MinIOService[MinIO Service<br/>Port: 9000<br/>Bucket: loan-statements-dev]
            MinIOCreds["Credentials:<br/>Access: fyz13d2czRW7l4sBW8gD<br/>Secret: 1ix...1A<br/>API: s3v4"]
        end
        
        subgraph CurrentServer["Current Server<br/>10.0.97.164<br/>cfo-prod-llm-uv01"]
            IDPService[IDP Service]
            Nginx1[Nginx<br/>Port 8004: main<br/>Port 8006: main-dev]
            Docker1[Docker 28.5.1<br/>Docker Compose v2.40.2]
        end
        
        subgraph FastAPIServer["FastAPI Server<br/>10.0.94.226<br/>rb-ocr-dev-app-uv01"]
            FastAPIApp[FastAPI Application<br/>Document Verification]
            FastAPIDep[Dependencies:<br/>Tesseract Client<br/>LLM Client<br/>PostgreSQL Client]
        end
        
        subgraph DBServer["Database Server<br/>10.0.94.227<br/>rb-ocr-dev-pgsql-uv01"]
            PostgreSQL[(PostgreSQL<br/>Database)]
            DBCreds["Account: TBA<br/>Password: TBA"]
        end
        
        subgraph ExternalServer["External Services Server<br/>10.0.84.144"]
            TesseractAPI[Tesseract OCR<br/>ocr.fortebank.com<br/>Endpoints:<br/>POST /v2/pdf<br/>GET /v2/result/{uuid}]
            LLMAPI[LLM Service<br/>dl-ai-dev-app01-uv01<br/>Endpoint:<br/>POST /openai/payment/out/completions]
        end
        
        KafkaCluster{{Kafka Cluster<br/>Topic: dl-loan-delay.event.docs-uploaded}}
    end
    
    Mobile -->|HTTPS| MinIOService
    Mobile -->|Event| KafkaCluster
    KafkaCluster -->|Subscribe| IDPService
    IDPService -->|S3 API| MinIOService
    IDPService -->|HTTP POST| FastAPIApp
    FastAPIApp -->|HTTPS| TesseractAPI
    FastAPIApp -->|HTTPS| LLMAPI
    FastAPIApp -->|SQL| PostgreSQL
    
    style Mobile fill:#b3e5fc,stroke:#0277bd
    style MinIOServer fill:#f8bbd0,stroke:#c2185b
    style CurrentServer fill:#c8e6c9,stroke:#388e3c
    style FastAPIServer fill:#ffccbc,stroke:#d84315
    style DBServer fill:#b2dfdb,stroke:#00695c
    style ExternalServer fill:#d1c4e9,stroke:#512da8
    style KafkaCluster fill:#fff9c4,stroke:#f57f17
```

---

## 5. Integration Details

### 5.1 Kafka Event Schema

**Topic**: `dl-loan-delay.event.docs-uploaded`

**Event Body**:
```json
{
    "request_id": 123123,
    "document_type": 4,
    "s3_path": "some_s3_address",
    "iin": 960125000000,
    "first_name": "Иван",
    "last_name": "Иванов",
    "second_name": "Иванович"
}
```

### 5.2 MinIO Configuration (DEV)

| Property | Value |
|----------|-------|
| **IP** | 10.0.99.212 |
| **Domain** | s3-dev.fortebank.com:9000 |
| **Bucket** | loan-statements-dev |
| **Access Key** | fyz13d2czRW7l4sBW8gD |
| **Secret Key** | 1ixYVVoZKSnG0rwfTy0vnqQplupXOOn8DF9gS1A |
| **API Version** | s3v4 |
| **Path Style** | auto |

### 5.3 FastAPI Endpoint

**Endpoint**: `POST /v1/verify`

**Purpose**: Receives document verification requests from the IDP service, processes documents through OCR and LLM pipelines, stores results in PostgreSQL, and returns verification response.

### 5.4 Tesseract OCR Integration

**Base URL**: `https://ocr.fortebank.com`

**Endpoints**:
1. `POST /v2/pdf` - Submit document for OCR processing
   - Form-data: `file` (document file)
   - Returns: UUID for result retrieval
   
2. `GET /v2/result/{uuid}` - Retrieve OCR results
   - Returns: Extracted text from document

### 5.5 LLM Service Integration

**Base URL**: `https://dl-ai-dev-app01-uv01.fortebank.com`

**Endpoint**: `POST /openai/payment/out/completions`

**Request Body**:
```json
{
    "Model": "gpt-4o",
    "Content": "extracted text + prompts",
    "Temperature": 0.1,
    "MaxTokens": 100
}
```

**Response Structure**:
```json
{
    "choices": [{
        "message": {
            "content": "analysis result",
            "role": "assistant"
        },
        "finish_reason": "stop"
    }],
    "model": "gpt-4o-2024-08-06",
    "usage": {
        "total_tokens": 30,
        "prompt_tokens": 13,
        "completion_tokens": 17
    }
}
```

### 5.6 Server Infrastructure

| Server Type | IP | Domain | Details |
|-------------|----|----|---------|
| **Current Server** | 10.0.97.164 | cfo-prod-llm-uv01.fortebank.com | Nginx (8004, 8006)<br/>Docker 28.5.1 |
| **FastAPI Server** | 10.0.94.226 | rb-ocr-dev-app-uv01.fortebank.com | Account: rb_admin<br/>Password: Ret_ban_ocr1 |
| **Database Server** | 10.0.94.227 | rb-ocr-dev-pgsql-uv01.fortebank.com | PostgreSQL<br/>Account: TBA |
| **External Services** | 10.0.84.144 | ocr.fortebank.com<br/>dl-ai-dev-app01-uv01 | Tesseract OCR<br/>LLM Service |
| **MinIO Storage** | 10.0.99.212 | s3-dev.fortebank.com:9000 | Object Storage |

### 5.7 Unknown Integration Point

> [!WARNING]
> **Unknown Service Integration**
> 
> The IDP service sends a POST request to an unknown service after receiving the verification response from FastAPI. This integration point needs to be documented.
> 
> **Action Required**: Identify the target service and document:
> - Service purpose and endpoint
> - Request/response schema
> - Error handling requirements

---

## Processing Flow Summary

```mermaid
stateDiagram-v2
    [*] --> UserUpload: User initiates
    UserUpload --> StorageAndEvent: Mobile app processes
    StorageAndEvent --> EventConsumption: Kafka publishes
    EventConsumption --> FileRetrieval: IDP consumes
    FileRetrieval --> Verification: IDP retrieves file
    Verification --> OCRProcessing: FastAPI receives
    OCRProcessing --> LLMAnalysis: Text extracted
    LLMAnalysis --> DataStorage: Analysis complete
    DataStorage --> ResponseSent: Results stored
    ResponseSent --> UnknownIntegration: IDP receives response
    UnknownIntegration --> [*]: Process complete
    
    note right of Verification
        POST /v1/verify endpoint
        Orchestrates OCR and LLM
    end note
    
    note right of DataStorage
        PostgreSQL Database
        10.0.94.227
    end note
    
    note right of UnknownIntegration
        Unknown service
        Needs documentation
    end note
```

---

## Document Metadata

- **Created**: 2025-12-02
- **Source**: [integration-details.md](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/.etc/.info-project-management/integration-details.md)
- **Related**: [servers.md](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/.etc/.info-project-management/servers.md)
- **Status**: Active Development
