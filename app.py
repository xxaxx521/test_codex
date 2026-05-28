from __future__ import annotations

import json
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PROBLEMS_PATH = ROOT / "data" / "problems.json"
GENERATED_PROBLEMS_PATH = ROOT / "data" / "generated_problems.json"
UPDATE_STATE_PATH = ROOT / "data" / "update_state.json"
UPDATE_SOURCES_PATH = ROOT / "data" / "update_sources.json"
AI_CONFIG_PATH = ROOT / "data" / "ai_config.json"
USER_STATE_PATH = ROOT / "data" / "user_state.json"
SUBMISSIONS_PATH = ROOT / "data" / "submissions.json"
PORT = 8765


def load_problems() -> list[dict[str, Any]]:
    with PROBLEMS_PATH.open("r", encoding="utf-8") as file:
        problems = json.load(file)
    if GENERATED_PROBLEMS_PATH.exists():
        with GENERATED_PROBLEMS_PATH.open("r", encoding="utf-8") as file:
            problems.extend(json.load(file))
    return problems


def starter_template(problem: dict[str, Any]) -> str:
    if problem.get("starter_sql_template"):
        return str(problem["starter_sql_template"])
    table_name = problem.get("schema", [{}])[0].get("name", "table_name")
    return f"SELECT\n  -- TODO: 写出题目要求返回的列\nFROM {table_name};"


def problem_progress(problem_id: str) -> dict[str, Any]:
    state = load_user_state()
    item = state.get("problems", {}).get(problem_id, {})
    return {
        "accepted": bool(item.get("accepted", False)),
        "submissionCount": int(item.get("submissionCount", 0)),
        "lastSubmittedAt": item.get("lastSubmittedAt"),
        "draft": item.get("draft", ""),
    }


def public_problem(problem: dict[str, Any], full: bool = False) -> dict[str, Any]:
    keys = ["id", "title", "difficulty", "tags", "description"]
    if full:
        keys.append("schema")
    data = {key: problem[key] for key in keys if key in problem}
    progress = problem_progress(problem["id"])
    data["accepted"] = progress["accepted"]
    data["submissionCount"] = progress["submissionCount"]
    data["lastSubmittedAt"] = progress["lastSubmittedAt"]
    if full:
        data["template_sql"] = starter_template(problem)
        data["starter_sql"] = progress["draft"] or data["template_sql"]
        data["source_note"] = problem.get("source_note")
    return data


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def ensure_readonly_query(sql: str) -> None:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("请输入 SQL。")
    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("当前判题只允许 SELECT 或 WITH 查询。")
    if ";" in cleaned:
        raise ValueError("一次只运行一条查询语句。")
    blocked = [" insert ", " update ", " delete ", " drop ", " alter ", " create ", " attach ", " pragma "]
    padded = f" {lowered} "
    if any(token in padded for token in blocked):
        raise ValueError("检测到会修改数据库的语句，请只提交查询 SQL。")


def build_database(problem: dict[str, Any]) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    for table in problem["schema"]:
        table_name = quote_identifier(table["name"])
        columns = ", ".join(
            f"{quote_identifier(column['name'])} {column['type']}" for column in table["columns"]
        )
        connection.execute(f"CREATE TABLE {table_name} ({columns})")
        if table["rows"]:
            names = [column["name"] for column in table["columns"]]
            placeholders = ", ".join("?" for _ in names)
            column_list = ", ".join(quote_identifier(name) for name in names)
            values = [[row.get(name) for name in names] for row in table["rows"]]
            connection.executemany(
                f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})",
                values,
            )
    return connection


def run_query(connection: sqlite3.Connection, sql: str) -> dict[str, Any]:
    ensure_readonly_query(sql)
    cursor = connection.execute(sql.strip().rstrip(";"))
    columns = [description[0] for description in cursor.description or []]
    rows = [list(row) for row in cursor.fetchall()]
    return {"columns": columns, "rows": rows}


