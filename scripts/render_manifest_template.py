#!/usr/bin/env python3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv: list[str]) -> int:
    try:
        from meme_studio.renderer import render_manifest
    except ImportError:
        from meme_studio_core import render_manifest

    if len(argv) < 4:
        print("用法: render_manifest_template.py <头像图片> <输出路径> <manifest路径>", file=sys.stderr)
        return 1

    avatar_path = Path(argv[1])
    output_path = Path(argv[2])
    manifest_path = Path(argv[3])
    render_manifest(avatar_path, manifest_path, output_path)
    print(f"生成成功: {output_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:
        print(f"生成失败: {exc}", file=sys.stderr)
        sys.exit(1)
