#!/usr/bin/env python3
"""
命令行批处理 MinerU：
 - 输入 PDF 目录（默认 7-杨皓然-高研院/paper）
 - 上传到 MinerU，轮询解析，下载解压到 md 原始目录（默认 mineru_raw/）
 - 调用现有 extract_md 清洗，分别导出 .md 与 .txt 到 md_clean/（默认）

环境变量：
 - MINERU_API_KEY  必填（或用 --api-key 参数，但建议走环境变量）

示例：
  MINERU_API_KEY=xxxx \
  python DMH/mineru_cli.py --start 0 --limit 10 \
      --pdf-dir '7-杨皓然-高研院/paper' --md-dir mineru_raw --out-dir md_clean --logs-dir logs
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from os import path
from typing import List, Dict, Any
from io import BytesIO
from zipfile import ZipFile

import requests
import subprocess

sys.path.append(path.dirname(__file__))
from my_tips import extract_md, path_check  # type: ignore


API_BASE = "https://mineru.net/api/v4"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def find_pdfs(pdf_dir: str) -> List[str]:
    if not path.exists(pdf_dir):
        raise FileNotFoundError(f"PDF 目录不存在：{pdf_dir}")
    files = []
    for fn in os.listdir(pdf_dir):
        fp = path.join(pdf_dir, fn)
        if path.isfile(fp) and fn.lower().endswith(".pdf"):
            files.append(fp)
    files.sort(key=lambda p: path.basename(p))
    return files


def chunk(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def download_and_extract(zurl: str, out_dir: str, max_retries: int = 6) -> bool:
    """下载 MinerU 提供的 ZIP 并解压到 out_dir。
    - 带指数退避重试：1,2,4,8,16,32 秒
    - 先尝试 verify=True，如遇 SSL 异常或 EOF，再以 verify=False 重试
    - 使用短连接避免复用引发的异常
    """
    path_check(out_dir)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
        "Connection": "close",
    }
    delay = 1
    last_err = None
    for i in range(max_retries):
        for verify in (True, False):
            try:
                r = requests.get(zurl, headers=headers, timeout=180, stream=True, verify=verify)
                r.raise_for_status()
                data = BytesIO()
                for chunk in r.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        data.write(chunk)
                data.seek(0)
                with ZipFile(data) as zf:
                    zf.extractall(out_dir)
                return True
            except Exception as e:
                last_err = e
        time.sleep(delay)
        delay = min(delay * 2, 32)
    if last_err:
        eprint(f"Python 请求失败：{type(last_err).__name__}: {last_err}")

    # Fallback 2: 尝试 curl 下载（不同 TLS 栈）
    try:
        tmp_zip = path.join(out_dir, "__mineru_tmp__.zip")
        # 先尝试严格校验证书
        cmd = [
            "curl", "-L", "--retry", "5", "--connect-timeout", "20", "-m", "180",
            "-H", "Accept: application/zip,application/octet-stream,*/*;q=0.8",
            "-H", "Connection: close",
            "-o", tmp_zip, zurl,
        ]
        rc = subprocess.run(cmd, capture_output=True)
        if rc.returncode != 0 or (not path.exists(tmp_zip)) or path.getsize(tmp_zip) < 128:
            # 不校验证书再试
            cmd2 = cmd[:]
            cmd2.insert(1, "-k")
            rc2 = subprocess.run(cmd2, capture_output=True)
            if rc2.returncode != 0 or (not path.exists(tmp_zip)) or path.getsize(tmp_zip) < 128:
                raise RuntimeError(f"curl 下载失败：code={rc2.returncode}, err={rc2.stderr.decode('utf-8','ignore')[:200]}")
        # 解压
        with open(tmp_zip, 'rb') as f:
            data = BytesIO(f.read())
        with ZipFile(data) as zf:
            zf.extractall(out_dir)
        try:
            os.remove(tmp_zip)
        except Exception:
            pass
        return True
    except Exception as e:
        eprint(f"curl 兜底失败：{e}")
        return False


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MinerU 批处理（命令行）")
    p.add_argument("--api-key", default=os.environ.get("MINERU_API_KEY"), help="MinerU API Key（或设置环境变量 MINERU_API_KEY）")
    p.add_argument("--pdf-dir", default="7-杨皓然-高研院/paper", help="输入 PDF 目录")
    p.add_argument("--md-dir", default="mineru_raw", help="MinerU 解压的原始目录")
    p.add_argument("--out-dir", default="md_clean", help="清洗输出目录（.md 与 .txt）")
    p.add_argument("--logs-dir", default="logs", help="处理日志目录")
    p.add_argument("--start", type=int, default=0, help="起始下标（按文件名排序）")
    p.add_argument("--limit", type=int, default=10, help="最多处理数")
    p.add_argument("--timeout", type=int, default=3600, help="轮询超时秒，默认 3600")
    args = p.parse_args(argv)

    if not args.api_key:
        eprint("未提供 MinerU API Key。请设置环境变量 MINERU_API_KEY 或使用 --api-key。")
        return 2

    # 准备目录
    for d in (args.md_dir, args.out_dir, args.logs_dir):
        path_check(d)

    # 收集 PDF
    all_pdfs = find_pdfs(args.pdf_dir)
    if args.start < 0:
        start = 0
    else:
        start = args.start
    end = start + args.limit if args.limit and args.limit > 0 else None
    pdfs = all_pdfs[start:end] if end is not None else all_pdfs[start:]
    if not pdfs:
        eprint("未找到待处理的 PDF。")
        return 0
    eprint(f"待处理：{len(pdfs)} 篇（起点 {start}，目录 {args.pdf_dir}）")

    # 分批（每批最多 190）
    for batch_idx, batch in enumerate(chunk(pdfs, 190), start=1):
        names = [path.basename(p) for p in batch]
        eprint(f"[批 {batch_idx}] 上传 {len(batch)} 篇：{names[:3]}{' ...' if len(names)>3 else ''}")

        # 申请上传 URL
        data = {
            "enable_formula": True,
            "enable_table": True,
            "language": "ch",
            "files": [{"name": n, "is_ocr": False, "data_id": "abcd"} for n in names],
        }
        try:
            r = requests.post(f"{API_BASE}/file-urls/batch", headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {args.api_key}",
            }, json=data, timeout=60)
        except Exception as e:
            eprint(f"请求上传 URL 失败：{e}")
            return 3
        if r.status_code != 200:
            eprint(f"上传 URL 请求失败：HTTP {r.status_code} -> {r.text[:200]}")
            return 3
        resp = r.json()
        if resp.get("code") != 0:
            eprint(f"MinerU 返回错误：{resp}")
            return 3
        batch_id = resp.get("data", {}).get("batch_id")
        file_urls = resp.get("data", {}).get("file_urls") or []
        if not batch_id or len(file_urls) != len(batch):
            eprint("返回的 file_urls 数量与本地不一致，请稍后复核！")

        # 上传文件
        for i, up_url in enumerate(file_urls):
            fp = batch[i]
            try:
                with open(fp, "rb") as f:
                    putr = requests.put(up_url, data=f, timeout=60)
                if putr.status_code == 200:
                    eprint(f"上传成功：{path.basename(fp)}")
                else:
                    eprint(f"上传失败：{path.basename(fp)} -> HTTP {putr.status_code}")
            except Exception as e:
                eprint(f"上传出错：{path.basename(fp)} -> {e}")

        # 轮询
        t0 = time.time()
        while True:
            if time.time() - t0 > args.timeout:
                eprint("超时：处理时间超过限制")
                return 4
            try:
                gr = requests.get(f"{API_BASE}/extract-results/batch/{batch_id}", headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {args.api_key}",
                }, timeout=30)
            except Exception as e:
                eprint(f"轮询失败：{e}")
                time.sleep(10)
                continue
            try:
                jq = gr.json()
            except Exception:
                jq = {}
            results = ((jq.get("data") or {}).get("extract_result") or [])
            states = [x.get('state') for x in results]
            if results and all(s in {"done", "failed"} for s in states):
                eprint("本批处理完成，开始下载结果。")
                # 下载与解压
                for info in results:
                    fname = info.get('file_name') or ""
                    err = info.get('err_msg')
                    if err:
                        eprint(f"处理失败：{fname} -> {err}")
                        continue
                    zurl = info.get('full_zip_url')
                    if not zurl:
                        eprint(f"无下载链接：{fname}")
                        continue
                    out_dir = path.join(args.md_dir, path.splitext(fname)[0])
                    path_check(out_dir)
                    ok = download_and_extract(zurl, out_dir)
                    if ok:
                        eprint(f"已解压：{fname} -> {out_dir}")
                    else:
                        short = zurl.split("/pdf/")[-1] if "/pdf/" in zurl else zurl[-60:]
                        eprint(f"下载/解压失败：{fname} -> 链接片段 {short}")
                break
            else:
                eprint("处理中……10s 后继续检查")
                time.sleep(10)

    # 扫描原始 md 并清洗导出
    cleaned = 0
    for root, dirs, files in os.walk(args.md_dir):
        for d in dirs:
            md_fp = path.join(root, d, 'full.md')
            if path.exists(md_fp):
                with open(md_fp, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                base = path.join(args.out_dir, f"{d}.txt")
                raw_dir = path.join(args.md_dir, d)
                info = extract_md(d, lines, base, raw_dir)
                cleaned += 1
                eprint(f"清洗完成：{d} -> MD/TXT 输出于 {args.out_dir}")

    eprint(f"完成：解压并清洗 {cleaned} 篇")
    return 0


if __name__ == "__main__":
    sys.exit(main())
