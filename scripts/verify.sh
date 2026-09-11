#!/usr/bin/env bash
# SKALA Multi-Worker Agent 플랫폼 - 원클릭 자동 채점 래퍼 스크립트

set -e

# 프로젝트 루트 탐색
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# 파이썬 실행 바이너리 결정 (.venv 우선, venv 차선, 시스템 python3 폴백)
if [ -f "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PYTHON_EXEC="${PROJECT_ROOT}/.venv/bin/python"
elif [ -f "${PROJECT_ROOT}/venv/bin/python" ]; then
    PYTHON_EXEC="${PROJECT_ROOT}/venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_EXEC="python3"
else
    PYTHON_EXEC="python"
fi

# 자동 채점 검증 스크립트 실행
exec "${PYTHON_EXEC}" scripts/verify.py "$@"
