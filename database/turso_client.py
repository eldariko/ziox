"""Native Turso Cloud SQLite HTTP Client using /v2/pipeline.

Bypasses legacy websocket (hrana2) and /v1/execute deprecations without external native binary dependencies.
Built entirely on top of standard httpx.
"""

import base64
import logging
from typing import Any, Dict, List, Optional, Sequence, Union
import httpx

logger = logging.getLogger(__name__)


class TursoRow(dict):
    """Row representation accessible by column name or numeric index."""

    def __init__(self, cols: Sequence[str], values: Sequence[Any]):
        super().__init__(zip(cols, values))
        self._values = tuple(values)

    def __getitem__(self, item: Union[str, int]) -> Any:
        if isinstance(item, int):
            return self._values[item]
        return super().__getitem__(item)


class TursoResultSet:
    """Result set returned from a Turso SQL query."""

    def __init__(
        self,
        columns: Sequence[str],
        rows: Sequence[TursoRow],
        rows_affected: int = 0,
        last_insert_rowid: Optional[int] = None
    ):
        self.columns = tuple(columns)
        self.rows = tuple(rows)
        self.rows_affected = rows_affected
        self.last_insert_rowid = last_insert_rowid

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)


class TursoClient:
    """Synchronous HTTP client for Turso / libSQL SQLite databases using /v2/pipeline."""

    def __init__(self, url: str, auth_token: Optional[str] = None, timeout: float = 15.0):
        clean_url = (url or "").strip()
        if clean_url.startswith("libsql://"):
            clean_url = "https://" + clean_url[len("libsql://"):]
        elif clean_url.startswith("wss://"):
            clean_url = "https://" + clean_url[len("wss://"):]
        elif clean_url.startswith("ws://"):
            clean_url = "http://" + clean_url[len("ws://"):]
        elif not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = "https://" + clean_url

        self.base_url = clean_url.rstrip("/")
        self.pipeline_url = f"{self.base_url}/v2/pipeline"
        self.auth_token = auth_token
        self.timeout = timeout
        self._session = httpx.Client(timeout=self.timeout)

    def close(self) -> None:
        """Close the underlying HTTP client session cleanly."""
        if hasattr(self, "_session") and not self._session.is_closed:
            self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def _to_proto_value(val: Any) -> Dict[str, Any]:
        """Convert a Python value into a Hrana v2 Value payload."""
        if val is None:
            return {"type": "null"}
        if isinstance(val, bool):
            return {"type": "integer", "value": "1" if val else "0"}
        if isinstance(val, int):
            return {"type": "integer", "value": str(val)}
        if isinstance(val, float):
            return {"type": "float", "value": val}
        if isinstance(val, (bytes, bytearray)):
            return {"type": "blob", "base64": base64.b64encode(val).decode("ascii")}
        return {"type": "text", "value": str(val)}

    @staticmethod
    def _from_proto_value(cell: Dict[str, Any]) -> Any:
        """Convert a Hrana v2 cell payload into a Python primitive."""
        if not isinstance(cell, dict):
            return cell
        v_type = cell.get("type")
        if v_type == "null":
            return None
        if v_type == "integer":
            try:
                return int(cell.get("value", 0))
            except (ValueError, TypeError):
                return 0
        if v_type == "float":
            try:
                return float(cell.get("value", 0.0))
            except (ValueError, TypeError):
                return 0.0
        if v_type == "blob":
            return base64.b64decode(cell.get("base64", ""))
        return cell.get("value", "")

    def execute(self, stmt: str, args: Optional[Sequence[Any]] = None) -> TursoResultSet:
        """Execute a SQL statement against Turso via /v2/pipeline."""
        proto_args = [self._to_proto_value(v) for v in (args or [])]
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": stmt,
                        "args": proto_args
                    }
                },
                {
                    "type": "close"
                }
            ]
        }
        headers = {
            "Content-Type": "application/json"
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        resp = self._session.post(self.pipeline_url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Turso HTTP request failed (status {resp.status_code}): {resp.text}"
            )

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return TursoResultSet([], [], 0, None)

        first_res = results[0]
        if first_res.get("type") == "error":
            err = first_res.get("error", {})
            raise RuntimeError(
                f"Turso SQLite Error: {err.get('message', 'Unknown error')} (code: {err.get('code')})"
            )

        stmt_result = first_res.get("response", {}).get("result", {})
        cols = [c.get("name") or "" for c in stmt_result.get("cols", [])]
        raw_rows = stmt_result.get("rows", [])

        rows: List[TursoRow] = []
        for raw_row in raw_rows:
            row_vals = [self._from_proto_value(cell) for cell in raw_row]
            rows.append(TursoRow(cols, row_vals))

        rows_affected = stmt_result.get("affected_row_count", 0)
        raw_last_id = stmt_result.get("last_insert_rowid")
        last_insert_rowid = int(raw_last_id) if raw_last_id is not None else None

        return TursoResultSet(
            columns=cols,
            rows=rows,
            rows_affected=rows_affected,
            last_insert_rowid=last_insert_rowid
        )
