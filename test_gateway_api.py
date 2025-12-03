"""
Unit tests for the GOMS Extraction Gateway API
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import httpx
from io import BytesIO
import os
import sys

# Add parent directory to path to import api
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import app, generate_ids, jobs


@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)


@pytest.fixture
def mock_http_client():
    """Mock the HTTP client for ADK API calls"""
    with patch('api.http_client') as mock:
        yield mock


@pytest.fixture(autouse=True)
def clear_jobs():
    """Clear jobs dictionary before each test"""
    jobs.clear()
    yield
    jobs.clear()


class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_generate_ids(self):
        """Test ID generation"""
        job_id, user_id, session_id = generate_ids()
        
        assert isinstance(job_id, str)
        assert isinstance(user_id, str)
        assert isinstance(session_id, str)
        
        assert user_id.startswith("user_")
        assert session_id.startswith("session_")
        assert len(job_id) == 36  # UUID format
    
    def test_generate_ids_unique(self):
        """Test that generated IDs are unique"""
        id1, user1, session1 = generate_ids()
        id2, user2, session2 = generate_ids()
        
        assert id1 != id2
        assert user1 != user2
        assert session1 != session2


class TestRootEndpoint:
    """Test root endpoint"""
    
    def test_root_endpoint(self, client):
        """Test GET /"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "GOMS Extraction Gateway API"
        assert data["version"] == "1.0.0"
        assert data["app_name"] == "goms_extraction_workflow_agent"
        assert "endpoints" in data


