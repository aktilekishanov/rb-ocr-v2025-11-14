[Note: we are utilizing the server of a colleague for now]

------------------------------------------------------------------------------------

CURRENT SERVER:
IP:         10.0.97.164
DOMAIN:     cfo-prod-llm-uv01.fortebank.com

nginx/sites-enabled/:
- main:     8004
- main-dev: 8006

- Docker version 28.5.1, build e180ab8
- Docker Compose version v2.40.2

------------------------------------------------------------------------------------

OWN SERVER FOR FASTAPI SERVICE:
IP:         10.0.94.226
DOMAIN:     rb-ocr-dev-app-uv01.fortebank.com

ACCOUNT:    rb_admin
PASSWORD:   Qw12er34
NEW PASS:   Ret_ban_ocr1

------------------------------------------------------------------------------------

OWN SERVER FOR DATABASE:
IP:         10.0.94.227
DOMAIN:     rb-ocr-dev-pgsql-uv01.fortebank.com

ACCOUNT:    rbocruser
PASSWORD:   rbocruserDEV
DB NAME:    rbocrdb

------------------------------------------------------------------------------------

EXTERNAL SERVER FOR TESSERACT SERVICE:
IP:         10.0.84.144
DOMAIN:     ocr.fortebank.com

ENDPOINT:
1. POST    https://ocr.fortebank.com/v2/pdf
    form-data: 
        - key: file
        - value: <file>

2. GET     https://ocr.fortebank.com/v2/result/<uuid>

------------------------------------------------------------------------------------

EXTERNAL SERVER FOR LLM SERVICE:
IP:         10.0.84.144
DOMAIN:     dl-ai-dev-app01-uv01.fortebank.com

CURRENT ENDPOINT (as of 2025-12-03):
1. POST    https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions
    raw (application/json):
    ```json
    {
        "Model": "gpt-4o",
        "Content": "bonsoir, ca va?",
        "Temperature": 0.1,
        "MaxTokens": 100
    }
    ```

    response (application/json):
    ```json
    {
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "logprobs": null,
                "message": {
                    "annotations": [],
                    "content": "Bonsoir ! Oui, ça va bien, merci. Et toi, comment ça va ?",
                    "refusal": null,
                    "role": "assistant"
                }
            }
        ],
        "created": 1764226180,
        "id": "chatcmpl-CgQ6uXQHNuHIGSrUeerFWWnL1c68j",
        "model": "gpt-4o-2024-08-06",
        "object": "chat.completion",
        "service_tier": "default",
        "system_fingerprint": "fp_689bad8e9a",
        "usage": {
            "completion_tokens": 17,
            "completion_tokens_details": {
                "accepted_prediction_tokens": 0,
                "audio_tokens": 0,
                "reasoning_tokens": 0,
                "rejected_prediction_tokens": 0
            },
            "prompt_tokens": 13,
            "prompt_tokens_details": {
                "audio_tokens": 0,
                "cached_tokens": 0
            },
            "total_tokens": 30
        }
    }
    ```

DEPRECATED ENDPOINT (replaced 2025-12-03):
- https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2
- No longer used in production code


POSTMAN LOGS FOR LLM ENDPOINT CALL:
"""
POST https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions2003.54 s
Warning: Self signed certificate in certificate chain
POST /openai/payment/out/completions HTTP/1.1
Content-Type: text/plain
User-Agent: PostmanRuntime/7.28.0
Accept: */*
Postman-Token: 90191572-0be0-4c7f-a016-338c592fde6c
Host: dl-ai-dev-app01-uv01.fortebank.com
Accept-Encoding: gzip, deflate, br
Connection: keep-alive
Content-Length: 110
{
"Model": "gpt-4o",
"Content": "bonsoir, ca va?",
"Temperature": 0.1,
"MaxTokens": 100
}
HTTP/1.1 200 OK
Server: nginx/1.24.0
Date: Wed, 03 Dec 2025 11:42:07 GMT
Content-Type: application/json
Content-Length: 644
Connection: keep-alive
{"choices":[{"finish_reason":"stop","index":0,"logprobs":null,"message":{"annotations":[],"content":"Bonsoir ! Oui, ça va bien, merci. Et toi, comment ça va ?","refusal":null,"role":"assistant"}}],"created":1764762125,"id":"chatcmpl-CifXB1wPaY8PhU7X2sb652Obf5Llz","model":"gpt-4o-2024-08-06","object":"chat.completion","service_tier":"default","system_fingerprint":"fp_e819e3438b","usage":{"completion_tokens":17,"completion_tokens_details":{"accepted_prediction_tokens":0,"audio_tokens":0,"reasoning_tokens":0,"rejected_prediction_tokens":0},"prompt_tokens":13,"prompt_tokens_details":{"audio_tokens":0,"cached_tokens":0},"total_tokens":30}}
"""


------------------------------------------------------------------------------------
