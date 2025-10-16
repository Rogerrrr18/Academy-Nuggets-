# 文献下载、转录与清洗管道（基于 MinerU）

本项目提供从 Excel 批量下载论文 PDF、调用 MinerU 进行 PDF→Markdown 转录，并对转录结果进行面向大模型数据挖掘的“二阶段清洗”。当前推荐且默认的入口为 GUI（DocNerd MinerU Helper），输出两类：结构化的 Markdown（主语料）与降级的纯文本（备选）。

- 论文下载：`download_papers.py`（DOI/标题检索，优先 DOI，支持 Unpaywall/OpenAlex 回退）
- 转录与清洗（GUI）：`DMH/DocNerd MinerU Helper.py`（CLI 入口已移除）
- 清洗规则（第一阶段 + 第二阶段，默认开启）：位于 `DMH/my_tips.py`

## 背景与目标

- 背景：原始 PDF 直接喂给检索与建模常遇到版面噪音（页眉页脚、断词连字）、图片/表格丢失、数学/化学公式字符被拆散、参考文献干扰等问题。
- 目标：在尽量保留结构信息（标题、列表、表格、公式等）的前提下，输出清爽、稳定的 Markdown 语料；同时提供纯文本版本用于统计/训练等场景。

## 目录结构与角色

- `download_papers.py`：主脚本。读取 Excel（默认 `undownload.xlsx`），按 DOI/标题下载 PDF；日志写入 `download_log.csv`。
- `3-sci-hub-download.py`：困难场景的备用下载脚本（仅作兜底）。
- `DMH/`：MinerU 集成与清洗工具集
  - `DocNerd MinerU Helper.py`：PyQt5 GUI（设置 API/Folders，Run 批处理）。
  - `my_tips.py`：清洗核心与通用工具（见下文“清洗规则”）。
  - `my_dialogs_*.py`、`my_styles.py`：GUI 组件与样式。
- 默认产物目录（可自定义）
  - `pdfs/`：下载产物（或你的自定义目录，如 `7-杨皓然-高研院/paper/`）
  - `mineru_raw/`：MinerU 解压输出（每篇一子目录，含 `full.md` 与资源）
  - `md_clean/`：清洗后 Markdown 与 TXT（与 PDF 同名：`<index>.md/.txt`）
  - `logs/removed_refs/`：被剔除的参考文献存档（便于回溯）

## 环境准备

Conda（推荐）：

- `conda create -n nano python=3.10 -y && conda activate nano`
- `conda install -n nano -c conda-forge pyqt pyqtwebengine markdown requests python-dotenv -y`
- 其它依赖（若使用下载脚本）：`pip install pandas openpyxl beautifulsoup4 lxml`

矿工（MinerU）访问需网络与 API Key（放入 .env 或环境变量）：

- MinerU 文档：https://mineru.net/apiManage/docs

## 快速开始

### 1）下载论文 PDF（可选）

- 基本用法：
  - `python3 download_papers.py --input undownload.xlsx --delay 2 --limit 5 --email you@domain`
- 自动识别列（可被 `--doi-column/--title-column` 覆盖）：
  - DOI 候选：`DOI`、`DOI Number`、`Digital Object Identifier`
  - 标题候选：`Article Title`、`Title`、`Paper Title`、`Document Title`
- 日志：`download_log.csv`（index, doi, title, status, notes）

> 也可直接使用你已有 PDF 目录（例如 `7-杨皓然-高研院/paper/`），跳过本步骤，直接做 MinerU 转录与清洗。

### 2）MinerU 转录 + 清洗（GUI）

- `python "DMH/DocNerd MinerU Helper.py"`
- 菜单：MinerU → Set up（填入 API Key）→ Select Folders（pdf/md/txt[=md_clean]）→ Run

### 3）项目级配置（.env）

- 复制 `.env.example` 为 `.env`，并填入：
  - `MINERU_API_KEY="你的MinerU Key"`
  - `MINERU_PDF_DIR="7-杨皓然-高研院/paper"`
  - `MINERU_MD_DIR="mineru_raw"`
  - `MINERU_OUT_DIR="md_clean"`
  - 可选采样：`MINERU_START=0`、`MINERU_LIMIT=10`
- GUI 启动时自动加载 .env（已内置 python-dotenv），也可通过菜单重新设置。

## 清洗规则（DMH/my_tips.py）

清洗在“第一阶段基础 + 第二阶段增强”上迭代，默认开启增强。所有清洗在 Markdown 上进行，随后再导出降级的 `.txt`。

- 基础（第一阶段）
  - 去图片引用：删除行内 `![...](...)`（表格图片除外，见下）
  - 空白整理：去除行尾空白；折叠多余空行；去首尾空行
  - 同时导出：
    - `.md`：清洗后的结构化文本
    - `.txt`：在 `.md` 基础上去掉常见标记（标题/链接/强调等），保留内容

