"""
Quick script to sync missing PDFs to S3
Compares local folder with S3 and uploads only what's missing
"""
import os
import sys
from pathlib import Path

# Add project root to Python path
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from typing import BinaryIO, Optional, List, Any
import boto3
from app.core.config import settings

class CloudStorageService:
    """
    Service for managing files in AWS S3 cloud storage.
    
    This service provides methods to:
    - Upload PDF files to S3 bucket
    - Download files from S3
    - List all files in the bucket
    
    The service gracefully handles missing AWS credentials by setting
    s3_client to None, allowing the application to run without S3.
    
    Attributes:
        s3_client: Boto3 S3 client instance (None if not configured)
    """
    
    def __init__(self) -> None:
        """
        Initialize AWS S3 cloud storage service.
        
        Creates S3 client if AWS credentials are configured.
        If credentials are "changeme", service will be disabled but won't crash.
        """
        self.s3_client: Optional[Any] = None
        
        if settings.AWS_ACCESS_KEY_ID != "changeme":
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
    
    def upload_file(self, file_obj: BinaryIO, filename: str) -> Optional[str]:
        """
        Upload a file to S3 bucket.
        """
        if not self.s3_client:
            print("S3 client not configured. Please set AWS credentials.")
            return None
        
        try:
            self.s3_client.upload_fileobj(
                file_obj,
                settings.S3_BUCKET_NAME,
                filename
            )
            
            # Construct public URL (assumes bucket is public or has proper ACL)
            url = (
                f"https://{settings.S3_BUCKET_NAME}.s3."
                f"{settings.AWS_REGION}.amazonaws.com/{filename}"
            )
            return url
            
        except Exception as e:
            print(f"Error uploading to S3: {e}")
            return None
    
    def download_file(self, filename: str, destination: str) -> bool:
        """
        Download a file from S3 to local filesystem.
        """
        if not self.s3_client:
            print("S3 client not configured. Please set AWS credentials.")
            return False
        
        try:
            self.s3_client.download_file(
                settings.S3_BUCKET_NAME,
                filename,
                destination
            )
            return True
        except Exception as e:
            print(f"Error downloading from S3: {e}")
            return False
    
    def list_files(self) -> List[str]:
        """
        List all files in the S3 bucket.
        """
        if not self.s3_client:
            print("S3 client not configured. Please set AWS credentials.")
            return []
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=settings.S3_BUCKET_NAME
            )
            
            if 'Contents' in response:
                return [obj['Key'] for obj in response['Contents']]
            return []
            
        except Exception as e:
            print(f"Error listing S3 files: {e}")
            return []

def sync_pdfs_to_s3():
    """Upload only the files that are missing from S3."""
    
    print("🔍 Checking for missing knowledge base files in S3...")
    print("=" * 60)
    
    # Initialize cloud storage
    storage = CloudStorageService()
    
    # Get local files (.pdf, .txt, .docx)
    pdf_dir = Path(PROJECT_ROOT) / "data" / "kb_documents"
    local_files = set()
    for ext in ['*.pdf', '*.txt', '*.docx']:
        local_files.update(f.name for f in pdf_dir.glob(ext))
    
    print(f"\n📁 Local files: {len(local_files)}")
    
    # Get S3 files
    s3_files = set(storage.list_files())
    print(f"☁️  S3 files: {len(s3_files)}")
    
    # Find missing files
    missing = local_files - s3_files
    
    if not missing:
        print("\n✅ All knowledge base files are already in S3!")
        return
    
    print(f"\n📤 Found {len(missing)} missing files to upload:")
    for filename in sorted(missing):
        print(f"  - {filename}")
    
    # Upload missing files
    print(f"\n🚀 Uploading {len(missing)} files...")
    print("-" * 60)
    
    for i, filename in enumerate(sorted(missing), 1):
        file_path = pdf_dir / filename
        print(f"[{i}/{len(missing)}] Uploading {filename}...")
        
        with open(file_path, 'rb') as f:
            url = storage.upload_file(f, filename)
            if url:
                print(f"  ✅ Success: {url}")
            else:
                print(f"  ❌ Failed")
    
    # Verify
    s3_files_after = set(storage.list_files())
    print("\n" + "=" * 60)
    print("✨ Sync Complete!")
    print(f"📊 S3 now has {len(s3_files_after)} files (was {len(s3_files)})")
    
    if len(s3_files_after) == len(local_files):
        print("✅ All local files are now in S3!")
    else:
        still_missing = local_files - s3_files_after
        print(f"⚠️  Still missing {len(still_missing)} files:")
        for f in still_missing:
            print(f"  - {f}")

if __name__ == "__main__":
    sync_pdfs_to_s3()
    print("\n" + "=" * 60)
    input("Press Enter to close...")

