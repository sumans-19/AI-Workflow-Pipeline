FROM python:3.11-slim

WORKDIR /workspace

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir pytest pytest-cov

CMD ["sh", "-lc", "pytest /workspace -v --tb=short --cov=/workspace --cov-report=term-missing"]
