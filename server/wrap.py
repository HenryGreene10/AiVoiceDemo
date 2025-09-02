# server/wrap.py
from fastapi import APIRouter, HTTPException, Query, Response
import httpx, re, html

router = APIRouter()

WIDGET = '''
<script async
  src="https://ai-voice-demo-theta.vercel.app/"
  data-base="http://localhost:8000/"
  data-voice="21m00Tcm4TlvDq8ikWAM"
  data-selector="article, main, .post"
  data-position="bottom-right"
  data-variant="inline"
  data-doc-id="{doc}">
</script>'''

@router.get("/wrap")
async def wrap(url: str = Query(..., description="Public article URL to preview")):
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(400, "URL must start with http:// or https://")
    try:
        async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent":"AI-Listen-Demo/1.0"}) as c:
            r = await c.get(url, timeout=10)
    except Exception as e:
        raise HTTPException(400, f"Fetch failed: {e}")
    ct = r.headers.get("content-type","")
    if "text/html" not in ct:
        raise HTTPException(415, f"Not HTML (content-type: {ct})")
    body = r.text

    # Strip all inline scripts to avoid CSP and hostile JS
    body = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", body, flags=re.I)

    # Add <base> so relative assets still work
    if "</head>" in body:
        head, tail = body.split("</head>", 1)
        base = f'<base href="{html.escape(str(r.url))}">\n<meta name="robots" content="noindex">'
        body = head + "\n" + base + "\n</head>" + tail

    # Inject our widget before </body>
    doc_id = (r.url.host + r.url.path)[:128]
    inj = WIDGET.format(v="1", doc=html.escape(doc_id))
    if re.search(r"</body>", body, flags=re.I):
        body = re.sub(r"</body>", inj + "\n</body>", body, flags=re.I)
    else:
        body = body + inj

    return Response(content=body, media_type="text/html; charset=utf-8")