class TestHealthCheck:
    """Test health check endpoint"""
    
    def test_health_check_healthy(self, client, mock_http_client):
        """Test health check when ADK API is healthy"""
        # Mock successful ADK API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        with patch('shutil.which', return_value='/usr/bin/ocrmypdf'):
            response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["adk_api_healthy"] is True
        assert data["ocrmypdf_available"] is True
        assert data["ocrmypdf_required"] is True
    
    def test_health_check_degraded(self, client, mock_http_client):
        """Test health check when ADK API is down"""
        # Mock failed ADK API response
        mock_http_client.get = AsyncMock(side_effect=Exception("Connection failed"))
        
        with patch('shutil.which', return_value='/usr/bin/ocrmypdf'):
            response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "degraded"
        assert data["adk_api_healthy"] is False
    
    def test_health_check_no_ocr(self, client, mock_http_client):
        """Test health check when OCRmyPDF is not available"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        with patch('shutil.which', return_value=None):
            response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ocrmypdf_available"] is False


class TestProcessPdfPath:
    """Test process PDF from path endpoint"""
    
    def test_process_pdf_path_success(self, client):
        """Test successful PDF processing from path"""
        # Use the actual test file in the data directory
        test_file = os.path.join(os.path.dirname(__file__), "data", "amendments_from_1997_to_03-2008.pdf")
        
        # Skip test if file doesn't exist
        if not os.path.exists(test_file):
            pytest.skip(f"Test file not found: {test_file}")
        
        response = client.post(
            "/process-path",
            json={"pdf_path": test_file}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "job_id" in data
        assert "user_id" in data
        assert "session_id" in data
        assert data["status"] == "pending"
        assert data["message"] == "Job created, processing will start shortly"
        
        # Verify job was created
        assert data["job_id"] in jobs
    
    def test_process_pdf_path_file_not_found(self, client):
        """Test processing non-existent file"""
        response = client.post(
            "/process-path",
            json={"pdf_path": "/nonexistent/file.pdf"}
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_process_pdf_path_invalid_extension(self, client):
        """Test processing file with invalid extension"""
        # Create a temporary test file with wrong extension
        test_file = "/tmp/test_go.txt"
        with open(test_file, "w") as f:
            f.write("test")
        
        try:
            response = client.post(
                "/process-path",
                json={"pdf_path": test_file}
            )
            
            assert response.status_code == 400
            assert "PDF" in response.json()["detail"]
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)
    
    def test_process_pdf_path_with_output_dir(self, client):
        """Test processing with custom output directory"""
        test_file = "/tmp/test_go.pdf"
        with open(test_file, "w") as f:
            f.write("test")
        
        try:
            response = client.post(
                "/process-path",
                json={
                    "pdf_path": test_file,
                    "output_dir": "/tmp/custom_output"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)
    
    def test_process_pdf_path_custom_ids(self, client):
        """Test processing with custom user and session IDs"""
        test_file = "/tmp/test_go.pdf"
        with open(test_file, "w") as f:
            f.write("test")
        
        try:
            response = client.post(
                "/process-path",
                json={
                    "pdf_path": test_file,
                    "user_id": "custom_user",
                    "session_id": "custom_session"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == "custom_user"
            assert data["session_id"] == "custom_session"
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


class TestProcessPdfUpload:
    """Test process PDF upload endpoint"""
    
    def test_process_pdf_upload_success(self, client):
        """Test successful PDF upload"""
        # Create fake PDF file
        pdf_content = b"%PDF-1.4\ntest content"
        files = {"file": ("test.pdf", BytesIO(pdf_content), "application/pdf")}
        
        response = client.post("/process", files=files)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["job_id"] in jobs
    
    def test_process_pdf_upload_invalid_extension(self, client):
        """Test upload with invalid file extension"""
        files = {"file": ("test.txt", BytesIO(b"test"), "text/plain")}
        
        response = client.post("/process", files=files)
        
        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]


class TestJobManagement:
    """Test job management endpoints"""
    
    def test_get_job_status_success(self, client):
        """Test getting job status"""
        # Create a job manually
        job_id = "test-job-123"
        jobs[job_id] = {
            "job_id": job_id,
            "user_id": "user_test",
            "session_id": "session_test",
            "status": "completed",
            "result": {"test": "data"},
            "created_at": "2025-12-03T00:00:00",
            "updated_at": "2025-12-03T00:01:00"
        }
        
        response = client.get(f"/jobs/{job_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["job_id"] == job_id
        assert data["status"] == "completed"
        assert data["result"]["test"] == "data"
    
    def test_get_job_status_not_found(self, client):
        """Test getting non-existent job"""
        response = client.get("/jobs/nonexistent-job")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_list_jobs_empty(self, client):
        """Test listing jobs when empty"""
        response = client.get("/jobs")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 0
        assert data["jobs"] == []
    
    def test_list_jobs_with_data(self, client):
        """Test listing jobs with data"""
        # Create multiple jobs
        for i in range(3):
            job_id = f"test-job-{i}"
            jobs[job_id] = {
                "job_id": job_id,
                "user_id": f"user_{i}",
                "session_id": f"session_{i}",
                "status": "pending",
                "result": None,
                "created_at": "2025-12-03T00:00:00",
                "updated_at": "2025-12-03T00:00:00"
            }
        
        response = client.get("/jobs")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 3
        assert len(data["jobs"]) == 3
    
    def test_delete_job_success(self, client):
        """Test deleting a job"""
        job_id = "test-job-delete"
        jobs[job_id] = {
            "job_id": job_id,
            "user_id": "user_test",
            "session_id": "session_test",
            "status": "completed",
            "result": None,
            "created_at": "2025-12-03T00:00:00",
            "updated_at": "2025-12-03T00:00:00",
            "file_path": "/other/path/file.pdf"
        }
        
        response = client.delete(f"/jobs/{job_id}")
        
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]
        assert job_id not in jobs
    
    def test_delete_job_not_found(self, client):
        """Test deleting non-existent job"""
        response = client.delete("/jobs/nonexistent-job")
        
        assert response.status_code == 404


class TestADKPassthrough:
    """Test ADK API passthrough endpoints"""
    
    def test_list_adk_apps_success(self, client, mock_http_client):
        """Test listing ADK apps"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["goms_extraction_workflow_agent", "other_agent"]
        mock_http_client.get = AsyncMock(return_value=mock_response)
        
        response = client.get("/adk/list-apps")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "goms_extraction_workflow_agent" in data
        assert "other_agent" in data
    
    def test_list_adk_apps_failure(self, client, mock_http_client):
        """Test listing ADK apps when API fails"""
        mock_http_client.get = AsyncMock(side_effect=Exception("API error"))
        
        response = client.get("/adk/list-apps")
        
        assert response.status_code == 500
        assert "Failed to list apps" in response.json()["detail"]



