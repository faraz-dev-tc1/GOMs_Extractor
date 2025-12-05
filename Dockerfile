# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for OCR and PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OCRmyPDF dependencies
    ocrmypdf \
    tesseract-ocr \
    tesseract-ocr-eng \
    # PDF processing tools
    ghostscript \
    # Image processing
    libimage-exiftool-perl \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY goms_extractor/ ./goms_extractor/
COPY src/ ./src/
COPY .env.example .env.example

# Create necessary directories
RUN mkdir -p /tmp/documents /app/outputs/split_goms /app/outputs/markdown_goms

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)" || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8080"]
