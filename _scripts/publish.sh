#!/usr/bin/env bash
# 烹饪储备库 · 一键发布网页
# 用法：bash _scripts/publish.sh "本次改了什么"
#   不带参数时，用默认提交信息「更新菜谱 YYYY-MM-DD」
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MSG="${1:-更新菜谱 $(date +%Y-%m-%d)}"

echo "[1/4] 重新生成网页 index.html ..."
PYTHONIOENCODING=utf-8 python _scripts/build_web.py

echo "[2/4] 本次改动："
git status --short

if [ -z "$(git status --porcelain)" ]; then
  echo "没有需要提交的改动，结束。"
  exit 0
fi

echo "[3/4] 提交并推送 ..."
git add -A
git commit -m "$MSG"
git push origin main

echo "[4/4] 完成！稍等约 1 分钟，网页自动更新："
echo "      https://brilliant321.github.io/caipu/"
