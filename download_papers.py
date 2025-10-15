#!/usr/bin/env python3
"""
自动化下载 Excel 表（默认 undownload.xlsx）中的论文 PDF。

特性概览：
- 支持通过 DOI 或 标题 检索下载，优先 DOI。
- 自动识别列：index（用于命名）、DOI（多候选）、Title（多候选）。
- 优先使用 Unpaywall（需设置邮箱），回退到 DOI 内容协商与落地页解析。
- 可选标题 → Crossref 查询获取 DOI。
- 下载日志：download_log.csv（index, doi, title, status, notes）。
- 速率控制：--delay，区间抽样：--start/--limit，交互模式：--interactive。

依赖：requests pandas openpyxl beautifulsoup4

用法示例：
    python3 download_papers.py --input undownload.xlsx --delay 2 --limit 5 \
        --email you@domain

环境变量：
    UNPAYWALL_EMAIL  指定 Unpaywall 访问邮箱（与 --email 二选一，参数优先）。
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict

import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs


# 常量与默认设置
PDF_DIR_DEFAULT = "pdfs"
LOG_FILE_DEFAULT = "download_log.csv"
TIMEOUT_SECONDS = 25
MAX_CONTENT_MB = 200

DOI_CANDIDATES = [
    "DOI",
    "DOI Number",
    "Digital Object Identifier",
]

TITLE_CANDIDATES = [
    "Article Title",
    "Title",
    "Paper Title",
    "Document Title",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"

# 全局运行参数（Playwright 兜底配置在 main 中解析，通过环境变量传递细粒度参数较繁琐。
# 这里采用在调用处动态感知 sys.argv 与 os.environ 的方式获取必要参数。）


@dataclass
class RowData:
    idx: str
    doi: Optional[str]
    title: Optional[str]


def eprint(*args, **kwargs):  # 简洁 stderr 输出
    print(*args, file=sys.stderr, **kwargs)


def sanitize_filename(name: str) -> str:
    """清洗文件名中的非法字符，保留常用字符。"""
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", str(name)).strip()
    return cleaned or "unnamed"


def normalize_doi(doi: str) -> str:
    """更稳健地标准化/提取 DOI：
    - 去掉前缀（doi:, https://doi.org/ 等）
    - 允许在一段文本中提取第一个 DOI
    - 去掉尾随的常见标点与括号
    - 移除内部空白
    不做 URL 编码。
    """
    if not doi:
        return ""
    d = str(doi).strip()
    # 统一去前缀
    d = re.sub(r"^\s*doi\s*:\s*", "", d, flags=re.I)
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d, flags=re.I)
    # 若仍包含 DOI 模式，则从中提取
    m = re.search(r"(10\.\d{4,9}/[^\s\"'<>\)\]\}]+)", d, flags=re.I)
    if m:
        d = m.group(1)
    # 去除包裹性括号与引号
    d = d.strip().strip("'\"").strip()
    d = d.strip().strip("()[]{}<>《》（）【】‘’“”")
    # 去掉尾随常见标点（含中英文）
    d = d.rstrip(".,;:，。：；、！!？?\u3000")
    # 移除内部空白
    d = re.sub(r"\s+", "", d)
    return d


def is_probably_doi(text: str) -> bool:
    if not text:
        return False
    t = normalize_doi(text)
    # 粗略 DOI 模式
    return bool(re.match(r"^10\.\d{4,9}/\S+", t))


def pick_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """不区分大小写匹配列名，返回命中的真实列名。"""
    lower_to_real: Dict[str, str] = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_to_real:
            return lower_to_real[cand.lower()]
    return None


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def init_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": ACCEPT_LANGUAGE,
    })
    s.max_redirects = 20
    return s


def head_with_accept_pdf(session: requests.Session, url: str, timeout: int = TIMEOUT_SECONDS) -> requests.Response:
    headers = {"Accept": "application/pdf, */*;q=0.1"}
    return session.head(url, timeout=timeout, allow_redirects=True, headers=headers)


def get_with_html(session: requests.Session, url: str, timeout: int = TIMEOUT_SECONDS) -> requests.Response:
    headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    return session.get(url, timeout=timeout, allow_redirects=True, headers=headers)


def parse_link_header_for_pdf(link_header: Optional[str]) -> Optional[str]:
    """解析 HTTP Link 头，提取指向 application/pdf 的 URL。"""
    if not link_header:
        return None
    try:
        parts = [p.strip() for p in link_header.split(",") if p.strip()]
        for p in parts:
            if not p.startswith("<") or ">" not in p:
                continue
            url = p[1:p.index(">")]
            params = p[p.index(">") + 1 :]
            # 查找 type 或 content-type
            ctype = None
            rel = None
            for seg in params.split(";"):
                kv = seg.strip().split("=", 1)
                if len(kv) != 2:
                    continue
                k = kv[0].strip().lower()
                v = kv[1].strip().strip('"')
                if k in {"type", "content-type"}:
                    ctype = v.lower()
                elif k == "rel":
                    rel = v.lower()
            if (ctype and "application/pdf" in ctype) or (rel and "alternate" in rel and (ctype or "").find("pdf") != -1):
                return url
    except Exception:
        return None
    return None


def try_crossref_pdf(doi: str, session: requests.Session) -> Optional[str]:
    """从 Crossref 元数据中尝试提取 PDF 链接。"""
    if not doi:
        return None
    api = f"https://api.crossref.org/works/{requests.utils.quote(doi)}"
    try:
        r = session.get(api, timeout=TIMEOUT_SECONDS)
        if r.status_code != 200:
            return None
        msg = (r.json() or {}).get("message") or {}
        links = msg.get("link") or []
        # 优先 content-type 为 application/pdf 的链接
        for lk in links:
            if (lk.get("content-type") or "").lower() == "application/pdf" and lk.get("URL"):
                return lk.get("URL")
        # 其次尝试任何看起来像 pdf 的 URL
        for lk in links:
            url = lk.get("URL") or ""
            if url.lower().endswith(".pdf"):
                return url
        return None
    except Exception:
        return None


def try_openalex_pdf(doi: str, session: requests.Session) -> Optional[str]:
    """从 OpenAlex 获取 OA PDF 链接。无需注册。"""
    if not doi:
        return None
    api = f"https://api.openalex.org/works/doi:{requests.utils.quote(doi)}"
    try:
        r = session.get(api, timeout=TIMEOUT_SECONDS)
        if r.status_code != 200:
            return None
        data = r.json() or {}
        loc = data.get("best_oa_location") or {}
        url = loc.get("url_for_pdf") or loc.get("pdf_url") or loc.get("url")
        return url
    except Exception:
        return None


def try_unpaywall_pdf(doi: str, email: Optional[str], session: requests.Session) -> Optional[str]:
    """调用 Unpaywall 获取 OA PDF 链接。"""
    if not email:
        return None
    if not doi:
        return None
    api = f"https://api.unpaywall.org/v2/{requests.utils.quote(doi)}?email={requests.utils.quote(email)}"
    try:
        r = session.get(api, timeout=TIMEOUT_SECONDS)
        if r.status_code != 200:
            return None
        data = r.json()
        loc = data.get("best_oa_location") or {}
        url = loc.get("url_for_pdf") or loc.get("url")
        if url:
            return url
        # 回退：在所有 OA 位置中找 pdf
        for item in (data.get("oa_locations") or []):
            if item.get("url_for_pdf"):
                return item.get("url_for_pdf")
        return None
    except Exception:
        return None


def parse_pdf_from_html(html_text: str, base_url: str) -> Optional[str]:
    """从落地页 HTML 中解析 PDF 链接，增强版启发式（规避补充材料）。"""
    soup = BeautifulSoup(html_text, "html.parser")

    def join(href: str) -> str:
        return requests.compat.urljoin(base_url, href)

    candidates: List[Tuple[str, int]] = []  # (url, score)

    # 1) 通用元标签（高可信）
    for name in ("citation_pdf_url", "citation_fulltext_pdf", "dc.identifier", "pdfurl"):
        for tag in soup.find_all("meta", attrs={"name": name}):
            href = tag.get("content")
            if href:
                candidates.append((join(href), 100))

    # 2) link rel alternate type=application/pdf
    for tag in soup.find_all("link"):
        rel = " ".join(tag.get("rel", [])).lower()
        typ = (tag.get("type") or "").lower()
        href = tag.get("href") or tag.get("content")
        if href and ("application/pdf" in typ or "alternate" in rel):
            candidates.append((join(href), 90))

    # 3) 所有明显的 pdf 超链接，评分并过滤补充材料
    def is_supp(u: str, text: str) -> bool:
        t = (u + " " + text).lower()
        sup_kw = ["supp", "supplement", "supporting", "esi", "si", "suppl"]
        return any(k in t for k in sup_kw)

    page_host = urlparse(base_url).netloc
    for tag in soup.find_all("a"):
        href = tag.get("href") or ""
        if not href:
            continue
        text = (tag.get_text() or "").strip()
        url = join(href)
        score = 0
        low_href = href.lower()
        if low_href.endswith(".pdf") or "/pdf" in low_href or "pdf" in low_href:
            score += 30
        if text:
            t = text.lower()
            if "pdf" in t:
                score += 15
            if "full" in t or "article" in t:
                score += 5
        if urlparse(url).netloc == page_host:
            score += 3
        if is_supp(low_href, text):
            score -= 60
        if score >= 20:  # 过滤明显噪音
            candidates.append((url, score))

    if not candidates:
        return None
    # 选最高分
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def playwright_fallback_download(
    doi: Optional[str],
    article_url: Optional[str],
    pdf_hint: Optional[str],
    out_path: Path,
    session: requests.Session,
) -> Tuple[bool, str]:
    """使用 Playwright 浏览器做最后兜底：打开文章页，尝试点击 PDF 并保存。

    要求：已通过 --use-playwright 启用；用户需自行安装 playwright 并执行 playwright install。
    逻辑：
      1) 依次尝试进入 article_url / DOI 落地页 / pdf_hint 所在页。
      2) 在页面上寻找明显的 PDF 链接/按钮，优先非补充材料。
      3) 使用 expect_download 捕获下载；若无下载事件，则提取 href 并回退到 requests 流式下载，
         同时从浏览器上下文复制 Cookie 到 requests 的 session（最大化命中）。
    """
    # 读取 CLI 参数（从 sys.argv 解析）
    browser_name = "chromium"
    headless = True
    timeout_ms = 30000
    user_data_dir = None
    try:
        argv = sys.argv
        if "--browser" in argv:
            i = argv.index("--browser")
            if i + 1 < len(argv):
                browser_name = argv[i + 1]
        headless = not ("--playwright-headful" in argv)
        if "--playwright-timeout" in argv:
            i = argv.index("--playwright-timeout")
            if i + 1 < len(argv):
                timeout_ms = int(argv[i + 1])
        if "--user-data-dir" in argv:
            i = argv.index("--user-data-dir")
            if i + 1 < len(argv):
                user_data_dir = argv[i + 1]
    except Exception:
        pass

    def is_supp(u: str, t: str) -> bool:
        s = (u + " " + t).lower()
        return any(k in s for k in ["supp", "supplement", "supporting", "esi", "si", "suppl"])  # noqa: E501

    def join(base: str, href: str) -> str:
        return requests.compat.urljoin(base, href)

    target_urls: List[str] = []
    if article_url:
        target_urls.append(article_url)
    if doi and is_probably_doi(doi):
        target_urls.append(f"https://doi.org/{requests.utils.quote(normalize_doi(doi))}")
    if pdf_hint:
        # 若只有 pdf 线索，也先尝试打开其 referer 页
        ref = guess_referer_from_pdf_url(pdf_hint)
        if ref:
            target_urls.append(ref)
        target_urls.append(pdf_hint)

    # 去重，保持顺序
    seen = set()
    unique_targets = []
    for u in target_urls:
        if u and u not in seen:
            seen.add(u)
            unique_targets.append(u)

    try:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return False, "playwright-not-installed"

        with sync_playwright() as p:
            btype = getattr(p, browser_name, None)
            if btype is None:
                return False, f"unknown-browser:{browser_name}"

            # 建立上下文（优先持久化目录，以复用已登录态）
            context = None
            browser = None
            try:
                if user_data_dir:
                    context = btype.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        headless=headless,
                        accept_downloads=True,
                    )
                else:
                    browser = btype.launch(headless=headless)
                    context = browser.new_context(accept_downloads=True)
            except Exception as e:
                return False, f"launch-failed:{type(e).__name__}"

            page = context.new_page()

            def try_single(url: str) -> Tuple[bool, str]:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception:
                    # 继续尝试下一个 URL
                    return False, "goto-failed"

                # 若当前就是 PDF 直链，尝试触发保存（有些会直接触发下载）
                if page.url.lower().endswith(".pdf"):
                    # 没有 download 事件时，直接让 requests 去下（复制 Cookie）
                    pdf_url2 = page.url
                    # 将浏览器 Cookie 合并到 requests session
                    try:
                        for ck in context.cookies():
                            try:
                                cookie = requests.cookies.create_cookie(
                                    name=ck.get("name"),
                                    value=ck.get("value"),
                                    domain=ck.get("domain") or urlparse(page.url).hostname,
                                    path=ck.get("path") or "/",
                                )
                                session.cookies.set_cookie(cookie)
                            except Exception:
                                continue
                    except Exception:
                        pass
                    okx, note = stream_download(
                        session,
                        pdf_url2,
                        out_path,
                        headers={"Accept": "application/pdf, */*;q=0.1", "Referer": url},
                    )
                    if okx:
                        return True, "browser-goto-pdf"
                    return False, f"goto-pdf-failed:{note}"

                # 页面内寻找 PDF 链接
                # 使用多种选择器组合
                selectors = [
                    'a[aria-label*="PDF" i]',
                    'a:has-text("PDF")',
                    'a[title*="PDF" i]',
                    'a[href$=".pdf"]',
                    'a[href*="/pdf"]',
                    'link[rel="alternate"][type="application/pdf"]',
                ]
                pdf_candidates: List[Tuple[str, int]] = []
                for sel in selectors:
                    try:
                        for el in page.locator(sel).all():
                            try:
                                href = el.get_attribute("href") or el.get_attribute("content") or ""
                                text = el.inner_text(timeout=1000) or ""
                            except Exception:
                                href = el.get_attribute("href") or el.get_attribute("content") or ""
                                text = ""
                            if not href:
                                continue
                            abs_url = join(page.url, href)
                            score = 0
                            lh = href.lower()
                            if lh.endswith(".pdf") or "/pdf" in lh or "pdf" in lh:
                                score += 30
                            if text and ("pdf" in text.lower()):
                                score += 10
                            if is_supp(href, text):
                                score -= 60
                            if score >= 10:
                                pdf_candidates.append((abs_url, score))
                    except Exception:
                        continue
                if not pdf_candidates:
                    return False, "no-pdf-link"
                pdf_candidates.sort(key=lambda x: x[1], reverse=True)
                target_pdf = pdf_candidates[0][0]

                # 优先使用浏览器下载（捕获 download 事件）
                try:
                    # 找到对应元素再次点击
                    with page.expect_download(timeout=timeout_ms) as dl_info:
                        # 尝试点击一个包含该 href 的元素
                        page.locator(f'a[href="{target_pdf}"]').first.click(timeout=timeout_ms)
                    d = dl_info.value
                    d.save_as(str(out_path))
                    # 简单校验
                    if out_path.exists() and out_path.stat().st_size > 1024:
                        return True, "browser-download"
                except Exception:
                    # 可能未触发 download 事件（内联 PDF），退回 requests 下载
                    pass

                # 将浏览器 Cookie 合并到 requests session 后用直连下载
                try:
                    for ck in context.cookies():
                        try:
                            cookie = requests.cookies.create_cookie(
                                name=ck.get("name"),
                                value=ck.get("value"),
                                domain=ck.get("domain") or urlparse(target_pdf).hostname,
                                path=ck.get("path") or "/",
                            )
                            session.cookies.set_cookie(cookie)
                        except Exception:
                            continue
                except Exception:
                    pass

                okx, note = stream_download(
                    session,
                    target_pdf,
                    out_path,
                    headers={"Accept": "application/pdf, */*;q=0.1", "Referer": page.url},
                )
                if okx:
                    return True, "browser-cookie-requests"
                return False, f"requests-failed:{note}"

            last_note = ""
            for u in unique_targets:
                ok1, n1 = try_single(u)
                if ok1:
                    try:
                        context.close()
                    except Exception:
                        pass
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass
                    return True, n1
                last_note = n1

            try:
                context.close()
            except Exception:
                pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            return False, last_note or "no-target"
    except Exception as e:
        return False, f"playwright-error:{type(e).__name__}"


def guess_referer_from_pdf_url(pdf_url: str) -> Optional[str]:
    """根据常见站点的 PDF 直链推断文章页 Referer。"""
    try:
        u = urlparse(pdf_url)
        host = u.netloc.lower()
        path = u.path
        scheme = u.scheme or "https"

        def build(url_path: str) -> str:
            return f"{scheme}://{host}{url_path}"

        if not host:
            return None
        # MDPI: /.../pdf -> /...
        if "mdpi.com" in host and "/pdf" in path:
            base = path.replace("/pdf", "")
            return build(base)
        # ACS: /doi/pdf/DOI -> /doi/DOI
        if "pubs.acs.org" in host and "/doi/pdf/" in path:
            base = path.replace("/doi/pdf/", "/doi/")
            return build(base)
        # Springer: /content/pdf/10...pdf -> /article/10...
        if "springer.com" in host and "/content/pdf/" in path and path.endswith(".pdf"):
            base = path.replace("/content/pdf/", "/article/").rsplit(".pdf", 1)[0]
            return build(base)
        # Wiley: /doi/pdfdirect/DOI 或 /doi/pdf/DOI -> /doi/full/DOI
        if "wiley.com" in host and "/doi/" in path and ("/pdf" in path or "/pdfdirect" in path):
            base = path
            base = base.replace("/pdfdirect/", "/full/")
            base = base.replace("/pdf/", "/full/")
            return build(base)
        # ScienceDirect: /science/article/am/pii/<id> -> /science/article/pii/<id>
        if "sciencedirect.com" in host and "/science/article/" in path:
            base = path.replace("/science/article/am/", "/science/article/")
            return build(base)
        # Taylor & Francis（尽力而为）: /doi/pdf/... -> /doi/full/...
        if "tandfonline.com" in host and "/doi/pdf" in path:
            base = path.replace("/doi/pdf/", "/doi/full/")
            return build(base)
        # IEEE Xplore: /stamp/stamp.jsp?tp=&arnumber=XXXX -> /document/XXXX/
        if "ieeexplore.ieee.org" in host and "/stamp/stamp.jsp" in path:
            try:
                qs = parse_qs(urlparse(pdf_url).query)
                ar = (qs.get("arnumber") or [None])[0]
                if ar:
                    return build(f"/document/{ar}/")
            except Exception:
                pass
        # AIP/Scitation: /doi/pdf/DOI -> /doi/DOI
        if ("scitation.org" in host or "aip.org" in host) and "/doi/pdf/" in path:
            base = path.replace("/doi/pdf/", "/doi/")
            return build(base)
        # ACM: dl.acm.org/doi/pdf/... -> /doi/...
        if ("dl.acm.org" in host) and "/doi/pdf/" in path:
            base = path.replace("/doi/pdf/", "/doi/")
            return build(base)
        # OUP: academic.oup.com/.../article-pdf/... -> 相应 article 页（尽力）
        if "oup.com" in host and "/article-pdf/" in path:
            base = path.replace("/article-pdf/", "/article/")
            base = base.rsplit(".pdf", 1)[0]
            return build(base)
        # Nature: /articles/xxxx.pdf -> /articles/xxxx
        if "nature.com" in host and path.endswith(".pdf") and "/articles/" in path:
            base = path.rsplit(".pdf", 1)[0]
            return build(base)
        # IOP: iopscience.iop.org/pdf/... -> /article/...
        if "iop.org" in host and "/pdf/" in path:
            base = path.replace("/pdf/", "/article/").rsplit(".pdf", 1)[0]
            return build(base)
        # PNAS/AAS: /doi/pdf/... -> /doi/full/...
        if ("pnas.org" in host or "aip.org" in host or "royalsocietypublishing.org" in host) and "/doi/pdf" in path:
            base = path.replace("/doi/pdf/", "/doi/full/")
            return build(base)
        # Frontiers: /articles/pdf/... -> /articles/...
        if "frontiersin.org" in host and "/articles/" in path and "/pdf" in path:
            base = path.replace("/pdf", "")
            return build(base)
        # RSC（尽力）: articlepdf -> articlelanding
        if "rsc.org" in host and "articlepdf" in path:
            base = path.replace("articlepdf", "articlelanding")
            return build(base)
        # 默认回退：站点根
        return f"{scheme}://{host}/"
    except Exception:
        return None


def fetch_pdf_via_doi(doi: str, session: requests.Session, email: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    通过 DOI 获取 PDF。
    返回 (pdf_url, note)。pdf_url 为最终可下载的 pdf 链接（若探测到），否则为 None。
    """
    doi_norm = normalize_doi(doi)
    if not doi_norm:
        return None, "empty-doi"

    # 1) Unpaywall 优先
    pdf_url = try_unpaywall_pdf(doi_norm, email=email, session=session)
    if pdf_url:
        return pdf_url, "unpaywall"

    # 2) Crossref 元数据中的 PDF 链接
    cr_pdf = try_crossref_pdf(doi_norm, session=session)
    if cr_pdf:
        return cr_pdf, "crossref-link"

    # 3) OpenAlex OA 位置
    oa_pdf = try_openalex_pdf(doi_norm, session=session)
    if oa_pdf:
        return oa_pdf, "openalex"

    # 4) DOI 内容协商：优先 HEAD（含 Link 头），必要时 GET 复核
    doi_url = f"https://doi.org/{requests.utils.quote(doi_norm)}"
    try:
        h = head_with_accept_pdf(session, doi_url)
        ctype = h.headers.get("Content-Type", "").lower()
        if "application/pdf" in ctype and h.url:
            return h.url, "doi-head-pdf"
        # 一些注册机构通过 Link 提供 pdf 备选
        link_hdr = h.headers.get("Link") or h.headers.get("link")
        pdf_from_link = parse_link_header_for_pdf(link_hdr)
        if pdf_from_link:
            return pdf_from_link, "doi-link-header"
    except Exception:
        pass

    # GET + Accept: application/pdf，以便跟随 303 定位至 pdf
    try:
        g = session.get(doi_url, timeout=TIMEOUT_SECONDS, allow_redirects=True, headers={"Accept": "application/pdf, */*;q=0.1"})
        if g.status_code == 200:
            g_ctype = (g.headers.get("Content-Type") or "").lower()
            if "application/pdf" in g_ctype and g.url:
                return g.url, "doi-get-pdf"
            link_hdr = g.headers.get("Link") or g.headers.get("link")
            pdf_from_link = parse_link_header_for_pdf(link_hdr)
            if pdf_from_link:
                return pdf_from_link, "doi-get-link"
    except Exception:
        pass

    # 5) 访问落地页解析 html 中可能的 pdf 链接
    try:
        r = get_with_html(session, doi_url)
        if r.status_code == 200 and r.text:
            cand = parse_pdf_from_html(r.text, r.url)
            if cand:
                return cand, "html-parse"
    except Exception:
        pass

    # 6) 若是常见的补充材料 DOI（如 ACS: ...s001），尝试回退到主体 DOI
    try:
        if re.search(r"\.s\d{2,4}$", doi_norm, flags=re.I):
            parent = re.sub(r"\.s\d{2,4}$", "", doi_norm, flags=re.I)
            if parent and parent != doi_norm:
                pdf2, note2 = fetch_pdf_via_doi(parent, session=session, email=email)
                if pdf2:
                    return pdf2, f"parent-doi:{note2}"
    except Exception:
        pass

    return None, "no-pdf-from-doi"


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower().strip(), (b or "").lower().strip()).ratio()


