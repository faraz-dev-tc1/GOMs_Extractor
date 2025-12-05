"""
Google Cloud Storage utility for uploading GOMS processing outputs.
"""

import os
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("google-cloud-storage not installed. GCS upload will be disabled.")


class GCSUploader:
    """Handles uploading files to Google Cloud Storage"""
    
    def __init__(self, bucket_name: Optional[str] = None, credentials_path: Optional[str] = None):
        """
        Initialize GCS uploader.
        
        Args:
            bucket_name: GCS bucket name (can also be set via GCS_BUCKET env var)
            credentials_path: Path to service account JSON (can also be set via GOOGLE_APPLICATION_CREDENTIALS)
        """
        if not GCS_AVAILABLE:
            raise ImportError(
                "google-cloud-storage is not installed. "
                "Install it with: pip install google-cloud-storage"
            )
        
        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET")
        if not self.bucket_name:
            raise ValueError(
                "GCS bucket name must be provided either as argument or via GCS_BUCKET environment variable"
            )
        
        # Set credentials if provided
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        # Initialize client
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)
        
        logger.info(f"GCS Uploader initialized for bucket: {self.bucket_name}")
    
    def upload_file(
        self, 
        local_path: str, 
        gcs_path: Optional[str] = None,
        make_public: bool = False
    ) -> Dict[str, Any]:
        """
        Upload a single file to GCS.
        
        Args:
            local_path: Local file path to upload
            gcs_path: Destination path in GCS (if None, uses basename of local_path)
            make_public: Whether to make the file publicly accessible
        
        Returns:
            Dictionary with upload result:
            {
                "status": "success|error",
                "local_path": str,
                "gcs_path": str,
                "gcs_uri": str,
                "public_url": str (if make_public=True),
                "message": str
            }
        """
        try:
            if not os.path.exists(local_path):
                return {
                    "status": "error",
                    "local_path": local_path,
                    "message": f"File not found: {local_path}"
                }
            
            # Determine GCS path
            if gcs_path is None:
                gcs_path = os.path.basename(local_path)
            
            # Upload file
            blob = self.bucket.blob(gcs_path)
            blob.upload_from_filename(local_path)
            
            # Make public if requested
            if make_public:
                blob.make_public()
            
            result = {
                "status": "success",
                "local_path": local_path,
                "gcs_path": gcs_path,
                "gcs_uri": f"gs://{self.bucket_name}/{gcs_path}",
                "message": f"Successfully uploaded to GCS"
            }
            
            if make_public:
                result["public_url"] = blob.public_url
            
            logger.info(f"Uploaded: {local_path} -> gs://{self.bucket_name}/{gcs_path}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {str(e)}")
            return {
                "status": "error",
                "local_path": local_path,
                "message": f"Upload failed: {str(e)}"
            }
    
    def upload_directory(
        self,
        local_dir: str,
        gcs_prefix: str = "",
        file_extensions: Optional[List[str]] = None,
        make_public: bool = False
    ) -> Dict[str, Any]:
        """
        Upload all files in a directory to GCS.
        
        Args:
            local_dir: Local directory to upload
            gcs_prefix: Prefix for GCS paths (e.g., "outputs/2024-12-05/")
            file_extensions: List of file extensions to include (e.g., [".pdf", ".md"])
            make_public: Whether to make files publicly accessible
        
        Returns:
            Dictionary with upload results:
            {
                "status": "success|partial|error",
                "total_files": int,
                "successful_uploads": int,
                "failed_uploads": int,
                "uploads": List[Dict],
                "message": str
            }
        """
        try:
            if not os.path.exists(local_dir):
                return {
                    "status": "error",
                    "message": f"Directory not found: {local_dir}"
                }
            
            # Find all files to upload
            files_to_upload = []
            for root, dirs, files in os.walk(local_dir):
                for file in files:
                    local_path = os.path.join(root, file)
                    
                    # Filter by extension if specified
                    if file_extensions:
                        if not any(file.endswith(ext) for ext in file_extensions):
                            continue
                    
                    # Calculate relative path for GCS
                    rel_path = os.path.relpath(local_path, local_dir)
                    gcs_path = os.path.join(gcs_prefix, rel_path) if gcs_prefix else rel_path
                    
                    files_to_upload.append((local_path, gcs_path))
            
            # Upload all files
            upload_results = []
            successful = 0
            failed = 0
            
            for local_path, gcs_path in files_to_upload:
                result = self.upload_file(local_path, gcs_path, make_public)
                upload_results.append(result)
                
                if result["status"] == "success":
                    successful += 1
                else:
                    failed += 1
            
            total = len(files_to_upload)
            
            if successful == total:
                status = "success"
            elif successful > 0:
                status = "partial"
            else:
                status = "error"
            
            return {
                "status": status,
                "total_files": total,
                "successful_uploads": successful,
                "failed_uploads": failed,
                "uploads": upload_results,
                "message": f"Uploaded {successful}/{total} files to GCS"
            }
            
        except Exception as e:
            logger.error(f"Failed to upload directory {local_dir}: {str(e)}")
            return {
                "status": "error",
                "message": f"Directory upload failed: {str(e)}"
            }
    
    def upload_processing_results(
        self,
        split_files: List[str],
        markdown_files: List[str],
        gcs_prefix: str = "",
        make_public: bool = False
    ) -> Dict[str, Any]:
        """
        Upload GOMS processing results (split PDFs and markdown files).
        
        Args:
            split_files: List of split PDF file paths
            markdown_files: List of markdown file paths
            gcs_prefix: Prefix for GCS paths (e.g., "goms_outputs/job_123/")
            make_public: Whether to make files publicly accessible
        
        Returns:
            Dictionary with upload results
        """
        all_files = split_files + markdown_files
        
        upload_results = []
        successful = 0
        failed = 0
        
        for local_path in all_files:
            # Determine file type for organization
            if local_path.endswith('.pdf'):
                file_type = "split_pdfs"
            elif local_path.endswith('.md'):
                file_type = "markdown"
            else:
                file_type = "other"
            
            # Create GCS path
            filename = os.path.basename(local_path)
            gcs_path = os.path.join(gcs_prefix, file_type, filename) if gcs_prefix else os.path.join(file_type, filename)
            
            # Upload
            result = self.upload_file(local_path, gcs_path, make_public)
            upload_results.append(result)
            
            if result["status"] == "success":
                successful += 1
            else:
                failed += 1
        
        total = len(all_files)
        
        if successful == total:
            status = "success"
        elif successful > 0:
            status = "partial"
        else:
            status = "error"
        
        return {
            "status": status,
            "total_files": total,
            "successful_uploads": successful,
            "failed_uploads": failed,
            "uploads": upload_results,
            "gcs_bucket": self.bucket_name,
            "gcs_prefix": gcs_prefix,
            "message": f"Uploaded {successful}/{total} files to gs://{self.bucket_name}/{gcs_prefix}"
        }


