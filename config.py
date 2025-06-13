"""Configuration for KYC MCP Server"""

import os
from typing import Optional

# SurePass API Configuration
BASE_URL = os.getenv("SUREPASS_BASE_URL", "https://kyc-api.surepass.io/api/v1")

# Environment variables for authentication
SUREPASS_API_TOKEN: Optional[str] = os.getenv("SUREPASS_API_TOKEN")

# API Endpoints
ENDPOINTS = {
    # Document Verification
    "tan": "/tan/",
    "voter_id": "/voter-id/voter-id",
    "driving_license": "/driving-license/driving-license",
    "passport": "/passport/passport/passport-details",
    "aadhaar_generate_otp": "/aadhaar-v2/generate-otp",
    "aadhaar_validation": "/aadhaar-validation/aadhaar-validation",
    "pan_comprehensive": "/pan/pan-comprehensive",
    "pan": "/pan/pan",  # Basic PAN verification endpoint
    "pan_kra": "/pan/pan-kra",  # PAN-KRA verification endpoint
    "pan_adv": "/pan/pan-adv",  # Advanced PAN verification endpoint
    "pan_adv_v2": "/pan/pan-adv-v2",  # Advanced PAN verification v2 endpoint
    "pan_aadhaar_link": "/pan/pan-aadhaar-link-check",  # PAN-Aadhaar link verification endpoint
    "pan_to_uan": "/pan/pan-to-uan",
    "aadhaar_to_uan": "/income/epfo/aadhaar-to-uan",
    "aadhaar_pan_link": "/pan/aadhaar-pan-link-check",
    "pull_kra": "/pull-kra/pull-kra",
    "e_aadhaar": "/aadhaar/eaadhaar/generate-otp",
    "aadhaar_qr": "/aadhaar/upload/qr",
    
    # Bank Verification
    "bank_verification": "/bank-verification/",
    "upi_verification": "/bank-verification/upi-verification",
    "find_upi_id": "/bank-verification/find-upi-id",
    "upi_mobile_name": "/bank-verification/upi-mobile-to-name",
    "mobile_to_bank": "/mobile-to-bank-details/verification",
    
    # Corporate Verification
    "gstin": "/corporate/gstin",
    "gstin_advanced": "/corporate/gstin-advanced",
    "pan_udyam": "/corporate/pan-udyam-check",
    "gstin_by_pan": "/corporate/gstin-by-pan",
    "company_details": "/corporate/company-details",
    "name_to_cin": "/corporate/name-to-cin-list",
    "din": "/corporate/din",
    "udyog_aadhaar": "/corporate/udyog-aadhaar",
    "director_phone": "/corporate/director-phone",
    
    # OCR Services
    "ocr_pan": "/ocr/pan",
    "ocr_aadhaar": "/ocr/aadhaar",
    "ocr_passport": "/ocr/passport",
    "ocr_license": "/ocr/license",
    "ocr_voter": "/ocr/voter",
    "ocr_gst": "/ocr/gst",
    "ocr_itr": "/ocr/itr-v",
    "ocr_cheque": "/ocr/cheque",
    "ocr_document_detect": "/ocr/document-detect",
    
    # Utility Services
    "electricity_bill": "/utility/electricity/",
    "telecom_generate_otp": "/telecom/generate-otp",
    "telecom_verification": "/telecom/telecom-verification",
    
    # Financial Services
    "itr_compliance": "/itr/itr-compliance-check",
    "tds_check": "/tan/tds-check",
    "credit_report": "/credit-report-v2/fetch-report",
    "credit_report_pdf": "/credit-report-v2/fetch-pdf-report",
    "credit_report_commercial": "/credit-report-commercial/fetch-report",
    "esic_details": "/esic/esic-v2",
    
    # Legal Services
    "ckyc_search": "/ckyc/search",
    "ecourts_search": "/ecourts/search",
    "ecourts_cnr": "/ecourts/ecourt-cnr-search",
    "pep_match": "/pep/match",
    
    # Face Services
    "face_match": "/face/face-match",
    "face_liveness": "/face/face-liveness",
    "face_extract": "/face/face-extract",
    "face_background_remover": "/face/face-background-remover",
    
    # Vehicle Services
    "rc_full": "/rc/rc-full",
    "rc_to_mobile": "/rc/rc-to-mobile-number",
    
    # PAN Services
    "mobile_to_pan": "/pan/mobile-to-pan",
    
    # Utility Services
    "email_check": "/employment/email-check",
    "name_matching": "/utils/name-matching/",
    "prefill_report": "/prefill/prefill-report-v2",
    "lei_validation": "/lei-validation/",
}

# Default headers
DEFAULT_HEADERS = {
    "Content-Type": "application/json"
}

# File upload headers
MULTIPART_HEADERS = {
    # Content-Type will be set automatically for multipart/form-data
}
