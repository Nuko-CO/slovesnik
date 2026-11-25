"""Обращение к Gemini API с автоматическим переключением моделей."""
import json
import os
import re
import time

import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Перебираем по порядку: если модель перегружена или недоступна — берём следующую.
MODELS = [
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-flash-lite-latest",
]


class LLMError(Exception):
    pass


def _api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        raise LLMError("Не найден GEMINI_API_KEY (добавьте его в Secrets).")


def generate(prompt, system=None, history=None, as_json=False, temperature=0.8):
    if not as_json:
        return _request(prompt, system, history, False, temperature)
    # модель изредка возвращает испорченный JSON — тогда просто спрашиваем ещё раз
    for attempt in range(3):
        text = _request(prompt, system, history, True, temperature)
        try:
            return _parse_json(text)
        except LLMError:
            if attempt == 2:
                raise


def _request(prompt, system, history, as_json, temperature):
    """history — список {"role": "user"|"model", "text": ...} для режима чата."""
    contents = [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in (history or [])]
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    body = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"

    key = _api_key()
    last_error = ""
    for model in MODELS:
        for attempt in range(2):
            try:
                r = requests.post(API_URL.format(model=model), params={"key": key}, json=body, timeout=120)
            except requests.RequestException as e:
                last_error = str(e)
                continue
            if r.status_code == 200:
                parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                if text:
                    return text
                last_error = "пустой ответ модели"
                break
            last_error = f"{model}: HTTP {r.status_code}"
            if r.status_code in (429, 500, 503) and attempt == 0:
                time.sleep(2)
                continue
            break
    raise LLMError(f"Сервис ИИ временно недоступен ({last_error}). Попробуйте ещё раз через минуту.")


def _parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        try:
            return json.loads(m.group(0))
        except (AttributeError, json.JSONDecodeError):
            pass
        raise LLMError("ИИ вернул ответ в неверном формате, попробуйте сгенерировать ещё раз.")
