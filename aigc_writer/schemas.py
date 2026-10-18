"""接口层 Pydantic 模型：入参校验 + 出参结构。

FastAPI 的约定：请求体和响应体都用 Pydantic 模型声明，
框架自动完成 JSON ↔ Python 对象转换与校验（类型/范围不符直接 422）。
"""
from pydantic import BaseModel, Field


class TemplateOut(BaseModel):
    """任务模板出参。fields 是输入框元数据，前端据此渲染表单。"""

    task: str
    name: str
    description: str | None = None
    system_prompt: str
    user_template: str
    temperature: float
    fields: list[dict]
    builtin: bool


class TemplateUpdateRequest(BaseModel):
    """修改模板：只允许改提示词、温度与展示名，task 作为资源标识不可变。"""

    system_prompt: str = Field(..., min_length=1, max_length=4000)
    user_template: str = Field(..., min_length=1, max_length=4000)
    temperature: float = Field(0.8, ge=0, le=2, description="0-2，越高越有创意")
    name: str | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=200)


class TemplateCreateRequest(BaseModel):
    """新增自定义任务。task 限定为小写字母开头，保证能安全拼进 URL 与正则。"""

    task: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,29}$", description="任务标识")
    name: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(None, max_length=200)
    system_prompt: str = Field(..., min_length=1, max_length=4000)
    user_template: str = Field(..., min_length=1, max_length=4000)
    temperature: float = Field(0.8, ge=0, le=2)
    fields: list[dict] = Field(default_factory=list, description="输入框元数据，可留空")


class GenerateRequest(BaseModel):
    task: str = Field(..., description="任务标识，如 copywriting")
    params: dict[str, str] = Field(default_factory=dict, description="任务入参")


class GenerateResponse(BaseModel):
    id: int
    task: str
    content: str
    latency_ms: float
    created_at: str


class PromptPreview(BaseModel):
    """提示词预览出参：不调模型，直接看最终发出去的提示词长什么样。"""

    task: str
    system_prompt: str
    user_prompt: str


class HistoryItem(BaseModel):
    """生成记录单条出参；params 回显入参，方便用同样条件再生成一次。"""

    id: int
    task: str
    params: dict
    content: str
    latency_ms: float
    created_at: str


class MessageResponse(BaseModel):
    message: str
