import asyncio
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .views import _build_signature


class AdminLiveConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated or not user.is_staff:
            await self.close()
            return

        await self.accept()
        self._poll_task = asyncio.create_task(self._send_signatures())

    async def disconnect(self, close_code):
        poll_task = getattr(self, '_poll_task', None)
        if poll_task:
            poll_task.cancel()

    async def _send_signatures(self):
        while True:
            signature = await database_sync_to_async(_build_signature)()
            await self.send(text_data=json.dumps({'signature': signature}))
            await asyncio.sleep(5)
