"""Vector memory for protoClaw — semantic search over conversation history.

Uses Ollama (nomic-embed-text) for embeddings and sqlite-vec for storage.
Falls back silently if Ollama is unreachable.
"""

import json
import struct
import time
from pathlib import Path
from typing import Any

import httpx
import sqlite3

from nanobot.agent.tools.base import Tool

_OLLAMA_URL = "http://host.docker.internal:11434"
_EMBED_MODEL = "nomic-embed-text"
_DB_PATH = Path("/sandbox/memory/vectors.db")
_EMBED_DIM = 768  # nomic-embed-text dimension


class VectorMemory:
    """Semantic vector store backed by sqlite-vec + Ollama embeddings."""

    def __init__(
        self,
        db_path: Path = _DB_PATH,
        ollama_url: str = _OLLAMA_URL,
        model: str = _EMBED_MODEL,
    ):
        self.db_path = db_path
        self.ollama_url = ollama_url
        self.model = model
        self._db: sqlite3.Connection | None = None

    def _get_db(self) -> sqlite3.Connection | None:
        """Lazy-init database with sqlite-vec extension."""
        if self._db is not None:
            return self._db
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            import sqlite_vec

            db = sqlite3.connect(str(self.db_path))
            db.enable_load_extension(True)
            sqlite_vec.load(db)
            db.enable_load_extension(False)

            db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    session_id TEXT DEFAULT '',
                    created_at REAL NOT NULL
                )
            """)
            db.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec
                USING vec0(embedding float[{_EMBED_DIM}])
            """)
            db.commit()
            self._db = db
            return db
        except Exception:
            return None

    def embed(self, text: str) -> list[float] | None:
        """Get embedding from Ollama. Returns None if unreachable."""
        try:
            resp = httpx.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception:
            return None

    def add(
        self,
        content: str,
        source: str = "",
        session_id: str = "",
    ) -> bool:
        """Embed and store a memory chunk. Returns True on success."""
        db = self._get_db()
        if db is None:
            return False

        embedding = self.embed(content)
        if embedding is None:
            return False

        cursor = db.execute(
            "INSERT INTO memories (content, source, session_id, created_at) VALUES (?, ?, ?, ?)",
            (content, source, session_id, time.time()),
        )
        rowid = cursor.lastrowid
        # sqlite-vec expects raw bytes for float vectors
        vec_bytes = struct.pack(f"{len(embedding)}f", *embedding)
        db.execute(
            "INSERT INTO memory_vec (rowid, embedding) VALUES (?, ?)",
            (rowid, vec_bytes),
        )
        db.commit()
        return True

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Search for similar memories. Returns empty list on failure."""
        db = self._get_db()
        if db is None:
            return []

        embedding = self.embed(query)
        if embedding is None:
            return []

        vec_bytes = struct.pack(f"{len(embedding)}f", *embedding)
        rows = db.execute(
            """
            SELECT m.content, m.source, m.session_id, m.created_at, v.distance
            FROM memory_vec v
            JOIN memories m ON m.id = v.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (vec_bytes, k),
        ).fetchall()

        return [
            {
                "content": row[0],
                "source": row[1],
                "session_id": row[2],
                "created_at": row[3],
                "distance": row[4],
            }
            for row in rows
        ]

    def as_tool(self) -> "VectorMemoryTool":
        """Return a nanobot Tool wrapping this memory store."""
        return VectorMemoryTool(self)


class VectorMemoryTool(Tool):
    """Tool interface for vector memory — search and store memories."""

    def __init__(self, memory: VectorMemory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Semantic memory store. Use 'search' to find relevant past context, "
            "or 'store' to save important information for future retrieval."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "store"],
                    "description": "Action: 'search' to find memories, 'store' to save one.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query or content to store.",
                },
                "source": {
                    "type": "string",
                    "description": "Source label when storing (e.g. 'user', 'conversation').",
                },
            },
            "required": ["action", "query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        query = kwargs["query"]

        if action == "store":
            source = kwargs.get("source", "agent")
            ok = self._memory.add(content=query, source=source)
            if ok:
                return "Memory stored successfully."
            return "Error: Failed to store memory (embedding service may be unavailable)."

        if action == "search":
            results = self._memory.search(query, k=5)
            if not results:
                return "No relevant memories found."
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. [{r['source']}] {r['content']}")
            return "\n".join(lines)

        return f"Error: Unknown action '{action}'. Use 'search' or 'store'."
