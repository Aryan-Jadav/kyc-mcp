# KYC Verification MCP Server

A Model Context Protocol (MCP) server that provides comprehensive KYC (Know Your Customer) verification services using the SurePass API. This server implements various document verification, OCR, face verification, and other KYC-related services.

## Features

### Document Verification
- **TAN Verification**: Verify Tax Deduction Account Numbers
- **Voter ID Verification**: Validate voter identification cards
- **Driving License Verification**: Verify driving license details
- **Passport Verification**: Validate passport information
- **Aadhaar Services**: OTP generation and validation
- **PAN Card Verification**: Verify PAN card details

### Bank Verification
- **Bank Account Verification**: Validate bank account details with IFSC
- **UPI Verification**: Verify UPI IDs
- **Mobile to Bank Mapping**: Find bank details from mobile numbers

### Corporate Verification
- **GSTIN Verification**: Validate GST identification numbers
- **Company CIN Verification**: Verify Corporate Identification Numbers
- **Director Information**: Get director phone numbers and details
- **Udyog Aadhaar**: Verify MSME registration details

### OCR Services
- **Document OCR**: Extract data from various document images
  - PAN cards
  - Passports
  - Driving licenses
  - Voter IDs
  - GST certificates
  - ITR documents
  - Cheques

### Face Verification
- **Face Matching**: Compare faces between selfie and ID documents
- **Liveness Detection**: Verify if a face image is from a live person
- **Face Extraction**: Extract face from images
- **Background Removal**: Remove background from face images

### Utility Services
- **Electricity Bill Verification**: Validate utility bills
- **Telecom Verification**: Verify mobile numbers
- **Email Verification**: Validate email addresses
- **Name Matching**: Compare and match names

### Legal & Compliance
- **Court Case Search**: Search for legal cases
- **PEP Checks**: Politically Exposed Person verification
- **CKYC Search**: Central KYC repository searches

### Financial Services
- **ITR Compliance**: Check income tax return compliance
- **TDS Verification**: Verify tax deduction at source
- **Credit Reports**: Generate credit reports
- **ESIC Details**: Employee State Insurance Corporation verification

### Vehicle Services
- **RC Verification**: Verify vehicle registration certificates
- **RC to Mobile**: Map registration numbers to mobile numbers

### Universal Database Storage (NEW! 🚀)
- **Universal Data Capture**: ALL KYC verification results automatically stored (50+ API endpoints)
- **Person-Centric Architecture**: Intelligent linking of records across different verification types
- **Smart Cross-Linking**: Links PAN, Aadhaar, Bank, GSTIN, Voter ID, and other verifications to same person
- **Complete Person Profiles**: 360° view combining data from multiple verification sources
- **Universal Search**: Find person by any identifier (PAN, name, phone, email) across all verification types
- **Data Quality Enhancement**: Cross-validation and confidence scoring from multiple sources
- **Comprehensive Audit Trail**: Complete history of all verification activities
- **Privacy Compliant**: Configurable data retention and anonymization features

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd kyc-verification-mcp
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your SurePass API credentials (see Configuration section)

## Configuration

### API Authentication
Most KYC services require authentication. You'll need:
- **Authorization Token**: Bearer token for API access
- **Customer ID**: Your SurePass customer identifier

### Environment Setup
Create a `.env` file or set environment variables:
```bash
# API Configuration
SUREPASS_API_TOKEN=your_bearer_token_here
SUREPASS_CUSTOMER_ID=your_customer_id_here

# Database Configuration (Optional)
KYC_DATABASE_ENABLED=true
KYC_DATABASE_URL=sqlite+aiosqlite:///kyc_data.db
KYC_DATA_RETENTION_DAYS=365
KYC_MAX_SEARCH_RESULTS=100
```

## Usage

### Testing the Server
First, run the comprehensive test to ensure everything is working:
```bash
python test_mcp.py
```

### Running the Server
```bash
python kyc_mcp_server.py
```

### Claude Desktop Integration
To connect this MCP server to Claude Desktop:

1. **Locate your Claude Desktop configuration file:**
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. **Add the MCP server configuration:**
   ```json
   {
     "mcpServers": {
       "kyc-verification": {
         "command": "python",
         "args": ["C:\\full\\path\\to\\your\\kyc_mcp_server.py"],
         "env": {
           "SUREPASS_API_TOKEN": "your_actual_token_here",
           "SUREPASS_CUSTOMER_ID": "your_actual_customer_id_here"
         }
       }
     }
   }
   ```

3. **Replace the placeholders:**
   - Replace `C:\\full\\path\\to\\your\\kyc_mcp_server.py` with the actual full path to your server file
   - Replace `your_actual_token_here` with your SurePass API token
   - Replace `your_actual_customer_id_here` with your SurePass customer ID

4. **Restart Claude Desktop**

The KYC verification tools will then be available in Claude Desktop!

### Available Tools

#### Document Verification Tools
- `verify_tan` - Verify TAN number
- `verify_voter_id` - Verify Voter ID
- `verify_driving_license` - Verify driving license
- `verify_passport` - Verify passport details
- `generate_aadhaar_otp` - Generate OTP for Aadhaar
- `validate_aadhaar` - Validate Aadhaar number

