# GOMS Extraction Project

A comprehensive system for extracting, splitting, and converting Government Order (GO) PDF documents into structured markdown format using Google Cloud services.

## Project Overview

This project processes Government Orders from Andhra Pradesh and other states by:

1. **Splitting multi-GO PDFs** into individual Government Order PDF files
2. **Converting PDFs to Markdown** with concurrent processing for efficiency
3. **Uploading results to Google Cloud Storage** for centralized document management
4. **Providing REST API endpoints** for easy integration and batch processing

The system is built with a modular architecture using FastAPI for the API gateway and Google Cloud Storage for document persistence.

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

- Python 3.8+
- Google Cloud Project with:
  - Google Cloud Storage bucket
  - Service account with GCS permissions
  - Application Default Credentials configured
- FastAPI and dependencies

## Installation

### 1. Clone or Download the Project

```bash
cd /home/faraz/workspace/goms
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# GCS Configuration (REQUIRED)
GCS_BUCKET=your-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# Optional: ADK API Configuration
ADK_API_URL=http://localhost:8000
UPLOAD_DIR=/tmp/documents
```

### 5. Set Up Google Cloud Authentication

```bash
# Authenticate with Google Cloud
gcloud auth application-default login

# Or use a service account key
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

## Running the Application

### Start the API Server

```bash
# From the project root
python src/api.py
```

The API will be available at `http://localhost:8000`

### Access API Documentation

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## API Endpoints

### 1. Process PDF Upload (Direct)

**Endpoint**: `POST /process-direct`

Upload a PDF file and process it immediately with concurrent conversion.

**Request**:
```bash
curl -X POST "http://localhost:8000/process-direct" \
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
curl -X POST "http://localhost:8000/process-path-direct" \
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
curl "http://localhost:8000/job-status/uuid-string"
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
curl "http://localhost:8000/jobs"
```

### 5. API Info

**Endpoint**: `GET /`

Get API information and configuration details.

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

### GCS_BUCKET is None

**Error**: `GCS_BUCKET is set to: None`

**Solution**: 
1. Verify `.env` file has `GCS_BUCKET=your-bucket-name`
2. Load environment variables before running: `source .env`
3. Or pass as environment variable: `GCS_BUCKET=your-bucket-name python src/api.py`

### Permission Denied for GCS

**Error**: `Permission denied` or authentication errors

**Solution**:
1. Verify service account has GCS permissions
2. Run `gcloud auth application-default login`
3. Check `GOOGLE_APPLICATION_CREDENTIALS` path is correct

### PDF Conversion Failures

**Error**: Files not converted or incomplete conversions

**Solution**:
1. Check logs for detailed error messages
2. Verify PDF is not corrupted
3. Increase `max_workers` if resources allow
4. Check available disk space in `/tmp/documents`

## Development

### Running Tests

```bash
pytest tests/
```

### Code Structure

- **splitter.py**: PDF splitting using PyPDF2
- **md_converter.py**: PDF to markdown conversion with Claude
- **gcs_storage.py**: Google Cloud Storage operations
- **models.py**: Pydantic data models
- **token_tracker.py**: Token usage tracking for API calls

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

Key dependencies:
- `fastapi` - Web framework
- `google-cloud-storage` - GCS client
- `google-adk` - ADK integration
- `pydantic` - Data validation
- `httpx` - Async HTTP client
- `python-dotenv` - Environment configuration

See `requirements.txt` for complete list.

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
