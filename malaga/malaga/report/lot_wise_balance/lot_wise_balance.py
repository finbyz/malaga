from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, formatdate, getdate, get_url_to_form
from frappe.utils.data import escape_html


def normalize_filters(filters):
	filters = frappe._dict(filters or {})
	for key in ("warehouse", "show_location", "group_item_qty"):
		filters[key] = cint(filters.get(key))
	return filters


def execute(filters=None):
	filters = normalize_filters(filters)

	float_precision = cint(frappe.db.get_default("float_precision")) or 3

	columns = get_columns(filters)
	item_pick_map = get_picked_qty(filters, float_precision)
	iwb_map = get_item_warehouse_batch_map(filters, float_precision)

	data = []

	if filters.warehouse:
		data = get_warehouse_wise_data(filters, iwb_map, item_pick_map, float_precision)
	elif filters.show_location:
		data = get_location_wise_data(filters, iwb_map, item_pick_map, float_precision)
	else:
		data = get_default_data(filters, iwb_map, item_pick_map, float_precision)

	for row in data:
		if row.get('item_code') and filters.warehouse:
			row['buying_unit_price'] = frappe.db.get_value("Item Group", row['item_group'], 'production_price') or 0
			row['new_qty'] = get_change_qty_button(row)
		elif row.get('batch_no') and filters.show_location and not filters.warehouse and not filters.group_item_qty:
			row['change_location'] = get_change_location_button(row)

	if filters.group_item_qty:
		data = group_data_by_item(data, float_precision)

	return columns, data


def group_data_by_item(data, float_precision):
	grouped = {}
	qty_fields = [
		'balance_qty', 'picked_qty', 'unlocked_qty', 'remaining_qty',
		'opening_qty', 'in_qty', 'out_qty', 'so_picked_qty'
	]
	for row in data:
		key = row.get('item_code')
		if key not in grouped:
			grouped[key] = row.copy()
			continue

		target = grouped[key]
		for field in qty_fields:
			target[field] = flt(target.get(field), float_precision) + flt(row.get(field), float_precision)

		for field in ('lot_no', 'batch_no', 'location', 'warehouse'):
			if row.get(field) and row.get(field) not in cstr(target.get(field) or ''):
				target[field] = ', '.join(filter(None, [target.get(field), row.get(field)]))

	result = list(grouped.values())
	for row in result:
		row['picked_detail'] = ''
		row['change_location'] = ''
	return result


def get_so_picked_qty(filters, item, batch):
	if not filters.get('sales_order'):
		return 0.0
	batch = batch_key(batch)
	if batch:
		return frappe.db.sql("""
			SELECT SUM(pli.qty - pli.delivered_qty - pli.wastage_qty)
			FROM `tabPick List Item` as pli
			LEFT JOIN `tabPick List` as pl on pli.parent = pl.name
			WHERE pli.sales_order = %s AND pli.item_code = %s AND pli.batch_no = %s AND pl.docstatus = 1
		""", (filters.get("sales_order"), item, batch))[0][0] or 0.0
	return frappe.db.sql("""
		SELECT SUM(pli.qty - pli.delivered_qty - pli.wastage_qty)
		FROM `tabPick List Item` as pli
		LEFT JOIN `tabPick List` as pl on pli.parent = pl.name
		WHERE pli.sales_order = %s AND pli.item_code = %s AND pl.docstatus = 1
	""", (filters.get("sales_order"), item))[0][0] or 0.0


def build_row(item, batch, qty_dict, filters, picked_qty, unlocked_qty, float_precision, extra=None):
	row = {
		'item_code': item,
		'lot_no': qty_dict.lot_no,
		'packing_type': qty_dict.packing_type,
		'balance_qty': flt(qty_dict.bal_qty, float_precision),
		'picked_qty': picked_qty,
		'unlocked_qty': unlocked_qty + (flt(qty_dict.bal_qty, float_precision) - picked_qty),
		'remaining_qty': flt(qty_dict.bal_qty, float_precision) - picked_qty,
		'picked_detail': get_detail_button(
			item, batch, filters,
			flt(qty_dict.bal_qty, float_precision), picked_qty,
			flt(qty_dict.bal_qty, float_precision) - picked_qty, qty_dict.lot_no),
		'opening_qty': flt(qty_dict.opening_qty, float_precision),
		'in_qty': flt(qty_dict.in_qty, float_precision),
		'out_qty': flt(qty_dict.out_qty, float_precision),
		'batch_no': batch,
		'item_group': qty_dict.item_group,
		'tile_quality': qty_dict.tile_quality,
		'item_design': qty_dict.item_design,
		'image': qty_dict.image,
		'posting_date': qty_dict.posting_date,
		'so_picked_qty': get_so_picked_qty(filters, item, batch),
	}
	if extra:
		row.update(extra)
	return row


