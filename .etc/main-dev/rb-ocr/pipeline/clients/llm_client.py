"""
Client for the internal ForteBank LLM completion endpoint (dev).
"""

import json
import ssl
import urllib.request


def call_fortebank_llm(
    prompt: str, model: str = "gpt-4o", temperature: float = 0, max_tokens: int = 500
) -> str:
    """
    Calls the internal ForteBank LLM endpoint and returns the model's response as a string.
    """

    url = "https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions"
    payload = {
        "Model": model,
        "Content": prompt,
        "Temperature": temperature,
        "MaxTokens": max_tokens,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "Accept": "*/*"}, method="POST"
    )

    # WORKAROUND: ignore SSL verification for dev DMZ endpoint (self-signed certs).
    # SECURITY: this must be revisited for production deployments.
    context = ssl._create_unverified_context()

    with urllib.request.urlopen(req, context=context) as response:
        raw = response.read().decode("utf-8")

    return raw


def ask_llm(
    prompt: str, model: str = "gpt-4o", temperature: float = 0, max_tokens: int = 500
) -> str:
    """
    Calls the LLM and returns the full raw API response (pretty-printed JSON).
    
    The response includes metadata like usage stats, model version, and timing,
    which is valuable for debugging, monitoring, and cost tracking.
    
    The downstream filter (filter_llm_generic_response) will extract the actual
    content from choices[0].message.content.
    
    Returns:
        Pretty-printed JSON string of the full API response.
    """
    raw = call_fortebank_llm(prompt, model=model, temperature=temperature, max_tokens=max_tokens)
    try:
        # Parse to validate it's JSON, then pretty-print it
        obj = json.loads(raw)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        # If parsing fails, return raw string as-is
        return raw
