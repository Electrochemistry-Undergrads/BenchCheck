"""Bound request bodies before multipart parsing and attach browser security headers."""
from starlette.responses import JSONResponse

class HTTPHygiene:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        head = scope['method'] == 'HEAD'
        if head:
            scope = {**scope, 'method': 'GET'}
        limit = 1024 * 1024 if scope['path'] == '/api/report' else 30 * 1024 * 1024
        chunks, size = [], 0
        headers = dict(scope.get('headers', []))
        try:
            too_big = int(headers.get(b'content-length', b'0')) > limit
        except ValueError:
            too_big = True
        if too_big:
            return await JSONResponse({'detail':'Request body is too large.'}, 413)(scope, receive, send)
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            data = message.get('body', b'')
            size += len(data)
            if size > limit:
                return await JSONResponse({'detail':'Request body is too large.'}, 413)(scope, receive, send)
            chunks.append(data)
            if not message.get('more_body'):
                break
        body = b''.join(chunks)
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type':'http.request', 'body':body, 'more_body':False}
            return await receive()
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers', []).extend([
                    (b'x-content-type-options', b'nosniff'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")])
            if head and message['type'] == 'http.response.body':
                message = {**message, 'body':b''}
            await send(message)
        await self.app(scope, replay, secure_send)
