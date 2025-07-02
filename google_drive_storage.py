"""Google Drive File Storage Manager for KYC Documents - FIXED VERSION"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, IO
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
from google.oauth2.service_account import Credentials
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("kyc-google-drive")

class GoogleDriveKYCStorage:
    """Google Drive storage manager for KYC documents and files"""
    
    def __init__(self):
        self.drive_service = None
        self.initialized = False
        self.executor = ThreadPoolExecutor(max_workers=3)
        
        # Configuration - FIXED to properly use environment variables
        self.root_folder_name = os.getenv("KYC_DRIVE_FOLDER_NAME", "KYC_Documents")
        self.parent_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")  # This is the key fix!
        
        logger.info(f"🔧 Google Drive Configuration:")
        logger.info(f"   Root folder name: {self.root_folder_name}")
        logger.info(f"   Parent folder ID: {self.parent_folder_id}")
        
        self.folder_structure = {
            'documents': 'Documents',
            'ocr_results': 'OCR_Results',
            'verification_reports': 'Verification_Reports',
            'face_images': 'Face_Images',
            'raw_responses': 'Raw_API_Responses'
        }
        self.folder_ids = {}
    
    async def initialize(self):
        """Initialize Google Drive connection"""
        try:
            # Load credentials
            creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
            if not os.path.exists(creds_path):
                logger.error(f"Google credentials file not found: {creds_path}")
                raise FileNotFoundError(f"Google credentials file not found: {creds_path}")
            
            # Set up scopes
            scopes = ['https://www.googleapis.com/auth/drive']
            
            # Initialize credentials
            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
            
            # Initialize Google Drive service
            self.drive_service = build('drive', 'v3', credentials=creds)
            
            # Create folder structure
            await self._initialize_folders()
            
            self.initialized = True
            logger.info("✅ Google Drive storage initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive storage: {str(e)}")
            raise
    
    async def _run_sync(self, func, *args, **kwargs):
        """Run synchronous function in thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args, **kwargs)
    
    async def _initialize_folders(self):
        """Create and organize folder structure in Google Drive - FIXED VERSION"""
        try:
            logger.info("📁 Initializing Google Drive folders...")
            
            # Determine where to create folders
            if self.parent_folder_id:
                logger.info(f"📂 Using specified parent folder: {self.parent_folder_id}")
                
                # Verify parent folder exists and we have access
                try:
                    parent_info = await self._run_sync(
                        self.drive_service.files().get,
                        fileId=self.parent_folder_id,
                        fields='id,name,mimeType'
                    )
                    parent_result = parent_info.execute()
                    logger.info(f"✅ Parent folder verified: {parent_result['name']}")
                    
                    # Use the specified parent folder as root
                    root_folder_id = self.parent_folder_id
                    self.folder_ids['root'] = root_folder_id
                    
                except Exception as e:
                    logger.error(f"❌ Cannot access parent folder {self.parent_folder_id}: {e}")
                    raise
            else:
                logger.info("📂 No parent folder specified, creating in service account root")
                # Create or find root folder in service account's drive
                root_folder_id = await self._create_or_find_folder(self.root_folder_name)
                self.folder_ids['root'] = root_folder_id
            
            # Create subfolders within the root folder
            for folder_key, folder_name in self.folder_structure.items():
                folder_id = await self._create_or_find_folder(folder_name, root_folder_id)
                self.folder_ids[folder_key] = folder_id
                logger.info(f"✅ Initialized folder: {folder_name} (ID: {folder_id})")
            
            logger.info(f"📊 Total folders created/found: {len(self.folder_ids)}")
            logger.info(f"📋 Folder IDs: {self.folder_ids}")
            
        except Exception as e:
            logger.error(f"Error initializing folders: {str(e)}")
            raise
    
    async def _create_or_find_folder(self, folder_name: str, parent_id: str = None) -> str:
        """Create folder if it doesn't exist, return folder ID - FIXED VERSION"""
        try:
            # Search for existing folder with proper parent constraint
            if parent_id:
                query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
            else:
                query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            def search_folder():
                results = self.drive_service.files().list(q=query).execute()
                return results.get('files', [])
            
            existing_folders = await self._run_sync(search_folder)
            
            if existing_folders:
                folder_id = existing_folders[0]['id']
                logger.info(f"📁 Found existing folder: {folder_name} (ID: {folder_id})")
                return folder_id
            
            # Create new folder with explicit parent
            def create_folder():
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                # CRITICAL FIX: Always specify parent if provided
                if parent_id:
                    folder_metadata['parents'] = [parent_id]
                    logger.info(f"📁 Creating folder '{folder_name}' in parent '{parent_id}'")
                else:
                    logger.info(f"📁 Creating folder '{folder_name}' in root")
                
                folder = self.drive_service.files().create(body=folder_metadata).execute()
                return folder.get('id')
            
            folder_id = await self._run_sync(create_folder)
            logger.info(f"✅ Created new folder: {folder_name} (ID: {folder_id})")
            
            # Verify folder was created in correct location
            if parent_id:
                def verify_folder():
                    folder_info = self.drive_service.files().get(
                        fileId=folder_id,
                        fields='id,name,parents'
                    ).execute()
                    return folder_info
                
                folder_info = await self._run_sync(verify_folder)
                actual_parents = folder_info.get('parents', [])
                if parent_id not in actual_parents:
                    logger.warning(f"⚠️ Folder created but not in expected parent. Expected: {parent_id}, Actual: {actual_parents}")
                else:
                    logger.info(f"✅ Folder verified in correct parent: {parent_id}")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"Error creating/finding folder {folder_name}: {str(e)}")
            raise
    
    async def close(self):
        """Close connections and cleanup"""
        if self.executor:
            self.executor.shutdown(wait=True)
        logger.info("Google Drive storage connections closed")
    
    async def store_document(self, file_content: bytes, filename: str, 
                           document_type: str = 'documents', 
                           metadata: Dict[str, Any] = None) -> Optional[str]:
        """Store document in Google Drive"""
        if not self.initialized:
            logger.warning("Google Drive not initialized, cannot store document")
            return None
            
        try:
            folder_id = self.folder_ids.get(document_type, self.folder_ids.get('documents'))
            if not folder_id:
                logger.error(f"No folder ID found for document type: {document_type}")
                return None
            
            logger.info(f"📄 Storing document '{filename}' in folder '{document_type}' (ID: {folder_id})")
            
            # Prepare file metadata
            file_metadata = {
                'name': filename,
                'parents': [folder_id]  # Explicit parent
            }
            
            # Add custom metadata if provided
            if metadata:
                # Convert metadata to description
                file_metadata['description'] = json.dumps(metadata)
            
            # Create media upload
            media_body = MediaIoBaseUpload(
                io.BytesIO(file_content),
                mimetype='application/octet-stream',
                resumable=True
            )
            
            def upload_file():
                file = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media_body,
                    fields='id,name,webViewLink,parents'
                ).execute()
                return file
            
            uploaded_file = await self._run_sync(upload_file)
            
            logger.info(f"✅ Uploaded document: {filename} (ID: {uploaded_file['id']})")
            logger.info(f"🔗 File link: {uploaded_file.get('webViewLink', 'No link')}")
            
            # Verify file location
            actual_parents = uploaded_file.get('parents', [])
            if folder_id not in actual_parents:
                logger.warning(f"⚠️ File uploaded but not in expected folder. Expected: {folder_id}, Actual: {actual_parents}")
            
            return uploaded_file['id']
            
        except Exception as e:
            logger.error(f"Error storing document: {str(e)}")
            return None
    
    async def store_verification_report(self, verification_data: Dict[str, Any], 
                                      verification_type: str, 
                                      record_id: str) -> Optional[str]:
        """Store verification report as JSON file"""
        if not self.initialized:
            return None
            
        try:
            # Prepare report data
            report = {
                'record_id': record_id,
                'verification_type': verification_type,
                'timestamp': datetime.utcnow().isoformat(),
                'data': verification_data
            }
            
            # Create filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{verification_type}_{record_id}_{timestamp}.json"
            
            # Convert to JSON bytes
            json_content = json.dumps(report, indent=2, ensure_ascii=False)
            content_bytes = json_content.encode('utf-8')
            
            # Store in verification_reports folder
            file_id = await self.store_document(
                content_bytes, 
                filename, 
                'verification_reports',
                {
                    'type': 'verification_report',
                    'verification_type': verification_type,
                    'record_id': record_id
                }
            )
            
            return file_id
            
        except Exception as e:
            logger.error(f"Error storing verification report: {str(e)}")
            return None
    
    async def store_ocr_result(self, ocr_data: Dict[str, Any], 
                              original_filename: str, 
                              record_id: str) -> Optional[str]:
        """Store OCR processing result"""
        if not self.initialized:
            return None
            
        try:
            # Prepare OCR result data
            ocr_result = {
                'record_id': record_id,
                'original_filename': original_filename,
                'timestamp': datetime.utcnow().isoformat(),
                'ocr_data': ocr_data
            }
            
            # Create filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"ocr_{record_id}_{timestamp}.json"
            
            # Convert to JSON bytes
            json_content = json.dumps(ocr_result, indent=2, ensure_ascii=False)
            content_bytes = json_content.encode('utf-8')
            
            # Store in ocr_results folder
            file_id = await self.store_document(
                content_bytes, 
                filename, 
                'ocr_results',
                {
                    'type': 'ocr_result',
                    'original_filename': original_filename,
                    'record_id': record_id
                }
            )
            
            return file_id
            
        except Exception as e:
            logger.error(f"Error storing OCR result: {str(e)}")
            return None
    
    async def store_face_image(self, image_content: bytes, 
                              image_type: str, 
                              record_id: str) -> Optional[str]:
        """Store face verification images"""
        if not self.initialized:
            return None
            
        try:
            # Create filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{image_type}_{record_id}_{timestamp}.jpg"
            
            # Store in face_images folder
            file_id = await self.store_document(
                image_content, 
                filename, 
                'face_images',
                {
                    'type': 'face_image',
                    'image_type': image_type,
                    'record_id': record_id
                }
            )
            
            return file_id
            
        except Exception as e:
            logger.error(f"Error storing face image: {str(e)}")
            return None
    
    async def store_raw_api_response(self, api_response: Dict[str, Any], 
                                   api_endpoint: str, 
                                   record_id: str) -> Optional[str]:
        """Store raw API response for audit purposes"""
        if not self.initialized:
            return None
            
        try:
            # Prepare raw response data
            raw_response = {
                'record_id': record_id,
                'api_endpoint': api_endpoint,
                'timestamp': datetime.utcnow().isoformat(),
                'response': api_response
            }
            
            # Create filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            endpoint_name = api_endpoint.strip('/').split('/')[-1]
            filename = f"raw_{endpoint_name}_{record_id}_{timestamp}.json"
            
            # Convert to JSON bytes
            json_content = json.dumps(raw_response, indent=2, ensure_ascii=False)
            content_bytes = json_content.encode('utf-8')
            
            # Store in raw_responses folder
            file_id = await self.store_document(
                content_bytes, 
                filename, 
                'raw_responses',
                {
                    'type': 'raw_api_response',
                    'api_endpoint': api_endpoint,
                    'record_id': record_id
                }
            )
            
            return file_id
            
        except Exception as e:
            logger.error(f"Error storing raw API response: {str(e)}")
            return None
    
    async def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file information from Google Drive"""
        if not self.initialized:
            return None
            
        try:
            def get_file():
                file = self.drive_service.files().get(
                    fileId=file_id,
                    fields='id,name,size,createdTime,modifiedTime,webViewLink,description'
                ).execute()
                return file
            
            file_info = await self._run_sync(get_file)
            return file_info
            
        except Exception as e:
            logger.error(f"Error getting file info: {str(e)}")
            return None
    
    async def list_files_by_record(self, record_id: str) -> List[Dict[str, Any]]:
        """List all files associated with a record ID"""
        if not self.initialized:
            return []
            
        try:
            # Search for files containing the record ID in description or name
            query = f"(name contains '{record_id}' or description contains '{record_id}') and trashed=false"
            
            def search_files():
                results = self.drive_service.files().list(
                    q=query,
                    fields='files(id,name,size,createdTime,webViewLink,description)'
                ).execute()
                return results.get('files', [])
            
            files = await self._run_sync(search_files)
            return files
            
        except Exception as e:
            logger.error(f"Error listing files by record: {str(e)}")
            return []
    
    async def delete_file(self, file_id: str) -> bool:
        """Delete file from Google Drive"""
        if not self.initialized:
            return False
            
        try:
            def delete():
                self.drive_service.files().delete(fileId=file_id).execute()
                return True
            
            success = await self._run_sync(delete)
            logger.info(f"Deleted file: {file_id}")
            return success
            
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            return False
    
    async def get_storage_statistics(self) -> Dict[str, Any]:
        """Get storage statistics"""
        if not self.initialized:
            return {}
            
        try:
            stats = {
                'folders': {},
                'total_files': 0,
                'total_size': 0,
                'parent_folder_id': self.parent_folder_id,
                'folder_ids': self.folder_ids
            }
            
            # Get statistics for each folder
            for folder_key, folder_id in self.folder_ids.items():
                if folder_key == 'root':
                    continue
                    
                query = f"'{folder_id}' in parents and trashed=false"
                
                def get_folder_stats():
                    results = self.drive_service.files().list(
                        q=query,
                        fields='files(id,name,size)'
                    ).execute()
                    return results.get('files', [])
                
                files = await self._run_sync(get_folder_stats)
                
                folder_size = sum(int(f.get('size', 0)) for f in files if f.get('size'))
                stats['folders'][folder_key] = {
                    'file_count': len(files),
                    'total_size': folder_size,
                    'folder_id': folder_id
                }
                stats['total_files'] += len(files)
                stats['total_size'] += folder_size
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting storage statistics: {str(e)}")
            return {}

# Global instance
google_drive_storage = GoogleDriveKYCStorage()