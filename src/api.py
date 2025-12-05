"""
API Gateway for GOMS Extraction Agent
Provides a simplified REST API that forwards requests to the ADK API server.
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Union
import os
import shutil
import uuid
from datetime import datetime
import logging
import httpx
import asyncio
import functools
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from goms_extractor.splitter import split_goms
from goms_extractor.md_converter import convert_split_gos_to_markdown

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GCS_BUCKET = os.getenv("GCS_BUCKET")  # Set via environment variable
print(f"GCS_BUCKET is set to: {GCS_BUCKET}")

# Create FastAPI app
app = FastAPI(
    title="GOMS Extraction Gateway API",
    description="Simplified API gateway for GOMS extraction agent using ADK",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
ADK_API_URL = os.getenv("ADK_API_URL", "http://localhost:8000")
APP_NAME = "goms_extraction_workflow_agent"
UPLOAD_DIR = "/tmp/documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)  # Requires directory to be created with proper permissions

# GCS Configuration

GCS_ENABLED = GCS_BUCKET is not None

# HTTP client for ADK API
http_client = httpx.AsyncClient(timeout=600.0)  # 10 minute timeout for long-running tasks


class ProcessRequest(BaseModel):
    """Request model for processing a PDF from a file path"""
    pdf_path: str
    output_dir: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None



class JobResponse(BaseModel):
    """Response model for job submission"""
    job_id: str
    user_id: str
    session_id: str
    status: str
    message: str
    created_at: str


class JobStatusResponse(BaseModel):
    """Response model for job status"""
    job_id: str
    user_id: str
    session_id: str
    status: str
    message: Optional[str] = None
    result: Optional[Union[Dict[str, Any], List[Any]]] = None
    created_at: str
    updated_at: str

jobs: Dict[str, Dict[str, Any]] = {}


def generate_ids():
    """Generate unique user and session IDs"""
    job_id = str(uuid.uuid4())
    user_id = f"user_{job_id[:8]}"
    session_id = f"session_{job_id[:8]}"
    return job_id, user_id, session_id


async def create_adk_session(user_id: str, session_id: str) -> bool:
    """Create a session in the ADK API server"""
    try:
        url = f"{ADK_API_URL}/apps/{APP_NAME}/users/{user_id}/sessions/{session_id}"
        response = await http_client.post(url, json={})
        return response.status_code in [200, 201]
    except Exception as e:
        logger.error(f"Failed to create ADK session: {e}")
        return False


async def send_message_to_agent(user_id: str, session_id: str, message: str) -> Dict[str, Any]:
    """Send a message to the agent via ADK API"""
    try:
        url = f"{ADK_API_URL}/run"
        payload = {
            "appName": APP_NAME,
            "userId": user_id,
            "sessionId": session_id,
            "newMessage": {
                "role": "user",
                "parts": [{"text": message}]
            }
        }
        
        logger.info(f"Sending request to ADK API: {url}")
        response = await http_client.post(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        logger.error(f"Failed to send message to agent: {e}")
        raise


async def process_pdf_task(job_id: str, pdf_path: str, user_id: str, session_id: str, output_dir: Optional[str] = None):
    """Background task to process PDF"""
    try:
        logger.info(f"Job {job_id}: Starting processing")
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        # Create session in ADK
        session_created = await create_adk_session(user_id, session_id)
        if not session_created:
            raise Exception("Failed to create ADK session")

        # Prepare message with file path
        message = f"Process this document:\n{pdf_path}"
        if output_dir:
            message += f"\nSave outputs to: {output_dir}"

        # Send to agent
        logger.info(f"Job {job_id}: Sending message to agent with file path: {pdf_path}")
        result = await send_message_to_agent(user_id, session_id, message)

        # Update job status
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
        jobs[job_id]["message"] = "Processing completed successfully"
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        logger.info(f"Job {job_id}: Completed successfully")

        # Clean up the uploaded file after successful processing
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                logger.info(f"Cleaned up file: {pdf_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up file {pdf_path}: {cleanup_error}")

    except Exception as e:
        logger.error(f"Job {job_id}: Failed - {str(e)}", exc_info=True)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Processing failed: {str(e)}"
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        # Even in case of failure, try to clean up the file
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                logger.info(f"Cleaned up file after failure: {pdf_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up file after failure {pdf_path}: {cleanup_error}")


async def process_pdf_task_direct(
    job_id: str, 
    pdf_path: str, 
    output_dir: Optional[str] = None, 
    max_workers: int = 4
):
    """
    Background task to process PDF using direct in-process calls (concurrent).
    This bypasses the ADK agent and directly calls split_goms and convert_split_gos_to_markdown.
    Automatically uploads results to GCS if GCS_BUCKET is configured.
    """
    try:
        logger.info(f"Job {job_id}: Starting direct processing (concurrent with {max_workers} workers)")
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        # Step 1: Split the PDF into individual GOs
        logger.info(f"Job {job_id}: Splitting PDF into individual GOs...")
        loop = asyncio.get_event_loop()
        split_result = await loop.run_in_executor(
            None,
            functools.partial(split_goms, input_pdf_path=pdf_path, output_dir=output_dir)
        )
        
        if split_result.get("status") != "success":
            raise Exception(f"Splitting failed: {split_result.get('message')}")
        
        logger.info(f"Job {job_id}: Split completed - {len(split_result.get('split_files', []))} files created")

        # Step 2: Convert split PDFs to markdown (concurrent)
        logger.info(f"Job {job_id}: Converting split PDFs to markdown (concurrent)...")
        markdown_result = await loop.run_in_executor(
            None,
            functools.partial(
                convert_split_gos_to_markdown, 
                split_result=split_result, 
                output_dir=output_dir,
                max_workers=max_workers
            )
        )
        
        if markdown_result.get("status") != "success":
            logger.warning(f"Job {job_id}: Markdown conversion had issues: {markdown_result.get('message')}")

        # Combine results
        result = {
            "split_result": split_result,
            "markdown_result": markdown_result,
            "summary": {
                "total_gos_found": len(split_result.get("split_files", [])),
                "successful_conversions": len(markdown_result.get("markdown_files", [])),
                "split_files": split_result.get("split_files", []),
                "markdown_files": markdown_result.get("markdown_files", [])
            }
        }

        # Step 3: Upload to GCS if configured, otherwise use local storage
        if GCS_ENABLED:
            logger.info(f"Job {job_id}: Uploading results to GCS bucket: {GCS_BUCKET}...")
            try:
                from src.gcs_storage import GCSUploader
                
                uploader = GCSUploader(bucket_name=GCS_BUCKET)
                
                # Generate timestamp-based prefix for organization
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                gcs_prefix = f"goms_outputs/{timestamp}_{job_id[:8]}"
                
                # Upload split PDFs and markdown files to separate folders
                upload_results = []
                successful_uploads = 0
                failed_uploads = 0
                
                # Upload split PDFs
                logger.info(f"Job {job_id}: Uploading {len(split_result.get('split_files', []))} split PDFs...")
                for pdf_file in split_result.get("split_files", []):
                    filename = os.path.basename(pdf_file)
                    gcs_path = f"{gcs_prefix}/split_pdfs/{filename}"
                    upload_result = await loop.run_in_executor(
                        None,
                        functools.partial(uploader.upload_file, pdf_file, gcs_path, False)
                    )
                    upload_results.append(upload_result)
                    if upload_result["status"] == "success":
                        successful_uploads += 1
                    else:
                        failed_uploads += 1
                
                # Upload markdown files
                logger.info(f"Job {job_id}: Uploading {len(markdown_result.get('markdown_files', []))} markdown files...")
                for md_file in markdown_result.get("markdown_files", []):
                    filename = os.path.basename(md_file)
                    gcs_path = f"{gcs_prefix}/markdown/{filename}"
                    upload_result = await loop.run_in_executor(
                        None,
                        functools.partial(uploader.upload_file, md_file, gcs_path, False)
                    )
                    upload_results.append(upload_result)
                    if upload_result["status"] == "success":
                        successful_uploads += 1
                    else:
                        failed_uploads += 1
                
                total_files = len(upload_results)
                gcs_result = {
                    "status": "success" if failed_uploads == 0 else "partial" if successful_uploads > 0 else "error",
                    "total_files": total_files,
                    "successful_uploads": successful_uploads,
                    "failed_uploads": failed_uploads,
                    "gcs_bucket": GCS_BUCKET,
                    "gcs_prefix": gcs_prefix,
                    "split_pdfs_path": f"gs://{GCS_BUCKET}/{gcs_prefix}/split_pdfs/",
                    "markdown_path": f"gs://{GCS_BUCKET}/{gcs_prefix}/markdown/",
                    "message": f"Uploaded {successful_uploads}/{total_files} files to gs://{GCS_BUCKET}/{gcs_prefix}",
                    "uploads": upload_results
                }
                
                result["storage"] = gcs_result
                result["storage_type"] = "gcs"
                logger.info(f"Job {job_id}: GCS upload completed - {gcs_result['message']}")
                
            except Exception as gcs_error:
                logger.error(f"Job {job_id}: GCS upload failed - {str(gcs_error)}")
                result["storage"] = {
                    "status": "error",
                    "message": f"GCS upload failed: {str(gcs_error)}"
                }
                result["storage_type"] = "gcs"
        else:
            # Use local storage when GCS is not configured
            logger.info(f"Job {job_id}: GCS_BUCKET not configured, using local storage")
            
            # Get the output directories from the results
            split_dir = os.path.dirname(split_result.get("split_files", [""])[0]) if split_result.get("split_files") else "N/A"
            markdown_dir = os.path.dirname(markdown_result.get("markdown_files", [""])[0]) if markdown_result.get("markdown_files") else "N/A"
            
            result["storage"] = {
                "status": "success",
                "storage_type": "local",
                "split_pdfs_path": split_dir,
                "markdown_path": markdown_dir,
                "total_files": len(split_result.get("split_files", [])) + len(markdown_result.get("markdown_files", [])),
                "message": f"Files stored locally (GCS not configured)"
            }
            result["storage_type"] = "local"
            logger.info(f"Job {job_id}: Using local storage - split PDFs: {split_dir}, markdown: {markdown_dir}")

        # Update job status
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
        
        # Update message to include storage info
        message = f"Processing completed: {result['summary']['successful_conversions']}/{result['summary']['total_gos_found']} GOs converted"
        if result.get("storage_type") == "gcs" and result.get("storage", {}).get("status") == "success":
            message += f" | Uploaded to GCS: gs://{GCS_BUCKET}/{result['storage']['gcs_prefix']}"
        elif result.get("storage_type") == "local":
            message += f" | Stored locally: {result['storage']['split_pdfs_path']}"
        
        jobs[job_id]["message"] = message
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        logger.info(f"Job {job_id}: Completed successfully - {result['summary']}")

        # Clean up the uploaded file after successful processing
        try:
            if os.path.exists(pdf_path) and pdf_path.startswith(UPLOAD_DIR):
                os.remove(pdf_path)
                logger.info(f"Cleaned up file: {pdf_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up file {pdf_path}: {cleanup_error}")

    except Exception as e:
        logger.error(f"Job {job_id}: Failed - {str(e)}", exc_info=True)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Processing failed: {str(e)}"
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        # Even in case of failure, try to clean up the file
        try:
            if os.path.exists(pdf_path) and pdf_path.startswith(UPLOAD_DIR):
                os.remove(pdf_path)
                logger.info(f"Cleaned up file after failure: {pdf_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up file after failure {pdf_path}: {cleanup_error}")





@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "GOMS Extraction Gateway API",
        "version": "1.0.0",
        "description": "Simplified API gateway for GOMS extraction using ADK",
        "adk_api_url": ADK_API_URL,
        "app_name": APP_NAME,
        "endpoints": {
            "/health": "Health check",
            "/process": "Process a PDF file (upload) via ADK agent",
            "/process-path": "Process a PDF from file path via ADK agent",
            "/process-direct": "Process a PDF file (upload) with direct concurrent processing",
            "/process-path-direct": "Process a PDF from file path with direct concurrent processing",
            "/jobs/{job_id}": "Get job status",
            "/jobs": "List all jobs",
            "/adk/list-apps": "List ADK apps (passthrough)"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Check if ADK API is reachable
    adk_healthy = False
    try:
        response = await http_client.get(f"{ADK_API_URL}/list-apps", timeout=5.0)
        adk_healthy = response.status_code == 200
    except:
        pass
    
    # Check if ocrmypdf is available
    ocr_available = shutil.which("ocrmypdf") is not None
    
    return {
        "status": "healthy" if adk_healthy else "degraded",
        "timestamp": datetime.now().isoformat(),
        "adk_api_healthy": adk_healthy,
        "adk_api_url": ADK_API_URL,
        "ocrmypdf_available": ocr_available,
        "ocrmypdf_required": True
    }


@app.post("/process", response_model=JobResponse)
async def process_pdf_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Upload and process a PDF file.
    Returns a job ID that can be used to check processing status.
    """
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Generate IDs
    job_id, user_id, session_id = generate_ids()

    # Save uploaded file to shared directory with unique name
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create job entry
    jobs[job_id] = {
        "job_id": job_id,
        "user_id": user_id,
        "session_id": session_id,
        "status": "pending",
        "message": "Job created, processing will start shortly",
        "result": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "file_path": file_path,
        "original_filename": file.filename
    }

    # Add background task
    background_tasks.add_task(process_pdf_task, job_id, file_path, user_id, session_id)

    logger.info(f"Created job {job_id} for file {file.filename}")

    return JobResponse(**jobs[job_id])


