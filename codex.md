# Codex / AI Agent 开发指引

## 项目概述

SQL Practice Lab — 单文件 Python HTTP 后端 + 纯前端 SPA 的 SQL 刷题网站，运行于 127.0.0.1:8765。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.8+ 标准库：http.server、sqlite3、json |
| 前端 | 原生 HTML/CSS/JS，无框架 |
| 编辑器 | CodeMirror 5（本地 vendor） |
| 数据库 | SQLite :memory: |
| AI | OpenAI 兼容 /chat/completions 接口 |

## 架构

app.py 单文件包含完整后端：JSON 数据层 → SQLite 判题引擎 → AI 客户端 → REST 路由 → 静态文件服务。

## 代码规范

- 文件顶部 `from __future__ import annotations`
- 使用 `pathlib.Path` 处理文件路径
- 每次判题新建 `:memory:` SQLite 连接
- `ensure_readonly_query()` 阻止 INSERT/UPDATE/DELETE/DROP 等写操作
- 前端无框架，全局状态挂 `window.AppState`
- CodeMirror 实例挂 `window.editor`

## 关键路由

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/problems | 题目列表 |
| GET | /api/problems/{id} | 题目详情 |
| POST | /api/run | 运行判题 |
| POST | /api/ai | AI 助手 |
| POST | /api/draft | 保存草稿 |
| GET | /api/submissions | 提交记录 |
| GET | /api/solution | 题目解析 |
| POST | /api/ai-config | 保存 AI 配置 |

## 添加新题目

编辑 `data/problems.json`，在数组末尾追加题目对象：

```json
{
  "id": "problem-slug",
  "title": "题目标题",
  "difficulty": "Easy | Medium | Hard",
  "tags": ["标签"],
  "description": "题目描述",
  "starter_sql_template": "SELECT ...",
  "expected_sql": "SELECT ...",
  "order_sensitive": false,
  "schema": [...]
}
```

## 注意事项

- 勿提交 `submissions.json`、`user_state.json`、`generated_problems.json`、`update_state.json`
- 保持零外部依赖，不引入 pip 包
- 端口 8765，硬编码于 `app.py` 顶部 `PORT` 变量
- 本地单用户工具，无认证/鉴权机制
