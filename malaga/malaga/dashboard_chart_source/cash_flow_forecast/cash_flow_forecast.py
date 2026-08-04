import frappe
from frappe.utils.dashboard import cache_source

from malaga.analytics import cash_flow_forecast_data


@frappe.whitelist()
@cache_source
def get(filters=None, **kwargs):
	return cash_flow_forecast_data(filters)
