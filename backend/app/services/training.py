"""安全培训业务规则：状态流转、字段校验、主题看板聚合与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训主题", "培训讲师"]
STATUS_ORDER = ["计划中", "已组织", "已完成", "需补训"]
ACTION_RULES = {"组织培训": "已组织", "登记考核": "已完成", "安排补训": "需补训"}
NEGATIVE_ACTIONS = []

# 看板固定展示的培训主题：即便还没有培训记录，也保留列位并提示“待安排”。
TOPIC_ORDER = ["电气安全", "高处作业", "消防安全", "应急救护", "危化品管理", "特种设备作业"]
# 复训有效期：同一主题最近一次培训距今超过一年，即视为复训到期。
RETRAIN_VALID_MONTHS = 12


def _to_int(value: Any) -> int:
    """把种子数据或表单里的人数字段解析成整数，解析不了按 0 处理，不阻断列表。"""
    try:
        return max(int(float(value)), 0)
    except (TypeError, ValueError):
        return 0


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _same_or_before_month(a: date | None, year: int, month: int) -> bool:
    return a is not None and a.year == year and a.month == month


class TrainingService:
    def _filtered_rows(
        self,
        *,
        keyword: str | None = None,
        trainer: str | None = None,
        topic: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("培训编号", ""))]
        if trainer:
            rows = [row for row in rows if trainer in str(row.get("培训讲师", ""))]
        if topic:
            rows = [row for row in rows if str(row.get("培训主题", "")).strip() == topic]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def board(self, rows: list[dict[str, Any]], *, today: date | None = None) -> tuple[list[dict[str, Any]], int]:
        """按主题聚合成看板列，并单独统计复训到期人数。

        看板列固定按 TOPIC_ORDER 排布：没有记录的主题标记为待安排，
        这样前端选中该主题时筛选仍可保留。
        """
        today = today or date.today()
        grouped: dict[str, list[dict[str, Any]]] = {topic: [] for topic in TOPIC_ORDER}
        for row in rows:
            topic = str(row.get("培训主题", "")).strip() or "未命名主题"
            grouped.setdefault(topic, []).append(row)

        topics: list[dict[str, Any]] = []
        retrain_due_total = 0
        ordered_names = TOPIC_ORDER + [name for name in grouped if name not in TOPIC_ORDER]
        for name in ordered_names:
            items = sorted(grouped.get(name, []), key=lambda row: str(row.get("培训日期", "")), reverse=True)
            attend_total = sum(_to_int(row.get("参训人数")) for row in items)
            pass_total = sum(_to_int(row.get("考核通过")) for row in items)
            rate = round(pass_total / attend_total, 4) if attend_total else 0.0

            latest_date = None
            latest_trainer = None
            retrain_due = 0
            if items:
                latest = items[0]
                latest_date = str(latest.get("培训日期") or "") or None
                latest_trainer = str(latest.get("培训讲师") or "") or None
                latest_day = _parse_date(latest_date)
                if latest_day is not None:
                    months = (today.year - latest_day.year) * 12 + (today.month - latest_day.month)
                    if today.day < latest_day.day:
                        months -= 1
                    if months >= RETRAIN_VALID_MONTHS:
                        retrain_due = _to_int(latest.get("参训人数"))
                        retrain_due_total += retrain_due

            topics.append({
                "topic": name,
                "arranged": bool(items),
                "record_count": len(items),
                "latest_date": latest_date,
                "latest_trainer": latest_trainer,
                "attend_total": attend_total,
                "pass_total": pass_total,
                "completion_rate": rate,
                "retrain_due": retrain_due,
                "items": items,
            })
        return topics, retrain_due_total

    def summarize(self, rows: list[dict[str, Any]], *, retrain_due_total: int, today: date | None = None) -> dict[str, Any]:
        """统计卡片：本月培训场次、通过率、待补训人数，复训到期人数单独给一项。"""
        today = today or date.today()
        month_rows = [row for row in rows if _same_or_before_month(_parse_date(row.get("培训日期")), today.year, today.month)]
        attend_total = sum(_to_int(row.get("参训人数")) for row in rows)
        pass_total = sum(_to_int(row.get("考核通过")) for row in rows)
        makeup_total = sum(
            max(_to_int(row.get("参训人数")) - _to_int(row.get("考核通过")), 0)
            for row in rows
        )
        return {
            "month_sessions": len(month_rows),
            "pass_rate": round(pass_total / attend_total, 4) if attend_total else 0.0,
            "makeup_people": makeup_total,
            "retrain_due_people": retrain_due_total,
        }

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        trainer: str | None = None,
        topic: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """看板与明细读同一份筛选结果：主题看板取全量，分页只切明细。"""
        rows = self._filtered_rows(keyword=keyword, trainer=trainer, topic=topic, status=status)
        topics, retrain_due_total = self.board(rows)
        stats = self.summarize(rows, retrain_due_total=retrain_due_total)
        total = len(rows)
        start = max(page - 1, 0) * size
        return {
            "items": rows[start:start + size],
            "total": total,
            "page": page,
            "size": size,
            "topics": topics,
            "retrain_due_total": retrain_due_total,
            "stats": stats,
        }

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
