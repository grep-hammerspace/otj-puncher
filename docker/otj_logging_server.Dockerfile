FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    firefox-esr \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

# Install geckodriver
RUN curl -fsSL "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux64.tar.gz" \
    | tar -xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/geckodriver

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY otj_server.py puncher.py llm_prompt.txt ./

COPY docker/start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8945

CMD ["/start.sh"]
