FROM --platform=linux/amd64 python:3.11-slim-bookworm

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget curl unzip jq xvfb \
    libvulkan1 libgbm1 libasound2 libatk-bridge2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Add Google's signing key and Chrome's repository
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list

# Install Google Chrome
RUN apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Get Chrome's major version
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+') && \
    CHROME_MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d '.' -f 1)

# Download and install the matching ChromeDriver version
RUN CHROMEDRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_MAJOR_VERSION) && \
    wget -q --continue -P /usr/local/bin/ "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip" && \
    unzip /usr/local/bin/chromedriver_linux64.zip -d /usr/local/bin/ && \
    rm /usr/local/bin/chromedriver_linux64.zip && \
    chmod +x /usr/local/bin/chromedriver

# Python setup
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE $PORT

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "api:app"]