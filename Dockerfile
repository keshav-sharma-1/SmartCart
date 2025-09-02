# ---------- Stage 1: Node.js Build ----------
FROM node:20-slim AS node-builder

WORKDIR /app

# Copy and install Node.js dependencies
COPY package*.json ./
RUN npm ci --only=production && npm cache clean --force

# Copy app source code
COPY . .

# ---------- Final Stage: Runtime ----------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    DEBIAN_FRONTEND=noninteractive \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# Install system dependencies, Node.js, and Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    vim \
    ca-certificates \
    gnupg \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libxss1 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (from NodeSource)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest \
    && rm -rf /var/lib/apt/lists/*

# Copy Node build
COPY --from=node-builder /app /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080


CMD ["node", "server.js"]
