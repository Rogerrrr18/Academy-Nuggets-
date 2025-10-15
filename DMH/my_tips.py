from os import path, makedirs, listdir, getenv
from time import strftime, localtime
from json import dump
from re import match, findall, sub
import re
import json
import markdown


def path_check(directory_path):
    """检查文件夹路径，如果不存在则创建相应的路径"""

    if not path.exists(directory_path):
        makedirs(directory_path)


def data_to_json(directory_path, datas):
    """将符合 JSON 格式的数据写入 json 文件"""

    path_check(directory_path)

    time_str = str(strftime('%Y%m%d_%H%M%S', localtime()))
    file_path = path.join(directory_path, f"LOG_{time_str}.json")

    with open(file_path, 'w', encoding='utf-8') as f:
        dump(datas, f, indent=4, ensure_ascii=False)


def find_txts(directory_path, extension='.txt'):
    """获取文件夹下所有 txt 文件的路径（也可以指定为其它类型的文件）"""

    path_check(directory_path)

    file_infos = []

    for file_name in listdir(directory_path):

        file_path = path.join(directory_path, file_name)

        if path.isfile(file_path):
            if path.splitext(file_name)[1].lower() == extension:
                file_infos.append(file_path)

    return file_infos


def model_split(model, only_name=False):
    """按照 [] 分割模型的名称和特殊参数"""

    matchs = match(r'^(.*?)\[(.*)\]$', model)
    models = [matchs.group(1).strip(), matchs.group(2).strip()] if matchs else [model, ""]

    if only_name:
        return models[0]

    return {"T": True if models[1] == "T" else False, "t": True if models[1] == "t" else False}    


