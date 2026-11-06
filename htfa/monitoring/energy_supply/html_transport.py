"""Compact transport for generated map documents."""
from __future__ import annotations

import base64
import gzip
from pathlib import Path


_INFLATE_SCRIPT = (Path(__file__).with_name("vendor") / "fflate" / "fflate.js").read_text()


def compressed_document(html: str) -> str:
    """Restore the generated iframe document without another network request."""
    payload = base64.b64encode(gzip.compress(
        html.encode("utf-8"), compresslevel=6, mtime=0)).decode("ascii")
    return f"""<script>
    (() => {{
      const module = {{exports: {{}}}};
      const exports = module.exports;
      {_INFLATE_SCRIPT}
      const bytes = Uint8Array.from(atob('{payload}'), char => char.charCodeAt(0));
      const html = new TextDecoder().decode(module.exports.gunzipSync(bytes));
      document.open(); document.write(html); document.close();
    }})();
    </script>"""
