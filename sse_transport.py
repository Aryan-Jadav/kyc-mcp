"""
SSE Transport Layer for KYC MCP Server
This module provides Server-Sent Events support for the KYC MCP server
to enable integration with n8n MCP client nodes.
"""

import logging
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse

logger = logging.getLogger("kyc-sse-transport")

def create_sse_server(mcp: FastMCP) -> Starlette:
    """
    Create a Starlette app that handles SSE connections and message handling
    for the KYC MCP server.
    
    Args:
        mcp: FastMCP instance with KYC tools and resources
        
    Returns:
        Starlette application configured for SSE transport
    """
    transport = SseServerTransport("/messages/")
    
    async def handle_sse(request):
        """Handle SSE connections for MCP protocol"""
        try:
            logger.info("New SSE connection established")
            async with transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await mcp._mcp_server.run(
                    streams[0], streams[1], mcp._mcp_server.create_initialization_options()
                )
        except Exception as e:
            logger.error(f"Error in SSE connection: {str(e)}")
            raise
    
    async def handle_sse_info(request):
        """Provide information about the SSE endpoint"""
        return JSONResponse({
            "service": "KYC MCP Server",
            "transport": "Server-Sent Events",
            "endpoint": "/sse",
            "messages": "/messages/",
            "status": "ready"
        })
    
    # Create Starlette routes for SSE and message handling
    routes = [
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Route("/sse/info", endpoint=handle_sse_info, methods=["GET"]),
        Mount("/messages/", app=transport.handle_post_message),
    ]
    
    # Create a Starlette app
    sse_app = Starlette(routes=routes)
    logger.info("SSE transport layer initialized")
    
    return sse_app