def crossref_find_doi_by_title(title: str, session: requests.Session) -> Optional[str]:
    """使用 Crossref 根据标题查找 DOI。"""
    if not title:
        return None
    url = "https://api.crossref.org/works"
    params = {"query.title": title, "rows": 3}
    try:
        r = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        if r.status_code != 200:
            return None
        data = r.json()
        items = (data.get("message") or {}).get("items") or []
        best: Tuple[float, Optional[str]] = (0.0, None)
        for it in items:
            cand_title_list = it.get("title") or []
            cand_title = cand_title_list[0] if cand_title_list else ""
            score = similar(title, cand_title)
            if score > best[0]:
                best = (score, it.get("DOI"))
        if best[0] >= 0.80 and best[1]:
            return best[1]
        return None
    except Exception:
        return None


def stream_download(
    session: requests.Session,
    url: str,
    out_path: Path,
    timeout: int = TIMEOUT_SECONDS,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    """流式下载 URL 到 out_path。返回 (ok, note)。可自定义 headers。

    仅当 Content-Type 为 application/pdf 或首块数据包含 PDF 魔数（%PDF-）时写入，
    避免将 HTML/登录页误存为 PDF。
    """
    try:
        h = headers or {}
        with session.get(url, stream=True, timeout=timeout, headers=h) as r:
            if r.status_code >= 400:
                return False, f"http-{r.status_code}"
            ctype = (r.headers.get("Content-Type") or "").lower()
            # 预读首块以判定是否为 PDF
            first_chunk: bytes = b""
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    first_chunk = chunk
                    break
            if not first_chunk:
                return False, "empty-file"

            def looks_like_pdf(buf: bytes) -> bool:
                head = buf[:1024]
                return b"%PDF-" in head

            is_pdf_ct = "application/pdf" in ctype
            is_pdf_sig = looks_like_pdf(first_chunk)
            if not (is_pdf_ct or is_pdf_sig):
                return False, "not-pdf"
            total = 0
            max_bytes = MAX_CONTENT_MB * 1024 * 1024
            with open(out_path, "wb") as f:
                # 写入首块
                f.write(first_chunk)
                total += len(first_chunk)
                if total > max_bytes:
                    return False, "too-large"
                # 继续写入后续块
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        total += len(chunk)
                        if total > max_bytes:
                            return False, "too-large"
                        f.write(chunk)
        # 基础校验：非空
        if out_path.exists() and out_path.stat().st_size > 1024:
            return True, "downloaded"
        return False, "empty-file"
    except Exception as e:
        return False, f"error:{type(e).__name__}"


def detect_columns(df: pd.DataFrame, doi_col_arg: Optional[str], title_col_arg: Optional[str]) -> Tuple[str, Optional[str], Optional[str]]:
    """
    返回 (index_col, doi_col, title_col)。
    index_col：优先第一列，其次名为 index（不区分大小写）。
    doi_col / title_col：按参数或候选自动识别。
    """
    if df.empty:
        raise ValueError("输入表为空")

    # index 列
    index_col = df.columns[0]
    for c in df.columns:
        if c.lower() == "index":
            index_col = c
            break

    # doi 列
    doi_col = doi_col_arg or pick_column(df, DOI_CANDIDATES)
    # title 列
    title_col = title_col_arg or pick_column(df, TITLE_CANDIDATES)

    return index_col, doi_col, title_col


def iter_rows(df: pd.DataFrame, index_col: str, doi_col: Optional[str], title_col: Optional[str]) -> Iterable[RowData]:
    for _, row in df.iterrows():
        idx = str(row.get(index_col, "")).strip()
        doi_val = str(row.get(doi_col, "")).strip() if doi_col else ""
        title_val = str(row.get(title_col, "")).strip() if title_col else ""
        idx = idx if idx else ""
        doi_val = doi_val if doi_val.lower() != "nan" else ""
        title_val = title_val if title_val.lower() != "nan" else ""
        yield RowData(idx=idx, doi=doi_val or None, title=title_val or None)


def append_log(log_path: Path, records: List[Tuple[str, str, str, str, str]]) -> None:
    is_new = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["index", "doi", "title", "status", "notes"])
        for rec in records:
            w.writerow(rec)


