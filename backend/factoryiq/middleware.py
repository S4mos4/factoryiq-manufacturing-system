from starlette.responses import JSONResponse

JSON_LIMIT = 96 * 1024


class LimitApiBody:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] not in {"POST","PUT","PATCH"}
                or not scope["path"].startswith("/api/") or scope["path"] == "/api/sorter/imports"):
            await self.app(scope,receive,send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body",b"")
            if len(body)+len(chunk) > JSON_LIMIT:
                response = JSONResponse({"detail":"The request exceeds 96 KiB."},status_code=413)
                await response(scope,receive,send)
                return
            body.extend(chunk)
            if not message.get("more_body",False):
                break

        pending = True

        async def replay_body():
            nonlocal pending
            if pending:
                pending = False
                return {"type":"http.request","body":bytes(body),"more_body":False}
            return await receive()

        await self.app(scope,replay_body,send)