- 增强（第二阶段）
  - 数学/化学公式（仅数学环境 `$...$/$$...$$` 内，保守模式）：
    - `\bf{}`→`\mathbf{}`，规范命令与花括号空格
    - 合并被空格拆散的字符与上下标：`CO _ { 2 }`→`CO_{2}`
    - 温度单位：`290 ^{\circ} C`→`290^{\circ}\mathrm{C}`
  - 孤儿图注删除：
    - 删除以 `Figure/Fig./FIG./图/Scheme/Schematic/Graph/Chart + 编号/罗马数字/S号` 开头的“图注整段”（至下一空行）
  - 表格还原（HTML 注入）：
    - 若 `mineru_raw/<index>/*_content_list.json` 标记为 `type: table`，则以 JSON 的 `table_body` 注入 `HTML <table>` 替代表格图片；保留表格 caption/footnote
  - 参考文献剔除（两段式）：
    - 标题法：匹配 `参考文献/参考资料/References/Bibliography/Works Cited/References and Notes/Literature Cited`，自标题起截断至文末
    - 回退法（更稳妥）：仅在文末 40% 窗口寻找“首个强参考行”（编号/DOI/年份/期刊缩写/卷期页组合）；要求处于最后 25% 且后续 10 行至少 5 行像参考条目，才整篇截断；否则在后半段逐块删除“参考块”（≥5 行且参考行比例≥0.6）
  - 不可见字符清理：移除 `\x00` 等控制字符，避免工具误判二进制
  - 参考文献存档：被删内容写入 `logs/removed_refs/<index>.md`

> 说明：我们保留结构优先，尽量避免误删正文；所有删除均可在 `logs/removed_refs/` 找回。

## 参数与环境变量

- `MINERU_API_KEY`（必需）：MinerU 授权
- 采样（可选）：`MINERU_START`、`MINERU_LIMIT`（GUI 后台线程可读取）
- 清洗开关（默认开启，可设为 `0` 关闭）
  - `MINERU_CLEAN_MATH`：数学/化学公式归一（默认 1）
  - `MINERU_DROP_REFS`：参考文献剔除（默认 1）
  - `MINERU_REPLACE_TABLES`：表格图片→HTML 表格（默认 1）
  - `MINERU_DROP_FIG_CAPTIONS`：孤儿图注删除（默认 1）
- 日志目录：`MINERU_LOGS_DIR`（默认 `logs`）

## 与下载脚本协同

- 上游下载（可选）：`download_papers.py` 将 Excel 的 `index` 列用于命名输出 PDF（如 `0001.pdf`），默认输出目录 `pdfs/`。
- 转录解压：MinerU 解压目录名复用 PDF 文件名（去后缀），天然对齐 `index`。
- 清洗输出：`md_clean/<index>.md/.txt`，可结合 `download_log.csv` 做二次对齐或回写 Excel。

## 常见问题（FAQ）

- MinerU 下载 ZIP 失败/SSL 异常？
  - GUI 已内置指数退避重试 + `verify` 切换 + `curl` 兜底（不同 TLS 栈）；仍失败请检查网络/代理，或稍后重试。
- 表格为什么用 HTML 而不是 Markdown？
  - 复杂表格（合并单元格）在 Markdown 下信息会损失；HTML 渲染兼容性更好。若你需要 Markdown 表格，可再加“降级转换”选项（会丢失合并信息）。
- 数学/化学公式为什么只“保守归一”？
  - 为避免误伤语义，仅在数学环境内做有限范围的清理；个别边界可以再迭代规则。
- 参考文献为什么有时不整篇截断？
  - 无标题又不满足“末段强参考”约束时，采用“块级删除”，尽量不误删正文。

## 开发与测试

- Python 3.9+，PEP 8，4 空格缩进，`snake_case` 命名；常量 `UPPER_SNAKE_CASE`；函数小而清晰，添加类型注解与简短文档。
- 工具函数保持纯净，避免全局状态副作用；输出文件名做好字符清洗。
- 暂无正式测试；建议用 `.env` 的 `MINERU_LIMIT` 做端到端抽样，核对 `md_clean/` 与 `logs/removed_refs/`。
- 如新增测试，推荐 `pytest` 放于 `tests/test_*.py`，并 mock 网络请求。

## 提交规范与安全

- 约定式提交：`feat|fix|refactor|docs|chore: 简述`
- 小步提交，说明使用的参数与可见改动；PR 需包含动机、运行命令、关键日志/截图、关联问题
- 遵守目标站点条款，合理设置 `--delay`；敏感信息（如 `MINERU_API_KEY`、`UNPAYWALL_EMAIL`）用环境变量，不要硬编码

## 版权与声明

- 请确保你对目标 PDF 的处理符合版权与授权要求；遵守 MinerU 与数据源站点的服务条款
- 本项目仅提供自动化处理工具，不对外部服务的可用性与条款变更承担责任
