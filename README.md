# GOMS Extraction Project

A comprehensive system for extracting, splitting, and converting Government Order (GO) PDF documents into structured markdown format using Google Cloud services.

## Project Overview

This project processes Government Orders from Andhra Pradesh and other states by:

1. **Splitting multi-GO PDFs** into individual Government Order PDF files
2. **Converting PDFs to Markdown** with concurrent processing for efficiency
3. **Uploading results to Google Cloud Storage** for centralized document management
4. **Providing REST API endpoints** for easy integration and batch processing

The system is built with a modular architecture using FastAPI for the API gateway and Google Cloud Storage for document persistence.

## Quick Start

Get started in 3 simple steps using Docker:

```bash
# 1. Clone and navigate to the project
git clone <repository-url>
cd goms

# 2. Configure environment (optional - works with local storage by default)
cp .env.example .env
# Edit .env if you want to use Google Cloud Storage

# 3. Run with Docker Compose
docker compose up --build
```

The API will be available at `http://localhost:8080/docs`

**Test the API:**
```bash
# Upload and process a PDF
curl -X POST "http://localhost:8080/process-direct" \
  -F "file=@/path/to/your/document.pdf"
```

For detailed setup and configuration, see the [Installation](#installation) section below.

## Architecture

```
Input PDF (Multiple GOs)
         ↓
    [Splitter Module]
         ↓
Individual GO PDFs
         ↓
  [MD Converter Module] (concurrent)
         ↓
Individual GO Markdown Files
         ↓
  [GCS Upload Module]
         ↓
Google Cloud Storage (Organized by timestamp)
```

## Key Features

- **Concurrent PDF Processing**: Process multiple PDFs in parallel using configurable worker threads
- **Automatic GCS Upload**: Automatically upload split PDFs and markdown files to Google Cloud Storage
- **REST API**: Simplified API endpoints for both file uploads and direct path processing
- **Job Tracking**: Monitor processing status with job IDs
- **Error Handling**: Comprehensive error logging and graceful failure handling
- **Background Tasks**: Async processing with FastAPI BackgroundTasks
- **CORS Support**: Cross-origin request support for web applications

## Project Structure

```
goms/
├── goms_extractor/          # Core extraction modules
│   ├── splitter.py         # PDF splitting logic
│   ├── md_converter.py      # PDF to Markdown conversion
│   ├── models.py            # Data models
│   ├── token_tracker.py     # Token usage tracking
│   ├── tools.py             # Utility tools
│   ├── agent.py             # Agent orchestration
│   └── README.md            # Module documentation
├── src/
│   ├── api.py               # FastAPI application and endpoints
│   └── gcs_storage.py       # Google Cloud Storage utilities
├── data/                    # Sample markdown files
├── outputs/                 # Processing output directory
├── .env                     # Environment configuration (not in repo)
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Prerequisites

### For Docker Deployment (Recommended)
- Docker Engine 20.10+
- Docker Compose V2
- Google Cloud Project with:
  - Google Cloud Storage bucket (optional, for cloud storage)
  - Service account with GCS permissions (if using GCS)

### For Local Development
- Python 3.12+
- Google Cloud Project with:
  - Google Cloud Storage bucket
  - Service account with GCS permissions
  - Application Default Credentials configured
- System dependencies:
  - ocrmypdf
  - tesseract-ocr
  - ghostscript

## Installation

### Option 1: Docker Deployment (Recommended)

#### 1. Clone the Project

```bash
git clone <repository-url>
cd goms
```

#### 2. Configure Environment Variables

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_REGION=us-central1

# GCS Configuration (optional - will use local storage if not set)
GCS_BUCKET=your-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json

# API Configuration
API_HOST=0.0.0.0
API_PORT=8080
LOG_LEVEL=INFO
MAX_WORKERS=4

# ADK API Configuration (if using agent-based processing)
ADK_API_URL=http://localhost:8000
```

#### 3. Set Up Google Cloud Credentials (Optional)

If using GCS, uncomment the credentials volume mount in `docker-compose.yml`:

```yaml
volumes:
  # Uncomment and set the path to your service account JSON file
  - /path/to/your/service-account.json:/app/credentials/service-account.json:ro
```

#### 4. Build and Run with Docker Compose

```bash
# Build and start the service
docker compose up --build

# Or run in detached mode
docker compose up -d --build
```

The API will be available at `http://localhost:8080`

#### 5. View Logs

```bash
# View logs
docker compose logs -f goms-api

# View specific number of log lines
docker compose logs --tail=100 goms-api
```

#### 6. Stop the Service

```bash
# Stop and remove containers
docker compose down

# Stop, remove containers, and remove volumes
docker compose down -v
```

### Option 2: Local Development Setup

#### 1. Clone the Project

```bash
git clone <repository-url>
cd goms
```

#### 2. Install System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y ocrmypdf tesseract-ocr tesseract-ocr-eng ghostscript
```

**macOS:**
```bash
brew install ocrmypdf tesseract ghostscript
```

#### 3. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### 5. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit the `.env` file with your configuration (see `.env.example` for all available options).

#### 6. Set Up Google Cloud Authentication

```bash
# Authenticate with Google Cloud
gcloud auth application-default login

# Or use a service account key
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

## Running the Application

### With Docker (Recommended)

```bash
docker compose up
```

The API will be available at `http://localhost:8080`

### Local Development

```bash
# From the project root
python -m uvicorn src.api:app --host 0.0.0.0 --port 8080 --reload
```

The API will be available at `http://localhost:8080`

### Access API Documentation

- **Swagger UI**: `http://localhost:8080/docs`
- **ReDoc**: `http://localhost:8080/redoc`
- **Health Check**: `http://localhost:8080/health`

## API Endpoints

### 1. Process PDF Upload (Direct)

**Endpoint**: `POST /process-direct`

Upload a PDF file and process it immediately with concurrent conversion.

**Request**:
```bash
curl -X POST "http://localhost:8080/process-direct" \
  -F "file=@/path/to/document.pdf" \
  -F "max_workers=4"
```

**Response**:
```json
{
  "job_id": "uuid-string",
  "user_id": "direct",
  "session_id": "direct",
  "status": "pending",
  "message": "Job created, direct processing will start shortly",
  "created_at": "2025-12-05T10:30:00.000000"
}
```

### 2. Process PDF from Path (Direct)

**Endpoint**: `POST /process-path-direct`

Process a PDF from a file system path.

**Request**:
```bash
curl -X POST "http://localhost:8080/process-path-direct" \
  -H "Content-Type: application/json" \
  -d "{
    \"pdf_path\": \"/path/to/document.pdf\",
    \"output_dir\": \"/path/to/output\",
    \"max_workers\": 4
  }"
```

### 3. Get Job Status

**Endpoint**: `GET /job-status/{job_id}`

Check the status and results of a processing job.

**Request**:
```bash
curl "http://localhost:8080/job-status/uuid-string"
```

**Response**:
```json
{
  "job_id": "uuid-string",
  "user_id": "direct",
  "session_id": "direct",
  "status": "completed",
  "message": "Processing completed: 5/5 GOs converted",
  "result": {
    "split_result": { ... },
    "markdown_result": { ... },
    "gcs_upload": {
      "status": "success",
      "gcs_bucket": "your-bucket-name",
      "gcs_prefix": "goms_outputs/20251205_103000_uuid1234"
    }
  },
  "created_at": "2025-12-05T10:30:00.000000",
  "updated_at": "2025-12-05T10:35:00.000000"
}
```

### 4. List All Jobs

**Endpoint**: `GET /jobs`

Get a list of all processing jobs.

**Request**:
```bash
curl "http://localhost:8080/jobs"
```

### 5. Health Check

**Endpoint**: `GET /health`

Check if the API is running and healthy.

**Request**:
```bash
curl "http://localhost:8080/health"
```

### 6. API Info

**Endpoint**: `GET /`

Get API information and configuration details.

**Request**:
```bash
curl "http://localhost:8080/"
```

## Configuration

### GCS Bucket Setup

1. **Create a GCS bucket**:
   ```bash
   gsutil mb gs://your-bucket-name
   ```

2. **Set bucket lifecycle** (optional, for auto-cleanup):
   ```bash
   gsutil lifecycle set lifecycle.json gs://your-bucket-name
   ```

3. **Set the environment variable**:
   ```bash
   export GCS_BUCKET=your-bucket-name
   ```

### Upload Directory

The default upload directory is `/tmp/documents`. Ensure it has appropriate permissions:

```bash
mkdir -p /tmp/documents
chmod 755 /tmp/documents
```

## Processing Workflow

### Step 1: PDF Splitting
- Input: Multi-GO PDF document
- Process: Splits the PDF into individual Government Order files
- Output: Individual PDF files for each GO

### Step 2: Markdown Conversion
- Input: Individual GO PDF files
- Process: Converts each PDF to markdown format (concurrent processing)
- Output: Markdown files with structured content

### Step 3: GCS Upload
- Input: Split PDFs and markdown files
- Process: Uploads all files to Google Cloud Storage with organized prefix
- Output: Files stored in `gs://bucket-name/goms_outputs/{timestamp}_{job_id}/`

### Step 4: Cleanup
- Removes uploaded temporary files from the local filesystem
- Keeps files in GCS for persistence

## Error Handling

The API implements comprehensive error handling:

- **400 Bad Request**: Invalid file format or missing required parameters
- **404 Not Found**: File path not found
- **503 Service Unavailable**: GCS_BUCKET not configured (required service)
- **500 Internal Server Error**: Processing or upload failures

All errors are logged with detailed information for debugging.

## Logging

Logs are output to the console with INFO level by default. Adjust logging in `api.py`:

```python
logging.basicConfig(level=logging.DEBUG)  # For more verbose output
```

## Troubleshooting

### Docker-Specific Issues

#### Container Won't Start

**Error**: Container exits immediately or fails health check

**Solution**:
1. Check logs: `docker compose logs goms-api`
2. Verify `.env` file exists and is properly configured
3. Ensure port 8080 is not already in use: `lsof -i :8080`
4. Check Docker daemon is running: `docker ps`

#### Permission Issues with Volumes

**Error**: Permission denied when writing to mounted volumes

**Solution**:
```bash
# Fix permissions on output directory
sudo chown -R $USER:$USER ./outputs

# Or run with appropriate user in docker-compose.yml
user: "${UID}:${GID}"
```

#### GCS Credentials Not Found

**Error**: `GOOGLE_APPLICATION_CREDENTIALS` file not found in container

**Solution**:
1. Verify the credentials file exists on your host system
2. Update the volume mount path in `docker-compose.yml`:
   ```yaml
   volumes:
     - /absolute/path/to/service-account.json:/app/credentials/service-account.json:ro
   ```
3. Ensure the path in `.env` matches the container path:
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json
   ```

### General Issues

### GCS_BUCKET is None

**Error**: `GCS_BUCKET is set to: None`

**Solution**: 
1. Verify `.env` file has `GCS_BUCKET=your-bucket-name`
2. For Docker: Restart the container after updating `.env`
   ```bash
   docker compose down
   docker compose up -d
   ```
3. For local: Load environment variables: `source .env`
4. Or pass as environment variable: `GCS_BUCKET=your-bucket-name python src/api.py`

### Permission Denied for GCS

**Error**: `Permission denied` or authentication errors

**Solution**:
1. Verify service account has GCS permissions
2. For local development: Run `gcloud auth application-default login`
3. For Docker: Ensure credentials file is properly mounted
4. Check `GOOGLE_APPLICATION_CREDENTIALS` path is correct

### PDF Conversion Failures

**Error**: Files not converted or incomplete conversions

**Solution**:
1. Check logs for detailed error messages
2. Verify PDF is not corrupted
3. Increase `max_workers` if resources allow (default: 4)
4. Check available disk space:
   - Docker: `docker system df`
   - Local: `df -h /tmp/documents`
5. For Docker: Check container resources:
   ```bash
   docker stats goms-extraction-api
   ```

### Port Already in Use

**Error**: `Address already in use` or port binding error

**Solution**:
1. Check what's using port 8080:
   ```bash
   lsof -i :8080
   # or
   netstat -tuln | grep 8080
   ```
2. Stop the conflicting service or change the port in `docker-compose.yml`:
   ```yaml
   ports:
     - "8081:8080"  # Use port 8081 on host
   ```

## Development

### Docker Development Workflow

#### Rebuilding After Code Changes

```bash
# Rebuild and restart the container
docker compose up --build

# Or rebuild without cache
docker compose build --no-cache
docker compose up
```

#### Accessing the Container Shell

```bash
# Open a shell in the running container
docker compose exec goms-api bash

# Or start a new container with shell
docker compose run --rm goms-api bash
```

#### Viewing Real-time Logs

```bash
# Follow logs from all services
docker compose logs -f

# Follow logs from specific service
docker compose logs -f goms-api

# View last 100 lines
docker compose logs --tail=100 goms-api
```

#### Running Tests in Docker

```bash
# Run tests in the container
docker compose exec goms-api pytest tests/

# Run specific test file
docker compose exec goms-api pytest tests/test_splitter.py

# Run with coverage
docker compose exec goms-api pytest --cov=goms_extractor tests/
```

### Local Development Workflow

#### Running Tests Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest tests/

# Run with coverage
pytest --cov=goms_extractor --cov=src tests/

# Run specific test file
pytest tests/test_splitter.py -v
```

#### Hot Reload for Development

```bash
# Run with auto-reload on code changes
python -m uvicorn src.api:app --host 0.0.0.0 --port 8080 --reload
```

### Code Structure

- **splitter.py**: PDF splitting using regex-based page analysis
- **md_converter.py**: PDF to markdown conversion with OCR
- **gcs_storage.py**: Google Cloud Storage operations
- **models.py**: Pydantic data models
- **token_tracker.py**: Token usage tracking for API calls
- **api.py**: FastAPI application and endpoints

### Adding New Features

1. **Create a new branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** in the appropriate module

3. **Test locally**:
   ```bash
   # Test with Docker
   docker compose up --build
   
   # Or test locally
   pytest tests/
   ```

4. **Update documentation** in README.md if needed

5. **Commit and push**:
   ```bash
   git add .
   git commit -m "Add: your feature description"
   git push origin feature/your-feature-name
   ```

## Performance Considerations

- **Concurrent Workers**: Default is 4. Adjust based on available CPU and memory
- **File Size**: Tested with PDFs up to 100MB
- **GCS Upload**: Automatic retry on transient failures
- **Timeout**: API timeout is 10 minutes per request

## Security

- CORS enabled for all origins (customize in production)
- Environment variables used for sensitive configuration
- Service account authentication for GCS
- No API authentication (add in production)

## Dependencies

### Docker Image

The Docker image is based on `python:3.12-slim` and includes:

**System Dependencies:**
- `ocrmypdf` - OCR processing for PDFs
- `tesseract-ocr` - OCR engine
- `tesseract-ocr-eng` - English language data for Tesseract
- `ghostscript` - PDF rendering and manipulation
- `libimage-exiftool-perl` - Image metadata extraction

**Python Dependencies:**

Key dependencies (see `requirements.txt` for complete list):
- `fastapi` - Web framework for building APIs
- `uvicorn` - ASGI server for running FastAPI
- `google-cloud-storage` - GCS client library
- `google-adk` - Google ADK integration
- `pydantic` - Data validation and settings management
- `httpx` - Async HTTP client
- `python-dotenv` - Environment variable management
- `pdfplumber` - PDF text extraction
- `ocrmypdf` - PDF OCR processing
- `PyPDF2` - PDF manipulation

### Installing Dependencies Locally

For local development without Docker:

**System Dependencies:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ocrmypdf tesseract-ocr tesseract-ocr-eng ghostscript

# macOS
brew install ocrmypdf tesseract ghostscript
```

**Python Dependencies:**
```bash
pip install -r requirements.txt
```

## Contributing

To contribute to this project:
1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

[Add your license here]

## Support

For issues or questions:
1. Check logs in the API output
2. Review troubleshooting section
3. Check GCS console for upload issues
4. Verify environment configuration

## Future Enhancements

- [ ] Database integration for job persistence
- [ ] Authentication and authorization
- [ ] Webhook notifications on completion
- [ ] Batch processing with job queuing
- [ ] Advanced scheduling capabilities
- [ ] Document metadata extraction
- [ ] Full-text search indexing
