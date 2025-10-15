#!/usr/bin/env python3
"""
第二阶段清洗小样本预览脚本：
 - 从 mineru_raw/<index>/full.md 读取
 - 应用二阶段清洗（标题/作者/机构分离、数学归一、参考文献剔除、表格图片→HTML表格、去孤儿图注）
 - 输出到 md_clean/preview/<index>.md 与 .txt，不覆盖原 md_clean/<index>.md

用法：
  python DMH/second_stage_preview.py 102 10019 10046
若不传参数，则提示用法。
"""

import sys
from os import path
from my_tips import extract_md, path_check


def run_one(idx: str) -> None:
    raw_dir = path.join('mineru_raw', idx)
    md_path = path.join(raw_dir, 'full.md')
    if not path.exists(md_path):
        print(f"缺少原始 MD：{md_path}")
        return
    out_dir = path.join('md_clean', 'preview')
    path_check(out_dir)
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    txt_out = path.join(out_dir, f'{idx}.txt')
    info = extract_md(idx, lines, txt_out, raw_dir)
    print(f"预览完成：{idx} -> {info.get('md_path')} 及 {info.get('txt_path')}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    for idx in argv[1:]:
        run_one(idx)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

