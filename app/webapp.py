from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from .defense import router as defense_router
from .main import STATIC_DIR, app

app.include_router(defense_router)


@app.middleware("http")
async def inject_defense_assets(request: Request, call_next):
    if request.method == "GET" and request.url.path == "/":
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("beta 0.8", "beta 0.9")
        html = html.replace(
            "</head>",
            '  <link rel="stylesheet" href="/static/defense.css">\n</head>',
        )
        html = html.replace(
            "</body>",
            '  <script src="/static/defense.js"></script>\n</body>',
        )
        return HTMLResponse(html)
    return await call_next(request)
