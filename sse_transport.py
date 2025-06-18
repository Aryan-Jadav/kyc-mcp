"""
SSE Transport Layer for KYC MCP Server
This module provides Server-Sent Events support for the KYC MCP server
to enable integration with n8n MCP client nodes.
"""

import logging
import json
import asyncio
from datetime import datetime
from sse_starlette import EventSourceResponse
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

logger = logging.getLogger("kyc-sse-transport")

def create_sse_server(mcp_server) -> Starlette:
    """
    Create a Starlette app that handles SSE connections and message handling
    for the KYC MCP server.

    Args:
        mcp_server: FastMCP instance with KYC tools and resources

    Returns:
        Starlette application configured for SSE transport
    """

    async def handle_sse(request):
        """Handle SSE connections for MCP protocol"""
        try:
            logger.info("New SSE connection established")

            async def event_generator():
                # Send initial connection event
                yield {
                    "event": "endpoint",
                    "data": "/mcp/call"
                }

                # Send server capabilities
                yield {
                    "event": "capabilities",
                    "data": json.dumps({
                        "service": "KYC MCP Server",
                        "version": "1.0.0",
                        "tools": ["verify_pan_basic", "verify_pan_comprehensive", "verify_pan_kra"],
                        "resources": ["kyc://api/status", "kyc://api/endpoints"]
                    })
                }

                # Send periodic ping to keep connection alive
                counter = 0
                while True:
                    await asyncio.sleep(30)
                    counter += 1
                    yield {
                        "event": "ping",
                        "data": f"ping - {counter}"
                    }

            return EventSourceResponse(event_generator())

        except Exception as e:
            logger.error(f"Error in SSE connection: {str(e)}")
            return JSONResponse(
                {"error": f"SSE connection failed: {str(e)}"},
                status_code=500
            )

    async def handle_sse_info(request):
        """Provide information about the SSE endpoint"""
        return JSONResponse({
            "service": "KYC MCP Server",
            "transport": "Server-Sent Events",
            "endpoint": "/sse",
            "status": "ready",
            "mcp_version": "1.0.0",
            "available_tools": [
                "verify_pan_basic",
                "verify_pan_comprehensive",
                "verify_pan_kra"
            ],
            "available_resources": [
                "kyc://api/status",
                "kyc://api/endpoints"
            ]
        })

    async def handle_mcp_call(request):
        """Handle MCP tool calls via POST"""
        try:
            body = await request.json()
            tool_name = body.get("tool")
            parameters = body.get("parameters", {})

            logger.info(f"MCP tool call: {tool_name} with parameters: {parameters}")

            # Route to appropriate tool
            if tool_name == "verify_pan_basic":
                from kyc_mcp_sse import verify_pan_basic_direct
                result = await verify_pan_basic_direct(parameters.get("id_number"))
            elif tool_name == "verify_pan_comprehensive":
                from kyc_mcp_sse import verify_pan_comprehensive_direct
                result = await verify_pan_comprehensive_direct(parameters.get("id_number"))
            elif tool_name == "verify_pan_kra":
                from kyc_mcp_sse import verify_pan_kra_direct
                result = await verify_pan_kra_direct(parameters.get("id_number"))
            else:
                result = json.dumps({
                    "success": False,
                    "error": f"Unknown tool: {tool_name}"
                })

            return JSONResponse({
                "success": True,
                "result": result
            })

        except Exception as e:
            logger.error(f"Error in MCP call: {str(e)}")
            return JSONResponse({
                "success": False,
                "error": str(e)
            }, status_code=500)

    # Create Starlette routes for SSE and message handling
    routes = [
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Route("/sse/info", endpoint=handle_sse_info, methods=["GET"]),
        Route("/call", endpoint=handle_mcp_call, methods=["POST"]),
    ]

    # Create a Starlette app
    sse_app = Starlette(routes=routes)
    logger.info("SSE transport layer initialized")

    return sse_app
