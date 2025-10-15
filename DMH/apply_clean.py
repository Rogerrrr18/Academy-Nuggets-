#!/usr/bin/env python3
"""
仅对已存在的 MinerU 原始结果（mineru_raw/<index>/full.md）执行清洗覆盖：
 - 读取 full.md
 - 调用 my_tips.extract_md（包含二阶段清洗）
 - 输出到 md_clean/<index>.md 与 md_clean/<index>.txt

用法示例：
  python DMH/apply_clean.py --start 0 --limit 10 \
      --pdf-dir '7-杨皓然-高研院/paper' --raw-dir mineru_raw --out-dir md_clean
或指定具体索引：
  python DMH/apply_clean.py --indices 10019 10046 10073
"""

from __future__ import annotations

import argparse
import os
from os import path
from typing import List

from my_tips import extract_md, path_check


def find_indices_from_pdf_dir(pdf_dir: str) -> List[str]:
    files = []
    for fn in os.listdir(pdf_dir):
        if fn.lower().endswith('.pdf'):
            files.append(path.splitext(fn)[0])
    files.sort()
    return files


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="对现有 raw 结果执行清洗覆盖")
    p.add_argument("--pdf-dir", default="7-杨皓然-高研院/paper", help="用于推导 index 的 PDF 目录")
    p.add_argument("--raw-dir", default="mineru_raw", help="MinerU 原始结果目录（含 full.md）")
    p.add_argument("--out-dir", default="md_clean", help="清洗输出目录")
    p.add_argument("--indices", nargs="*", default=None, help="指定一批 index 覆盖清洗，例如 10019 10046")
    p.add_argument("--start", type=int, default=0, help="从第几个 index 开始（基于排序）")
    p.add_argument("--limit", type=int, default=10, help="最多处理多少个 index")
    args = p.parse_args(argv)

    path_check(args.out_dir)

    if args.indices:
        indices = list(dict.fromkeys(args.indices))  # 去重保持顺序
    else:
        all_idx = find_indices_from_pdf_dir(args.pdf_dir)
        start = max(args.start or 0, 0)
        end = start + args.limit if args.limit and args.limit > 0 else None
        indices = all_idx[start:end] if end is not None else all_idx[start:]

    if not indices:
        print("未找到待处理 index。")
        return 0

    ok, fail = 0, 0
    for idx in indices:
        raw_dir = path.join(args.raw_dir, idx)
        md_path = path.join(raw_dir, 'full.md')
        if not path.exists(md_path):
            print(f"缺少 full.md：{md_path}")
            fail += 1
            continue
        try:
            with open(md_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            base = path.join(args.out_dir, f"{idx}.txt")
            extract_md(idx, lines, base, raw_dir)
            ok += 1
            print(f"覆盖清洗完成：{idx} -> {args.out_dir}")
        except Exception as e:
            print(f"清洗失败：{idx} -> {e}")
            fail += 1

    print(f"完成：成功 {ok}，失败 {fail}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

