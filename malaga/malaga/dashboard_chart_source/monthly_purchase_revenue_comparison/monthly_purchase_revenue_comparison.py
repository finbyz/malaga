import frappe
from frappe.utils.dashboard import cache_source

from malaga.analytics import monthly_purchase_revenue_data


@frappe.whitelist()
@cache_source
def get(filters=None, **kwargs):
	return monthly_purchase_revenue_data(filters)

