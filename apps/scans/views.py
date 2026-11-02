from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from apps.scans.models import Scan


class ScanListView(LoginRequiredMixin, ListView):
    model = Scan
    template_name = "scans/list.html"
    context_object_name = "scans"
    paginate_by = 25

    def get_queryset(self):
        return Scan.objects.select_related("repository")


class ScanDetailView(LoginRequiredMixin, DetailView):
    model = Scan
    template_name = "scans/detail.html"
    context_object_name = "scan"

    def get_queryset(self):
        return Scan.objects.select_related("repository")
