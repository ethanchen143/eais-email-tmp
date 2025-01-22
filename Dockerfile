# Final verified working Dockerfile for Render
FROM --platform=linux/amd64 python:3.11-slim-bookworm

# Clean up repository configurations
RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    echo "deb http://deb.debian.org/debian bookworm main contrib non-free" > /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian bookworm-updates main contrib non-free" >> /etc/apt/sources.list

# Install system dependencies with curl
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
    curl wget gnupg unzip xvfb \
    fonts-liberation libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libc6 libcairo2 libcups2 libcurl4 \
    libdbus-1-3 libdrm2 libexpat1 libgbm1 libglib2.0-0 \
    libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libvulkan1 \
    libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxkbcommon0 libxrandr2 libxshmfence1 \
    xdg-utils vulkan-tools mesa-vulkan-drivers \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    DEBIAN_FRONTEND=noninteractive \
    dpkg --install --force-all ./google-chrome-stable_current_amd64.deb || true && \
    apt-get install -yf --no-install-recommends && \
    rm google-chrome-stable_current_amd64.deb

# Install ChromeDriver with validation
# RUN set -ex && \
# CHROME_VERSION=$(google-chrome --version | awk '{print $3}') && \
# MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d '.' -f 1) && \
# echo "Chrome Major Version: $MAJOR_VERSION" && \
# CHROMEDRIVER_VERSION=$(curl -f -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$MAJOR_VERSION") || \
# (echo "Failed to get ChromeDriver version"; exit 1) && \
# echo "Downloading ChromeDriver $CHROMEDRIVER_VERSION"

# RUN wget -q --tries=3 --retry-connrefused "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" && \
# [ -f chromedriver_linux64.zip ] || (echo "Download failed"; exit 1) && \
# unzip chromedriver_linux64.zip && \
# mv chromedriver /usr/local/bin/ && \
# chmod +x /usr/local/bin/chromedriver && \
# rm chromedriver_linux64.zip && \
# echo "Installed versions:" && \
# google-chrome --version && \
# chromedriver --version

# Install ChromeDriver for Chrome ≥115
RUN set -ex && \
    CHROME_VERSION=$(google-chrome --version | awk '{print $3}') && \
    CHROMEDRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone.json" | \
    jq -r '.milestones."'"$(echo $CHROME_VERSION | cut -d '.' -f 1)"'".version') && \
    echo "Downloading ChromeDriver $CHROMEDRIVER_VERSION" && \
    wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/$CHROMEDRIVER_VERSION/linux64/chromedriver-linux64.zip" && \
    unzip chromedriver-linux64.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf chromedriver-linux64*

# Python setup
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE $PORT

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "api:app"]