def get_picked_values(item_pick_map, item, batch):
	batch = batch_key(batch)
	item_picks = item_pick_map.get(item)
	if not item_picks:
		return 0.0, 0.0

	if not batch:
		picked_qty = sum(flt(row.pickedqty) for row in item_picks.values())
		unlocked_qty = sum(flt(row.unlocked_qty) for row in item_picks.values())
		return picked_qty, unlocked_qty

	try:
		return item_picks[batch].pickedqty, item_picks[batch].unlocked_qty
	except KeyError:
		return 0.0, 0.0


def get_default_data(filters, iwb_map, item_pick_map, float_precision):
	data = []
	for item in iwb_map:
		for batch in sorted(iwb_map[item]):
			qty_dict = iwb_map[item][batch]
			picked_qty, unlocked_qty = get_picked_values(item_pick_map, item, batch)
			if qty_dict.opening_qty or qty_dict.in_qty or qty_dict.out_qty or qty_dict.bal_qty:
				data.append(build_row(item, batch, qty_dict, filters, picked_qty, unlocked_qty, float_precision))
	return data


def get_location_wise_data(filters, iwb_map, item_pick_map, float_precision):
	data = []
	for item in sorted(iwb_map):
		for location in sorted(iwb_map[item]):
			for batch in sorted(iwb_map[item][location]):
				qty_dict = iwb_map[item][location][batch]
				picked_qty, unlocked_qty = get_picked_values(item_pick_map, item, batch)
				if qty_dict.opening_qty or qty_dict.in_qty or qty_dict.out_qty or qty_dict.bal_qty:
					data.append(build_row(
						item, batch, qty_dict, filters, picked_qty, unlocked_qty, float_precision,
						extra={'location': qty_dict.location or ''}
					))
	return data


def get_warehouse_wise_data(filters, iwb_map, item_pick_map, float_precision):
	data = []
	for item in sorted(iwb_map):
		for wh in sorted(iwb_map[item]):
			for batch in sorted(iwb_map[item][wh]):
				qty_dict = iwb_map[item][wh][batch]
				picked_qty, unlocked_qty = get_picked_values(item_pick_map, item, batch)
				if qty_dict.opening_qty or qty_dict.in_qty or qty_dict.out_qty or qty_dict.bal_qty:
					data.append(build_row(
						item, batch, qty_dict, filters, picked_qty, unlocked_qty, float_precision,
						extra={
							'warehouse': wh,
							'company': frappe.db.get_value("Warehouse", wh, "company")
						}
					))
	return data


def get_detail_button(item, batch, filters, bal_qty, picked_qty, remaining_qty, lot_no):
	return """<button class="lot-wise-view-btn" style="margin-left:5px;border:none;color:#fff;background-color:#5e64ff;padding:3px 5px;border-radius:5px;"
		type="button"
		data-item-code="{item_code}"
		data-batch-no="{batch_no}"
		data-company="{company}"
		data-from-date="{from_date}"
		data-to-date="{to_date}"
		data-bal-qty="{bal_qty}"
		data-total-picked-qty="{picked_qty}"
		data-total-remaining-qty="{remaining_qty}"
		data-lot-no="{lot_no}">View</button>""".format(
		item_code=escape_html(cstr(item)),
		batch_no=escape_html(cstr(batch)),
		company=escape_html(cstr(filters.get("company") or "")),
		from_date=escape_html(cstr(filters.get("from_date") or "")),
		to_date=escape_html(cstr(filters.get("to_date") or "")),
		bal_qty=bal_qty,
		picked_qty=picked_qty,
		remaining_qty=remaining_qty,
		lot_no=escape_html(cstr(lot_no or "")),
	)


