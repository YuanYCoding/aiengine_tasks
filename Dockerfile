FROM python:3.11-slim

WORKDIR /app

ENV DISPLAY=:99
ENV HEADLESS=false
ENV PORT=8000
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/

# Configure apt to use Aliyun mirrors (fast in China) and reduce memory pressure
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true

# Install Chromium system dependencies + Xvfb + x11vnc + Chinese fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 curl \
    xvfb x11vnc x11-utils \
    fontconfig fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# Batch 2: heavier deps (may pull llvm)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatk-bridge2.0-0 libpango-1.0-0 libcairo2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps with Tsinghua mirror
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# Install Playwright Chromium browser only (not all browsers)
RUN python -m playwright install chromium

# Only install the system libs that playwright chromium needs
RUN python -m playwright install-deps chromium 2>/dev/null || true

COPY . .

RUN mkdir -p /app/browser_data /app/static

# noVNC ESM source files already in static/novnc/core/ (pre-downloaded locally)

# Copy startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
