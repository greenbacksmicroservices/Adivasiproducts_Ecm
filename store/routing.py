from django.urls import path

from . import consumers


websocket_urlpatterns = [
    path('ws/admin/live/', consumers.AdminLiveConsumer.as_asgi()),
]
