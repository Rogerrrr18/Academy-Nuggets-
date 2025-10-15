# Repository Guidelines
- 请始终用中文回复

## 项目结构与模块组织
- `download_papers.py` —— 主脚本（DOI/标题检索、日志、Excel 更新）。
- `3-sci-hub-download.py` —— 困难场景的备用脚本。
- `pdfs/` —— 默认 PDF 输出目录。
- `papers/` —— 现有本地 PDF/素材（默认不写入）。
- `*.xlsx` —— 输入表（如 `undownload.xlsx`），可选输出状态表。
- `download_log.csv` —— 运行日志（index/doi/title/status/notes）。

## 构建、运行与开发命令
- 创建环境：`python3 -m venv .venv && source .venv/bin/activate`
- 安装依赖：`pip install requests pandas openpyxl beautifulsoup4`
- 交互运行：`python3 download_papers.py --input undownload.xlsx --interactive`
- 设置 Unpaywall：`export UNPAYWALL_EMAIL="you@domain"` 或 `--email you@domain`
- 安全抽样：`--delay 2.0 --start 0 --limit 5`

## 编码风格与命名约定
- Python 3.9+，PEP 8，4 空格缩进，`snake_case` 命名。
- 常量用 `UPPER_SNAKE_CASE`，函数小而清晰，添加类型注解与简短文档。
- 保持工具函数纯净，避免全局状态与副作用。
- 脚本文件用 `lower_snake_case.py`；输出文件名需做字符清洗。

## Excel 列与自动识别
- DOI 候选：`DOI`、`DOI Number`、`Digital Object Identifier`。
- 标题候选：`Article Title`、`Title`、`Paper Title`、`Document Title`。
- 可用 `--doi-column` / `--title-column` 覆盖自动识别。
- 建议添加稳定的 `index` 列用于人工对照与命名（如 `0001.pdf`）。

## 测试指南
- 暂无正式测试；用 `--limit` 验证端到端并检查 `pdfs/` 与 `download_log.csv`。
- 若新增测试，建议 `pytest` 放于 `tests/test_*.py`，并 mock 网络请求。

## 提交与 PR 规范
- 采用约定式提交：`feat|fix|refactor|docs|chore: 简述`。
- 小步提交，说明使用的参数与可见改动。
- PR 需包含动机、复现/运行命令、关键日志/截图、关联问题。
- 避免提交大体量二进制或包含隐私的表格，优先脱敏/示例。

## 安全与配置提示
- 遵守目标站点条款，合理设置 `--delay`。
- 使用环境变量存放敏感信息（如 `UNPAYWALL_EMAIL`），不要硬编码。
- 交互模式可配合浏览器进行机构登录与手动下载。

