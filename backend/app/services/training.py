"""安全培训业务规则：状态流转、字段校验、筛选口径与主题看板汇总都收在这里。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训主题", "培训讲师"]
STATUS_ORDER = ["计划中", "已组织", "已完成", "需补训"]
ACTION_RULES = {"组织培训": "已组织", "登记考核": "已完成", "安排补训": "需补训"}
NEGATIVE_ACTIONS = ["安排补训"]

# 安全培训常设主题：即使一条记录都还没有，也要在看板上保留入口并提示待安排。
TRAINING_TOPICS = ["消防安全", "电气安全", "高处作业", "应急急救", "危化品管理", "职业健康"]
# 复训周期：距上一次培训超过一年即视为到期，到期人数取最近一次参训人数。
RETRAIN_CYCLE_DAYS = 365


def _to_int(value: Any) -> int:
    """参训人数、考核通过可能是数字也可能是字符串，统一安全转成整数。"""
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


class TrainingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        topic: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("培训编号", ""))]
        if topic:
            rows = [row for row in rows if str(row.get("培训主题") or "").strip() == topic]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"培训记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于安全培训可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"培训记录已{action}"

    def topic_board(self, as_of: date | None = None) -> dict[str, Any]:
        """按主题汇总培训看板。

        看板与明细共用仓库里的同一份记录：每个主题携带其全部记录，
        前端不再为看板单独取数；复训到期人数在此统一算好，避免两处口径不一致。
        """
        as_of = as_of or date.today()
        grouped: dict[str, list[dict[str, Any]]] = {topic: [] for topic in TRAINING_TOPICS}
        for row in store.rows(MODULE):
            topic = str(row.get("培训主题") or "").strip() or "未命名主题"
            grouped.setdefault(topic, []).append(row)

        topics: list[dict[str, Any]] = []
        retrain_due_total = 0
        for topic, records in grouped.items():
            ordered = sorted(
                records,
                key=lambda row: _parse_date(row.get("培训日期")) or date.min,
                reverse=True,
            )
            total_trainees = sum(_to_int(row.get("参训人数")) for row in ordered)
            total_passed = sum(_to_int(row.get("考核通过")) for row in ordered)
            pass_rate = round(total_passed / total_trainees, 4) if total_trainees else None

            latest = ordered[0] if ordered else None
            latest_date = _parse_date(latest.get("培训日期")) if latest else None
            retrain_due = False
            overdue_days = 0
            retrain_due_count = 0
            # 已排期但尚未开展的培训不算到期；到期只看“上一次培训是否已满一个周期”。
            if latest_date is not None and latest_date <= as_of:
                deadline = latest_date + timedelta(days=RETRAIN_CYCLE_DAYS)
                overdue_days = max(0, (as_of - deadline).days)
                retrain_due = overdue_days > 0
            if retrain_due and latest is not None:
                explicit = latest.get("复训到期人数")
                retrain_due_count = (
                    _to_int(explicit) if explicit not in (None, "") else _to_int(latest.get("参训人数"))
                )
                retrain_due_total += retrain_due_count

            topics.append({
                "topic": topic,
                "scheduled": bool(ordered),
                "record_count": len(ordered),
                "latest_date": latest.get("培训日期") if latest else None,
                "latest_instructor": latest.get("培训讲师") if latest else None,
                "total_trainees": total_trainees,
                "total_passed": total_passed,
                "pass_rate": pass_rate,
                "retrain_due": retrain_due,
                "retrain_due_count": retrain_due_count,
                "overdue_days": overdue_days,
                "records": ordered,
            })

        return {
            "as_of": as_of.isoformat(),
            "retrain_cycle_days": RETRAIN_CYCLE_DAYS,
            "topics": topics,
            "total_sessions": sum(item["record_count"] for item in topics),
            "retrain_due_count": retrain_due_total,
        }
