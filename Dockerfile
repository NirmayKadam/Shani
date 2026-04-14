# ----- Builder Stage -----
FROM python:3.11-slim as builder

WORKDIR /app

# Install Python dependencies strictly into the local user space
COPY requirements.txt .
RUN pip install --user --no-cache-dir --upgrade pip && \
    pip install --user --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --user --no-cache-dir -r requirements.txt

# ----- Final Runtime Stage -----
FROM python:3.11-slim

WORKDIR /app

# Pull only the compiled libraries, leaving all pip caches/metadata behind
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Default command runs all core in-container processes
CMD ["./scripts/entrypoint_single_container.sh"]