def get_change_location_button(row):
	return """<button class="lot-wise-change-location-btn" style="margin-left:5px;border:none;color:#fff;background-color:#5e64ff;padding:3px 5px;border-radius:5px;"
		type="button"
		data-batch-no="{batch_no}"
		data-location="{location}"
		data-item-code="{item_code}">Change Location</button>""".format(
		batch_no=escape_html(cstr(row.get("batch_no") or "")),
		location=escape_html(cstr(row.get("location") or "")),
		item_code=escape_html(cstr(row.get("item_code") or "")),
	)


def get_change_qty_button(row):
	return """<button class="lot-wise-change-qty-btn" style="margin-left:5px;border:none;color:#fff;background-color:#5e64ff;padding:3px 5px;border-radius:5px;"
		type="button"
		data-company="{company}"
		data-item-code="{item_code}"
		data-item-group="{item_group}"
		data-balance-qty="{balance_qty}"
		data-warehouse="{warehouse}"
		data-buying-unit-price="{buying_unit_price}"
		data-batch-no="{batch_no}"
		data-lot-no="{lot_no}"
		data-packing-type="{packing_type}">Change Qty</button>""".format(
		company=escape_html(cstr(row.get("company") or "")),
		item_code=escape_html(cstr(row.get("item_code") or "")),
		item_group=escape_html(cstr(row.get("item_group") or "")),
		balance_qty=row.get("balance_qty") or 0,
		warehouse=escape_html(cstr(row.get("warehouse") or "")),
		buying_unit_price=row.get("buying_unit_price") or 0,
		batch_no=escape_html(cstr(row.get("batch_no") or "")),
		lot_no=escape_html(cstr(row.get("lot_no") or "")),
		packing_type=escape_html(cstr(row.get("packing_type") or "")),
	)