def normalize_row(row: list[Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)


def compare_results(actual: dict[str, Any], expected: dict[str, Any], order_sensitive: bool) -> dict[str, Any]:
    same_columns = actual["columns"] == expected["columns"]
    if order_sensitive:
        same_rows = actual["rows"] == expected["rows"]
    else:
        same_rows = Counter(normalize_row(row) for row in actual["rows"]) == Counter(
            normalize_row(row) for row in expected["rows"]
        )
    return {
        "accepted": same_columns and same_rows,
        "sameColumns": same_columns,
        "sameRows": same_rows,
        "rowCount": len(actual["rows"]),
        "expectedRowCount": len(expected["rows"]),
    }


def problem_by_id(problem_id: str) -> dict[str, Any]:
    for problem in load_problems():
        if problem["id"] == problem_id:
            return problem
    raise KeyError(problem_id)


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_user_state() -> dict[str, Any]:
    return load_json(USER_STATE_PATH, {"problems": {}})


def save_user_state(state: dict[str, Any]) -> None:
    if "problems" not in state:
        state["problems"] = {}
    save_json(USER_STATE_PATH, state)


def submissions() -> list[dict[str, Any]]:
    return load_json(SUBMISSIONS_PATH, [])


def save_submissions(items: list[dict[str, Any]]) -> None:
    save_json(SUBMISSIONS_PATH, items)


def save_draft(problem_id: str, sql: str) -> dict[str, Any]:
    problem_by_id(problem_id)
    state = load_user_state()
    item = state.setdefault("problems", {}).setdefault(problem_id, {})
    item["draft"] = sql
    item["lastDraftAt"] = datetime.now().isoformat(timespec="seconds")
    save_user_state(state)
    return {"saved": True, "problemId": problem_id, "lastDraftAt": item["lastDraftAt"]}


def summarize_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "columns": result.get("columns", []),
        "rowCount": len(result.get("rows", [])),
        "previewRows": result.get("rows", [])[:5],
    }