def upload_to_gcs(
    files: List[str],
    bucket_name: Optional[str] = None,
    gcs_prefix: str = "",
    make_public: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to upload files to GCS.
    
    Args:
        files: List of file paths to upload
        bucket_name: GCS bucket name
        gcs_prefix: Prefix for GCS paths
        make_public: Whether to make files publicly accessible
    
    Returns:
        Dictionary with upload results
    """
    try:
        uploader = GCSUploader(bucket_name=bucket_name)
        
        upload_results = []
        successful = 0
        failed = 0
        
        for local_path in files:
            filename = os.path.basename(local_path)
            gcs_path = os.path.join(gcs_prefix, filename) if gcs_prefix else filename
            
            result = uploader.upload_file(local_path, gcs_path, make_public)
            upload_results.append(result)
            
            if result["status"] == "success":
                successful += 1
            else:
                failed += 1
        
        total = len(files)
        
        return {
            "status": "success" if successful == total else "partial" if successful > 0 else "error",
            "total_files": total,
            "successful_uploads": successful,
            "failed_uploads": failed,
            "uploads": upload_results,
            "message": f"Uploaded {successful}/{total} files to GCS"
        }
        
    except Exception as e:
        logger.error(f"GCS upload failed: {str(e)}")
        return {
            "status": "error",
            "message": f"GCS upload failed: {str(e)}"
        }