def get_columns(filters):
	columns = [
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 180},
	]

	if not filters.group_item_qty:
		columns.append({"label": _("Lot No"), "fieldname": "lot_no", "fieldtype": "Data", "width": 80})

	columns += [
		{"label": _("Packing Type"), "fieldname": "packing_type", "fieldtype": "Link", "options": "Packing Type", "width": 80},
		{"label": _("Balance Qty"), "fieldname": "balance_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Unlocked Qty"), "fieldname": "unlocked_qty", "fieldtype": "Float", "width": 80},
	]

	if not filters.warehouse:
		columns += [
			{"label": _("Picked Qty"), "fieldname": "picked_qty", "fieldtype": "Float", "width": 80},
			{"label": _("Remaining Qty"), "fieldname": "remaining_qty", "fieldtype": "Float", "width": 80},
		]
		if not filters.group_item_qty:
			columns.append({"label": _("Details"), "fieldname": "picked_detail", "fieldtype": "HTML", "width": 70})

	if filters.show_location and not filters.warehouse:
		columns += [
			{"label": _("Location"), "fieldname": "location", "fieldtype": "Data", "width": 80},
		]
		if not filters.group_item_qty:
			columns.append({"label": _("Change Location"), "fieldname": "change_location", "fieldtype": "HTML", "width": 100})

	if filters.get('sales_order'):
		columns += [
			{"label": _("SO Picked Qty"), "fieldname": "so_picked_qty", "fieldtype": "Float", "width": 70, "default": 0}
		]

	if not filters.group_item_qty:
		columns.append({"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 85})
		columns.append({"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 100})

	columns += [
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 180},
		{"label": _("Quality"), "fieldname": "tile_quality", "fieldtype": "Data", "width": 70},
		{"label": _("Item Design"), "fieldname": "item_design", "fieldtype": "Data", "width": 100},
		{"label": _("Opening Qty"), "fieldname": "opening_qty", "fieldtype": "Float", "width": 80},
		{"label": _("In Qty"), "fieldname": "in_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Out Qty"), "fieldname": "out_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Image"), "fieldname": "image", "fieldtype": "Data", "width": 80},
	]

	if filters.warehouse:
		columns += [
			{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 80},
			{"label": _("Change Qty"), "fieldname": "new_qty", "fieldtype": "HTML", "width": 100},
		]

	return columns


def get_conditions(filters):
	conditions = ""
	if not filters.get("from_date"):
		frappe.throw(_("'From Date' is required"))
	if not filters.get("to_date"):
		frappe.throw(_("'To Date' is required"))

	conditions += " and sle.posting_date <= '%s'" % filters["to_date"]

	if filters.get("item_group"):
		group_placeholder = ', '.join(f"'{i}'" for i in filters["item_group"])
		conditions += " and i.item_group in (%s)" % group_placeholder

	if filters.get("item_code"):
		item_placeholder = ', '.join(f"'{i}'" for i in filters["item_code"])
		conditions += " and sle.item_code in (%s)" % item_placeholder

	if filters.get("not_in_item_code"):
		not_in_item_placeholder = ', '.join(f"'{i}'" for i in filters["not_in_item_code"])
		conditions += " and sle.item_code not in (%s)" % not_in_item_placeholder

	if filters.get("tile_quality"):
		tile_quality_placeholder = ', '.join(f"'{i}'" for i in filters["tile_quality"])
		conditions += " and i.tile_quality in (%s)" % tile_quality_placeholder

	if filters.get("packing_type"):
		packing_type_placeholder = ', '.join(f"'{i}'" for i in filters["packing_type"])
		conditions += " and batch.packing_type in (%s)" % packing_type_placeholder

	if filters.get("not_in_packing_type"):
		not_in_packing_type_placeholder = ', '.join(f"'{i}'" for i in filters["not_in_packing_type"])
		conditions += " and batch.packing_type not in (%s)" % not_in_packing_type_placeholder

	if filters.get("company"):
		conditions += " and sle.company = '%s'" % filters["company"]

	if filters.get("sales_order"):
		so_doc = frappe.get_doc("Sales Order", filters.get("sales_order"))
		so_item_list = [row.item_code for row in so_doc.items]
		so_item_list_placeholder = ', '.join(f"'{i}'" for i in so_item_list)
		conditions += " and sle.item_code in (%s)" % so_item_list_placeholder

	return conditions


def batch_key(batch_no):
	return batch_no or ""


def get_sle_batch_sql_expressions():
	batch_no = "IFNULL(NULLIF(sle.batch_no, ''), sbe.batch_no)"
	return {
		"batch_no": batch_no,
		"batch_group": f"IFNULL({batch_no}, '')",
		"actual_qty": """CASE
			WHEN IFNULL(sle.batch_no, '') != '' THEN sle.actual_qty
			WHEN sbe.name IS NOT NULL THEN sbe.qty
			ELSE sle.actual_qty
		END""",
		"sle_joins": """
			from `tabStock Ledger Entry` as sle
			JOIN `tabItem` as i on i.item_code = sle.item_code
			LEFT JOIN `tabSerial and Batch Entry` as sbe
				on sbe.parent = sle.serial_and_batch_bundle and IFNULL(sle.batch_no, '') = ''
			LEFT JOIN `tabBatch` as batch on batch.name = {batch_no}
		""".format(batch_no=batch_no),
	}


def get_stock_ledger_entries(filters):
	conditions = get_conditions(filters)
	has_batch_location = frappe.get_meta("Batch").has_field("location")
	location_field = "batch.location" if has_batch_location else "sle.warehouse"
	sql_exprs = get_sle_batch_sql_expressions()
	batch_group = sql_exprs["batch_group"]
	sle_joins = sql_exprs["sle_joins"]
	actual_qty = sql_exprs["actual_qty"]
	batch_no = sql_exprs["batch_no"]

	if filters.warehouse:
		return frappe.db.sql("""
			select sle.item_code, sle.warehouse, {location_field} as location, i.item_group, i.tile_quality, i.item_design,
				i.image as image, batch.lot_no, batch.packing_type, {batch_no} as batch_no,
				MIN(sle.posting_date) as posting_date, sum({actual_qty}) as actual_qty
			{sle_joins}
			where sle.is_cancelled = 0 and sle.docstatus < 2 %s
			group by {batch_group}, sle.item_code, sle.warehouse
			having sum({actual_qty}) != 0
			order by sle.item_code, sle.warehouse""" .format(
			location_field=location_field,
			batch_group=batch_group,
			sle_joins=sle_joins,
			actual_qty=actual_qty,
			batch_no=batch_no,
		) % conditions, as_dict=1)
	elif filters.show_location:
		return frappe.db.sql("""
			select sle.item_code, sle.warehouse, {location_field} as location, i.item_group, i.tile_quality, i.item_design,
				i.image as image, batch.lot_no, batch.packing_type, {batch_no} as batch_no,
				MIN(sle.posting_date) as posting_date, sum({actual_qty}) as actual_qty
			{sle_joins}
			where sle.is_cancelled = 0 and sle.docstatus < 2 %s
			group by {batch_group}, sle.item_code, {location_field}
			having sum({actual_qty}) != 0
			order by sle.item_code, {location_field}""" .format(
			location_field=location_field,
			batch_group=batch_group,
			sle_joins=sle_joins,
			actual_qty=actual_qty,
			batch_no=batch_no,
		) % conditions, as_dict=1)
	else:
		return frappe.db.sql("""
			select sle.item_code, i.item_group, i.tile_quality, i.item_design,
				i.image as image, batch.lot_no, batch.packing_type, {batch_no} as batch_no,
				MIN(sle.posting_date) as posting_date, sum({actual_qty}) as actual_qty
			{sle_joins}
			where sle.is_cancelled = 0 and sle.docstatus < 2 %s
			group by {batch_group}, sle.item_code
			having sum({actual_qty}) != 0
			order by i.item_group, sle.item_code""" .format(
			batch_group=batch_group,
			sle_joins=sle_joins,
			actual_qty=actual_qty,
			batch_no=batch_no,
		) % conditions, as_dict=1)


def get_item_warehouse_batch_map(filters, float_precision):
	sle = get_stock_ledger_entries(filters)
	iwb_map = {}

	from_date = getdate(filters["from_date"])
	to_date = getdate(filters["to_date"])

	for d in sle:
		batch = batch_key(d.batch_no)
		if filters.warehouse:
			iwb_map.setdefault(d.item_code, {}).setdefault(d.warehouse, {}).setdefault(
				batch, frappe._dict({"opening_qty": 0.0, "in_qty": 0.0, "out_qty": 0.0, "bal_qty": 0.0}))
			qty_dict = iwb_map[d.item_code][d.warehouse][batch]
		elif filters.show_location:
			location_key = d.location or d.warehouse
			iwb_map.setdefault(d.item_code, {}).setdefault(location_key, {}).setdefault(
				batch, frappe._dict({"opening_qty": 0.0, "in_qty": 0.0, "out_qty": 0.0, "bal_qty": 0.0}))
			qty_dict = iwb_map[d.item_code][location_key][batch]
		else:
			iwb_map.setdefault(d.item_code, {}).setdefault(
				batch, frappe._dict({"opening_qty": 0.0, "in_qty": 0.0, "out_qty": 0.0, "bal_qty": 0.0}))
			qty_dict = iwb_map[d.item_code][batch]

		if d.posting_date < from_date:
			qty_dict.opening_qty = flt(qty_dict.opening_qty, float_precision) + flt(d.actual_qty, float_precision)
		elif d.posting_date >= from_date and d.posting_date <= to_date:
			if flt(d.actual_qty) > 0:
				qty_dict.in_qty = flt(qty_dict.in_qty, float_precision) + flt(d.actual_qty, float_precision)
			else:
				qty_dict.out_qty = flt(qty_dict.out_qty, float_precision) + abs(flt(d.actual_qty, float_precision))

		qty_dict.bal_qty = flt(qty_dict.bal_qty, float_precision) + flt(d.actual_qty, float_precision)
		qty_dict.lot_no = d.lot_no
		qty_dict.item_group = d.item_group
		qty_dict.tile_quality = d.tile_quality
		qty_dict.item_design = d.item_design
		qty_dict.packing_type = d.packing_type
		qty_dict.image = d.image
		qty_dict.posting_date = d.posting_date
		qty_dict.location = getattr(d, 'location', None)

	return iwb_map


def get_picked_qty(filters, float_precision):
	picked = get_picked_items(filters)
	picked_map = {}
	for d in picked:
		batch = batch_key(d.batch_no)
		picked_map.setdefault(d.item_code, {}).setdefault(
			batch, frappe._dict({"pickedqty": 0.0, "unlocked_qty": 0.0}))
		picked_dict = picked_map[d.item_code][batch]
		picked_dict.pickedqty = flt(picked_dict.pickedqty, float_precision) + flt(d.pickedqty, float_precision)
		picked_dict.unlocked_qty += d.unlocked_qty
	return picked_map


def get_picked_items(filters):
	conditions = get_picked_conditions(filters)
	batch_join = ""
	if filters.get("packing_type") or filters.get("not_in_packing_type"):
		batch_join = "JOIN `tabBatch` as batch on batch.name = pli.batch_no"
	return frappe.db.sql(f"""
		SELECT pli.item_code, pli.batch_no,
			(pli.qty - (pli.wastage_qty + pli.delivered_qty)) as pickedqty,
			IF(so.lock_picked_qty=0, (pli.qty - (pli.wastage_qty + pli.delivered_qty)), 0) as unlocked_qty
		FROM `tabPick List Item` as pli
		JOIN `tabPick List` as pl on pli.parent = pl.name
		JOIN `tabItem` as i on i.item_code = pli.item_code
		JOIN `tabSales Order` as so on so.name = pli.sales_order
		{batch_join}
		WHERE pl.docstatus = 1 {conditions}
	""", as_dict=1)


def get_picked_conditions(filters):
	conditions = ""
	if not filters.get("to_date"):
		frappe.throw(_("'To Date' is required"))

	conditions += " and pl.posting_date <= '%s'" % filters["to_date"]

	if filters.get("item_group"):
		group_placeholder = ', '.join(f"'{i}'" for i in filters["item_group"])
		conditions += " and pli.item_group in (%s)" % group_placeholder

	if filters.get("item_code"):
		item_placeholder = ', '.join(f"'{i}'" for i in filters["item_code"])
		conditions += " and pli.item_code in (%s)" % item_placeholder

	if filters.get("not_in_item_code"):
		not_in_item_placeholder = ', '.join(f"'{i}'" for i in filters["not_in_item_code"])
		conditions += " and pli.item_code not in (%s)" % not_in_item_placeholder

	if filters.get("tile_quality"):
		tile_quality_placeholder = ', '.join(f"'{i}'" for i in filters["tile_quality"])
		conditions += " and i.tile_quality in (%s)" % tile_quality_placeholder

	if filters.get("packing_type"):
		packing_type_placeholder = ', '.join(f"'{i}'" for i in filters["packing_type"])
		conditions += " and batch.packing_type in (%s)" % packing_type_placeholder

	if filters.get("not_in_packing_type"):
		not_in_packing_type_placeholder = ', '.join(f"'{i}'" for i in filters["not_in_packing_type"])
		conditions += " and batch.packing_type not in (%s)" % not_in_packing_type_placeholder

	if filters.get("company"):
		conditions += " and pl.company = '%s'" % filters["company"]

	if filters.get("sales_order"):
		so_doc = frappe.get_doc("Sales Order", filters.get("sales_order"))
		so_item_list = [row.item_code for row in so_doc.items]
		so_item_list_placeholder = ', '.join(f"'{i}'" for i in so_item_list)
		conditions += " and pli.item_code in (%s)" % so_item_list_placeholder
		conditions += " and pli.sales_order = '%s'" % filters.get("sales_order")

	return conditions


@frappe.whitelist()
def get_picked_item(
	item_code,
	batch_no,
	company=None,
	from_date=None,
	to_date=None,
	bal_qty=0,
	total_picked_qty=0,
	total_remaining_qty=0,
	lot_no=None,
):
	conditions = ""
	if to_date:
		conditions += " and pl.posting_date <= '%s'" % to_date
	if company:
		conditions += " and pl.company = '%s'" % company

	batch_condition = "" if not batch_key(batch_no) else "AND pli.batch_no = %(batch_no)s"

	picked_items = frappe.db.sql(
		f"""
		SELECT
			pli.name as pick_list_item,
			pli.parent as pick_list,
			pli.sales_order,
			pli.sales_order_item,
			pli.customer,
			so.lock_picked_qty,
			so.transaction_date as order_date,
			IFNULL(soi.delivery_date, pli.date) as delivery_date,
			sp.sales_person_name as dispatch_person,
			so.per_picked,
			(pli.qty - pli.delivered_qty - pli.wastage_qty) as picked_qty,
			IF(so.lock_picked_qty=0, (pli.qty - pli.delivered_qty - pli.wastage_qty), 0) as unlocked_qty
		FROM `tabPick List Item` pli
		INNER JOIN `tabPick List` pl ON pli.parent = pl.name
		INNER JOIN `tabSales Order` so ON pli.sales_order = so.name
		LEFT JOIN `tabSales Order Item` soi ON pli.sales_order_item = soi.name
		LEFT JOIN `tabSales Person` sp ON sp.name = so.dispatch_person
		WHERE pl.docstatus = 1
		AND pli.item_code = %(item_code)s
		{batch_condition}
		AND (pli.qty - pli.delivered_qty - pli.wastage_qty) > 0
		{conditions}
		ORDER BY IFNULL(soi.delivery_date, pli.date), pli.name
		""",
		{"item_code": item_code, "batch_no": batch_no},
		as_dict=True,
	)

	unlocked_qty = sum(flt(row.unlocked_qty) for row in picked_items)
	float_precision = cint(frappe.db.get_default("float_precision")) or 3
	summary = frappe._dict(
		lot_no=lot_no,
		total_picked_qty=flt(total_picked_qty, float_precision),
		bal_qty=flt(bal_qty, float_precision),
		total_remaining_qty=flt(total_remaining_qty, float_precision),
		unlocked_qty=flt(unlocked_qty + flt(total_remaining_qty), float_precision),
	)

	data = [summary]
	for row in picked_items:
		row = frappe._dict(row)
		row.lock_picked_qty = _("Yes") if cint(row.lock_picked_qty) else _("No")
		row.picked_qty = flt(row.picked_qty, float_precision)
		row.order_date = formatdate(row.order_date) if row.order_date else ""
		row.delivery_date = formatdate(row.delivery_date) if row.delivery_date else ""
		row.dispatch_person = row.dispatch_person or ""
		row.per_picked_display = f"{flt(row.per_picked, 3)}%"
		row.sales_order_link = (
			f"<a href='{get_url_to_form('Sales Order', row.sales_order)}'>{row.sales_order}</a>"
		)
		row.pick_list_link = (
			f"<a href='{get_url_to_form('Pick List', row.pick_list)}'>{row.pick_list_item}</a>"
		)
		data.append(row)

	if picked_items:
		summary.customer = picked_items[0].customer

	return data


@frappe.whitelist()
def update_batch_location(batch_no, location):
	if not batch_no:
		frappe.throw(_("Batch is required"))

	frappe.db.set_value("Batch", batch_no, "location", location, update_modified=True)
	return _("Location updated for Batch {0}").format(batch_no)


@frappe.whitelist()
def create_stock_entry(company, warehouse, item_code, balance_qty, buying_unit_price, new_qty, date, time, batch_no, lot_no, packing_type):
	if float(new_qty) < 0:
		frappe.throw("Please Don't Enter Negative Qty")
	elif float(balance_qty) > float(new_qty):
		se_qty = abs(float(balance_qty) - float(new_qty))
		se = frappe.new_doc("Stock Entry")
		se.company = company
		se.stock_entry_type = "Material Issue"
		se.posting_date = frappe.utils.nowdate()
		se.posting_time = frappe.utils.nowtime()
		abbr = frappe.db.get_value('Company', company, 'abbr')
		se.from_warehouse = warehouse
		se.append("items", {
			"item_code": item_code,
			"s_warehouse": warehouse,
			"qty": se_qty,
			"batch_no": batch_no,
			"lot_no": lot_no,
			"packing_type": packing_type,
			"cost_center": f"Main - {abbr}"
		})
		try:
			se.save()
			se.submit()
			url = get_url_to_form("Stock Entry", se.name)
			frappe.msgprint("Stock Entry <b><a href='{url}'>{name}</a></b> created successfully!".format(url=url, name=frappe.bold(se.name)))
		except Exception as e:
			frappe.msgprint(str(e))
	elif float(balance_qty) < float(new_qty):
		se_qty = abs(float(balance_qty) - float(new_qty))
		se = frappe.new_doc("Stock Entry")
		se.company = company
		se.stock_entry_type = "Material Receipt"
		se.set_posting_time = 1
		se.posting_date = date or frappe.utils.nowdate()
		se.posting_time = time or frappe.utils.nowtime()
		abbr = frappe.db.get_value('Company', company, 'abbr')
		se.append("items", {
			"item_code": item_code,
			"t_warehouse": warehouse,
			"qty": se_qty,
			"basic_rate": buying_unit_price,
			"batch_no": batch_no,
			"lot_no": lot_no,
			"packing_type": packing_type,
			"cost_center": f"Main - {abbr}"
		})
		try:
			se.save()
			se.submit()
			url = get_url_to_form("Stock Entry", se.name)
			frappe.msgprint("Stock Entry <b><a href='{url}'>{name}</a></b> created successfully!".format(url=url, name=frappe.bold(se.name)))
		except Exception as e:
			frappe.throw(str(e))