#!/usr/bin/env python3
import json
from pathlib import Path
from math import ceil
import config

MAX_OPS_PER_FILE = 30

def make_openapi(paths_chunk, part_num):
    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"KYC MCP Endpoints (part {part_num})",
            "version": "1.0.0",
            "description": f"Auto-generated subset of KYC MCP endpoints (part {part_num})"
        },
        "servers": [{ "url": "https://zicuro.shop" }],
        "paths": paths_chunk
    }

# 1) Build all /mcp/... paths
all_paths = {}
for key, route in config.ENDPOINTS.items():
    props = { "id_number": { "type": "string" } }
    if key in ("aadhaar_validation", "pan_comprehensive"):
        props["dob"] = { "type": "string", "format": "date" }

    all_paths[f"/mcp{route}"] = {
        "post": {
            "operationId": key,
            "summary": f"{key} via MCP",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": props,
                            "required": list(props.keys())
                        }
                    }
                }
            },
            "responses": {
                "200": {
                    "description": "OK",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {}
                            }
                        }
                    }
                }
            }
        }
    }

# 2) Add /universal-verify at the root
all_paths["/universal-verify"] = {
    "post": {
        "operationId": "universal_verify",
        "summary": "Universal KYC verification",
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "tool": { "type": "string" },
                            "params": {
                                "type": "object",
                                "properties": {
                                    "id_number": { "type": "string" }
                                },
                                "required": ["id_number"]
                            }
                        },
                        "required": ["tool", "params"]
                    }
                }
            }
        },
        "responses": {
            "200": {
                "description": "OK",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object"
                            
                        }
                    }
                }
            }
        }
    }
}

# 3) Add /mcp/approve for the approval callback
all_paths["/mcp/approve"] = {
    "post": {
        "operationId": "approve_action",
        "summary": "Approve or reject a pending MCP action",
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "action_id": { "type": "string" },
                            "approve": { "type": "boolean" }
                        },
                        "required": ["action_id", "approve"]
                    }
                }
            }
        },
        "responses": {
            "200": {
                "description": "Approval Result",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "approved": { "type": "boolean" }
                            }
                        }
                    }
                }
            }
        }
    }
}

# 4) Split into chunks of ≤ MAX_OPS_PER_FILE endpoints
keys = list(all_paths.keys())
num_files = ceil(len(keys) / MAX_OPS_PER_FILE)

for i in range(num_files):
    chunk_keys = keys[i*MAX_OPS_PER_FILE : (i+1)*MAX_OPS_PER_FILE]
    chunk_paths = { k: all_paths[k] for k in chunk_keys }
    spec = make_openapi(chunk_paths, i+1)
    fname = Path(f"openapi_part{i+1}.json")
    fname.write_text(json.dumps(spec, indent=2))
    print(f"Wrote {fname} ({len(chunk_paths)} operations)")