#### Bank Verification Tools
- `verify_bank_account` - Verify bank account details
- `verify_upi` - Verify UPI ID

#### Corporate Verification Tools
- `verify_gstin` - Verify GSTIN details
- `verify_company_cin` - Verify company CIN

#### OCR Tools
- `ocr_pan_card` - Extract PAN card data
- `ocr_passport` - Extract passport data

#### Face Verification Tools
- `face_match` - Match faces between images
- `face_liveness` - Check face liveness

#### Universal Database Search Tools (NEW! 🚀)
- `search_person_by_pan` - Find complete person profile by PAN across ALL verification types
- `search_person_by_name` - Search persons by name across ALL verification sources
- `search_person_by_phone` - Find all persons associated with phone number
- `get_person_complete_profile_tool` - Get comprehensive person profile with all verifications
- `search_pan_database` - Legacy PAN-specific search (maintained for compatibility)
- `search_name_database` - Legacy name search in PAN records
- `get_database_statistics` - Database statistics and health information

### Example Usage

#### Verify TAN Number
```json
{
  "tool": "verify_tan",
  "arguments": {
    "id_number": "RTKT06731E"
  }
}
```

#### Verify Bank Account
```json
{
  "tool": "verify_bank_account",
  "arguments": {
    "id_number": "12121245457878",
    "ifsc": "CNRB0000000",
    "ifsc_details": true,
    "authorization_token": "Bearer YOUR_TOKEN"
  }
}
```

#### OCR PAN Card
```json
{
  "tool": "ocr_pan_card",
  "arguments": {
    "file_path": "/path/to/pan_card_image.jpg"
  }
}
```

#### Face Matching
```json
{
  "tool": "face_match",
  "arguments": {
    "selfie_path": "/path/to/selfie.jpg",
    "id_card_path": "/path/to/id_card.jpg"
  }
}
```

#### Universal Database Search Examples
```json
{
  "tool": "search_person_by_pan",
  "arguments": {
    "pan_number": "ABCDE1234F"
  }
}
```
*Returns complete person profile with ALL verifications (PAN, Bank, GSTIN, etc.)*

```json
{
  "tool": "search_person_by_name",
  "arguments": {
    "name": "John Doe",
    "exact_match": false
  }
}
```
*Returns all persons matching name with their complete verification history*

```json
{
  "tool": "get_person_complete_profile_tool",
  "arguments": {
    "person_id": 123
  }
}
```
*Returns comprehensive profile including all verifications, documents, and contacts*

## API Reference

The server implements the SurePass KYC API endpoints. For detailed API documentation, refer to the SurePass API documentation.

### Base URL
```
https://kyc-api.surepass.io/api/v1
```

### Authentication
Most endpoints require:
- `Authorization: Bearer TOKEN` header
- `X-Customer-Id: CUSTOMER_ID` header (for some endpoints)

## Error Handling

The server provides comprehensive error handling:
- API errors are returned with status codes and messages
- File not found errors for OCR operations
- Network connectivity issues
- Invalid parameter validation

## File Structure

```
kyc-verification-mcp/
├── kyc_mcp_server.py          # Main MCP server with universal database
├── kyc_client.py              # HTTP client for API calls
├── models.py                  # Data models and schemas
├── config.py                  # Configuration and endpoints
├── database.py                # Legacy PAN database management
├── universal_database.py      # Universal database manager
├── database_models.py         # Universal SQLAlchemy models
├── config_db.py               # Database configuration
├── requirements.txt           # Python dependencies
├── api name and curls.txt     # API reference
├── README.md                  # This file
├── universal_kyc_data.db      # Universal SQLite database (auto-created)
└── kyc_data.db               # Legacy SQLite database (auto-created)
```

## 📍 Data Storage & Access

### Where Data is Stored
- **`universal_kyc_data.db`** - SQLite database storing ALL verification types
- **`kyc_data.db`** - Legacy database for PAN-only verifications
- Files are auto-created in your project directory when first verification runs

### How to Access Data

#### 1. Using MCP Search Tools (Recommended)
```json
// Find person by PAN across ALL verification types
{"tool": "search_person_by_pan", "arguments": {"pan_number": "ABCDE1234F"}}

// Search by name across ALL verifications
{"tool": "search_person_by_name", "arguments": {"name": "John Doe"}}

// Search by phone number
{"tool": "search_person_by_phone", "arguments": {"phone_number": "9876543210"}}

// Get complete person profile
{"tool": "get_person_complete_profile_tool", "arguments": {"person_id": 123}}
```

#### 2. Direct SQLite Access
```bash
# Using SQLite command line
sqlite3 universal_kyc_data.db
.tables                    # View all tables
SELECT * FROM person_records;     # View all persons
SELECT * FROM verification_records;  # View all verifications
```

#### 3. Database Statistics
```json
{"tool": "get_database_statistics", "arguments": {}}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
1. Check the SurePass API documentation
2. Review the error messages and logs
3. Create an issue in this repository

## Disclaimer

This server is a wrapper around the SurePass KYC API. Ensure you comply with all applicable laws and regulations when using KYC verification services. The accuracy and reliability of verification results depend on the underlying SurePass API service.
