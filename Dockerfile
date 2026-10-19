FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
# TZ is a default; set it in /srv/goldryn/.env to change it. It decides log
# timestamps and when the daily log file rolls over. The DB stores UTC regardless.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/New_York \
    GOLDRYN_HOST=0.0.0.0

# Run as the app's dedicated host user (UID/GID come from APP_UID/APP_GID in .env, see DEPLOY.md)
ARG UID
ARG GID
RUN groupadd --gid ${GID} goldryn && \
    useradd --uid ${UID} --gid ${GID} --no-create-home --shell /usr/sbin/nologin goldryn

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN mkdir -p data logs && chown goldryn:goldryn data logs

USER goldryn
EXPOSE 8000
CMD ["python", "backend/GoldrynBackend.py"]
