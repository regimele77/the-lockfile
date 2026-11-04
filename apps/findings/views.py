from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from apps.findings.models import Finding
from apps.repositories.models import Repository


class FindingListView(LoginRequiredMixin, ListView):
    model = Finding
    template_name = "findings/list.html"
    context_object_name = "findings"
    paginate_by = 25

    def get_queryset(self):
        repos = Repository.objects.selected_for_user(self.request.user)
        qs = Finding.objects.filter(scan__repository__in=repos).select_related(
            "scan", "scan__repository"
        )
        severity = self.request.GET.get("severity", "").lower()
        if severity in Finding.Severity.values:
            qs = qs.filter(severity=severity)
        return qs

    def get_template_names(self):
        if self.request.htmx:
            return ["findings/partials/filtered.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_severity"] = self.request.GET.get("severity", "").lower()
        context["severity_choices"] = Finding.Severity.choices
        return context


class FindingDetailView(LoginRequiredMixin, DetailView):
    model = Finding
    template_name = "findings/detail.html"
    context_object_name = "finding"

    def get_queryset(self):
        repos = Repository.objects.selected_for_user(self.request.user)
        return Finding.objects.filter(scan__repository__in=repos).select_related(
            "scan", "scan__repository"
        )