def extract_md(
    md_name: str,            # md 文件的文件名（不含扩展名）
    md_lines: list,          # 使用 readlines() 读取的 md 文件的行内容
    txt_file_path: str,      # 保存纯文本的 .txt 文件路径（将同时生成同名 .md 文件）
    raw_dir: str = None,     # 对应 mineru_raw/<index> 目录，用于表格替换及辅助清洗
) -> dict:
    """将 markdown 文本做基础清洗，并同时导出为 .md 与 .txt。

    清洗策略（第一阶段）：
    - 移除 Markdown 图片语法：![...](...)
    - 去除行尾多余空白
    - 折叠多余的空行（最多保留一个）

    导出：
    - 同名 .md：写入清洗后的 Markdown 文本
    - 同名 .txt：在 Markdown 基础上做轻量标记去除后的纯文本
    """

    # 环境变量控制（默认开启）
    split_header = (getenv('MINERU_SPLIT_HEADER') or '1') != '0'
    clean_math = (getenv('MINERU_CLEAN_MATH') or '1') != '0'
    drop_refs = (getenv('MINERU_DROP_REFS') or '1') != '0'
    replace_tables = (getenv('MINERU_REPLACE_TABLES') or '1') != '0'
    drop_fig_caps = (getenv('MINERU_DROP_FIG_CAPTIONS') or '1') != '0'

    # 0) 基础清理：移除不可见字符（如 NUL）
    md_lines = [l.replace('\x00', '') for l in md_lines]

    # 0) 构建表格映射（img -> HTML 表格）
    table_map = {}
    if raw_dir and replace_tables and path.exists(raw_dir):
        try:
            for fn in listdir(raw_dir):
                if fn.endswith('_content_list.json'):
                    with open(path.join(raw_dir, fn), 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                    # data 可能是 list 或 dict
                    items = data if isinstance(data, list) else data.get('content_list') or []
                    for it in items:
                        try:
                            if (it.get('type') == 'table') and it.get('img_path') and it.get('table_body'):
                                imgp = it['img_path']  # 如 images/xxx.jpg
                                base = path.basename(imgp)
                                caption = ''
                                if it.get('table_caption'):
                                    cap = ' '.join([str(x).strip() for x in it['table_caption'] if x])
                                    if cap:
                                        caption = f"<p><em>{cap}</em></p>\n"
                                tfoot = ''
                                if it.get('table_footnote'):
                                    foot = ' '.join([str(x).strip() for x in it['table_footnote'] if x])
                                    if foot:
                                        tfoot = f"\n<p><small>{foot}</small></p>\n"
                                html = f"\n<!-- table:start {base} -->\n{caption}{it['table_body']}{tfoot}<!-- table:end -->\n"
                                table_map[base] = html
                                table_map[imgp] = html
                        except Exception:
                            continue
        except Exception:
            pass

    # 1) 图片处理：表格图片替换为 HTML 表格，其余图片移除
    processed_lines = []
    removed_images = []
    img_pat = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
    for line in md_lines:
        # 逐个替换同一行中的多个图片
        def repl(m):
            url = m.group(1)
            base = path.basename(url)
            if base in table_map or url in table_map:
                return table_map.get(base) or table_map.get(url)
            else:
                removed_images.append(m.group(0))
                return ''
        new_line = img_pat.sub(repl, line)
        processed_lines.append(new_line)

    # 2) 基础空白清理：去行尾空格 + 折叠空行
    # 去除行尾空白
    processed_lines = [l.rstrip() + ("\n" if not l.endswith("\n") else "") for l in processed_lines]

    # 折叠多余空行（保留单个空行），同时去掉首尾空白行
    collapsed_lines = []
    prev_blank = True  # 去掉开头空行
    for l in processed_lines:
        is_blank = (l.strip() == "")
        if is_blank and prev_blank:
            continue
        collapsed_lines.append(l)
        prev_blank = is_blank
    # 去掉末尾空行
    while collapsed_lines and collapsed_lines[-1].strip() == "":
        collapsed_lines.pop()
    if collapsed_lines and not collapsed_lines[-1].endswith("\n"):
        collapsed_lines[-1] += "\n"

    lines = collapsed_lines

    # 2) 移除孤儿图注（图片已删，去除以 Figure/ Fig./ FIG./ 图 开头的段落，大小写不敏感）
    if drop_fig_caps and lines:
        new = []
        skip = False
        pat_fig = re.compile(r'^(figure|fig\.?|图|scheme|schematic|graph|chart)\s*[\.:]?\s*(?:[A-Za-z]*\s*)?(?:[IVXLCDM]+|S?\d+)\b', re.I)
        for ln in lines:
            s = ln.strip()
            if not skip and pat_fig.match(s):
                skip = True
                continue
            if skip:
                if s == '':
                    skip = False
                continue
            new.append(ln)
        lines = new

    # 4) 数学/化学公式（保守归一，仅数学环境内）
    if clean_math and lines:
        def normalize_math_text(t: str) -> str:
            # 命令规范化
            t = re.sub(r'\\bf\s*\{', r'\\mathbf{', t)
            t = re.sub(r'\\mathrm\s*\{', r'\\mathrm{', t)
            t = re.sub(r'\\mathsf\s*\{', r'\\mathsf{', t)
            # 数字空格合并
            t = re.sub(r'(\d)\s+(\d)', r'\1\2', t)
            # 上下标空格规整
            t = re.sub(r'\^\s*\{\s*([^}]+)\s*\}', r'^{\1}', t)
            t = re.sub(r'_\s*\{\s*([^}]+)\s*\}', r'_{\1}', t)
            # 常见化学式：去除 \\mathrm/\\mathbf 内部多余空格
            def compact_inside(cmd):
                pattern = re.compile(r'(\\' + cmd + r'\{)([^}]*)(\})')
                def _rep(m):
                    inner = m.group(2)
                    inner = re.sub(r'\s+', ' ', inner)
                    # 合并大写/小写字母与数字序列中的空格（保守）
                    inner = re.sub(r'([A-Za-z])\s+([A-Za-z0-9])', r'\1\2', inner)
                    # 去掉与 _ 和 ^ 相邻的多余空格
                    inner = re.sub(r'\s+_', r'_', inner)
                    inner = re.sub(r'\s+\^', r'^', inner)
                    inner = re.sub(r'(\d)\s+(\d)', r'\1\2', inner)
                    inner = re.sub(r'_\s*\{\s*([^}]+)\s*\}', r'_{\1}', inner)
                    inner = re.sub(r'\^\s*\{\s*([^}]+)\s*\}', r'^{\1}', inner)
                    return m.group(1) + inner + m.group(3)
                return pattern.sub(_rep, t)
            for cmd in ('mathrm','mathbf','mathsf'):
                t = compact_inside(cmd)
            # 温度与单位：290^{\circ} C -> 290^{\circ}\mathrm{C}
            t = re.sub(r'(\d+)\s*\^\{\\circ\}\s*C\b', r'\1^{\\circ}\\mathrm{C}', t)
            # \\mathbf 包裹纯数字：去掉
            t = re.sub(r'\\mathbf\{([0-9\.\-]+)\}', r'\1', t)
            # 花括号内首尾空格清理
            t = re.sub(r'\{\s*([^}]*?)\s*\}', r'{\1}', t)
            return t

        out_lines = []
        for ln in lines:
            # 逐个 $...$ 处理（不跨行）
            parts = []
            pos = 0
            while True:
                m = re.search(r'\$(.+?)\$', ln[pos:])
                if not m:
                    parts.append(ln[pos:])
                    break
                start = pos + m.start()
                end = pos + m.end()
                # 非贪婪匹配，处理该段
                math_text = m.group(1)
                math_norm = normalize_math_text(math_text)
                parts.append(ln[pos:start])
                parts.append('$' + math_norm + '$')
                pos = end
            out_lines.append(''.join(parts))
        lines = out_lines

    # 4) 参考文献剔除（标题法 + 形态回退更强规则）
    removed_refs = []
    if drop_refs and lines:
        try:
            title_pat = re.compile(r'^(#+\s*)?(参考文献|参考资料|References|Bibliography|Works Cited|Notes and references|References and Notes|Literature Cited)\b', re.I)
            cut_idx = None
            for i in range(int(len(lines)*0.5), len(lines)):
                s = lines[i].strip()
                if title_pat.match(s):
                    cut_idx = i
                    break
            if cut_idx is None:
                # 形态回退：在文末 40% 内查找“参考文献密集区”
                start_scan = int(len(lines) * 0.6)
                window = lines[start_scan:]

                def is_ref_like(s: str) -> bool:
                    s = s.strip()
                    if not s:
                        return False
                    score = 0
                    # 编号开头
                    if re.match(r'^(\[\d+[a-z]?\]|\d{1,3}[\.)]|[a-z]\))\s+', s, flags=re.I):
                        score += 2
                    # 年份/DOI
                    if re.search(r'(19|20)\d{2}', s):
                        score += 1
                    if re.search(r'10\.\d{4,9}/\S+', s, flags=re.I):
                        score += 2
                    # 期刊/出版社常见缩写
                    if re.search(r'(Phys\.|Chem\.|Catal\.|Angew\.|ACS |Appl\.|Commun\.|J\.\s|Rev\.|Sci\.|Technol\.|Surf\.|Lett\.)', s):
                        score += 1
                    # 页码/卷期
                    if re.search(r'\b\d{1,4}\s*[,;]\s*\d{1,4}([–\-]\d{1,4})?', s):
                        score += 1
                    return score >= 2

                flags = [is_ref_like(x) for x in window]
                # 位置约束：最后 25% 区域
                last_quarter = int(len(lines) * 0.75)
                # 寻找“第一个强参考行”的位置
                first_idx = next((i for i,f in enumerate(flags) if f), None)
                if first_idx is not None:
                    cand = start_scan + first_idx
                    if cand >= last_quarter:
                        # 连续性约束：后续 10 行内至少 5 行命中
                        tail = flags[first_idx:first_idx+10]
                        if len([1 for v in tail if v]) >= 5:
                            cut_idx = cand
            if cut_idx is not None:
                removed_refs = lines[cut_idx:]
                lines = lines[:cut_idx]
            else:
                # 进一步：删除位于文后半段的“参考文献样式块”（不整篇截断）
                start_scan = int(len(lines) * 0.5)
                i = start_scan
                new_lines = lines[:start_scan]
                while i < len(lines):
                    s = lines[i].strip()
                    if is_ref_like(s):
                        # 收集连续块（允许空行穿插）
                        j = i
                        block = []
                        ref_count = 0
                        while j < len(lines):
                            sj = lines[j].strip()
                            if sj == '':
                                block.append(lines[j])
                                j += 1
                                continue
                            if is_ref_like(sj):
                                block.append(lines[j])
                                ref_count += 1
                                j += 1
                                continue
                            break
                        # 判定块：长度>=5 且参考行比例>=0.6
                        if ref_count >= 5 and ref_count / max(1, len(block)) >= 0.6:
                            removed_refs.extend(block)
                            i = j
                            continue
                        # 否则保留原样
                        new_lines.extend(block)
                        i = j
                    else:
                        new_lines.append(lines[i])
                        i += 1
                lines = new_lines
        except Exception:
            pass

    # 3) 生成 .md 与 .txt 输出路径
    md_file_path = txt_file_path[:-4] + ".md" if txt_file_path.lower().endswith('.txt') else txt_file_path + ".md"
    # 确保目录存在
    for out_path in (md_file_path, txt_file_path):
        dir_path = path.dirname(out_path)
        if dir_path:
            path_check(dir_path)

    # 6) 写入清洗后的 Markdown
    with open(md_file_path, 'w', encoding='utf-8') as f_md:
        f_md.writelines(lines)

    # 5) 生成轻量纯文本（去除常见 Markdown 标记）
    def md_to_text(lines: list) -> list:
        out = []
        for ln in lines:
            s = ln
            # 链接 [text](url) -> text
            s = sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
            # 强调/删除线/行内代码标记去除，但保留内容
            s = s.replace("**", "").replace("__", "").replace("*", "").replace("_", "").replace("~~", "").replace("`", "")
            # 标题/引用/列表标记去除
            s = sub(r"^\s{0,3}#{1,6}\s*", "", s)          # #, ## ... ######
            s = sub(r"^\s{0,3}>\s?", "", s)                # blockquote
            s = sub(r"^\s*[-+*]\s+", "", s)               # unordered list
            s = sub(r"^\s*\d+[\.)]\s+", "", s)          # ordered list
            # 表格分隔去除
            s = sub(r"^\s*\|", "", s)
            s = s.replace("|", "\t")  # 粗暴转为制表符，保留信息
            # 代码围栏去除（仅去掉标记，不清空内容）
            s = sub(r"^\s*```.*$", "", s)
            # 多余空白
            s = s.rstrip()
            out.append(s + ("\n" if not s.endswith("\n") else ""))
        # 再次折叠空行
        final = []
        prev_blank = True
        for l in out:
            blank = (l.strip() == "")
            if blank and prev_blank:
                continue
            final.append(l)
            prev_blank = blank
        while final and final[-1].strip() == "":
            final.pop()
        if final and not final[-1].endswith("\n"):
            final[-1] += "\n"
        return final

    txt_lines = md_to_text(lines)
    with open(txt_file_path, 'w', encoding='utf-8') as f_txt:
        f_txt.writelines(txt_lines)

    # 7) 日志信息与参考文献存档
    if removed_refs:
        try:
            logs_root = getenv('MINERU_LOGS_DIR') or 'logs'
            removed_dir = path.join(logs_root, 'removed_refs')
            path_check(removed_dir)
            with open(path.join(removed_dir, f'{md_name}.md'), 'w', encoding='utf-8') as rf:
                rf.writelines(removed_refs)
        except Exception:
            pass

    process_steps = []
    process_steps.append(f"去除图片{len(removed_images)}处")
    process_steps.append("折叠空行与去尾空白/二阶段清洗")
    return {
        "index": md_name,
        "process": "，".join(process_steps),
        "md_path": md_file_path,
        "txt_path": txt_file_path,
    }


def api_key_change(type, value):
    """按照格式转化 API key"""

    return getenv(value) if type == "Environment Variable" else value


def markdown_to_html(md_text, extensions=None):
    """将 Markdown 文本转换为 HTML"""
    
    if extensions is None:
        extensions = ['extra', 'fenced_code', 'nl2br', 'admonition']
    
    html_body = markdown.markdown(md_text, extensions=extensions)
    
    css_style = """
    <style>
        body { 
            max-width: 800px;
            margin: auto;
            padding: 1em;
            font-family: 'Microsoft YaHei UI', monospace;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }
        table, th, td {
            border: 1px solid #ddd;
        }
        th, td {
            padding: 8px 12px;
        }
        th {
            background-color: #f2f2f2;
        }
    </style>
    """
    html = f"""<!DOCTYPE html>
        <html lang="zh-CN">
        <head>
        <meta charset="UTF-8">
        <title>Markdown Render</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/default.min.css">
        {css_style}
        </head>
        <body>
        {html_body}
        </body>
        </html>
    """
    return html
