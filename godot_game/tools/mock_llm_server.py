#!/usr/bin/env python3
"""《今天的规则》—— 本地 mock LLM 服务（Stage 3 测试用）。

模拟一个 OpenAI 兼容的 /v1/chat/completions 接口，返回合法的规则 JSON。
用于在没有真实 API key 的情况下，端到端验证 llm_client 的调用、解析与校验链路。

用法:
    python tools/mock_llm_server.py --port 8765 &
    OPENAI_BASE_URL=http://127.0.0.1:8765/v1 OPENAI_MODEL=mock \
        python tools/llm_client.py --count 5
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rule_gen


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静默
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(body or b"{}")
        except json.JSONDecodeError:
            req = {}
        # 依据请求里的用户文本推断条数（可选）
        n = 8
        for msg in req.get("messages", []):
            content = str(msg.get("content", ""))
            for token in content.split():
                pass
        rules = [r.as_dict() for r in rule_gen.sample_rules(n, seed=42)]
        content = json.dumps(rules, ensure_ascii=False)
        resp = {
            "id": "mock-1",
            "object": "chat.completion",
            "model": req.get("model", "mock"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
        }
        data = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mock LLM 服务已启动: http://127.0.0.1:{args.port}/v1/chat/completions")
    srv.serve_forever()


if __name__ == "__main__":
    main()
