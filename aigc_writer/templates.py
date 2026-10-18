"""内置任务模板 + 模板渲染 —— 本项目的核心设计所在。

一句话：把「提示词」从代码里搬到数据库，让它变成可配置的数据。

分三点讲清：
1. 一个「任务」= 一条模板记录（system 提示词 + user 模板 + temperature）。
   这些记录启动时作为种子写入 MySQL，之后前端可以改、可以新增，代码不用动。
2. 每条模板还带一份 fields 元数据，描述这个任务需要哪些输入框。
   前端拿到它就能自动渲染表单 —— 新增任务无需改前端代码（元数据驱动 UI）。
3. render() 只替换「白名单 token」，刻意不用 str.format：
   模板来自数据库、参数来自用户输入，而 str.format 会解析属性与下标访问
   （例如 {a.__class__}），既有信息泄露风险，也会在参数缺失时抛 KeyError。
   正则替换只认 {字段名} 这一种形式，安全、可控、缺参数就填空串。
"""
import re

# ---------- 营销文案的平台风格：风格名 → 格式要求 ----------
# user 模板里用 {style_format} 占位，生成前由 generator 注入
STYLE_FORMATS: dict[str, dict] = {
    "xiaohongshu": {
        "label": "小红书笔记",
        "format": (
            "先写一句抓眼球的标题（带 emoji），换行后正文分 3-5 行写卖点，"
            "每行开头用 emoji；结尾带 3-5 个话题标签（# 开头）。总字数 120-200。"
        ),
    },
    "moments": {
        "label": "朋友圈 / 社群",
        "format": (
            "口语化，像朋友真心推荐：1-2 句勾兴趣 + 3 个卖点短句，"
            "结尾一句行动号召。不要话题标签。总字数 60-120。"
        ),
    },
    "ecommerce": {
        "label": "电商商品详情",
        "format": (
            "先写一句话核心卖点，再列 5 条参数或优势（每条一行，用「-」开头），"
            "最后一句售后承诺。风格专业、信息密度高。总字数 100-180。"
        ),
    },
    "general": {
        "label": "通用营销文案",
        "format": "结构清晰：标题 + 正文 + 行动号召，总字数 100-150。",
    },
}

TONES = ["活泼", "专业", "亲切", "高冷"]
REWRITE_TONES = ["正式书面", "口语自然", "简洁有力", "文艺华丽"]
SUMMARY_LENS = ["一句话", "3-5 句", "一个自然段"]


def _select(name: str, label: str, options: list[str], default: str) -> dict:
    """构造一个下拉框字段的元数据。"""
    return {
        "name": name,
        "label": label,
        "type": "select",
        "default": default,
        "options": [{"value": o, "label": o} for o in options],
    }


# ---------- 内置任务（启动时作为种子写入数据库） ----------
DEFAULT_TEMPLATES: list[dict] = [
    {
        "task": "copywriting",
        "name": "营销文案生成",
        "description": "按产品 + 平台风格 + 语气生成营销文案",
        "system_prompt": (
            "你是一名资深中文营销文案撰稿人，擅长把产品卖点写得有感染力、贴合平台调性。"
            "只输出文案本身，不要输出任何解释、前言或「以下是」之类的引导语。"
        ),
        "user_template": (
            "产品 / 主题：{product}\n"
            "平台风格：{style_label}\n"
            "语气：{tone}\n"
            "必须包含的关键词：{keywords}\n\n"
            "格式要求：{style_format}"
        ),
        "temperature": 0.8,  # 求创意，温度偏高
        "fields": [
            {
                "name": "product",
                "label": "产品 / 主题",
                "type": "text",
                "placeholder": "例：轻食代餐奶昔",
                "required": True,
            },
            {
                "name": "style",
                "label": "平台风格",
                "type": "select",
                "default": "xiaohongshu",
                "options": [
                    {"value": k, "label": v["label"]} for k, v in STYLE_FORMATS.items()
                ],
            },
            _select("tone", "语气", TONES, "活泼"),
            {
                "name": "keywords",
                "label": "必须包含的关键词",
                "type": "text",
                "placeholder": "可留空，多个词用逗号分隔",
            },
        ],
    },
    {
        "task": "summarize",
        "name": "文本摘要",
        "description": "把长文本压缩成指定长度的摘要，保留关键信息",
        "system_prompt": (
            "你是一名严谨的中文文本编辑，擅长提炼要点。"
            "只输出摘要本身，不要添加任何解释、评价或「摘要如下」之类的引导语。"
        ),
        "user_template": (
            "请把下面的文本压缩成{length}的摘要，保留关键信息与数字，用连贯的中文表述。\n\n"
            "原文：\n{text}"
        ),
        "temperature": 0.3,  # 摘要要忠于原文，温度调低
        "fields": [
            {
                "name": "text",
                "label": "原文",
                "type": "textarea",
                "placeholder": "粘贴需要摘要的文本",
                "required": True,
            },
            _select("length", "摘要长度", SUMMARY_LENS, "3-5 句"),
        ],
    },
    {
        "task": "rewrite",
        "name": "改写润色",
        "description": "在不改变原意的前提下，把文本改写成指定风格",
        "system_prompt": (
            "你是一名中文编辑，擅长在不改变原意的前提下重写文字。"
            "只输出改写后的文本，不要输出对比、说明或任何额外内容。"
        ),
        "user_template": (
            "把下面的文本改写成{tone}的风格，保持原意不变，不要增加原文没有的信息。\n\n"
            "原文：\n{text}"
        ),
        "temperature": 0.5,  # 既要变又不能跑偏，取中间值
        "fields": [
            {
                "name": "text",
                "label": "原文",
                "type": "textarea",
                "placeholder": "粘贴需要改写的文本",
                "required": True,
            },
            _select("tone", "目标风格", REWRITE_TONES, "正式书面"),
        ],
    },
]

# 只匹配 {字段名} 这一种形式：字母/数字/下划线，别的一律不动
_TOKEN = re.compile(r"\{(\w+)\}")


def render(template: str, values: dict) -> str:
    """把 user 模板里的 {字段名} 换成实际值；模板里没写到的字段自动忽略。

    用正则而不是 str.format：模板内容存在数据库、可以被前端改，
    而 str.format 会解析属性访问（{x.__class__}）并在缺参时抛异常，
    换成白名单替换后，模板怎么改都不会出安全问题或崩掉。
    """

    def _replace(match: re.Match) -> str:
        return str(values.get(match.group(1), ""))

    return _TOKEN.sub(_replace, template)
