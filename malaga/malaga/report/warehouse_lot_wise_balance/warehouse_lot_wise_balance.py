from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	float_precision = cint(frappe.db.get_default("float_precision")) or 3

	columns = get_columns()
	iwb_map = get_item_warehouse_batch_map(filters, float_precision)
	item_uom_cache = {}

	data = []
	for item in sorted(iwb_map):
		for wh in sorted(iwb_map[item]):
			for batch in sorted(iwb_map[item][wh]):
				qty_dict = iwb_map[item][wh][batch]
				if not qty_dict.bal_qty:
					continue

				data.append({
					"item_code": item,
					"warehouse": wh,
					"batch_no": batch,
					"lot_no": qty_dict.lot_no,
					"packing_type": qty_dict.packing_type,
					"balance_qty": flt(qty_dict.bal_qty, float_precision),
					"stock_uom": get_item_uom(item, item_uom_cache),
				})

	return columns, data


def get_columns():
	return [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 200},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 120},
		{"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 120},
		{"label": _("Lot No"), "fieldname": "lot_no", "fieldtype": "Data", "width": 100},
		{"label": _("Packing"), "fieldname": "packing_type", "fieldtype": "Link", "options": "Packing Type", "width": 100},
		{"label": _("Balance Qty"), "fieldname": "balance_qty", "fieldtype": "Float", "width": 90},
		{"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
	]


def get_conditions(filters):
	if not filters.get("to_date"):
		frappe.throw(_("'To Date' is required"))
	return " and sle.posting_date <= '%s'" % filters["to_date"]


def get_stock_ledger_entries(filters):
	conditions = get_conditions(filters)
	batch_no = "IFNULL(NULLIF(sle.batch_no, ''), sbe.batch_no)"
	actual_qty = """CASE
		WHEN IFNULL(sle.batch_no, '') != '' THEN sle.actual_qty
		WHEN sbe.name IS NOT NULL THEN sbe.qty
		ELSE sle.actual_qty
	END"""
	return frappe.db.sql("""
		select sle.item_code, {batch_no} as batch_no, sle.warehouse, sle.posting_date,
			sum({actual_qty}) as actual_qty, batch.lot_no, batch.packing_type
		from `tabStock Ledger Entry` as sle
		left join `tabSerial and Batch Entry` as sbe
			on sbe.parent = sle.serial_and_batch_bundle and IFNULL(sle.batch_no, '') = ''
		left join `tabBatch` as batch on batch.name = {batch_no}
		where sle.is_cancelled = 0 and sle.docstatus < 2
			and (IFNULL(sle.batch_no, '') != '' OR IFNULL(sle.serial_and_batch_bundle, '') != '') %s
		group by sle.voucher_no, {batch_no}, sle.item_code, sle.warehouse
		order by sle.item_code, sle.warehouse""".format(
		batch_no=batch_no,
		actual_qty=actual_qty,
	) % conditions, as_dict=1)


def get_item_warehouse_batch_map(filters, float_precision):
	sle = get_stock_ledger_entries(filters)
	iwb_map = {}

	from_date = getdate(filters["to_date"])
	to_date = getdate(filters["to_date"])

	for d in sle:
		iwb_map.setdefault(d.item_code, {}).setdefault(d.warehouse, {}).setdefault(
			d.batch_no, frappe._dict({
				"opening_qty": 0.0, "in_qty": 0.0, "out_qty": 0.0, "bal_qty": 0.0,
				"lot_no": d.lot_no, "packing_type": d.packing_type,
			}))
		qty_dict = iwb_map[d.item_code][d.warehouse][d.batch_no]

		if d.posting_date < from_date:
			qty_dict.opening_qty = flt(qty_dict.opening_qty, float_precision) + flt(d.actual_qty, float_precision)
		elif from_date <= d.posting_date <= to_date:
			if flt(d.actual_qty) > 0:
				qty_dict.in_qty = flt(qty_dict.in_qty, float_precision) + flt(d.actual_qty, float_precision)
			else:
				qty_dict.out_qty = flt(qty_dict.out_qty, float_precision) + abs(flt(d.actual_qty, float_precision))

		qty_dict.bal_qty = flt(qty_dict.bal_qty, float_precision) + flt(d.actual_qty, float_precision)
		qty_dict.lot_no = d.lot_no or qty_dict.lot_no
		qty_dict.packing_type = d.packing_type or qty_dict.packing_type

	return iwb_map


def get_item_uom(item_code, cache):
	if item_code not in cache:
		cache[item_code] = frappe.db.get_value("Item", item_code, "stock_uom")
	return cache[item_code]
