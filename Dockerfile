FROM --platform=linux/amd64 python:3.11-slim-bookworm

# System dependencies
RUN apt-get update -qq -y && \
    apt-get install -y \
        libasound2 \
        libatk-bridge2.0-0 \
        libgtk-4-1 \
        libnss3 \
        xdg-utils \
        wget \
        unzip

# Install Chrome for Testing
RUN wget -q -O /tmp/chrome-linux64.zip https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/121.0.6167.0/linux64/chrome-linux64.zip && \
    unzip /tmp/chrome-linux64.zip -d /opt/ && \
    mv /opt/chrome-linux64 /opt/chrome && \
    ln -s /opt/chrome/chrome /usr/local/bin/chrome && \
    rm /tmp/chrome-linux64.zip

# Install ChromeDriver
RUN wget -q -O /tmp/chromedriver-linux64.zip https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/121.0.6167.0/linux64/chromedriver-linux64.zip && \
    unzip /tmp/chromedriver-linux64.zip -d /opt/ && \
    mv /opt/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf /opt/chromedriver-linux64 && \
    rm /tmp/chromedriver-linux64.zip

# Python setup
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE $PORT

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "api:app"]