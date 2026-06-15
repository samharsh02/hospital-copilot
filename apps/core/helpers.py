from datetime import datetime

from django.utils.timezone import now
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


def elapsed_minutes(since: datetime) -> int:
    delta = now() - since
    return int(delta.total_seconds() // 60)


def format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    hours, remaining = divmod(minutes, 60)
    if remaining == 0:
        return f"{hours}h"
    return f"{hours}h {remaining}m"


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data: list) -> Response:
        return Response({
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        })

    def get_paginated_response_schema(self, schema: dict) -> dict:
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results": schema,
            },
        }