def record_submission(
    problem_id: str,
    sql: str,
    comparison: dict[str, Any] | None = None,
    actual: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    items = submissions()
    entry = {
        "id": len(items) + 1,
        "problemId": problem_id,
        "sql": sql,
        "accepted": bool(comparison and comparison.get("accepted")),
        "error": error,
        "comparison": comparison,
        "resultSummary": summarize_result(actual),
        "submittedAt": now,
    }
    items.append(entry)
    save_submissions(items)

    state = load_user_state()
    item = state.setdefault("problems", {}).setdefault(problem_id, {})
    item["submissionCount"] = int(item.get("submissionCount", 0)) + 1
    item["accepted"] = bool(item.get("accepted")) or entry["accepted"]
    item["lastSubmittedAt"] = now
    item["lastSql"] = sql
    item["draft"] = sql
    save_user_state(state)
    return entry


def problem_submissions(problem_id: str) -> list[dict[str, Any]]:
    return [item for item in submissions() if item.get("problemId") == problem_id]


def solution_for(problem: dict[str, Any]) -> dict[str, str]:
    tags = "、".join(problem.get("tags", []))
    return {
        "problemId": problem["id"],
        "solution": problem["expected_sql"],
        "explanation": (
            f"这题的核心考点是 {tags or '基础查询'}。先根据题目确定输出列，"
            "再按照表关系补充 JOIN、过滤、分组或窗口函数。标准答案只作为一种可通过写法，"
            "你也可以写出等价 SQL。"
        ),
    }


def load_ai_config() -> dict[str, str]:
    config = load_json(
        AI_CONFIG_PATH,
        {"baseUrl": "https://api.openai.com/v1", "model": "", "apiKey": ""},
    )
    return {
        "baseUrl": str(config.get("baseUrl", "https://api.openai.com/v1")),
        "model": str(config.get("model", "")),
        "apiKey": str(config.get("apiKey", "")),
    }


def save_ai_config(payload: dict[str, Any]) -> dict[str, str]:
    config = {
        "baseUrl": str(payload.get("baseUrl", "https://api.openai.com/v1")).strip(),
        "model": str(payload.get("model", "")).strip(),
        "apiKey": str(payload.get("apiKey", "")).strip(),
    }
    if not config["baseUrl"]:
        config["baseUrl"] = "https://api.openai.com/v1"
    save_json(AI_CONFIG_PATH, config)
    return config


def fetch_source_signals() -> list[str]:
    sources = load_json(UPDATE_SOURCES_PATH, [])
    signals: list[str] = []
    keyword_pattern = re.compile(
        r"\b(window|rank|row_number|lag|lead|join|group by|having|retention|median|running total|cohort|sql)\b",
        re.IGNORECASE,
    )
    for source in sources:
        url = source.get("url", "")
        if not url.startswith(("http://", "https://")):
            continue
        request = urllib.request.Request(url, headers={"User-Agent": "SQLPracticeLab/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                text = response.read(180_000).decode("utf-8", errors="ignore")
        except Exception:
            continue
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        if title_match:
            signals.append(re.sub(r"\s+", " ", title_match.group(1)).strip())
        signals.extend(match.group(0).lower() for match in keyword_pattern.finditer(text[:80_000]))
    return signals[:60]


def daily_seed(today: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(today))


def generated_id(today: str, slug: str) -> str:
    return f"daily-{today.replace('-', '')}-{slug}"


def daily_templates(today: str, signals: list[str]) -> list[dict[str, Any]]:
    seed = daily_seed(today) + len("".join(signals))
    ad_spend = [120 + seed % 20, 80 + seed % 15, 200 + seed % 25, 60 + seed % 10, 90 + seed % 18]
    orders = [45 + seed % 6, 70 + seed % 8, 30 + seed % 5, 110 + seed % 9, 95 + seed % 7]
    return [
        {
            "id": generated_id(today, "campaign-roas"),
            "title": f"每日新题 {today} 广告 ROAS",
            "difficulty": "Medium",
            "tags": ["JOIN", "GROUP BY", "CASE"],
            "description": "统计每个广告渠道的 ROAS：订单收入 / 广告花费。只返回花费大于 0 的渠道。返回列 channel、spend、revenue、roas，roas 保留 2 位小数，并按 channel 升序排列。",
            "starter_sql_template": "SELECT\n  -- TODO: channel, spend, revenue, roas\nFROM CampaignSpend c\nJOIN Orders o ON c.campaign_id = o.campaign_id\nGROUP BY c.channel\nORDER BY c.channel;",
            "expected_sql": "SELECT c.channel, SUM(c.spend) AS spend, SUM(o.revenue) AS revenue, ROUND(1.0 * SUM(o.revenue) / SUM(c.spend), 2) AS roas FROM CampaignSpend c JOIN Orders o ON c.campaign_id = o.campaign_id GROUP BY c.channel HAVING SUM(c.spend) > 0 ORDER BY c.channel",
            "order_sensitive": True,
            "generated": True,
            "source_note": "根据公开 SQL 题型趋势生成的原创练习。",
            "schema": [
                {
                    "name": "CampaignSpend",
                    "columns": [
                        {"name": "campaign_id", "type": "INTEGER"},
                        {"name": "channel", "type": "TEXT"},
                        {"name": "spend", "type": "REAL"},
                    ],
                    "rows": [
                        {"campaign_id": 1, "channel": "Search", "spend": ad_spend[0]},
                        {"campaign_id": 2, "channel": "Social", "spend": ad_spend[1]},
                        {"campaign_id": 3, "channel": "Search", "spend": ad_spend[2]},
                        {"campaign_id": 4, "channel": "Email", "spend": ad_spend[3]},
                    ],
                },
                {
                    "name": "Orders",
                    "columns": [
                        {"name": "order_id", "type": "INTEGER"},
                        {"name": "campaign_id", "type": "INTEGER"},
                        {"name": "revenue", "type": "REAL"},
                    ],
                    "rows": [
                        {"order_id": 1, "campaign_id": 1, "revenue": orders[0]},
                        {"order_id": 2, "campaign_id": 1, "revenue": orders[1]},
                        {"order_id": 3, "campaign_id": 2, "revenue": orders[2]},
                        {"order_id": 4, "campaign_id": 3, "revenue": orders[3]},
                        {"order_id": 5, "campaign_id": 4, "revenue": orders[4]},
                    ],
                },
            ],
        },
        {
            "id": generated_id(today, "weekly-active-streak"),
            "title": f"每日新题 {today} 活跃周连续性",
            "difficulty": "Hard",
            "tags": ["WINDOW", "DATE", "GAPS AND ISLANDS"],
            "description": "找出至少连续活跃 3 周的用户。同一用户同一周多次活跃只算一周。返回列 user_id，并按 user_id 升序排列。",
            "starter_sql_template": "WITH weekly AS (\n  SELECT DISTINCT\n    user_id,\n    -- TODO: 计算用户活跃周\n    activity_date\n  FROM Activity\n)\nSELECT user_id\nFROM weekly\n-- TODO: 找出连续 3 周活跃的用户\nORDER BY user_id;",
            "expected_sql": "WITH weekly AS (SELECT DISTINCT user_id, strftime('%Y-%W', activity_date) AS active_week, CAST(strftime('%Y', activity_date) AS INTEGER) * 53 + CAST(strftime('%W', activity_date) AS INTEGER) AS week_no FROM Activity), grouped AS (SELECT user_id, active_week, week_no - ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY week_no) AS grp FROM weekly), streaks AS (SELECT user_id, COUNT(*) AS weeks FROM grouped GROUP BY user_id, grp) SELECT DISTINCT user_id FROM streaks WHERE weeks >= 3 ORDER BY user_id",
            "order_sensitive": True,
            "generated": True,
            "source_note": "根据公开 SQL 题型趋势生成的原创练习。",
            "schema": [
                {
                    "name": "Activity",
                    "columns": [
                        {"name": "user_id", "type": "INTEGER"},
                        {"name": "activity_date", "type": "TEXT"},
                    ],
                    "rows": [
                        {"user_id": 1, "activity_date": "2024-01-03"},
                        {"user_id": 1, "activity_date": "2024-01-10"},
                        {"user_id": 1, "activity_date": "2024-01-17"},
                        {"user_id": 2, "activity_date": "2024-01-02"},
                        {"user_id": 2, "activity_date": "2024-01-16"},
                        {"user_id": 2, "activity_date": "2024-01-23"},
                        {"user_id": 3, "activity_date": "2024-02-05"},
                        {"user_id": 3, "activity_date": "2024-02-12"},
                        {"user_id": 3, "activity_date": "2024-02-19"},
                        {"user_id": 3, "activity_date": "2024-02-19"},
                    ],
                }
            ],
        },
        {
            "id": generated_id(today, "support-response-time"),
            "title": f"每日新题 {today} 客服响应时间",
            "difficulty": "Medium",
            "tags": ["LAG", "WINDOW", "DATE"],
            "description": "计算每张工单从创建到第一次客服回复的小时数。返回列 ticket_id、first_response_hours，并按 ticket_id 升序排列。",
            "starter_sql_template": "WITH created AS (\n  SELECT ticket_id, MIN(event_time) AS created_time\n  FROM TicketEvents\n  WHERE event_type = 'created'\n  GROUP BY ticket_id\n)\nSELECT\n  ticket_id,\n  -- TODO: 计算首次客服回复小时数\n  NULL AS first_response_hours\nFROM created\nORDER BY ticket_id;",
            "expected_sql": "WITH first_reply AS (SELECT ticket_id, MIN(event_time) AS first_reply_time FROM TicketEvents WHERE actor = 'agent' GROUP BY ticket_id), created AS (SELECT ticket_id, MIN(event_time) AS created_time FROM TicketEvents WHERE event_type = 'created' GROUP BY ticket_id) SELECT c.ticket_id, ROUND((julianday(f.first_reply_time) - julianday(c.created_time)) * 24, 2) AS first_response_hours FROM created c JOIN first_reply f ON c.ticket_id = f.ticket_id ORDER BY c.ticket_id",
            "order_sensitive": True,
            "generated": True,
            "source_note": "根据公开 SQL 题型趋势生成的原创练习。",
            "schema": [
                {
                    "name": "TicketEvents",
                    "columns": [
                        {"name": "event_id", "type": "INTEGER"},
                        {"name": "ticket_id", "type": "INTEGER"},
                        {"name": "event_type", "type": "TEXT"},
                        {"name": "actor", "type": "TEXT"},
                        {"name": "event_time", "type": "TEXT"},
                    ],
                    "rows": [
                        {"event_id": 1, "ticket_id": 10, "event_type": "created", "actor": "user", "event_time": "2024-03-01 09:00"},
                        {"event_id": 2, "ticket_id": 10, "event_type": "reply", "actor": "agent", "event_time": "2024-03-01 10:30"},
                        {"event_id": 3, "ticket_id": 11, "event_type": "created", "actor": "user", "event_time": "2024-03-01 12:00"},
                        {"event_id": 4, "ticket_id": 11, "event_type": "reply", "actor": "user", "event_time": "2024-03-01 12:20"},
                        {"event_id": 5, "ticket_id": 11, "event_type": "reply", "actor": "agent", "event_time": "2024-03-01 15:00"},
                        {"event_id": 6, "ticket_id": 12, "event_type": "created", "actor": "user", "event_time": "2024-03-02 08:15"},
                        {"event_id": 7, "ticket_id": 12, "event_type": "reply", "actor": "agent", "event_time": "2024-03-02 09:00"},
                    ],
                }
            ],
        },
    ]


def validate_problem(problem: dict[str, Any]) -> None:
    connection = build_database(problem)
    result = run_query(connection, problem["expected_sql"])
    if not result["columns"]:
        raise ValueError(f"生成题 {problem['id']} 的标准答案没有返回列。")


def update_problem_bank(force: bool = False) -> dict[str, Any]:
    today = date.today().isoformat()
    state = load_json(UPDATE_STATE_PATH, {})
    if not force and state.get("last_checked") == today:
        return {
            "updated": False,
            "added": 0,
            "message": "今天已经检查过题库更新。",
            "lastChecked": state.get("last_checked"),
            "sourceSignals": state.get("source_signals", []),
        }

    signals = fetch_source_signals()
    existing = load_problems()
    existing_ids = {problem["id"] for problem in existing}
    generated = load_json(GENERATED_PROBLEMS_PATH, [])
    candidates = daily_templates(today, signals)
    added: list[dict[str, Any]] = []
    for problem in candidates[:2]:
        if problem["id"] in existing_ids:
            continue
        validate_problem(problem)
        generated.append(problem)
        added.append(public_problem(problem))

    if added:
        save_json(GENERATED_PROBLEMS_PATH, generated)
    state = {
        "last_checked": today,
        "last_updated_at": datetime.now().isoformat(timespec="seconds"),
        "added": len(added),
        "source_signals": signals,
    }
    save_json(UPDATE_STATE_PATH, state)
    return {
        "updated": bool(added),
        "added": len(added),
        "addedProblems": added,
        "message": f"已新增 {len(added)} 道每日原创练习。" if added else "今天没有可新增的题。",
        "lastChecked": today,
        "sourceSignals": signals,
    }


def local_hint(problem: dict[str, Any], sql: str) -> str:
    # Local fallback deliberately coaches instead of revealing the stored answer.
    tags = ", ".join(problem.get("tags", []))
    mode = "hint"
    hints = [
        f"这题重点是 {tags}。",
        "先确认 SELECT 的列名和题目要求完全一致，再看 JOIN / WHERE / GROUP BY 的条件。",
    ]
    if "LEFT JOIN" in problem.get("tags", []):
        hints.append("如果要保留左表所有行，用 LEFT JOIN；过滤右表时要考虑 NULL。")
    if "GROUP BY" in problem.get("tags", []):
        hints.append("涉及聚合筛选时，WHERE 先过滤明细行，HAVING 再过滤分组结果。")
    if "DATE" in problem.get("tags", []):
        hints.append("SQLite 可以用 julianday(date) 做日期差计算，也可以直接比较 ISO 日期字符串。")
    if not sql.strip():
        hints.append("可以从题目要求的输出列开始写，再逐步补 JOIN 和过滤条件。")
    return "\n".join(hints)


def call_model(payload: dict[str, Any], problem: dict[str, Any]) -> str:
    provider = load_ai_config()
    api_key = provider.get("apiKey", "").strip()
    base_url = provider.get("baseUrl", "https://api.openai.com/v1").strip().rstrip("/")
    model = provider.get("model", "").strip()
    sql = payload.get("sql", "")
    mode = payload.get("mode", "hint")
    user_message = payload.get("message", "")
    selected_text = payload.get("selectedText", "")
    selection_source = payload.get("selectionSource", "")
    allow_solution = bool(payload.get("allowSolution"))

    if not api_key or not model:
        if mode in {"solution", "optimize"} and not sql.strip():
            return "当前没有配置模型，也没有可分析的 SQL。你可以先写一点 SQL，或在 data/ai_config.json 里配置模型。"
        return local_hint(problem, sql)

    schema_text = json.dumps(problem["schema"], ensure_ascii=False, indent=2)
    policy = (
        "除非 allowSolution=true 或 mode=solution，否则不要给出完整可提交 SQL；"
        "优先分层提示、指出关键条件、解释思路。"
    )
    mode_instructions = {
        "explain": "讲解题目要求、表结构关系和解题方向，不给完整答案。",
        "hint": "给 2-4 条逐步提示，不给完整答案。",
        "debug": "检查用户 SQL 的逻辑问题，指出最可能错误和修正方向。",
        "optimize": "优化用户 SQL 的可读性或性能；如果给代码，只围绕用户已有 SQL 改写。",
        "selection-explain": "解释用户选中的文本或 SQL 片段。",
        "selection-hint": "围绕用户选中的内容给提示，不直接给完整答案。",
        "selection-optimize": "只优化用户选中的 SQL 片段，并说明原因。",
        "selection-ask": "回答用户围绕选中文本提出的问题。",
        "solution": "允许给完整 SQL，并附上简短解析。",
    }.get(mode, "给出简短 SQL 学习建议。")
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个 SQL 刷题助手。请像力扣 SQL 辅导一样帮助用户。"
                "回复使用中文，优先给短小、可执行的建议。"
                f"{policy}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"题目：{problem['title']}\n"
                f"要求：{problem['description']}\n"
                f"模式：{mode}\n"
                f"模式说明：{mode_instructions}\n"
                f"允许完整答案：{allow_solution}\n"
                f"表结构和数据：\n{schema_text}\n"
                f"用户 SQL：\n{sql}\n"
                f"选中来源：{selection_source}\n"
                f"选中文本：\n{selected_text}\n"
                f"用户补充：{user_message}"
            ),
        },
    ]
    request_body = json.dumps(
        {"model": model, "messages": messages, "temperature": 0.2},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=request_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"模型接口返回错误 {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"无法连接模型接口：{exc}") from exc


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, data: Any, status: int = 200) -> None:
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/api/problems":
            self.send_json([public_problem(problem) for problem in load_problems()])
            return
        if path == "/api/update-status":
            state = load_json(UPDATE_STATE_PATH, {})
            self.send_json(
                {
                    "lastChecked": state.get("last_checked"),
                    "lastUpdatedAt": state.get("last_updated_at"),
                    "added": state.get("added", 0),
                    "sourceSignals": state.get("source_signals", []),
                }
            )
            return
        if path == "/api/ai-config":
            self.send_json(load_ai_config())
            return
        if path == "/api/submissions":
            problem_id = query.get("problemId", [""])[0]
            self.send_json(problem_submissions(problem_id))
            return
        if path == "/api/solution":
            problem_id = query.get("problemId", [""])[0]
            try:
                self.send_json(solution_for(problem_by_id(problem_id)))
            except KeyError:
                self.send_json({"error": "题目不存在。"}, status=404)
            return
        if path.startswith("/api/problems/"):
            problem_id = path.rsplit("/", 1)[-1]
            try:
                self.send_json(public_problem(problem_by_id(problem_id), full=True))
            except KeyError:
                self.send_json({"error": "题目不存在。"}, status=404)
            return
        self.serve_static()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/run":
                payload = self.read_json()
                problem = problem_by_id(payload.get("problemId", ""))
                sql = payload.get("sql", "")
                try:
                    connection = build_database(problem)
                    actual = run_query(connection, sql)
                    expected = run_query(connection, problem["expected_sql"])
                    comparison = compare_results(
                        actual,
                        expected,
                        bool(problem.get("order_sensitive", False)),
                    )
                    submission = record_submission(problem["id"], sql, comparison, actual)
                    self.send_json(
                        {
                            "actual": actual,
                            "expected": expected,
                            "comparison": comparison,
                            "submission": submission,
                        }
                    )
                except Exception as exc:
                    submission = record_submission(problem["id"], sql, error=str(exc))
                    self.send_json({"error": str(exc), "submission": submission}, status=400)
                return
            if path == "/api/ai":
                payload = self.read_json()
                problem = problem_by_id(payload.get("problemId", ""))
                self.send_json({"reply": call_model(payload, problem)})
                return
            if path == "/api/update-problems":
                payload = self.read_json()
                self.send_json(update_problem_bank(force=bool(payload.get("force"))))
                return
            if path == "/api/ai-config":
                self.send_json(save_ai_config(self.read_json()))
                return
            if path == "/api/draft":
                payload = self.read_json()
                self.send_json(save_draft(payload.get("problemId", ""), payload.get("sql", "")))
                return
            self.send_json({"error": "未知接口。"}, status=404)
        except KeyError:
            self.send_json({"error": "题目不存在。"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def serve_static(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            file_path = STATIC / "index.html"
        else:
            file_path = (STATIC / path.lstrip("/")).resolve()
            if STATIC.resolve() not in file_path.parents and file_path != STATIC.resolve():
                self.send_error(403)
                return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(file_path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == "__main__":
    update = update_problem_bank(force=False)
    print(update["message"])
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"SQL practice app running at http://127.0.0.1:{PORT}")
    server.serve_forever()
