# KYC MCP Server with Server-Sent Events (SSE) Support

## 🌟 Overview

Your KYC server now supports **both** REST API and **Model Context Protocol (MCP) with Server-Sent Events (SSE)**. This dual capability allows you to:

1. **REST API**: Traditional HTTP requests for standard integrations
2. **MCP SSE**: Real-time streaming communication for AI agents and n8n MCP Client nodes

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   n8n Workflow │    │  KYC HTTP Server│    │  SurePass API   │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │                 │
│ │HTTP Request │ │───▶│ │ REST API    │ │───▶│                 │
│ └─────────────┘ │    │ └─────────────┘ │    │                 │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │                 │
│ │MCP Client   │ │◄──▶│ │ SSE/MCP     │ │───▶│                 │
│ │Node         │ │    │ │ Server      │ │    │                 │
│ └─────────────┘ │    │ └─────────────┘ │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🔧 Implementation Details

### Files Added/Modified

1. **`sse_transport.py`** - SSE transport layer using Starlette
2. **`kyc_mcp_sse.py`** - MCP server with KYC tools and resources
3. **`kyc_http_server.py`** - Updated to include SSE support
4. **`requirements.txt`** - Added Starlette dependency

### MCP Tools Available

- **`verify_pan_basic`** - Basic PAN verification
- **`verify_pan_comprehensive`** - Comprehensive PAN verification with address
- **`verify_pan_kra`** - PAN verification using KRA database

### MCP Resources Available

- **`kyc://api/status`** - API connectivity and status information
- **`kyc://api/endpoints`** - Available endpoints and services

## 🚀 Usage

### REST API (Traditional)
```bash
curl -X POST http://139.59.70.153:8000/api/verify/pan/comprehensive \
  -H "Content-Type: application/json" \
  -d '{"id_number": "ABCDE1234F"}'
```

### MCP SSE (New)
```bash
# Connect to SSE endpoint
curl http://139.59.70.153:8000/mcp/sse

# Get MCP information
curl http://139.59.70.153:8000/mcp/info
```

## 🔗 n8n Integration

### Method 1: HTTP Request Node (Existing)
```json
{
  "url": "http://139.59.70.153:8000/api/verify/pan/comprehensive",
  "method": "POST",
  "body": {"id_number": "ABCDE1234F"}
}
```

### Method 2: MCP Client Node (New)
```json
{
  "serverUrl": "http://139.59.70.153:8000/mcp/sse",
  "tool": "verify_pan_comprehensive",
  "parameters": {"id_number": "ABCDE1234F"}
}
```

## 📋 Endpoints Reference

### REST API Endpoints
- `GET /health` - Health check
- `GET /api/status` - API status
- `POST /api/verify/pan/basic` - Basic PAN verification
- `POST /api/verify/pan/comprehensive` - Comprehensive PAN verification
- `POST /api/verify/pan/kra` - KRA PAN verification

### MCP SSE Endpoints
- `GET /mcp/info` - MCP server information
- `GET /mcp/sse` - SSE connection endpoint
- `GET /mcp/sse/info` - SSE transport information
- `POST /mcp/messages/` - Message handling

## 🧪 Testing

### Test All Endpoints
```bash
python test-api.py
```

### Test SSE Connection
```bash
curl -N http://139.59.70.153:8000/mcp/sse
```

Expected SSE output:
```
event: endpoint
data: /messages/?session_id=abc123

: ping - 2025-01-17 10:30:00.000000+00:00
```

## 🔍 Troubleshooting

### SSE Connection Issues
1. **Check endpoint**: `curl http://139.59.70.153:8000/mcp/info`
2. **Verify SSE format**: Look for `event:` and `data:` lines
3. **Check logs**: `docker-compose logs kyc-server`

### MCP Client Connection Issues
1. **Verify URL**: Use `http://139.59.70.153:8000/mcp/sse`
2. **Check n8n MCP Client node configuration**
3. **Test SSE endpoint manually first**

### Common Errors
- **Connection refused**: Server not running or wrong port
- **404 Not Found**: Wrong endpoint URL
- **SSE format error**: Check Starlette configuration

## 🎯 Benefits of MCP SSE

1. **Real-time Communication**: Streaming responses instead of polling
2. **Better Integration**: Native support for AI agents and MCP clients
3. **Persistent Connections**: Reduced overhead for multiple requests
4. **Tool Discovery**: Automatic discovery of available KYC tools
5. **Resource Access**: Direct access to API status and endpoints

## 🔐 Security Considerations

- SSE endpoints use the same authentication as REST API
- CORS is configured for n8n integration
- API tokens are validated for all requests
- Consider network-level security for production

## 📈 Performance

- SSE connections are persistent, reducing connection overhead
- Both REST and SSE use the same underlying KYC client
- Retry logic and error handling are consistent across both interfaces
- Resource usage is optimized for concurrent connections

Your KYC server now provides the best of both worlds - traditional REST API compatibility and modern MCP SSE capabilities!
