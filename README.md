# 文献下载、转录与清洗工作流（基于 MinerU）

本项目服务于“高信噪比结构化语料”建设：从已下载的海量 PDF 中提取可用于大模型挖掘的 Markdown，并提供纯文本备选。当前推荐且默认的入口为 GUI（DocNerd MinerU Helper）。

- 下载与准备：Web of Science 元数据（含自定义 `index`）；Sci‑Hub 脚本批量拉取 PDF；人工补齐遗漏。
- 转录与清洗：调用 MinerU API 将 PDF 转 Markdown；执行二阶段清洗（去图片/图注、表格还原、公式归一、参考文献剔除、空白整理）。
- 输出：结构化 Markdown（主语料）与纯文本 TXT（备选），按 `index` 对齐。

## 工作流（推荐路径）

1. 获取元数据（Web of Science）
   - 在 Web of Science 导出目标领域的元数据（CSV/Excel）。
   - 设计并固化“文献主键”`index`（如 0001、10019），后续统一用作文件名与对齐键。
2. 批量下载 PDF（Sci‑Hub 脚本）
   - 使用脚本批量下载：根目录提供示例脚本 `3-sci-hub-download.py`（如你本地使用 `SCihub download/Sci-hub-download.py` 同样可行）。
   - 约束：下载失败的条目做列表输出，后续手动补齐。
3. 整理 PDF 并对齐命名
   - 将所有 PDF 重命名为 `index.pdf`，并放到统一目录，例如：`7-杨皓然-高研院/paper/`。
   - 目录结构示例：`7-杨皓然-高研院/paper/10019.pdf`、`.../102.pdf`。
4. 转录与清洗（GUI）
   - 启动：`python "DMH/DocNerd MinerU Helper.py"`
   - 配置：菜单 MinerU → Set up（填入 API Key）→ Select Folders（PDF 源目录 / MinerU 原始解压目录 / 清洗输出目录）
     - 建议目录：PDF=`7-杨皓然-高研院/paper`，原始=`mineru_raw`，输出=`md_clean`
   - 运行：MinerU → Run
     - GUI 将完成：批量上传 → 轮询任务 → 下载 ZIP → 解压到 `mineru_raw/<index>` → 调用清洗 → 生成 `md_clean/<index>.md` 与 `.txt`
5. 复核与追踪
   - 若发现清洗过度或不足：根据 `index` 直接定位 `mineru_raw/<index>/full.md` 与 `logs/removed_refs/<index>.md`（参考文献被删内容存档），便于回放与迭代规则。

## 目录结构与角色

- `3-sci-hub-download.py`：Sci‑Hub 批量下载示例脚本（可按需调整/替换）。
- `download_papers.py`：可选的 DOI/标题检索下载脚本（非主流程）。
- `DMH/DocNerd MinerU Helper.py`：GUI 入口（MinerU 批处理 + 清洗 + 日志）。
- `DMH/my_tips.py`：清洗核心（同时导出 `.md` 与 `.txt`；参考文献被删内容另存 `logs/removed_refs/`）。
- `DMH/my_dialogs_*.py`、`DMH/my_styles.py`：GUI 组件与样式（含字体回退与统一黑色文字）。
- 默认产物目录（可自定义）
  - `mineru_raw/`：MinerU 解压（每篇一子目录，含 `full.md` 与资源）
  - `md_clean/`：清洗后 Markdown 与 TXT（与 PDF 同名：`<index>.md/.txt`）
  - `logs/removed_refs/`：被剔除参考文献的存档

## 环境与安装

推荐使用 Conda；也提供 venv + pip 的方案。

- 方案 A：Conda（推荐，PyQt 更稳）
  - `conda create -n nano python=3.10 -y && conda activate nano`
  - 安装 GUI 组件（Qt）：`conda install -n nano -c conda-forge pyqt pyqtwebengine -y`
  - 安装其余依赖：`pip install -r requirements.txt`

