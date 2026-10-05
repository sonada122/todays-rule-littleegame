#!/usr/bin/env python3
"""《今天的规则》—— LLM 规则生成客户端（Stage 3）。

对接任意 OpenAI 兼容的 Chat Completions 接口（OpenAI / DeepSeek / 通义 /
本地 vLLM / 本仓库的 mock 服务）。LLM 只产出"JSON 参数组合 + 文案"，
参数一律经 dsl.py 校验，非法即丢弃；随后由谜题生成器与求解器验证可解性。

用法:
    export OPENAI_API_KEY=sk-xxx
    export OPENAI_BASE_URL=https://api.openai.com/v1   # 可选
    export OPENAI_MODEL=gpt-4o-mini                    # 可选
    python tools/llm_client.py --count 12 --theme "冰与火"

设计原则：任何网络/解析失败都回退到模板规则生成器，保证内容管线永不中断。
"""
import argparse
import json
import os
import sys

import requests

import rule_gen

DEFAULTS = {
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "timeout": 60,
    "temperature": 1.0,
}


class LLMConfig:
    def __init__(self, base_url=None, api_key=None, model=None,
                 timeout=None, temperature=None):
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL")
                         or DEFAULTS["base_url"]).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self.model = model or os.environ.get("OPENAI_MODEL") or DEFAULTS["model"]
        self.timeout = timeout or int(os.environ.get("OPENAI_TIMEOUT")
                                      or DEFAULTS["timeout"])
        self.temperature = (temperature if temperature is not None
                            else float(os.environ.get("OPENAI_TEMPERATURE")
                                       or DEFAULTS["temperature"]))

    @property
    def is_local(self):
        return "localhost" in self.base_url or "127.0.0.1" in self.base_url

    @property
    def configured(self):
        return bool(self.api_key) or self.is_local

    def endpoint(self):
        return f"{self.base_url}/chat/completions"


def _extract_json(text):
    """从模型输出中稳健地抽取 JSON（容忍 ```json 围栏与前后缀文字）。"""
    if not text:
        raise ValueError("空响应")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("无法从响应中解析 JSON")


def chat(cfg, system, user, json_mode=False):
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    payload = {
        "model": cfg.model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": cfg.temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    resp = requests.post(cfg.endpoint(), headers=headers, json=payload,
                         timeout=cfg.timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def generate_rules(count=10, theme="", cfg=None, allow_fallback=True,
                   verbose=False):
    """生成规则。返回 (rules: list[RuleSpec], source: 'llm'|'fallback')。"""
    cfg = cfg or LLMConfig()
    if not cfg.configured:
        if not allow_fallback:
            raise RuntimeError("未配置 LLM（缺少 OPENAI_API_KEY 且非本地端点）")
        if verbose:
            print("[llm] 未配置，回退到模板生成器", file=sys.stderr)
        return rule_gen.sample_rules(count), "fallback"

    system = rule_gen.SYSTEM_PROMPT.format(schema=rule_gen.SCHEMA_DOC)
    user = (f"本次主题倾向：{theme}\n" if theme else "") + f"请生成 {count} 条规则。"
    try:
        raw = chat(cfg, system, user)
        payload = _extract_json(raw)
        rules = rule_gen.validate_llm_rules(payload)
        if not rules:
            raise ValueError("LLM 返回的规则全部非法")
        if verbose:
            print(f"[llm] 采用模型 {cfg.model}，获得 {len(rules)} 条合法规则",
                  file=sys.stderr)
        return rules[:count], "llm"
    except Exception as e:  # noqa: BLE001
        if not allow_fallback:
            raise
        if verbose:
            print(f"[llm] 调用失败（{e}），回退到模板生成器", file=sys.stderr)
        return rule_gen.sample_rules(count), "fallback"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--theme", default="")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--no-fallback", action="store_true")
    args = ap.parse_args()

    cfg = LLMConfig(base_url=args.base_url, model=args.model)
    rules, source = generate_rules(
        count=args.count, theme=args.theme, cfg=cfg,
        allow_fallback=not args.no_fallback, verbose=True)
    print(f"\n来源：{source}，共 {len(rules)} 条\n")
    for r in rules:
        print(f"- [{r.name}] {r.desc}")
        print(f"    {r.params}\n")


if __name__ == "__main__":
    main()
