import frappe
from frappe.utils.dashboard import cache_source

from malaga.analytics import cash_and_bank_balance_data


@frappe.whitelist()
@cache_source
def get(filters=None, **kwargs):
	return cash_and_bank_balance_data(filters)
