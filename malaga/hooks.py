import frappe

from erpnext.stock.stock_ledger import update_entries_after, make_entry as erpnext_make_entry
from erpnext.stock import stock_ledger as stock_ledger_module
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.doctype.pick_list.pick_list import PickList
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals
from erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry import StockLedgerEntry
from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote
from . import __version__ as app_version

from malaga.override_default_class_method import (
	raise_exceptions, set_actual_qty, set_item_locations,
	pick_list_before_submit, get_current_tax_amount,
	determine_exclusive_rate, calculate_taxes, actual_amt_check
)
from malaga.override.delivery_note import validate as delivery_validate
from malaga.override.pick_list import validate_warehouses as pick_list_validate_warehouses
from malaga.doc_events.stock_ledger_entry import get_batch_no_for_args, get_batch_no_for_sle

update_entries_after.raise_exceptions = raise_exceptions
StockEntry.set_actual_qty = set_actual_qty
PickList.set_item_locations = set_item_locations
PickList.before_submit = pick_list_before_submit
PickList.validate_warehouses = pick_list_validate_warehouses
calculate_taxes_and_totals.get_current_tax_amount = get_current_tax_amount
calculate_taxes_and_totals.determine_exclusive_rate = determine_exclusive_rate
calculate_taxes_and_totals.calculate_taxes = calculate_taxes
StockLedgerEntry.actual_amt_check = actual_amt_check
DeliveryNote.validate = delivery_validate


def make_entry_with_batch(args, allow_negative_stock=False, via_landed_cost_voucher=False):
	if not args.get("batch_no"):
		batch_no = get_batch_no_for_args(args)
		if batch_no:
			args["batch_no"] = batch_no

	sle = erpnext_make_entry(args, allow_negative_stock, via_landed_cost_voucher)

	if not sle.batch_no:
		batch_no = get_batch_no_for_sle(sle)
		if batch_no:
			frappe.db.set_value("Stock Ledger Entry", sle.name, "batch_no", batch_no, update_modified=False)
			sle.batch_no = batch_no

	return sle


stock_ledger_module.make_entry = make_entry_with_batch


app_name = "malaga"
app_title = "Malaga"
app_publisher = "nandu bhadada"
app_description = "malaga"
app_email = "nandu@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/malaga/css/malaga.css"
app_include_js = "/assets/malaga/js/serial_no_batch_selector.js"

# include js in doctype views
doctype_js = {
	"Pick List": "public/js/doctype_js/pick_list.js",
	"Sales Order": "public/js/doctype_js/sales_order.js",
	"Delivery Note": "public/js/doctype_js/delivery_note.js",
 "Item": "public/js/doctype_js/item.js",
}

# Document Events
doc_events = {
	"Batch": {
		"before_insert": "malaga.doc_events.batch.before_insert",},
	"Stock Ledger Entry": {
		"before_insert": "malaga.doc_events.stock_ledger_entry.set_batch_from_voucher_detail",
		"validate": "malaga.doc_events.stock_ledger_entry.set_batch_from_voucher_detail",
		"on_submit": "malaga.doc_events.stock_ledger_entry.persist_batch_on_sle",
	},
	"Pick List": {
		"before_validate": "malaga.doc_events.pick_list.before_validate",
		"validate": "malaga.doc_events.pick_list.validate",
		"before_submit": "malaga.doc_events.pick_list.before_submit",
		"on_submit": "malaga.doc_events.pick_list.on_submit",
		"on_cancel": "malaga.doc_events.pick_list.on_cancel",
		"before_update_after_submit": "malaga.doc_events.pick_list.before_update_after_submit",
	},
	"Sales Order": {
		"before_validate": "malaga.doc_events.sales_order.before_validate",
		"validate": "malaga.doc_events.sales_order.validate",
		"on_submit": "malaga.doc_events.sales_order.on_submit",
		"before_validate_after_submit": "malaga.doc_events.sales_order.before_validate_after_submit",
		"before_update_after_submit": "malaga.doc_events.sales_order.before_update_after_submit",
		"on_update_after_submit": "malaga.doc_events.sales_order.on_update_after_submit",
		"on_cancel": "malaga.doc_events.sales_order.on_cancel",
	},
	"Delivery Note": {
		"before_validate": "malaga.doc_events.delivery_note.before_validate",
		"validate": "malaga.doc_events.delivery_note.validate",
		"before_save": "malaga.doc_events.delivery_note.before_save",
		"before_submit": "malaga.doc_events.delivery_note.before_submit",
		"on_submit": "malaga.doc_events.delivery_note.on_submit",
		"on_cancel": "malaga.doc_events.delivery_note.on_cancel",
		"on_update_after_submit": "malaga.doc_events.delivery_note.on_update_after_submit",
	},
}

override_doctype_dashboards = {
	"Pick List": "malaga.dashboard.pick_list.get_data",
}

doctype_list_js = {
	"Pick List": "public/js/pick_list_list.js",
	"Sales Order": "public/js/doctype_js/sales_order_list.js",
}

# DocType Class Overrides
override_doctype_class = {
	"Sales Order": "malaga.override.sales_order.SalesOrderCustom",
	"Quotation": "malaga.override.quotation.QuotationCustom",
}

scheduler_events = {
	"daily": [
		"malaga.doc_events.sales_order.schedule_daily",
	],
}

fixtures = [
	{
		"dt": "Custom Field",
		"filters": {"module": ["in", ["malaga"]]},
	},
	{
		"dt": "Property Setter",
		"filters": {"module": ["in", ["malaga"]]},
	},
]
