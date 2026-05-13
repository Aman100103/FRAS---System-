from utils.attendance_utils import (
    get_attendance_percentage_per_student,
    get_daily_trend,
    get_defaulters,
    get_overall_percentage,
    get_today_count,
    get_top_attenders,
)


def get_analytics_payload():
    """Return all analytics datasets used by dashboard and analytics pages."""
    return {
        "attendance_per_student": get_attendance_percentage_per_student(),
        "daily_trend": get_daily_trend(),
        "defaulters": get_defaulters(threshold=75),
        "top_attenders": get_top_attenders(top_n=5),
        "today_count": get_today_count(),
        "overall_percentage": get_overall_percentage(),
    }
