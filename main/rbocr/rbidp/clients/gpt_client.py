import json
import urllib.request
import urllib.error
import ssl
 
def call_fortebank_gpt(prompt: str, model: str = "gpt-4o-mini", temperature: float = 0.1, max_tokens: int = 200) -> str:
    """
    Calls the internal ForteBank GPT endpoint and returns the model's response as a string.
    """

    # url = "https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2" 
    url = "https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2"
    payload = {
        "Model": model,
        "Content": prompt,
        "Temperature": temperature,
        "MaxTokens": max_tokens
    }
 
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "*/*"
    }, method="POST")
 
    # ignore SSL verification (self-signed certs)
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=context) as response:
            raw = response.read().decode("utf-8")
        return raw
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            body = ""
        msg = f"ForteBank GPT HTTPError {getattr(e, 'code', '')} {getattr(e, 'reason', '')}: {body}"
        print(msg)
        raise RuntimeError(msg)
    except urllib.error.URLError as e:
        msg = f"ForteBank GPT URLError: {getattr(e, 'reason', e)}"
        print(msg)
        raise RuntimeError(msg)
    except ssl.SSLError as e:
        msg = f"ForteBank GPT SSLError: {e}"
        print(msg)
        raise
    except Exception as e:
        msg = f"ForteBank GPT unexpected error: {e}"
        print(msg)
        raise
 
def ask_gpt(prompt: str, model: str = "gpt-4o-mini", temperature: float = 0.1, max_tokens: int = 200) -> str:
    raw = call_fortebank_gpt(prompt, model=model, temperature=temperature, max_tokens=max_tokens)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            choices = obj.get("choices")
            if isinstance(choices, list) and choices:
                c0 = choices[0]
                if isinstance(c0, dict):
                    msg = c0.get("message")
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if isinstance(content, str):
                            return content
                    text = c0.get("text")
                    if isinstance(text, str):
                        return text
            content = obj.get("content")
            if isinstance(content, str):
                return content
        return raw
    except Exception:
        return raw
 

# import json
# import urllib.request
# import ssl
 
# def call_fortebank_gpt(prompt: str, model: str = "gpt-4o-mini", temperature: float = 0.1, max_tokens: int = 200) -> str:
#     """
#     Calls the internal ForteBank GPT endpoint and returns the model's response as a string.
#     """
 
#     url = "https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2"
#     payload = {
#         "Model": model,
#         "Content": prompt,
#         "Temperature": temperature,
#         "MaxTokens": max_tokens
#     }
 
#     data = json.dumps(payload).encode("utf-8")
#     req = urllib.request.Request(url, data=data, headers={
#         "Content-Type": "application/json",
#         "Accept": "*/*"
#     }, method="POST")
 
#     # ignore SSL verification (self-signed certs)
#     context = ssl._create_unverified_context()
 
#     with urllib.request.urlopen(req, context=context) as response:
#         raw = response.read().decode("utf-8")
 
#     return raw

# def ask_gpt(prompt: str, model: str = "gpt-4o-mini", temperature: float = 0.1, max_tokens: int = 200) -> str:
#     raw = call_fortebank_gpt(prompt, model=model, temperature=temperature, max_tokens=max_tokens)
#     try:
#         obj = json.loads(raw)
#         if isinstance(obj, dict):
#             choices = obj.get("choices")
#             if isinstance(choices, list) and choices:
#                 c0 = choices[0]
#                 if isinstance(c0, dict):
#                     msg = c0.get("message")
#                     if isinstance(msg, dict):
#                         content = msg.get("content")
#                         if isinstance(content, str):
#                             return content
#                     text = c0.get("text")
#                     if isinstance(text, str):
#                         return text
#             content = obj.get("content")
#             if isinstance(content, str):
#                 return content
#         return raw
#     except Exception:
#         return raw