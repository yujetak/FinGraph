# Base image with Python 3.10
FROM python:3.10-slim

# Install system dependencies including Chrome (Chromium) and ChromeDriver for Selenium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Create a non-root user (UID 1000) for Hugging Face Spaces compatibility
RUN useradd -m -u 1000 user
RUN chown user:user /app
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PYTHONPATH=/app

# Copy requirements and install python dependencies
COPY --chown=user web_app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy all essential packages into container working directory
COPY --chown=user pipeline /app/pipeline
COPY --chown=user web_app /app/web_app

# Expose standard Hugging Face Space port
EXPOSE 7860

# Run Streamlit on port 7860 and address 0.0.0.0 (app.py is inside web_app/)
CMD ["streamlit", "run", "web_app/app.py", "--server.port", "7860", "--server.address", "0.0.0.0"]
