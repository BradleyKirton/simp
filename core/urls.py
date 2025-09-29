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
    path(r"valkey/sse/", core_views.ValKeyIpcStreamView.as_view(), name="valkeysse"),
    path(r"valkey/", core_views.ValKeyIpcView.as_view(), name="valkey"),
    path(r"test/", core_views.TaskCountView.as_view(), name="task_count"),
    path(r"test/sse/", core_views.TaskCountSSEView.as_view(), name="task_count_sse"),
    path(r"valkey_2/sse/", core_views.valkey_stream, name="valkeysse_2"),
    path(r"valkey_2/", core_views.valkey_view, name="valkey_2"),
    path(r"datastar/", core_views.datastar_view, name="datastar"),
    path(r"datastar/sse/", core_views.datastar_sse_view, name="datastarsse"),
    path(
        r"speculation/",
        core_views.SpeculationRulesView.as_view(
            template_name="core/speculation_rules.html"
        ),
        name="speculation",
    ),
    path(
        r"speculation/a/",
        core_views.SpeculationRulesView.as_view(
            template_name="core/speculation_rules_a.html"
        ),
        name="speculation_a",
    ),
    path(
        r"speculation/b/",
        core_views.SpeculationRulesView.as_view(
            template_name="core/speculation_rules_b.html"
        ),
        name="speculation_b",
    ),
    path("sw/", core_views.service_worker_view, name="sw"),
    path("sw.js", core_views.service_worker_js_view, name="swjs"),
    path("conway/", core_views.ConwayView.as_view(), name="conway"),
    path("conway/sse/", core_views.conway_see_view, name="conwaysse"),
]
