# OHMS — Flauraly Order Hub Management System
# Container image for optional Docker deploy. Replit Reserved VM is the
# primary target; this Dockerfile is here for local reproduction and
# future portability.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Run as non-root — defense in depth.
RUN useradd --create-home --shell /bin/bash ohms
WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY main.py ./
COPY ohms/ ./ohms/

# Drop privileges before running the app.
USER ohms

EXPOSE 8080

# Bind to 0.0.0.0 for container; real host policy is controlled by TrustedHost.
CMD ["python", "main.py"]