- 方案 B：venv + pip（可行，但 PyQtWebEngine 可能在 macOS ARM 上失败）
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
  - `pip install PyQt5 PyQtWebEngine`（若安装失败请改用 Conda 安装 Qt 组件）

- 其它
  - MinerU 文档：https://mineru.net/apiManage/docs

## 配置（.env）

- 复制 `.env.example` 为 `.env`，填入：
  - `MINERU_API_KEY="你的MinerU Key"`
  - `MINERU_PDF_DIR="7-杨皓然-高研院/paper"`
  - `MINERU_MD_DIR="mineru_raw"`
  - `MINERU_OUT_DIR="md_clean"`
  - 可选采样：`MINERU_START=0`、`MINERU_LIMIT=10`
- GUI 启动时自动加载 `.env`（已内置 `python-dotenv`），也可通过菜单重新设置。

## 清洗规则与技术细节（DMH/my_tips.py）

- 图片与表格
  - 删除行内图片引用 `![...](...)`；若识别为“表格图片”，根据 MinerU 的 `*_content_list.json` 注入 HTML `<table>`（保留 caption/footnote）。
- 空白与结构
  - 去除行尾空白、折叠多余空行、去首尾空行；保持标题/列表/代码块的 Markdown 结构。
- 数学/化学公式（保守归一，仅数学环境 `$...$/$$...$$` 内）
  - `\bf{}` → `\mathbf{}`；合并被空格打散的上下标与化学式；`290^{\circ} C` → `290^{\circ}\mathrm{C}`。
- 孤儿图注
  - 以 `Figure/Fig./FIG./图/Scheme/Schematic/Graph/Chart + 编号/罗马数字/S号` 开头的“图注整段”（至下一空行）删除。
- 参考文献剔除（两段式）
  - 标题法：匹配 `参考文献/参考资料/References/Bibliography/Works Cited/References and Notes/Literature Cited`，自标题起截断至文末。
  - 回退法：仅在文末 40% 窗口寻找“首个强参考行”（编号/DOI/年份/期刊缩写/卷期页），要求处于最后 25% 且后续 10 行≥5 行命中才整篇截断；否则在后半段按块删除“参考块”（≥5 行且参考行比例≥0.6）。
- 纯文本导出
  - 在清洗后的 Markdown 基础上去除常见标记，生成 `.txt`；保留内容但不保留表格/标题层级等结构。
- 日志与可回放
  - 被删除的参考文献内容写入 `logs/removed_refs/<index>.md`；便于复核与追踪。
- 网络与稳定性
  - GUI 下载 ZIP 采用：指数退避 + `verify` 切换 + `Connection: close`（短连接）+ `curl` 兜底（必要时 `-k`）；显著降低网络边角导致的 SSL EOF。
- 字体与显示
  - GUI 统一黑色文字；自动选择系统可用中文字体（macOS 优先 `PingFang SC`），消除缺失字体告警。

## 常见问题（FAQ）

- MinerU 下载 ZIP 失败/SSL 异常？
  - 已内置重试与多 TLS 栈兜底；仍失败请检查网络/代理或稍后重试，或降低批量（设置 `.env` 的 `MINERU_LIMIT`）。
- 为什么表格用 HTML？
  - 复杂表格（合并单元格）在 Markdown 下信息易丢失；HTML 渲染更稳。若需 Markdown 表格，可另做降级转换（会丢失合并信息）。
- 为什么公式只“保守归一”？
  - 为避免误伤语义，仅在数学环境内进行有限规整；边界场景可按需迭代规则。
- 参考文献为什么有时不整篇截断？
  - 无标题又不满足“末段强参考”约束时，采用“块级删除”，尽量不误删正文。

## 开发与安全

- Python 3.9+；PEP 8；函数小而清晰，工具函数保持纯净，避免全局副作用。
- 不要将真实密钥写入代码库；使用 `.env`；`.gitignore` 已忽略 `*.xlsx`、PDF 与中间产物目录、`.env` 等。
- 遵守目标网站/服务条款与版权要求。