class TestBackgroundTasks:
    """Test background task processing"""
    
    @pytest.mark.asyncio
    async def test_create_adk_session(self, mock_http_client):
        """Test ADK session creation"""
        from api import create_adk_session
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_http_client.post = AsyncMock(return_value=mock_response)
        
        result = await create_adk_session("user_1", "session_1")
        
        assert result is True
        mock_http_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_adk_session_failure(self, mock_http_client):
        """Test ADK session creation failure"""
        from api import create_adk_session
        
        mock_http_client.post = AsyncMock(side_effect=Exception("Connection error"))
        
        result = await create_adk_session("user_1", "session_1")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_to_agent(self, mock_http_client):
        """Test sending message to agent"""
        from api import send_message_to_agent
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"events": [], "response": "Success"}
        mock_http_client.post = AsyncMock(return_value=mock_response)
        
        result = await send_message_to_agent("user_1", "session_1", "Test message")
        
        assert result["response"] == "Success"
        mock_http_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_message_to_agent_failure(self, mock_http_client):
        """Test sending message failure"""
        from api import send_message_to_agent
        
        mock_http_client.post = AsyncMock(side_effect=Exception("API error"))
        
        with pytest.raises(Exception):
            await send_message_to_agent("user_1", "session_1", "Test message")


class TestProcessingLogicIntegration:
    """Integration tests for processing logic against reference data"""
    
    def test_logic_against_reference_outputs(self):
        """
        Verify that running the actual processing logic on the test PDF
        produces the same number of files as in the reference outputs_001 directory.
        """
        import shutil
        import tempfile
        from goms_extractor.splitter import split_goms
        from goms_extractor.md_converter import convert_split_gos_to_markdown
        
        # Paths
        # test_gateway_api.py is in the root, so dirname gives us the root
        base_dir = os.path.dirname(os.path.abspath(__file__))
        test_pdf_path = os.path.join(base_dir, "data", "amendments_from_1997_to_03-2008.pdf")
        reference_split_dir = os.path.join(base_dir, "outputs_001", "split_goms")
        reference_md_dir = os.path.join(base_dir, "outputs_001", "markdown_goms")
        
        # Skip if test data or reference data is missing
        if not os.path.exists(test_pdf_path):
            pytest.skip(f"Test PDF not found: {test_pdf_path}")
        if not os.path.exists(reference_split_dir):
            pytest.skip(f"Reference split output not found: {reference_split_dir}")
        
        # Count reference files
        ref_split_count = len([f for f in os.listdir(reference_split_dir) if f.endswith('.pdf')])
        ref_md_count = len([f for f in os.listdir(reference_md_dir) if f.endswith('.md')])
        
        print(f"Reference: {ref_split_count} split PDFs, {ref_md_count} markdown files")
        
        # Create temp directory for outputs
        with tempfile.TemporaryDirectory() as temp_dir:
            split_out_dir = os.path.join(temp_dir, "split_goms")
            md_out_dir = os.path.join(temp_dir, "markdown_goms")
            
            # 1. Test Splitter
            print("Running splitter...")
            # We need to mock shutil.which to ensure it finds ocrmypdf if it's installed, 
            # or skip if not (though the code raises error now)
            if not shutil.which("ocrmypdf"):
                pytest.skip("OCRmyPDF not installed, cannot run integration test")
                
            split_result = split_goms(test_pdf_path, output_dir=split_out_dir)
            
            assert split_result["status"] == "success"
            generated_split_count = len(split_result["split_files"])
            
            print(f"Generated: {generated_split_count} split PDFs")
            
            # Verify split count matches reference
            # Note: We allow for exact match or explained deviation. 
            # For now, assert exact match as requested.
            assert generated_split_count == ref_split_count, \
                f"Split file count mismatch! Expected {ref_split_count}, got {generated_split_count}"
            
            # 2. Test Converter
            print("Running converter...")
            convert_result = convert_split_gos_to_markdown(split_result)
            
            assert convert_result["status"] == "success"
            generated_md_count = len(convert_result["markdown_files"])
            
            print(f"Generated: {generated_md_count} markdown files")
            
            # Verify markdown count matches reference
            assert generated_md_count == ref_md_count, \
                f"Markdown file count mismatch! Expected {ref_md_count}, got {generated_md_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
