# SQL Practice Lab — 需求设计书

> 版本：v1.0 | 日期：2026-05-28

---

## 1. 项目背景

SQL Practice Lab 是一个本地运行的 SQL 练习平台，面向学习 SQL 的开发者，提供即时判题反馈和 AI 辅助学习。核心理念：**零部署、零依赖、开箱即用**。

## 2. 目标用户

- SQL 初学者：通过刷题掌握 JOIN、GROUP BY、窗口函数等核心语法
- 面试准备者：练习经典 SQL 面试题型
- 数据分析师：巩固 SQL 查询能力

## 3. 功能需求

### 3.1 核心功能

| 编号 | 功能 | 描述 | 状态 |
|------|------|------|------|
| F-01 | 题库系统 | 内置 12+ 原创题目，JSON 文件存储 | 已实现 |
| F-02 | 在线判题 | SQLite 内存数据库执行用户 SQL，自动比对 | 已实现 |
| F-03 | AI 助手 | 支持 OpenAI/DeepSeek 兼容接口 | 已实现 |
| F-04 | SQL 编辑器 | CodeMirror 语法高亮、括号匹配 | 已实现 |
| F-05 | 学习记录 | 草稿保存、提交历史、通过状态追踪 | 已实现 |
| F-06 | 每日更新 | 从公开来源获取题型信号，生成原创每日练习 | 已实现 |

### 3.2 辅助功能

| 编号 | 功能 | 描述 | 状态 |
|------|------|------|------|
| F-07 | 难度筛选 | 全部/简单/中等/困难 | 已实现 |
| F-08 | 搜索过滤 | 题目名和标签搜索 | 已实现 |
| F-09 | 右键 AI | 选中 SQL 后右键询问 AI | 已实现 |
| F-10 | 表结构查看 | 查看题目 schema 和样例数据 | 已实现 |
| F-11 | 题目解析 | 可选的完整解法查看 | 已实现 |

### 3.3 待实现功能

| 编号 | 功能 | 描述 | 优先级 |
|------|------|------|--------|
| F-12 | 题目统计 | 通过率、尝试次数统计展示 | P2 |
| F-13 | 收藏题目 | 标记重点题目 | P3 |
| F-14 | 导出成绩 | 导出学习报告 | P3 |
| F-15 | 题目分类 | 按知识点分类浏览 | P2 |

## 4. 技术架构

### 4.1 整体架构

```
浏览器 (index.html + app.js + CodeMirror)
       ↕ HTTP (127.0.0.1:8765)
app.py (Python 标准库)
  ├── ThreadingHTTPServer
  │     ├── GET  → 静态文件 + API 查询
  │     └── POST → 判题 / AI / 配置
  ├── 判题引擎: SQLite :memory: + 结果比对
  └── 数据层: JSON 文件读写 (data/*.json)
```

### 4.2 技术选型理由

| 决策 | 选择 | 理由 |
|------|------|------|
| 后端框架 | 无，http.server | 零依赖，安装即用 |
| 数据库 | SQLite :memory: | 每次判题隔离，无需清理 |
| 存储 | JSON 文件 | 可读可编辑，适合小规模数据 |
| 前端框架 | 无，原生 JS | 轻量，无构建步骤 |
| 编辑器 | CodeMirror 5 | 成熟稳定，体积小 |

### 4.3 判题数据流

```
用户 SQL → ensure_readonly_query() 安全检查
         → build_database() 建表插数据
         → run_query(用户 SQL) → actual
         → run_query(标准答案) → expected
         → compare_results() 结果比对
         → 返回 {actual, expected, comparison}
```

## 5. REST API 清单

| 方法 | 路径 | 请求体 | 返回 |
|------|------|--------|------|
| GET | `/api/problems` | — | 题目列表 |
| GET | `/api/problems/{id}` | — | 题目详情 |
| POST | `/api/run` | `{problemId, sql}` | 判题结果 |
| POST | `/api/ai` | `{problemId, message, mode}` | AI 回复 |
| POST | `/api/draft` | `{problemId, sql}` | 保存确认 |
| GET | `/api/submissions` | — | 提交记录 |
| GET | `/api/solution` | — | 题目解析 |
| GET/POST | `/api/ai-config` | `{baseUrl, model, apiKey}` | 配置 |
| GET | `/api/update-status` | — | 更新状态 |
| POST | `/api/update-problems` | `{force}` | 更新结果 |

### 判题响应结构

```json
{
  "actual": {"columns": ["name"], "rows": [["Alice"]]},
  "expected": {"columns": ["name"], "rows": [["Alice"]]},
  "comparison": {"sameColumns": true, "sameRows": true, "passed": true},
  "submission": {"id": 1, "accepted": true, "submittedAt": "..."}
}
```

## 6. 代码审查与优化建议

### 6.1 已发现的问题

| 优先级 | 位置 | 问题 | 建议 |
|--------|------|------|------|
| P0 | app.py | 网络请求无超时 | 添加 `timeout=10` |
| P0 | app.py | 无请求体大小限制 | 检查 `Content-Length` |
| P1 | app.py | 端口硬编码 `8765` | 改用 `os.environ.get("PORT", 8765)` |
| P1 | app.py | AI 调用无错误重试 | 添加 try/except + 重试 |
| P1 | app.py | 无日志系统 | 引入 `logging` 模块 |
| P2 | app.js | 全局变量散落 | 收拢到 `AppState` |
| P2 | app.js | API 无加载/错误状态 | 添加 loading + error toast |

### 6.2 优化实施计划

| 阶段 | 内容 | 影响 |
|------|------|------|
| Phase 1 | 请求限制 + 超时 + 错误处理 | app.py |
| Phase 2 | 端口环境变量 + 日志 | app.py |
| Phase 3 | 前端状态管理重构 | app.js |
| Phase 4 | 单元测试 | 新文件 |

## 7. 测试策略

| 类型 | 内容 | 工具 |
|------|------|------|
| 单元 | `ensure_readonly_query` 安全检查 | pytest |
| 单元 | `build_database` + `compare_results` | pytest |
| 集成 | `/api/run` 端点 | pytest + http.client |

### 关键测试用例

1. SELECT/WITH 通过，INSERT/UPDATE/DELETE/DROP 被拒绝
2. 正确 SQL → 判过，错误 SQL → 友好错误提示
3. `order_sensitive: true` 时顺序不同 → 失败
4. NULL 值处理正确

## 8. 部署

- Python 3.8+
- `python app.py`
- http://127.0.0.1:8765
- 零安装、零配置

## 9. 版本规划

| 版本 | 目标 |
|------|------|
| v1.0 | 核心判题 + AI 辅助（当前） |
| v1.1 | 安全加固 + 错误处理优化 |
| v1.2 | 前端重构 + 题目统计 |
| v2.0 | 多用户 + 数据库迁移 |
