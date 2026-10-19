
"""
ASGI config for kisan project.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kisan.settings")

from django.core.asgi import get_asgi_application

# Initialize Django before importing code that uses models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from chat.routing import websocket_urlpatterns

websocket_application = AllowedHostsOriginValidator(
    AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    )
)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": websocket_application,
})
