from django.urls import path
from core import views as core_views

urlpatterns = [
	path(r"", core_views.IndexView.as_view()),
	path(r"fact/", core_views.RandomFactView.as_view(), name="fact"),
	path(r"favicon.ico", core_views.favicon_view, name="favicon"),
	path(r"sse/", core_views.stream_view, name="sse"),
]
