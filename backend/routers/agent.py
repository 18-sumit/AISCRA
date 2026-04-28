"""
backend/routers/agent.py
─────────────────────────
REST and WebSocket endpoints for the AI agent chat interface.

POST /api/agent/query   — single question, returns answer
WS   /api/agent/ws      — streaming WebSocket chat
GET  /api/agent/status  — agent availability status
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str


@router.get("/status")
def agent_status():
    """Check whether the AI agent is available."""
    try:
        from module4.agent import get_agent, _agent_available
        agent = get_agent()
        return {
            "available":  agent is not None,
            "mode":       "langchain_react" if agent is not None else "direct_fallback",
            "message":    "Agent ready" if agent else "Running in fallback mode (LangChain not installed)",
        }
    except Exception as e:
        return {"available": False, "mode": "error", "message": str(e)}


@router.post("/query")
def agent_query(req: QueryRequest):
    """
    Process a single natural language question through the AI agent.
    Returns the answer synchronously.
    """
    try:
        from module4.agent import query
        result = query(req.question)
        return {
            "answer":   result["answer"],
            "method":   result["method"],
            "question": result["question"],
        }
    except Exception as e:
        logger.error(f"Agent query error: {e}")
        return {
            "answer":   f"Agent error: {str(e)}",
            "method":   "error",
            "question": req.question,
        }


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for streaming agent responses.

    Protocol:
      Client sends: {"question": "..."}
      Server sends: {"type": "thinking"} then {"type": "answer", "text": "...", "method": "..."}
    """
    await websocket.accept()
    logger.info("Agent WebSocket connected")

    try:
        while True:
            data = await websocket.receive_json()
            question = data.get("question", "").strip()

            if not question:
                continue

            # Send thinking indicator
            await websocket.send_json({"type": "thinking", "question": question})

            try:
                # Run agent in thread pool to avoid blocking the event loop
                import asyncio
                from module4.agent import query

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, query, question)

                await websocket.send_json({
                    "type":     "answer",
                    "text":     result["answer"],
                    "method":   result["method"],
                    "question": question,
                })
            except Exception as e:
                await websocket.send_json({
                    "type":  "error",
                    "text":  f"Error processing query: {str(e)}",
                })

    except WebSocketDisconnect:
        logger.info("Agent WebSocket disconnected")
    except Exception as e:
        logger.error(f"Agent WebSocket error: {e}")