@app.post("/process-path", response_model=JobResponse)
async def process_pdf_path(
    background_tasks: BackgroundTasks,
    request: ProcessRequest
):
    """
    Process a PDF file from a file path.
    Returns a job ID that can be used to check processing status.
    """
    # Validate file exists
    if not os.path.exists(request.pdf_path):
        raise HTTPException(status_code=404, detail=f"File not found: {request.pdf_path}")
    
    if not request.pdf_path.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Generate IDs or use provided ones
    job_id = str(uuid.uuid4())
    user_id = request.user_id or f"user_{job_id[:8]}"
    session_id = request.session_id or f"session_{job_id[:8]}"
    
    # Create job entry
    jobs[job_id] = {
        "job_id": job_id,
        "user_id": user_id,
        "session_id": session_id,
        "status": "pending",
        "message": "Job created, processing will start shortly",
        "result": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "file_path": request.pdf_path,
        "original_filename": os.path.basename(request.pdf_path)
    }
    
    # Add background task
    background_tasks.add_task(
        process_pdf_task, 
        job_id, 
        request.pdf_path, 
        user_id, 
        session_id,
        request.output_dir
    )
    
    logger.info(f"Created job {job_id} for file {request.pdf_path}")
    
    return JobResponse(**jobs[job_id])


