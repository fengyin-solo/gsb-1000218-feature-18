"""安全培训接口：维护培训记录，覆盖组织培训、登记考核、安排补训等动作，并提供主题看板。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.training import TrainingService

router = APIRouter(prefix="/api/training", tags=["安全培训"])

service = TrainingService()

LIST_FIELDS = ["培训编号", "培训主题", "培训讲师", "培训日期", "参训人数", "考核通过", "培训资料", "培训状态"]
STATUSES = ["计划中", "已组织", "已完成", "需补训"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按培训编号检索"),
    topic: str | None = Query(default=None, description="按培训主题精确过滤"),
    status: str | None = Query(default=None, description="计划中、已组织、已完成、需补训"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按培训编号、主题与状态过滤安全培训列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, topic=topic, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/board")
def topic_board(
    as_of: str | None = Query(default=None, description="复训到期判定基准日，格式 YYYY-MM-DD，默认今天"),
) -> dict[str, Any]:
    """按主题汇总的培训看板：与明细读取同一份记录，复训到期人数单独给出。"""
    as_of_date = None
    if as_of:
        try:
            as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="as_of 需为 YYYY-MM-DD 格式")
    return service.topic_board(as_of=as_of_date)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出安全培训清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "training", "total": total, "items": items}


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
