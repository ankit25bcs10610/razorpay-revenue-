FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY . .
RUN uv sync --frozen --no-dev
EXPOSE 8000
ENV GATEWAY_HOST=0.0.0.0
CMD ["uv", "run", "python", "-m", "revrecover.gateway"]