def process_row(
    row: RowData,
    out_dir: Path,
    session: requests.Session,
    email: Optional[str],
    overwrite: bool,
) -> Tuple[str, str, str, str, str]:
    """处理单行，返回日志记录。"""
    idx = row.idx
    doi = row.doi or ""
    title = row.title or ""

    if not idx:
        return (idx, doi, title, "no_index", "跳过：index 为空")

    file_name = f"{sanitize_filename(idx)}.pdf"
    out_path = out_dir / file_name

    if out_path.exists() and not overwrite:
        return (idx, doi, title, "exists", str(out_path))

    # 优先 DOI 下载
    pdf_url = None
    note = ""
    if doi and is_probably_doi(doi):
        pdf_url, note = fetch_pdf_via_doi(doi, session=session, email=email)

    # 无 DOI 或 DOI 失败时，尝试标题 → Crossref 找 DOI
    if not pdf_url and title:
        cr_doi = crossref_find_doi_by_title(title, session=session)
        if cr_doi:
            doi = cr_doi
            pdf_url, note = fetch_pdf_via_doi(cr_doi, session=session, email=email)
            if not pdf_url:
                note = f"crossref-doi:{note}"

    if not pdf_url:
        # 最后尝试：对 DOI 做 GET + Accept: application/pdf，若服务器直接返回 PDF 则保存
        if doi and is_probably_doi(doi):
            doi_url = f"https://doi.org/{requests.utils.quote(normalize_doi(doi))}"
            ok, dnote = stream_download(
                session,
                doi_url,
                out_path,
                headers={"Accept": "application/pdf, */*;q=0.1"},
            )
            if ok:
                return (idx, doi, title, "downloaded", f"doi-get")
            # 若直接下载失败，则继续返回 not_found
        return (idx, doi, title, "not_found", note or "no-pdf")

    # 首选根据直链推断文章页 Referer；无则回退 DOI Referer
    art_ref = guess_referer_from_pdf_url(pdf_url)
    doi_ref = f"https://doi.org/{requests.utils.quote(normalize_doi(doi))}" if doi else None
    ref = art_ref or doi_ref
    hdrs = {"Accept": "application/pdf, */*;q=0.1"}
    if ref:
        hdrs["Referer"] = ref
    # 预取文章页以携带站点 Cookie（若有）
    try:
        if art_ref and (urlparse(art_ref).netloc != "doi.org"):
            get_with_html(session, art_ref)
    except Exception:
        pass
    ok, dnote = stream_download(session, pdf_url, out_path, headers=hdrs)
    # 若受限，尝试以 DOI 作为 Referer 再试一次
    if not ok and dnote in {"http-403", "not-pdf", "empty-file"} and doi_ref and art_ref != doi_ref:
        try:
            get_with_html(session, doi_ref)
        except Exception:
            pass
        hdrs2 = {"Accept": "application/pdf, */*;q=0.1", "Referer": doi_ref}
        ok2, dnote2 = stream_download(session, pdf_url, out_path, headers=hdrs2)
        if ok2:
            return (idx, doi, title, "downloaded", pdf_url)
        else:
            return (idx, doi, title, "error", f"{dnote2}|{pdf_url}")
    if ok:
        return (idx, doi, title, "downloaded", pdf_url)
    # 最终回退：直接对 DOI 执行 GET + Accept: application/pdf
    if doi and is_probably_doi(doi):
        doi_url_final = f"https://doi.org/{requests.utils.quote(normalize_doi(doi))}"
        ok3, dnote3 = stream_download(
            session,
            doi_url_final,
            out_path,
            headers={"Accept": "application/pdf, */*;q=0.1"},
        )
        if ok3:
            return (idx, doi, title, "downloaded", "doi-get-final")
        # Playwright 兜底（如启用）
        # 延后到下面统一处理
        last_fallback_note = f"{dnote}|{pdf_url}|fallback:{dnote3}"
    else:
        last_fallback_note = f"{dnote}|{pdf_url}"

    # 若启用了 Playwright，则用浏览器兜底尝试一次
    try:
        from argparse import Namespace
        # 获取顶层 main 的 args 需传入，这里通过环境变量标记不可靠；
        # 简化处理：检查全局 sys.argv 是否包含 --use-playwright
        use_pw = any(a == "--use-playwright" for a in sys.argv)
    except Exception:
        use_pw = False

    if use_pw:
        okb, nb = playwright_fallback_download(
            doi=(doi or None),
            article_url=art_ref or doi_ref,
            pdf_hint=pdf_url,
            out_path=out_path,
            session=session,
        )
        if okb:
            return (idx, doi, title, "downloaded", nb)
        else:
            return (idx, doi, title, "error", f"{last_fallback_note}|playwright:{nb}")

    return (idx, doi, title, "error", last_fallback_note)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="根据 DOI/标题从 Excel 批量下载论文 PDF")
    parser.add_argument("--input", default="undownload.xlsx", help="输入 Excel 文件路径（默认 undownload.xlsx）")
    parser.add_argument("--output-dir", default=PDF_DIR_DEFAULT, help="PDF 输出目录（默认 pdfs/）")
    parser.add_argument("--log-file", default=LOG_FILE_DEFAULT, help="下载日志 CSV（默认 download_log.csv）")
    parser.add_argument("--doi-column", default=None, help="覆盖 DOI 列名自动识别")
    parser.add_argument("--title-column", default=None, help="覆盖 Title 列名自动识别")
    parser.add_argument("--start", type=int, default=0, help="从第几个样本开始（基于切片起点）")
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少条记录")
    parser.add_argument("--delay", type=float, default=0.0, help="每条记录之间的延时（秒）")
    parser.add_argument("--email", default=None, help="Unpaywall 邮箱（或用环境变量 UNPAYWALL_EMAIL）")
    parser.add_argument("--overwrite", action="store_true", help="已存在同名 PDF 时是否覆盖")
    parser.add_argument("--interactive", action="store_true", help="交互模式（目前用于确认与提示）")
    parser.add_argument("--insecure", action="store_true", help="忽略 SSL 证书校验（不安全，仅在特定站点临时使用）")
    parser.add_argument("--use-browser-cookies", action="store_true", help="尝试从本机浏览器导入站点 Cookie（需要 browser-cookie3）")
    parser.add_argument("--enable-cache", action="store_true", help="启用 HTTP 请求缓存（需要 requests-cache）")
    parser.add_argument("--cache-expire", type=int, default=24*3600, help="HTTP 缓存过期秒数，默认 86400")
    parser.add_argument("--use-playwright", action="store_true", help="失败兜底：用 Playwright 浏览器尝试点击 PDF 并下载（需要 playwright）")
    parser.add_argument("--user-data-dir", default=None, help="Playwright 持久化会话目录（复用登录状态）")
    parser.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"], help="Playwright 浏览器内核，默认 chromium")
    parser.add_argument("--playwright-timeout", type=int, default=30000, help="Playwright 操作超时毫秒，默认 30000")
    parser.add_argument("--playwright-headful", action="store_true", help="以可见窗口运行 Playwright（默认无头）")

    args = parser.parse_args(argv)

    input_path = Path(args.input)
    out_dir = Path(args.output_dir)
    log_path = Path(args.log_file)
    ensure_output_dir(out_dir)

    if not input_path.exists():
        eprint(f"输入文件不存在：{input_path}")
        return 2

    try:
        df = pd.read_excel(input_path)
    except Exception as e:
        eprint(f"读取 Excel 失败：{input_path} -> {e}")
        return 2

    try:
        index_col, doi_col, title_col = detect_columns(df, args.doi_column, args.title_column)
    except Exception as e:
        eprint(f"列识别失败：{e}")
        return 2

    eprint(f"识别列：index='{index_col}', doi='{doi_col}', title='{title_col}'")

    email = args.email or os.environ.get("UNPAYWALL_EMAIL")
    if email:
        eprint(f"使用 Unpaywall 邮箱：{email}")
    else:
        eprint("未配置 Unpaywall 邮箱（--email 或 UNPAYWALL_EMAIL），将跳过 OA 优先通道。")

    # 切片
    start = max(args.start or 0, 0)
    end = start + args.limit if args.limit is not None else None
    df_slice = df.iloc[start:end] if end is not None else df.iloc[start:]

    # 可选：安装全局缓存
    if args.enable_cache:
        try:
            import requests_cache  # type: ignore
            requests_cache.install_cache("dl_cache", expire_after=args.cache_expire)
            eprint(f"已启用请求缓存，过期 {args.cache_expire}s")
        except Exception as e:
            eprint(f"启用缓存失败（未安装 requests-cache?）：{e}")

    session = init_session()

    # 可选：导入浏览器 Cookie，帮助通过站点校验（如 ACS/MDPI/ScienceDirect）
    if args.use_browser_cookies:
        target_domains = [
            "pubs.acs.org",
            "www.mdpi.com",
            "sciencedirect.com",
            "www.sciencedirect.com",
            "tandfonline.com",
            "ieeexplore.ieee.org",
            "asmedigitalcollection.asme.org",
            "onlinelibrary.wiley.com",
            "link.springer.com",
            "dl.acm.org",
            "iopscience.iop.org",
            "www.nature.com",
            "academic.oup.com",
            "royalsocietypublishing.org",
        ]
        loaded = 0
        try:
            import browser_cookie3 as bc  # type: ignore
            loaders = []
            for name in ("chrome", "chromium", "edge", "firefox"):
                fn = getattr(bc, name, None)
                if callable(fn):
                    loaders.append(fn)
            for dom in target_domains:
                for fn in loaders:
                    try:
                        cj = fn(domain_name=dom)
                        if cj:
                            session.cookies.update(cj)  # type: ignore[arg-type]
                            loaded += 1
                            break
                    except Exception:
                        continue
            if loaded:
                eprint(f"已从浏览器导入 Cookie：{loaded} 个域名")
            else:
                eprint("未能从浏览器导入 Cookie（可能未登录或不支持的浏览器）")
        except Exception as e:
            eprint(f"导入浏览器 Cookie 失败（未安装 browser-cookie3?）：{e}")
    if args.insecure:
        # 仅在用户明确指定时关闭 SSL 校验
        try:
            session.verify = False  # type: ignore[attr-defined]
            eprint("警告：已启用 --insecure，将忽略 SSL 证书校验。")
        except Exception:
            pass
    records: List[Tuple[str, str, str, str, str]] = []

    total = len(df_slice)
    eprint(f"待处理：{total} 条；输出目录：{out_dir}")

    for i, row in enumerate(iter_rows(df_slice, index_col, doi_col, title_col), start=1):
        try:
            rec = process_row(row, out_dir, session=session, email=email, overwrite=args.overwrite)
        except Exception as e:
            rec = (row.idx, row.doi or "", row.title or "", "error", f"exception:{type(e).__name__}")

        records.append(rec)

        # 及时写日志，防止中断丢失
        try:
            append_log(log_path, [rec])
        except Exception as e:
            eprint(f"写日志失败：{e}")

        status = rec[3]
        notes = rec[4]
        eprint(f"[{i}/{total}] index={row.idx} -> {status} | {notes}")

        if args.interactive and status in {"not_found", "error"}:
            # 交互提示（避免阻塞复杂操作，仅供人工辅助定位）
            try:
                input("未成功，按回车继续下一条（Ctrl+C 终止）...")
            except KeyboardInterrupt:
                eprint("用户中断。")
                break

        if args.delay and i < total:
            time.sleep(args.delay)

    # 汇总
    summary = {
        "downloaded": 0,
        "exists": 0,
        "not_found": 0,
        "error": 0,
        "no_index": 0,
    }
    for _, _, _, st, _ in records:
        if st in summary:
            summary[st] += 1
    eprint("完成：" + ", ".join([f"{k}:{v}" for k, v in summary.items()]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
