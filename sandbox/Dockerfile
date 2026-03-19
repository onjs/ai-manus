FROM ubuntu:22.04

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Set hostname to sandbox
ENV HOSTNAME=sandbox

ARG APT_MIRROR=""
ARG APT_FLAGS='-o Acquire::ForceIPv4=true -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::http::Pipeline-Depth=0'
ARG INSTALL_CJK_FONTS="true"

# Improve apt reliability in unstable networks
RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|http://ports.ubuntu.com/ubuntu-ports/|$APT_MIRROR|g" /etc/apt/sources.list; \
    fi && \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::ForceIPv4 "true";\nAcquire::http::Pipeline-Depth "0";\n' > /etc/apt/apt.conf.d/99-retry

# Update and install basic tools
RUN apt-get ${APT_FLAGS} update && apt-get ${APT_FLAGS} install -y \
    sudo \
    bc \
    curl \
    wget \
    gnupg \
    software-properties-common \
    xvfb \
    x11vnc \
    xterm \
    socat \
    supervisor \
    websockify \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create user ubuntu and grant sudo privileges
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

# Install Python 3.10.12
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get ${APT_FLAGS} update && \
    apt-get ${APT_FLAGS} install -y python3.10 python3.10-venv python3.10-dev python3-pip && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip3 install uv

# Install Node.js 20.18.0
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get ${APT_FLAGS} update && \
    apt-get ${APT_FLAGS} install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN add-apt-repository ppa:xtradeb/apps -y && \
    apt-get ${APT_FLAGS} update && \
    apt-get ${APT_FLAGS} install -y chromium --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Chinese language support first, then optionally install large CJK fonts with retry loop
RUN set -eux; \
    apt-get ${APT_FLAGS} update; \
    apt-get ${APT_FLAGS} install -y \
      language-pack-zh-hans \
      locales; \
    if [ "$INSTALL_CJK_FONTS" = "true" ]; then \
      ok=0; \
      for i in 1 2 3 4 5; do \
        if apt-get ${APT_FLAGS} install -y --fix-missing \
          fonts-noto-cjk \
          fonts-noto-color-emoji; then \
          ok=1; \
          break; \
        fi; \
        echo "Retrying CJK font install (${i}/5)"; \
        apt-get ${APT_FLAGS} update || true; \
        sleep 15; \
      done; \
      if [ "$ok" -ne 1 ]; then \
        echo "Failed to install CJK fonts after retries"; \
        exit 1; \
      fi; \
    else \
      echo "Skipping CJK font install (INSTALL_CJK_FONTS=${INSTALL_CJK_FONTS})"; \
    fi; \
    locale-gen zh_CN.UTF-8; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Set default locale
#ENV LANG=zh_CN.UTF-8 \
#    LANGUAGE=zh_CN:zh \
#    LC_ALL=zh_CN.UTF-8

# Set working directory
WORKDIR /app

# Copy project files (copy dependency files first to leverage cache)
COPY pyproject.toml ./

# Install Python dependencies
RUN uv sync --no-dev

# Copy remaining project files
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
