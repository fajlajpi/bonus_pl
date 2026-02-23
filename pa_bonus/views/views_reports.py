"""
Views for the Reports Hub.

This module provides two views:
    1. ReportsHubView -- renders the hub page listing all available reports.
    2. ReportDownloadView -- handles the actual report generation and file download.

The design keeps the views thin. All data-gathering and Excel logic lives in
pa_bonus/reports.py, so the views are purely about HTTP request/response handling.
"""

import logging

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views import View

from pa_bonus.utilities import ManagerGroupRequiredMixin
from pa_bonus.reports import get_all_reports, get_report_by_id

logger = logging.getLogger(__name__)


class ReportsHubView(ManagerGroupRequiredMixin, View):
    """
    Displays the Reports Hub page.

    Lists all registered reports with their title, description, and a download
    button. The reports are automatically discovered from the report registry,
    so adding a new report subclass in reports.py is all you need to do --
    it will appear here without any changes to this view or the template.
    """

    template_name = "manager/reports_hub.html"

    def get(self, request):
        reports = get_all_reports()

        context = {
            "reports": [
                {
                    "report_id": report.report_id,
                    "title": report.title,
                    "description": report.description,
                }
                for report in reports
            ],
        }

        return render(request, self.template_name, context)


class ReportDownloadView(ManagerGroupRequiredMixin, View):
    """
    Generates and streams a report as an Excel file download.

    Expects a POST request with a ``report_id`` parameter.  We use POST
    rather than GET to avoid accidental re-downloads on browser refresh
    and because report generation can be an expensive operation that
    should not be triggered by crawlers or prefetch.
    """

    def post(self, request):
        report_id = request.POST.get("report_id", "")
        report_class = get_report_by_id(report_id)

        if report_class is None:
            messages.error(request, f"Unknown report: {report_id}")
            return redirect("reports_hub")

        try:
            report = report_class()
            logger.info(
                "User %s generating report: %s", request.user.username, report_id
            )
            return report.generate_response()
        except Exception:
            logger.exception("Error generating report %s", report_id)
            messages.error(
                request,
                "An error occurred while generating the report. "
                "Please try again or contact the administrator.",
            )
            return redirect("reports_hub")