@app.post("/process-direct", response_model=JobResponse)
async def process_pdf_upload_direct(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    max_workers: int = 4
):
    """
    Upload and process a PDF file using direct in-process calls (concurrent).
    This endpoint bypasses the ADK agent and directly calls the processing functions.
    Returns a job ID that can be used to check processing status.
    """
    # Log storage configuration (GCS or local)
    if not GCS_ENABLED:
        logger.info("GCS_BUCKET not configured, will use local storage for this job")
    
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Generate IDs
    job_id = str(uuid.uuid4())

    # Save uploaded file to shared directory with unique name
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create job entry
    jobs[job_id] = {
        "job_id": job_id,
        "user_id": "direct",
        "session_id": "direct",
        "status": "pending",
        "message": f"Job created, direct processing will start shortly (concurrent with {max_workers} workers)",
        "result": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "file_path": file_path,
        "original_filename": file.filename
    }

    # Add background task for direct processing
    background_tasks.add_task(process_pdf_task_direct, job_id, file_path, None, max_workers)

    logger.info(f"Created direct processing job {job_id} for file {file.filename}")

    return JobResponse(**jobs[job_id])


@app.post("/process-path-direct", response_model=JobResponse)
async def process_pdf_path_direct(
    background_tasks: BackgroundTasks,
    request: ProcessRequest,
    max_workers: int = 4
):
    """
    Process a PDF file from a file path using direct in-process calls (concurrent).
    This endpoint bypasses the ADK agent and directly calls the processing functions.
    Automatically uploads results to GCS if GCS_BUCKET environment variable is set.
    Returns a job ID that can be used to check processing status.
    """
    # Log storage configuration (GCS or local)
    if not GCS_ENABLED:
        logger.info("GCS_BUCKET not configured, will use local storage for this job")
    
    # Validate file exists
    if not os.path.exists(request.pdf_path):
        raise HTTPException(status_code=404, detail=f"File not found: {request.pdf_path}")
    
    if not request.pdf_path.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Create job entry
    message = f"Job created, direct processing will start shortly (concurrent with {max_workers} workers)"
    if GCS_ENABLED:
        message += f" | Will auto-upload to GCS: {GCS_BUCKET}"
    else:
        message += " | Will use local storage"
    
    jobs[job_id] = {
        "job_id": job_id,
        "user_id": "direct",
        "session_id": "direct",
        "status": "pending",
        "message": message,
        "result": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "file_path": request.pdf_path,
        "original_filename": os.path.basename(request.pdf_path)
    }
    
    # Add background task for direct processing
    background_tasks.add_task(
        process_pdf_task_direct,
        job_id,
        request.pdf_path,
        request.output_dir,
        max_workers
    )
    
    logger.info(f"Created direct processing job {job_id} for file {request.pdf_path}")
    
    return JobResponse(**jobs[job_id])




@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get the status of a processing job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    return JobStatusResponse(**jobs[job_id])


@app.get("/jobs")
async def list_jobs():
    """List all jobs"""
    return {
        "total": len(jobs),
        "jobs": [JobStatusResponse(**job) for job in jobs.values()]
    }


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its associated files"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    job = jobs[job_id]
    
    # Delete uploaded file if it exists
    if "file_path" in job and job["file_path"].startswith(UPLOAD_DIR):
        try:
            if os.path.exists(job["file_path"]):
                os.remove(job["file_path"])
                logger.info(f"Deleted file during job cleanup: {job['file_path']}")
        except Exception as e:
            logger.warning(f"Failed to delete file {job['file_path']}: {e}")
    
    # Remove from store
    del jobs[job_id]
    
    return {"message": f"Job {job_id} deleted successfully"}


# ADK API Passthrough Endpoints
@app.get("/adk/list-apps")
async def list_adk_apps():
    """List available ADK apps (passthrough)"""
    try:
        response = await http_client.get(f"{ADK_API_URL}/list-apps")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list apps: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await http_client.aclose()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
