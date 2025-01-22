FROM --platform=linux/amd64 python:3.11-slim-bookworm

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget curl unzip jq xvfb \
    libvulkan1 libgbm1 libasound2 libatk-bridge2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    dpkg -i ./google-chrome-stable_current_amd64.deb || apt-get install -yf && \
    rm google-chrome-stable_current_amd64.deb

# Install ChromeDriver for Chrome 132+
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}') && \
    BUILD_NUMBER=$(echo $CHROME_VERSION | cut -d'.' -f1) && \
    CD_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone.json" | \
    jq -r ".milestones.\"$BUILD_NUMBER\".version") && \
    wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${CD_VERSION}/linux64/chromedriver-linux64.zip" && \
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