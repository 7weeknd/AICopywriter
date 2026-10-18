"""大模型客户端。

只依赖 requests，按 base_url 自动选择两条调用路径：
- Ollama（本地）：走原生 /api/chat，带 "think": false；
- 其余（DeepSeek / 豆包 / 通义等）：走 OpenAI 兼容的 /chat/completions。

为什么本地要单独走原生端点：
Ollama 的 OpenAI 兼容端点会忽略 think 参数，思考版模型（qwen3 等）的
reasoning 会把输出预算占满，最终 content 返回空字符串。
"""
import requests


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
        max_tokens: int = 1024,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    @property
    def enabled(self) -> bool:
        """三项都配齐才算可用；缺任何一项就走「未配置」分支。"""
        return bool(self.base_url and self.api_key and self.model)

    @property
    def is_ollama(self) -> bool:
        return (
            ":11434" in self.base_url
            or "localhost" in self.base_url
            or "127.0.0.1" in self.base_url
        )

    def generate(self, system: str, user: str, temperature: float = 0.8) -> str:
        """一次对话补全，返回模型生成的纯文本。"""
        if self.is_ollama:
            return self._generate_ollama(system, user, temperature)
        return self._generate_openai(system, user, temperature)

    def _generate_openai(self, system: str, user: str, temperature: float) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _generate_ollama(self, system: str, user: str, temperature: float) -> str:
        host = self.base_url.replace("/v1", "").rstrip("/")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,  # 关闭思考模式，否则 content 可能为空
            "options": {"num_predict": self.max_tokens, "temperature": temperature},
        }
        resp = requests.post(f"{host}/api/chat", json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
