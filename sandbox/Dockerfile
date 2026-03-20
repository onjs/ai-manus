ARG SANDBOX_BASE_IMAGE=ai-manus-sandbox-base:latest
FROM ${SANDBOX_BASE_IMAGE}

# Set working directory
WORKDIR /app

# Copy dependency files first for better layer cache hit
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --no-dev

# Copy source code
COPY . .

# Ensure application files are writable by app user
RUN chown -R ubuntu:ubuntu /app

# Configure supervisor
COPY supervisord.conf /etc/supervisor/conf.d/app.conf

# Expose ports
EXPOSE 8080 9222 5900 5901

ENV UVI_ARGS=""
ENV CHROME_ARGS=""

# Use supervisor to start all services
CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]
