import frappe
from frappe.utils.dashboard import cache_source

from malaga.analytics import purchase_price_trends_data


@frappe.whitelist()
@cache_source
def get(filters=None, **kwargs):
	return purchase_price_trends_data(filters)
