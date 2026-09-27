"""安全培训接口：维护培训记录，覆盖组织培训、登记考核、安排补训等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, TrainingListResult
from app.services.training import TrainingService

router = APIRouter(prefix="/api/training", tags=["安全培训"])

service = TrainingService()

LIST_FIELDS = ["培训编号", "培训主题", "培训讲师", "培训日期", "参训人数", "考核通过", "培训资料", "培训状态"]
STATUSES = ["计划中", "已组织", "已完成", "需补训"]


@router.get("", response_model=TrainingListResult)
def list_entries(
    keyword: str | None = Query(default=None, description="按培训编号检索"),
    trainer: str | None = Query(default=None, description="按培训讲师检索"),
    topic: str | None = Query(default=None, description="按培训主题筛选（看板主题点击后透传）"),
    status: str | None = Query(default=None, description="计划中、已组织、已完成、需补训"),
    page: int = 1,
    size: int = 20,
) -> TrainingListResult:
    """按编号、讲师、主题与状态过滤；明细分页与主题看板共用同一份筛选结果。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    payload = service.list_entries(keyword=keyword, trainer=trainer, topic=topic, status=status, page=page, size=size)
    return TrainingListResult(**payload)


@router.get("/export")
def export_entries(
    keyword: str | None = None,
    trainer: str | None = None,
    topic: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """导出安全培训清单：返回当前过滤条件下的全量数据。"""
    payload = service.list_entries(keyword=keyword, trainer=trainer, topic=topic, status=status, page=1, size=10000)
    return {"module": "training", "total": payload["total"], "items": payload["items"]}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条培训记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"培训记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条培训记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="培训记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条培训记录执行组织培训、登记考核、安排补训；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
