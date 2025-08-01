from django.urls import path
from core import views as core_views

urlpatterns = [
    path(r"", core_views.IndexView.as_view()),
    path(r"chat/", core_views.ChatView.as_view(), name="chat"),
    path(r"chat/sse/", core_views.ChatEventView.as_view(), name="chatsse"),
    path(r"fact/", core_views.RandomFactView.as_view(), name="fact"),
    path(r"spv/", core_views.SPVIew.as_view(), name="spv"),
    path(r"favicon.ico", core_views.favicon_view, name="favicon"),
    path(r"sse/", core_views.stream_view, name="sse"),
    path(r"sio/", core_views.SioView.as_view(), name="sio"),
    path(r"zmq/sse/", core_views.ZmqIpcStreamView.as_view(), name="zmqsse"),
    path(r"zmq/", core_views.ZmqIpcView.as_view(), name="zmq"),
]
