#!/usr/bin/env python3
"""Compatibility wrapper for the shared Skill Studio package builder."""
import argparse
import importlib.util
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
SHARED_BUILDER = REPOSITORY_ROOT / "skillstudio" / "build_platforms.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("playurl_skillstudio_builder", SHARED_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared Skill Studio builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(output):
    return load_builder().build("kugou", output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "dist" / "playurl-kugou-skill-studio.zip",
    )
    args = parser.parse_args()
    print(build(args.output))


if __name__ == "__main__":
    main()
