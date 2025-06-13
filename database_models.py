"""Unified Database Model for KYC MCP Server"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, JSON,
    Index, create_engine
)
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class PANRecord(Base):
    """Legacy table for PAN verification data"""
    __tablename__ = "pan_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pan_number = Column(String(10), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True, index=True)
    first_name = Column(String(100), nullable=True)
    middle_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    father_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone_number = Column(String(20), nullable=True)
    gender = Column(String(10), nullable=True)
    dob = Column(String(20), nullable=True)
    category = Column(String(50), nullable=True)
    is_minor = Column(Boolean, nullable=True)
    address_data = Column(JSON, nullable=True)
    masked_aadhaar = Column(String(12), nullable=True)
    aadhaar_linked = Column(Boolean, nullable=True)
    dob_verified = Column(Boolean, nullable=True)
    less_info = Column(Boolean, nullable=True)
    raw_api_data = Column(JSON, nullable=True)
    api_endpoint = Column(String(100), nullable=True)
    verification_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_verified_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary"""
        return {
            'id': self.id,
            'pan_number': self.pan_number,
            'full_name': self.full_name,
            'first_name': self.first_name,
            'middle_name': self.middle_name,
            'last_name': self.last_name,
            'father_name': self.father_name,
            'email': self.email,
            'phone_number': self.phone_number,
            'gender': self.gender,
            'dob': self.dob,
            'category': self.category,
            'is_minor': self.is_minor,
            'address_data': self.address_data,
            'masked_aadhaar': self.masked_aadhaar,
            'aadhaar_linked': self.aadhaar_linked,
            'dob_verified': self.dob_verified,
            'less_info': self.less_info,
            'raw_api_data': self.raw_api_data,
            'api_endpoint': self.api_endpoint,
            'verification_count': self.verification_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None
        }

class DataAuditLog(Base):
    """Audit log for tracking data changes"""
    __tablename__ = "data_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pan_record_id = Column(Integer, nullable=False)
    action = Column(String(10), nullable=False)  # INSERT, UPDATE, DELETE
    changed_fields = Column(JSON, nullable=True)  # List of changed field names
    old_values = Column(JSON, nullable=True)  # Previous values of changed fields
    new_values = Column(JSON, nullable=True)  # New values of changed fields
    timestamp = Column(DateTime, default=datetime.utcnow)


class UniversalRecord(Base):
    """Universal record for all KYC verification data"""
    __tablename__ = "universal_records"

    # Core identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Document numbers (various ID types)
    pan_number = Column(String(10), nullable=True, index=True)
    aadhaar_number = Column(String(12), nullable=True, index=True)
    voter_id = Column(String(20), nullable=True, index=True)
    driving_license = Column(String(20), nullable=True, index=True)
    passport_number = Column(String(20), nullable=True, index=True)
    gstin = Column(String(15), nullable=True, index=True)
    tan_number = Column(String(10), nullable=True, index=True)
    bank_account = Column(String(20), nullable=True, index=True)
    
    # Personal information
    full_name = Column(String(255), nullable=True, index=True)
    first_name = Column(String(100), nullable=True)
    middle_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    father_name = Column(String(255), nullable=True)
    gender = Column(String(10), nullable=True)
    dob = Column(String(20), nullable=True)
    category = Column(String(50), nullable=True)
    is_minor = Column(Boolean, nullable=True)
    
    # Contact information
    phone_number = Column(String(20), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    
    # Address information
    address_data = Column(JSON, nullable=True)
    
    # Business information
    company_name = Column(String(255), nullable=True, index=True)
    business_type = Column(String(50), nullable=True)
    incorporation_date = Column(String(20), nullable=True)
    
    # Bank information
    ifsc_code = Column(String(11), nullable=True)
    bank_name = Column(String(100), nullable=True)
    branch_name = Column(String(100), nullable=True)
    upi_id = Column(String(50), nullable=True)
    
    # Verification status
    aadhaar_linked = Column(Boolean, nullable=True)
    dob_verified = Column(Boolean, nullable=True)
    verification_status = Column(String(20), nullable=True)
    last_verification_type = Column(String(50), nullable=True)
    verification_source = Column(String(100), nullable=True)
    
    # Metadata
    verification_count = Column(Integer, default=1)
    confidence_score = Column(Integer, nullable=True)
    verification_history = Column(JSON, nullable=True)  # List of past verifications
    raw_responses = Column(JSON, nullable=True)  # Store raw API responses
    extra_data = Column(JSON, nullable=True)  # For any additional data
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_verified_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Search optimization indexes
    __table_args__ = (
        Index('idx_document_numbers', 'pan_number', 'aadhaar_number', 'voter_id', 'driving_license', 'passport_number'),
        Index('idx_contact_info', 'phone_number', 'email'),
        Index('idx_name_search', 'full_name', 'first_name', 'last_name'),
        Index('idx_business', 'company_name', 'gstin', 'tan_number'),
        Index('idx_verification', 'verification_status', 'last_verification_type'),
        Index('idx_timestamps', 'created_at', 'updated_at', 'last_verified_at')
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary"""
        return {
            'id': self.id,
            # Document numbers
            'pan_number': self.pan_number,
            'aadhaar_number': self.aadhaar_number,
            'voter_id': self.voter_id,
            'driving_license': self.driving_license,
            'passport_number': self.passport_number,
            'gstin': self.gstin,
            'tan_number': self.tan_number,
            'bank_account': self.bank_account,
            
            # Personal information
            'full_name': self.full_name,
            'first_name': self.first_name,
            'middle_name': self.middle_name,
            'last_name': self.last_name,
            'father_name': self.father_name,
            'gender': self.gender,
            'dob': self.dob,
            'category': self.category,
            'is_minor': self.is_minor,
            
            # Contact information
            'phone_number': self.phone_number,
            'email': self.email,
            'address_data': self.address_data,
            
            # Business information
            'company_name': self.company_name,
            'business_type': self.business_type,
            'incorporation_date': self.incorporation_date,
            
            # Bank information
            'ifsc_code': self.ifsc_code,
            'bank_name': self.bank_name,
            'branch_name': self.branch_name,
            'upi_id': self.upi_id,
            
            # Verification status
            'aadhaar_linked': self.aadhaar_linked,
            'dob_verified': self.dob_verified,
            'verification_status': self.verification_status,
            'last_verification_type': self.last_verification_type,
            'verification_source': self.verification_source,
            
            # Metadata
            'verification_count': self.verification_count,
            'confidence_score': self.confidence_score,
            'verification_history': self.verification_history,
            'raw_responses': self.raw_responses,
            'extra_data': self.extra_data,
            
            # Timestamps
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
        }

class SearchHistory(Base):
    """Table for storing search analytics"""
    __tablename__ = "search_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    search_type = Column(String(50), nullable=False)  # What field was searched
    search_query = Column(String(255), nullable=False)  # The search term
    results_count = Column(Integer, default=0)
    search_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_search_analytics', 'search_type', 'search_timestamp'),
    )
