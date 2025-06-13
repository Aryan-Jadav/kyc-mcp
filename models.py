"""Data models for KYC MCP Server"""

from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field

# Pydantic models for request validation
class KYCRequest(BaseModel):
    """Base KYC request model"""
    id_number: Optional[str] = None
    authorization_token: Optional[str] = None

class DocumentVerificationRequest(KYCRequest):
    """Document verification request"""
    dob: Optional[str] = None
    document_type: Optional[str] = None

class BankVerificationRequest(KYCRequest):
    """Bank verification request"""
    ifsc: Optional[str] = None
    ifsc_details: Optional[bool] = None
    upi_id: Optional[str] = None
    mobile_number: Optional[str] = None

class CorporateVerificationRequest(KYCRequest):
    """Corporate verification request"""
    company_name_search: Optional[str] = None
    pan_number: Optional[str] = None

class OCRRequest(BaseModel):
    """OCR request model"""
    file_path: str = Field(..., description="Path to the file to be processed")
    authorization_token: Optional[str] = None
    use_pdf: Optional[bool] = None

class FaceVerificationRequest(BaseModel):
    """Face verification request"""
    selfie_path: Optional[str] = None
    id_card_path: Optional[str] = None
    image_path: Optional[str] = None
    authorization_token: Optional[str] = None

class UtilityRequest(KYCRequest):
    """Utility verification request"""
    operator_code: Optional[str] = None
    phone_number: Optional[str] = None

class FinancialRequest(KYCRequest):
    """Financial verification request"""
    pan_number: Optional[str] = None
    tan_number: Optional[str] = None
    year: Optional[str] = None
    quarter: Optional[str] = None
    type_of_return: Optional[str] = None
    aadhaar_number: Optional[str] = None
    name: Optional[str] = None
    mobile: Optional[str] = None
    consent: Optional[str] = None
    id_type: Optional[str] = None

class LegalRequest(BaseModel):
    """Legal verification request"""
    name: Optional[str] = None
    father_name: Optional[str] = None
    address: Optional[str] = None
    case_type: Optional[str] = None
    state_name: Optional[str] = None
    search_type: Optional[str] = None
    category: Optional[str] = None
    cnr_number: Optional[str] = None
    dob: Optional[str] = None
    nationality: Optional[str] = None
    authorization_token: Optional[str] = None
    id_number: Optional[str] = None
    document_type: Optional[str] = None

class VehicleRequest(KYCRequest):
    """Vehicle verification request"""
    rc_number: Optional[str] = None

class UtilityServiceRequest(BaseModel):
    """Utility service request"""
    email: Optional[str] = None
    name_1: Optional[str] = None
    name_2: Optional[str] = None
    name_type: Optional[str] = None
    mobile: Optional[str] = None
    authorization_token: Optional[str] = None

class PANAddress(BaseModel):
    """PAN address details matching SurePass API structure"""
    line_1: Optional[str] = Field(None, description="House/building number and name")
    line_2: Optional[str] = Field(None, description="Colony/society name")
    street_name: Optional[str] = Field(None, description="Street or road name")
    zip: Optional[Union[str, int]] = Field(None, description="Postal/PIN code")
    city: Optional[str] = Field(None, description="City name")
    state: Optional[str] = Field(None, description="State name")
    country: Optional[str] = Field(None, description="Country name")
    full: Optional[str] = Field(None, description="Complete address as a single string")

    @classmethod
    def model_validate(cls, value):
        # Handle different types of input
        if isinstance(value, dict):
            value = dict(value)  # Create a copy to modify
            # Handle zip field (could be string, int, or empty)
            if 'zip' in value:
                if value['zip'] == '' or value['zip'] is None:
                    value['zip'] = None
                elif isinstance(value['zip'], (str, int)):
                    # Ensure zip is a string for consistency
                    value['zip'] = str(value['zip']).strip()
            
            # Handle other fields
            for key in ['line_1', 'line_2', 'street_name', 'city', 'state', 'country', 'full']:
                if key in value:
                    if value[key] == '' or value[key] is None:
                        value[key] = None
                    elif isinstance(value[key], str):
                        value[key] = value[key].strip()
                    elif isinstance(value[key], (int, float)):
                        value[key] = str(value[key]).strip()
        
        return super().model_validate(value)

class PANData(BaseModel):
    """PAN comprehensive data"""
    client_id: Optional[str] = None
    pan_number: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name_split: Optional[List[str]] = None
    father_name: Optional[str] = None
    masked_aadhaar: Optional[str] = None
    address: Optional[PANAddress] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    input_dob: Optional[str] = None
    aadhaar_linked: Optional[bool] = None
    dob_verified: Optional[bool] = None
    dob_check: Optional[bool] = None
    category: Optional[str] = None
    is_minor: Optional[bool] = None
    less_info: Optional[bool] = None
    pdf_bytes: Optional[str] = None
    extra_payload: Optional[Dict[str, Any]] = None

    @classmethod
    def model_validate(cls, value):
        # Convert empty string values to None for validation
        if isinstance(value, dict):
            value = dict(value)  # Create a copy to modify
            for key in ['client_id', 'pan_number', 'full_name', 'masked_aadhaar', 
                       'email', 'phone_number', 'gender', 'dob', 'input_dob',
                       'category']:
                if key in value and value[key] == '':
                    value[key] = None
            # Handle empty lists
            if 'full_name_split' in value and not value['full_name_split']:
                value['full_name_split'] = None
        return super().model_validate(value)

class KYCResponse(BaseModel):
    """Base KYC response model"""
    success: bool
    data: Optional[Union[Dict[str, Any], PANData]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    message: Optional[str] = None
    message_code: Optional[str] = None

class APIError(Exception):
    """Custom API error"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)
