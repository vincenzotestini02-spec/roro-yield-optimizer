FROM node:22-slim AS web
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
RUN useradd --create-home --uid 1000 app
WORKDIR /srv
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY roro_yield/ roro_yield/
COPY server/ server/
COPY benchmarks/ benchmarks/
COPY --from=web /build/dist web/dist
USER app
EXPOSE 7860
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "7860"]
