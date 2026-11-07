from django.conf import settings
from django.http import FileResponse, Http404


def service_worker(request):
    service_worker_path = settings.BASE_DIR / "static" / "js" / "sw.js"
    if not service_worker_path.exists():
        raise Http404
    return FileResponse(
        service_worker_path.open("rb"),
        content_type="application/javascript",
    )