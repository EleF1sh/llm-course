from __future__ import annotations

import configparser
import json
import sys
from pathlib import Path

import httpx

CONFIG_PATH = Path(__file__).with_name("config.ini")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"缺少 {CONFIG_PATH.name}。请复制 config.ini.example 为 config.ini 并填写。"
        )
    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH, encoding="utf-8")
    section = parser["llm"]
    return {
        "base_url": section.get("base_url", "https://api.openai.com/v1").rstrip("/"),
        "api_key": section.get("api_key", ""),
        "model": section.get("model", "gpt-4o-mini"),
        "temperature": section.getfloat("temperature", 0.7),
        "timeout": section.getfloat("timeout", 60),
    }


def build_payload(cfg: dict, messages: list[dict], stream: bool) -> dict:
    return {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg["temperature"],
        "stream": stream,
    }


def chat_once(cfg: dict, messages: list[dict]) -> str:
    """Non-streaming one-shot completion."""
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=cfg["timeout"]) as client:
        resp = client.post(url, headers=headers, json=build_payload(cfg, messages, False))
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def chat_stream(cfg: dict, messages: list[dict]) -> str:
    """Streaming completion with typewriter-style stdout."""
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    chunks: list[str] = []
    with httpx.Client(timeout=cfg["timeout"]) as client:
        with client.stream(
            "POST",
            url,
            headers=headers,
            json=build_payload(cfg, messages, True),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    payload = line[6:].strip()
                else:
                    continue
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = (
                    event.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content")
                )
                if delta:
                    chunks.append(delta)
                    print(delta, end="", flush=True)
    print()
    return "".join(chunks)


def main() -> None:
    cfg = load_config()
    if not cfg["api_key"] or cfg["api_key"] == "replace-me":
        print("请先在 config.ini 填写有效的 api_key / base_url / model。")
        sys.exit(1)

    # Use stream mode by default; set PRACTICE_STREAM=0 for non-stream.
    import os

    use_stream = os.getenv("PRACTICE_STREAM", "1") != "0"
    history: list[dict] = [
        {
            "role": "system",
            "content": "你是一个简洁、友好的中文助手。",
        }
    ]

    print("Practice01 多轮对话已启动。输入内容回车发送；Ctrl+C 退出。")
    print(f"模式: {'stream' if use_stream else 'non-stream'} | model={cfg['model']}")

    while True:
        try:
            user = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not user:
            continue
        history.append({"role": "user", "content": user})
        print("助手: ", end="", flush=True)
        try:
            if use_stream:
                answer = chat_stream(cfg, history)
            else:
                answer = chat_once(cfg, history)
                print(answer)
        except Exception as exc:
            print(f"\n[错误] {exc}")
            history.pop()  # drop failed user turn
            continue
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
