# syntax=docker/dockerfile:1

# 開発用イメージ。docker compose watch での運用を前提とする
# - ソースはイメージに含め、変更は watch の sync でコンテナへ反映する（バインドマウントは使わない）
# - 依存関係（pyproject.toml / uv.lock）が変わったら watch の rebuild でイメージを作り直す
# - コンテナに入って作業しないため、実行ステージには uv やシェル用ツールを入れない

ARG PYTHON_VERSION=3.14.8
ARG UV_VERSION=0.12.21

# =============================================================================
# uv: uv バイナリの取得元
# =============================================================================
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# =============================================================================
# base: builder と dev の共通ベース（venv の Python と実行時の Python を一致させる）
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-trixie AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# =============================================================================
# builder: 依存関係を仮想環境にインストールする
# =============================================================================
FROM base AS builder

# --link の層では /bin（/usr/bin へのシンボリックリンク）を上書きしてしまうため、/usr/local/bin に置く
COPY --link --from=uv /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 依存定義ファイルはバインドマウントで渡し、ソース変更で依存の層が無効化されないようにする
# 開発用なので dev グループ（django-debug-toolbar など）も含める（uv sync の既定動作）
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --frozen --no-install-project

# =============================================================================
# dev: 開発用の実行イメージ
# =============================================================================
FROM base AS dev

LABEL org.opencontainers.image.title="sandbox-dev" \
      org.opencontainers.image.description="Django 開発用イメージ（docker compose watch 前提）"

# 実行ユーザー。ホストとファイルを共有しない（watch の sync は一方向）ので UID/GID はホストに合わせなくてよい
# /app は watch の sync で新規ファイルを作れるよう、実行ユーザーの所有にする
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-log-init --no-create-home --shell /usr/sbin/nologin app \
    && install -d -o app -g app /app

COPY --link --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# ソースは最後にコピーし、ソース変更時に再利用できない層を最小にする
COPY --chown=app:app . .

USER app

EXPOSE 8000

# runserver は PID 1 で SIGTERM を処理しないため、SIGINT（Ctrl+C 相当）で停止させる
STOPSIGNAL SIGINT

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
