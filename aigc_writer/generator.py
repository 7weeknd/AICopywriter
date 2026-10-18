"""生成编排层：参数增强 → 渲染模板 → 调大模型。

把「怎么调模型」和「调什么任务」分开：
- templates.py 负责「任务长什么样」（模板、字段、风格库）；
- 本模块负责「把一次请求变成一次模型调用」（补派生参数、渲染、计时）。
"""
import time

from .config import load_config
from .llm import LLMClient
from .templates import STYLE_FORMATS, render

# 进程级单例：大模型客户端只建一次，HTTP 连接可复用
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        cfg = load_config()
        _llm = LLMClient(cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model)
    return _llm


def enrich(task: str, params: dict) -> dict:
    """补上「派生参数」——模板里要用、但用户不用直接填的值。

    目前只有文案任务需要：用户在表单里选的是风格代号（如 xiaohongshu），
    而模板里要的是风格展示名和格式要求，这里补进去。
    好处是「模板管结构、风格库管细节」，两边各自独立改。
    """
    values = dict(params)
    if task == "copywriting":
        style = STYLE_FORMATS.get(values.get("style", "")) or STYLE_FORMATS["general"]
        values["style_label"] = style["label"]
        values["style_format"] = style["format"]
    return values


def build_prompts(task: str, params: dict, tpl) -> tuple[str, str]:
    """只渲染提示词、不调模型。纯函数，供「预览」接口和生成共用。"""
    user_prompt = render(tpl.user_template, enrich(task, params))
    return tpl.system_prompt, user_prompt


def generate(task: str, params: dict, tpl) -> dict:
    """走完整链路：渲染提示词 → 调大模型 → 返回结果与耗时。

    未配置大模型抛 RuntimeError（路由层转 503）；
    调用失败由路由层捕获转 502。
    """
    llm = get_llm()
    if not llm.enabled:
        raise RuntimeError(
            "未配置大模型，无法生成（请在 start_web.bat 或 .env 中设置 "
            "LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）"
        )

    system_prompt, user_prompt = build_prompts(task, params, tpl)

    t0 = time.perf_counter()
    content = llm.generate(system_prompt, user_prompt, temperature=tpl.temperature)
    latency = (time.perf_counter() - t0) * 1000

    return {
        "content": content,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "latency_ms": round(latency, 1),
    }
