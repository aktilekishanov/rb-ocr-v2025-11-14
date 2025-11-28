[Note: we are utilizing the server of a colleague for now]

------------------------------------------------------------------------------------

CURRENT SERVER:
IP:         10.0.97.164
DOMAIN:     cfo-prod-llm-uv01.fortebank.com

nginx/sites-enabled/:
- main:     8004
- main-dev: 8006

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

ACCOUNT:    TBA
PASSWORD:   TBA

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

ENDPOINT:
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





