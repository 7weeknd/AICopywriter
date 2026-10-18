"""接口层：任务列表 / 生成 / 提示词预览 / 生成历史 / 提示词模板管理。

统一挂在 /api 前缀下：
- GET    /api/tasks            列出所有任务（含表单元数据）
- POST   /api/generate         生成（渲染模板 → 调模型 → 自动记入历史）
- POST   /api/preview          只渲染提示词，不调模型（改模板时先看效果）
- GET    /api/history          查生成记录（最新在前）
- DELETE /api/history/{id}     删除一条生成记录
- GET    /api/templates/{task} 查看单个任务模板
- PUT    /api/templates/{task} 修改模板（内置任务也可改，但不能删）
- POST   /api/templates        新增自定义任务
- DELETE /api/templates/{task} 删除自定义任务（内置任务返回 400）
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .generator import build_prompts, generate
from .models import GenerationHistory, PromptTemplate
from .schemas import (
    GenerateRequest,
    GenerateResponse,
    HistoryItem,
    MessageResponse,
    PromptPreview,
    TemplateCreateRequest,
    TemplateOut,
    TemplateUpdateRequest,
)

router = APIRouter(prefix="/api")


# ---------- 内部小工具 ----------
def _to_out(row: PromptTemplate) -> dict:
    """ORM 行 → 出参字典：把 fields_json 反序列化成前端能直接用的列表。"""
    return {
        "task": row.task,
        "name": row.name,
        "description": row.description,
        "system_prompt": row.system_prompt,
        "user_template": row.user_template,
        "temperature": row.temperature,
        "fields": json.loads(row.fields_json or "[]"),
        "builtin": row.builtin,
    }


def _get_template(db: Session, task: str) -> PromptTemplate:
    """按 task 取模板；不存在统一返回 404，库不可用则返回 503。"""
    try:
        row = db.scalar(select(PromptTemplate).where(PromptTemplate.task == task))
    except Exception as exc:  # 数据库不可用：给出可读提示而不是 500 堆栈
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"数据库不可用：{exc}")
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"任务不存在：{task}")
    return row


# ---------- 任务与生成 ----------
@router.get("/tasks", response_model=list[TemplateOut])
def list_tasks(db: Session = Depends(get_db)):
    """列出全部任务，前端用它的 fields 动态渲染表单。"""
    rows = db.scalars(select(PromptTemplate).order_by(PromptTemplate.id)).all()
    return [_to_out(r) for r in rows]


@router.post("/generate", response_model=GenerateResponse)
def do_generate(req: GenerateRequest, db: Session = Depends(get_db)):
    """生成：校验必填参数 → 渲染模板 → 调模型 → 落库。"""
    tpl = _get_template(db, req.task)

    # 必填校验：模板里标了 required 的输入框没填值，就不浪费一次模型调用
    fields = json.loads(tpl.fields_json or "[]")
    missing = [
        f["label"]
        for f in fields
        if f.get("required") and not str(req.params.get(f["name"], "")).strip()
    ]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "缺少必填参数：" + "、".join(missing)
        )

    try:
        result = generate(req.task, req.params, tpl)
    except RuntimeError as exc:  # 未配置大模型
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception as exc:  # 调用失败（网络/超时/返回异常）
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"大模型调用失败：{exc}")

    row = GenerationHistory(
        task=req.task,
        template_id=tpl.id,
        params=json.dumps(req.params, ensure_ascii=False),
        system_prompt=result["system_prompt"],
        user_prompt=result["user_prompt"],
        content=result["content"],
        temperature=tpl.temperature,
        latency_ms=result["latency_ms"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)  # 取回自增 id 与数据库生成的 created_at

    return {
        "id": row.id,
        "task": row.task,
        "content": row.content,
        "latency_ms": row.latency_ms,
        "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/preview", response_model=PromptPreview)
def preview(req: GenerateRequest, db: Session = Depends(get_db)):
    """预览最终提示词：不调模型，毫秒级返回，改模板时先看这里。"""
    tpl = _get_template(db, req.task)
    system_prompt, user_prompt = build_prompts(req.task, req.params, tpl)
    return {"task": tpl.task, "system_prompt": system_prompt, "user_prompt": user_prompt}


@router.get("/history", response_model=list[HistoryItem])
def history(
    limit: int = Query(20, ge=1, le=200, description="最多返回条数"),
    db: Session = Depends(get_db),
):
    """查生成记录（倒序：最新在最前）。"""
    rows = db.scalars(
        select(GenerationHistory).order_by(GenerationHistory.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "task": r.task,
            "params": json.loads(r.params or "{}"),
            "content": r.content,
            "latency_ms": r.latency_ms,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for r in rows
    ]


@router.delete("/history/{id}", response_model=MessageResponse)
def delete_history(id: int, db: Session = Depends(get_db)):
    row = db.get(GenerationHistory, id)  # 按主键取；不存在返回 None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "记录不存在")
    db.delete(row)
    db.commit()  # 不 commit 只标记删除，不会真正落库
    return {"message": "已删除"}


# ---------- 提示词模板管理 ----------
@router.get("/templates/{task}", response_model=TemplateOut)
def get_template(task: str, db: Session = Depends(get_db)):
    return _to_out(_get_template(db, task))


@router.put("/templates/{task}", response_model=TemplateOut)
def update_template(task: str, req: TemplateUpdateRequest, db: Session = Depends(get_db)):
    """改模板：提示词是数据，改完立刻生效，不用重启服务。"""
    row = _get_template(db, task)
    row.system_prompt = req.system_prompt
    row.user_template = req.user_template
    row.temperature = req.temperature
    if req.name:
        row.name = req.name
    if req.description is not None:
        row.description = req.description
    db.commit()  # ORM 的 UPDATE：改完属性 commit 就行
    db.refresh(row)
    return _to_out(row)


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(req: TemplateCreateRequest, db: Session = Depends(get_db)):
    """新增自定义任务：只填提示词即可，前端会自动按新任务渲染表单。"""
    exists = db.scalar(select(PromptTemplate).where(PromptTemplate.task == req.task))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"任务标识已被占用：{req.task}")

    row = PromptTemplate(
        task=req.task,
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
        user_template=req.user_template,
        temperature=req.temperature,
        fields_json=json.dumps(req.fields, ensure_ascii=False),
        builtin=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/templates/{task}", response_model=MessageResponse)
def delete_template(task: str, db: Session = Depends(get_db)):
    """删自定义任务；内置任务保护起来，避免把系统自带能力删空。"""
    row = _get_template(db, task)
    if row.builtin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "内置任务不允许删除")
    db.delete(row)
    db.commit()
    return {"message": "已删除"}
