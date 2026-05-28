# SQL Practice Lab 🧪

本地运行的 SQL 刷题网站，内置 SQLite 判题引擎和 AI 辅助学习。

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)

## ✨ 功能

- **SQLite 本地判题** — 内存数据库执行 SQL，自动比对标准答案
- **12+ 原创题目** — JOIN、GROUP BY、HAVING、窗口函数、连续区间、留存分析
- **AI 助手** — OpenAI / DeepSeek 兼容接口，讲解、提示、查错、优化
- **CodeMirror 编辑器** — 语法高亮、括号匹配
- **每日新题** — 根据公开题型趋势自动生成原创练习
- **本地学习记录** — 进度、草稿、提交历史持久化

## 🚀 快速开始

```powershell
python app.py
```

浏览器打开 **http://127.0.0.1:8765**

- Python 3.8+
- 零外部依赖，仅使用 Python 标准库

## 📁 项目结构

```
├── app.py                  # 主服务（HTTP Server + SQLite 判题）
├── static/
│   ├── index.html          # 页面主体
│   ├── app.js              # 前端逻辑
│   ├── styles.css          # 样式
│   └── vendor/codemirror/  # CodeMirror 编辑器
├── data/
│   ├── problems.json       # 题库
│   ├── ai_config.json      # AI 配置模板
│   └── update_sources.json # 更新来源
└── requirements.txt
```

## ⚙️ AI 模型配置

编辑 `data/ai_config.json` 或在网页面板填写：

```json
{
  "baseUrl": "https://api.openai.com/v1",
  "model": "gpt-4.1-mini",
  "apiKey": "sk-..."
}
```

不配置也可使用本地启发式提示。

## ⌨️ 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + Enter` | 运行判题 |
| `Ctrl + S` | 保存草稿 |
| 右键选中 | 询问 AI |

## 📄 License

MIT
