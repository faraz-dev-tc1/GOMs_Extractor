"""
API Gateway for GOMS Extraction Agent
Provides a simplified REST API that forwards requests to the ADK API server.
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import shutil
import uuid
from datetime import datetime
import logging
import httpx
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
APP_NAME = "goms_extractor"
UPLOAD_DIR = "/tmp/goms_gateway_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    result: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str


# In-memory job tracking
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
        
        # Prepare message
        message = f"Process this PDF file: {pdf_path}"
        if output_dir:
            message += f" and save outputs to {output_dir}"
        
        # Send to agent
        logger.info(f"Job {job_id}: Sending message to agent")
        result = await send_message_to_agent(user_id, session_id, message)
        
        # Update job status
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
        jobs[job_id]["message"] = "Processing completed successfully"
        jobs[job_id]["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"Job {job_id}: Completed successfully")
        
    except Exception as e:
        logger.error(f"Job {job_id}: Failed - {str(e)}", exc_info=True)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Processing failed: {str(e)}"
        jobs[job_id]["updated_at"] = datetime.now().isoformat()


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
            "/process": "Process a PDF file (upload)",
            "/process-path": "Process a PDF from file path",
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
    
    # Save uploaded file
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
