import frappe
import json
from frappe import _
from frappe.utils import today, flt
from malaga.doc_events.sales_order import update_sales_order_total_values


# ─── Doc Event Hooks ──────────────────────────────────────────────────────────

def before_validate(self, method):
	"""Fixed typo: was before_vaidate"""
	update_remaining_qty(self)
	set_warehouse(self)


def validate(self, method):
	check_item_qty(self)
	update_remaining_qty(self)

	for item in self.locations:
		if item.qty < 0:
			frappe.throw(f"Row: {item.idx} Quantity can not be negative.")

		ig = frappe.db.get_value("Item", item.item_code, 'item_group')
		if ig != item.item_group:
			item.item_group = ig
   
def before_submit(self, method):
	validate_locations_have_batch(self)
	validate_sales_order(self)
	if getattr(self, 'item', None) or getattr(self, 'customer', None):
		update_available_qty(self)
	update_remaining_qty(self)
	self.picked_sales_orders = []
	self.available_qty = []
	self.sales_order_item = []


def on_submit(self, method):
	check_item_qty(self)
	update_item_so_qty(self)
	update_sales_order(self, "submit")
	update_status_sales_order(self)


def on_cancel(self, method):
	update_sales_order(self, "cancel")
	update_status_sales_order(self)


def before_update_after_submit(self, method):
	validate_item_qty(self)


# ─── Validators ───────────────────────────────────────────────────────────────

def validate_sales_order(self):
	if self.sales_order:
		status = frappe.db.get_value("Sales Order", self.sales_order, "status")
		if status in ("Closed", "Cancelled"):
			frappe.throw(_("Sales Order Cannot be closed or cancelled"))

	for item in self.sales_order_item:
		if item.sales_order:
			status = frappe.db.get_value("Sales Order", item.sales_order, "status")
			if status in ("Closed", "Cancelled"):
				frappe.throw(_(f"ROW: {item.idx} : Sales Order Cannot be closed or cancelled"))


def check_item_qty(self):
    for item in self.available_qty:
        if item.remaining_qty < 0:
            frappe.throw(f"Row {item.idx}: Remaining Qty Less than 0")


def validate_item_qty(self):
	for row in self.locations:
		if row.qty < flt(row.delivered_qty + row.wastage_qty):
			frappe.throw(f"Row {row.idx}: Qty can not be less than delivered qty {flt(row.delivered_qty + row.wastage_qty)}")
		if row.qty > row.so_qty:
			frappe.throw(f"Row {row.idx}: Qty can not be greater than sales order qty {row.so_qty}")


# ─── Core Helpers ─────────────────────────────────────────────────────────────

def remove_items_without_batch_no(self):
	if self.locations:
		self.locations = [item for item in self.locations if item.batch_no]


def validate_locations_have_batch(self):
	if not self.locations:
		frappe.throw(_("Please add at least one item in Item Locations."))

	for item in self.locations:
		has_batch_no = frappe.db.get_value("Item", item.item_code, "has_batch_no")
		if has_batch_no and not item.batch_no:
			frappe.throw(
				_("Row {0}: Please select Batch No for Item {1} before submitting.").format(
					item.idx, frappe.bold(item.item_code)
				)
			)
		if not item.warehouse:
			frappe.throw(
				_("Row {0}: Please select Warehouse for Item {1} before submitting.").format(
					item.idx, frappe.bold(item.item_code)
				)
			)


def update_remaining_qty(self):
	sales_order_item_list = list(set([row.sales_order_item for row in self.locations if row.sales_order_item]))

	for sales_order_item in sales_order_item_list:
		rows = [item for item in self.locations if item.sales_order_item == sales_order_item]
		total_qty = sum(flt(item.qty) for item in rows)
		so_qty = flt(rows[0].so_qty)
		picked_qty = flt(rows[0].picked_qty)
		remaining = so_qty - picked_qty - total_qty

		if remaining < 0:
			frappe.throw(
				_(f"ROW: {rows[0].idx} : Remaining Qty Cannot be less than 0.")
			)

		for item in rows:
			item.remaining_qty = remaining


def update_delivered_percent(self):
	qty = 0
	delivered_qty = 0
	if self.locations:
		for index, item in enumerate(self.locations):
			qty += item.qty
			delivered_qty += item.delivered_qty
			item.db_set('idx', index + 1)

		try:
			self.db_set('per_delivered', (delivered_qty / qty) * 100)
		except Exception:
			self.db_set('per_delivered', 0)





def update_available_qty(self):
    self.available_qty = []
    data = get_item_qty(self.company, self.item, self.customer, self.sales_order)
    for item in data:
        self.append('available_qty', {
            'item_code': item.item_code,
            'batch_no': item.batch_no,
            'lot_no': item.lot_no,
            'total_qty': item.total_qty,
            'picked_qty': item.picked_qty,
            'available_qty': item.available_qty,
            'remaining_qty': item.available_qty,  # was 'remaining'
            'picked_in_current': 0,
        })

    for i in self.available_qty:
        qty = 0
        for j in self.locations:
            if i.item_code == j.item_code and i.batch_no == j.batch_no:
                qty += j.qty
        i.picked_in_current = qty
        i.remaining_qty -= qty  # was i.remaining -= qty

        if i.remaining_qty < 0:
            frappe.throw(_(f"Remaining Qty Cannot be less than 0 ({i.remaining_qty}) for item {i.item_code} and lot {getattr(i, 'lot_no', '')}"))


def update_status_sales_order(self):
	sales_order_list = list(set([item.sales_order for item in self.locations if item.sales_order]))

	for sales_order in sales_order_list:
		so = frappe.get_doc("Sales Order", sales_order)
		update_sales_order_total_values(so)
		qty = 0
		picked_qty = 0

		for item in so.items:
			qty += item.qty
			picked_qty += item.picked_qty

		if qty:
			so.db_set('per_picked', (picked_qty / qty) * 100)


# ─── Sales Order qty update on submit ────────────────────────────────────────

def update_item_so_qty(self):
	from malaga.update_item import update_child_qty_rate
	for item in self.locations:
		doc = frappe.get_doc("Sales Order Item", item.sales_order_item)
		parent_doc = frappe.get_doc("Sales Order", item.sales_order)
		data = []

		for row in parent_doc.items:
			if row.name != item.sales_order_item:
				data.append({
					'docname': row.name,
					'name': row.name,
					'item_code': row.item_code,
					'qty': row.qty,
					'rate': row.rate,
					'discounted_rate': row.discounted_rate,
					'real_qty': row.real_qty
				})
			else:
				data.append({
					'docname': row.name,
					'name': row.name,
					'item_code': row.item_code,
					'qty': item.so_qty,
					'rate': row.rate,
					'discounted_rate': row.discounted_rate,
					'real_qty': item.so_real_qty
				})

		update_child_qty_rate("Sales Order", json.dumps(data), doc.parent)


def update_sales_order(self, method):
	if method == "submit":
		for item in self.locations:
			if frappe.db.exists("Sales Order Item", item.sales_order_item):
				so_qty, so_picked_qty, so_delivered_without_pick = frappe.db.get_value(
					"Sales Order Item",
					item.sales_order_item,
					['qty', 'picked_qty', 'delivered_without_pick']
				)
				picked_qty = flt(so_picked_qty) + flt(item.qty) + flt(so_delivered_without_pick)

				if picked_qty > so_qty:
					frappe.throw("Can not pick item {} in row {} more than {}".format(
						item.item_code, item.idx, flt(item.qty) - flt(item.picked_qty)
					))

				frappe.db.set_value("Sales Order Item", item.sales_order_item, 'picked_qty', picked_qty)

				if picked_qty > 0:
					pick_qty_comment(item.sales_order, f"Picked Qty {picked_qty} from item {item.item_code}")

			if item.sales_order:
				so = frappe.get_doc("Sales Order", item.sales_order)
				total_picked_qty = 0.0
				total_picked_weight = 0.0
				for row in so.items:
					row.db_set('picked_weight', flt(row.weight_per_unit * row.picked_qty))
					total_picked_qty += flt(row.picked_qty)			# Fixed: was just = not +=
					total_picked_weight += flt(row.picked_weight)

				so.db_set('total_picked_qty', total_picked_qty)
				so.db_set('total_picked_weight', total_picked_weight)

	if method == "cancel":
		for item in self.locations:
			if frappe.db.exists("Sales Order Item", {'name': item.sales_order_item, 'parent': item.sales_order}):
				tile = frappe.get_doc("Sales Order Item", {'name': item.sales_order_item, 'parent': item.sales_order})
				picked_qty = flt(tile.picked_qty) - flt(item.qty)

				if tile.picked_qty < 0:
					frappe.throw("Row {}: All Items Already Cancelled".format(item.idx))

				tile.db_set('picked_qty', picked_qty)

			if item.sales_order:
				so = frappe.get_doc("Sales Order", item.sales_order)
				total_picked_qty = 0.0
				total_picked_weight = 0.0
				for row in so.items:
					row.db_set('picked_weight', flt(row.weight_per_unit * row.picked_qty))
					total_picked_qty += flt(row.picked_qty)			# Fixed: was = not +=
					total_picked_weight += flt(row.picked_weight)

				so.db_set('total_picked_qty', total_picked_qty)
				so.db_set('total_picked_weight', total_picked_weight)


# ─── Comment Helpers ──────────────────────────────────────────────────────────

def pick_qty_comment(sales_order, data):
	comment = frappe.new_doc("Comment")
	comment.comment_type = "Info"
	comment.comment_email = frappe.session.user
	comment.reference_doctype = "Sales Order"
	comment.reference_name = sales_order
	comment.content = data
	comment.save()


def unpick_qty_comment(reference_name, sales_order, data):
	comment_pl = frappe.new_doc("Comment")
	comment_pl.comment_type = "Info"
	comment_pl.comment_email = frappe.session.user
	comment_pl.reference_doctype = "Pick List"
	comment_pl.reference_name = reference_name
	comment_pl.content = data
	comment_pl.save()

	comment_so = frappe.new_doc("Comment")
	comment_so.comment_type = "Info"
	comment_so.comment_email = frappe.session.user
	comment_so.reference_doctype = "Sales Order"
	comment_so.reference_name = sales_order
	comment_so.content = data
	comment_so.save()


# ─── Whitelisted APIs ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_item_qty(company, item_code=None, customer=None, sales_order=None):
	if not item_code and not customer and not sales_order:
		return []

	batch_locations = []
	where_cond = f" AND soi.parent = {frappe.db.escape(sales_order)}" if sales_order else ''

	if customer:
		item_code_list = frappe.db.sql("""
			SELECT DISTINCT soi.item_code
			FROM `tabSales Order Item` AS soi
			JOIN `tabSales Order` AS so ON so.name = soi.parent
			WHERE so.docstatus = 1
			AND so.customer = %(customer)s
			AND soi.qty != soi.picked_qty
			AND so.status != 'Closed'
		""" + where_cond, {'customer': customer})
		item_codes = [i[0] for i in item_code_list]

		if item_code and item_code not in item_codes:
			frappe.throw(_(f"Item {item_code} is not in any sales order for Customer {customer}"))

	if sales_order:
		item_code_list = frappe.db.sql("""
			SELECT DISTINCT soi.item_code
			FROM `tabSales Order Item` AS soi
			JOIN `tabSales Order` AS so ON so.name = soi.parent
			WHERE so.docstatus = 1
			AND soi.qty != soi.picked_qty
			AND so.status != 'Closed'
		""" + where_cond, {})
		item_codes = [i[0] for i in item_code_list]

	if item_code:
		item_codes = [item_code]

	if not item_codes:
		return []

	for item in item_codes:
		rows = frappe.db.sql("""
			SELECT
				sle.item_code,
				sle.batch_no,
				batch.lot_no,
				SUM(sle.actual_qty) AS actual_qty
			FROM `tabStock Ledger Entry` sle
			JOIN `tabBatch` batch ON batch.name = sle.batch_no
			WHERE sle.is_cancelled = 0
			AND sle.item_code = %(item_code)s
			AND sle.company = %(company)s
			AND IFNULL(batch.expiry_date, '2200-01-01') > %(today)s
			GROUP BY sle.batch_no, sle.item_code
			HAVING SUM(sle.actual_qty) > 0
			ORDER BY IFNULL(batch.expiry_date, '2200-01-01'), batch.creation
		""", {'item_code': item, 'company': company, 'today': today()}, as_dict=1)
		batch_locations += rows

	for item in batch_locations:
		item['item_name'] = frappe.db.get_value('Item', item['item_code'], 'item_name')

		# Fixed: SQL aggregate in frappe.db.get_all not allowed — use raw sql
		pick_list_available = frappe.db.sql("""
			SELECT IFNULL(SUM(pli.qty - pli.delivered_qty - pli.wastage_qty), 0)
			FROM `tabPick List Item` AS pli
			JOIN `tabPick List` AS pl ON pl.name = pli.parent
			WHERE pli.item_code = %(item_code)s
			AND pli.batch_no = %(batch_no)s
			AND pl.docstatus = 1
		""", {'item_code': item['item_code'], 'batch_no': item['batch_no']})

		item['picked_qty'] = flt(pick_list_available[0][0]) if pick_list_available else 0.0
		item['available_qty'] = flt(item['actual_qty']) - item['picked_qty']
		item['to_pick_qty'] = item['available_qty']
		item['total_qty'] = item['actual_qty']

	return batch_locations


@frappe.whitelist()
def get_item_from_sales_order(company, item_code=None, customer=None, sales_order=None):
	if not item_code and not customer and not sales_order:
		return []

	where_clause = ''
	where_cond = f" AND soi.parent = {frappe.db.escape(sales_order)}" if sales_order else ''
	item_codes = []

	if customer:
		item_code_list = frappe.db.sql("""
			SELECT DISTINCT soi.item_code
			FROM `tabSales Order Item` AS soi
			JOIN `tabSales Order` AS so ON so.name = soi.parent
			WHERE so.docstatus = 1
			AND so.customer = %(customer)s
			AND soi.qty != soi.picked_qty
			AND so.status != 'Closed'
		""" + where_cond, {'customer': customer})
		where_clause += " AND so.customer = %(customer)s"
		item_codes = [i[0] for i in item_code_list]

		if item_code and item_code not in item_codes:
			frappe.throw(_(f"Item {item_code} is not in any sales order for Customer {customer}"))

	if sales_order:
		item_code_list = frappe.db.sql("""
			SELECT DISTINCT soi.item_code
			FROM `tabSales Order Item` AS soi
			JOIN `tabSales Order` AS so ON so.name = soi.parent
			WHERE so.docstatus = 1
			AND soi.qty != soi.picked_qty
			AND so.status != 'Closed'
		""" + where_cond, {})
		where_clause += " AND so.name = %(sales_order)s"
		item_codes = [i[0] for i in item_code_list]

		if item_code and item_code not in item_codes:
			frappe.throw(_(f"Item {item_code} is not in sales order {sales_order}"))

	if item_code:
		item_codes = [item_code]

	if not item_codes:
		return []

	sales_order_list = []
	params = {'company': company}
	if customer:
		params['customer'] = customer
	if sales_order:
		params['sales_order'] = sales_order

	for item in item_codes:
		params['item_code'] = item
		rows = frappe.db.sql("""
			SELECT
				so.name AS sales_order,
				soi.delivered_without_pick,
				so.customer,
				so.transaction_date,
				so.delivery_date,
				soi.packing_type,
				so.per_picked,
				so.order_item_priority,
				so.order_rank,
				soi.name AS sales_order_item,
				soi.item_code,
				soi.picked_qty,
				soi.qty - soi.delivered_without_pick - soi.picked_qty AS qty,
				soi.qty AS so_qty,
				soi.real_qty,
				soi.uom,
				soi.stock_qty,
				soi.stock_uom,
				soi.conversion_factor
			FROM `tabSales Order Item` AS soi
			JOIN `tabSales Order` AS so ON soi.parent = so.name
			WHERE soi.item_code = %(item_code)s
			AND so.company = %(company)s
			AND so.docstatus = 1
			AND soi.qty > soi.picked_qty
			AND so.status NOT IN ('Closed','Completed','Cancelled','On Hold')
		""" + where_clause + " ORDER BY soi.order_item_priority DESC", params, as_dict=1)
		sales_order_list += rows

	return sales_order_list


@frappe.whitelist()
def get_pick_list_so(sales_order, item_code, sales_order_item):
	pick_list_list = frappe.db.sql("""
		SELECT
			pli.sales_order,
			pli.sales_order_item,
			pli.customer,
			pli.name AS pick_list_item,
			batch.packing_type,
			pli.date,
			pli.item_code,
			pli.qty,
			pli.qty - pli.delivered_qty - pli.wastage_qty AS picked_qty,
			pli.delivered_qty,
			pli.wastage_qty,
			pli.batch_no,
			pli.lot_no,
			pli.uom,
			pli.stock_qty,
			pli.stock_uom,
			pli.conversion_factor,
			pli.name,
			pli.parent
		FROM `tabPick List Item` AS pli
		JOIN `tabBatch` AS batch ON batch.name = pli.batch_no
		WHERE pli.item_code = %(item_code)s
		AND pli.sales_order = %(sales_order)s
		AND pli.sales_order_item = %(sales_order_item)s
		AND pli.docstatus = 1
	""", {
		'item_code': item_code,
		'sales_order': sales_order,
		'sales_order_item': sales_order_item
	}, as_dict=1)

	result = []
	for item in pick_list_list:
		actual_qty_data = frappe.db.sql("""
			SELECT IFNULL(SUM(sle.actual_qty), 0)
			FROM `tabStock Ledger Entry` sle
			JOIN `tabBatch` batch ON batch.name = sle.batch_no
			WHERE sle.is_cancelled = 0
			AND sle.item_code = %(item_code)s
			AND sle.batch_no = %(batch_no)s
			GROUP BY sle.batch_no
			HAVING SUM(sle.actual_qty) > 0
		""", {'item_code': item_code, 'batch_no': item.batch_no})

		actual_qty = flt(actual_qty_data[0][0]) if actual_qty_data else 0

		pick_list_available_data = frappe.db.sql("""
			SELECT IFNULL(SUM(pli.qty - pli.delivered_qty - pli.wastage_qty), 0)
			FROM `tabPick List Item` AS pli
			JOIN `tabPick List` AS pl ON pl.name = pli.parent
			WHERE pli.item_code = %(item_code)s
			AND pli.batch_no = %(batch_no)s
			AND pl.docstatus = 1
		""", {'item_code': item_code, 'batch_no': item.batch_no})

		pick_list_available = flt(pick_list_available_data[0][0]) if pick_list_available_data else 0

		item.available_qty = actual_qty - pick_list_available + flt(item.picked_qty)
		item.actual_qty = actual_qty

		# Fixed: was returning unfiltered list — now only return items with remaining qty
		if flt(item.qty) > flt(item.delivered_qty) + flt(item.wastage_qty):
			result.append(item)

	return result


@frappe.whitelist()
def get_items(filters):
	from six import string_types

	if isinstance(filters, string_types):
		filters = json.loads(filters)

	item_code = filters.get("item_code")
	company = filters.get("company")
	to_pick_qty = flt(filters.get("to_pick_qty"))

	if not item_code:
		frappe.throw("Item Code is required")

	if not company:
		frappe.throw("Company is required")

	# Get item details
	item_details = frappe.db.get_value(
		"Item",
		item_code,
		["item_name"],
		as_dict=True
	)

	if not item_details:
		return []

	item_name = item_details.item_name

	# Stock Query (NO BATCH)
	stock_locations = frappe.db.sql("""
		SELECT
			sle.item_code,
			sle.warehouse,
			SUM(sle.actual_qty) AS actual_qty
		FROM `tabStock Ledger Entry` sle
		WHERE
			sle.is_cancelled = 0
			AND sle.item_code = %(item_code)s
			AND sle.company = %(company)s
		GROUP BY
			sle.item_code,
			sle.warehouse
		HAVING SUM(sle.actual_qty) > 0
		ORDER BY sle.warehouse
	""", {
		"item_code": item_code,
		"company": company
	}, as_dict=True)

	data = []

	for item in stock_locations:

		# Picked Qty
		picked_qty = frappe.db.sql("""
			SELECT
				IFNULL(SUM(
					pli.qty
					- IFNULL(pli.delivered_qty, 0)
					- IFNULL(pli.wastage_qty, 0)
				), 0)
			FROM `tabPick List Item` pli
			INNER JOIN `tabPick List` pl
				ON pl.name = pli.parent
			WHERE
				pl.docstatus = 1
				AND pli.item_code = %(item_code)s
				AND pli.warehouse = %(warehouse)s
		""", {
			"item_code": item_code,
			"warehouse": item["warehouse"]
		})[0][0]

		actual_qty = flt(item.actual_qty)
		picked_qty = flt(picked_qty)

		available_qty = actual_qty - picked_qty

		if available_qty <= 0:
			continue

		data.append({
			"item_code": item.item_code,
			"item_name": item_name,
			"warehouse": item.warehouse,
			"actual_qty": actual_qty,
			"picked_qty": picked_qty,
			"available_qty": available_qty,
			"to_pick_qty": min(available_qty, to_pick_qty)
		})

	return data



@frappe.whitelist()
def get_sales_order_items(sales_order):
    doc = frappe.get_doc("Sales Order", sales_order)
    items = []
    for item in doc.items:
        wastage_qty = getattr(item, 'wastage_qty', 0) or 0
        delivered_real_qty = getattr(item, 'delivered_real_qty', 0) or 0
        real_qty = getattr(item, 'real_qty', item.qty) or item.qty
        sqf_rate = getattr(item, 'sqf_rate', 0) or 0
        discounted_rate = getattr(item, 'discounted_rate', 0) or 0
        picked_qty = getattr(item, 'picked_qty', 0) or 0
        delivered_without_pick = getattr(item, 'delivered_without_pick', 0) or 0
        packing_type = getattr(item, 'packing_type', None)

        items.append({
            'sales_order': doc.name,
            'sales_order_item': item.name,
            'qty': item.qty - wastage_qty - item.delivered_qty,
            'real_qty': real_qty - delivered_real_qty,
            'item_code': item.item_code,
            'rate': item.rate,
            'sqf_rate': sqf_rate,
            'discounted_rate': discounted_rate,
            'picked_qty': picked_qty + delivered_without_pick - item.delivered_qty,
            'delivered_qty': item.delivered_qty,
            'wastage_qty': wastage_qty,
            'delivered_real_qty': delivered_real_qty,
            'packing_type': packing_type,
            'order_rank': getattr(doc, 'order_rank', 0) or 0,
            'delivered_without_pick': delivered_without_pick
        })
    return items


@frappe.whitelist()
def update_pick_list(items):
	picked_items = json.loads(items)
	for item in picked_items:
		pick_list_item_doc = frappe.get_doc("Pick List Item", item['pick_list_item'])
		picked_qty_old = pick_list_item_doc.qty
		diff_qty = picked_qty_old - flt(item['picked_qty'])

		if diff_qty:
			unpick_item(
				pick_list_item_doc.sales_order,
				sales_order_item=pick_list_item_doc.sales_order_item,
				pick_list=pick_list_item_doc.parent,
				pick_list_item=pick_list_item_doc.name,
				unpick_qty=diff_qty
			)
	return 'success'


@frappe.whitelist()
def correct_picked_qty(sales_order):
	so = frappe.get_doc("Sales Order", sales_order)

	for item in so.items:
		# Fixed: SQL aggregate string not allowed in frappe.db.get_value — use raw sql
		result = frappe.db.sql("""
			SELECT IFNULL(SUM(qty - wastage_qty), 0)
			FROM `tabPick List Item`
			WHERE sales_order = %(sales_order)s
			AND sales_order_item = %(sales_order_item)s
			AND docstatus = 1
			AND item_code = %(item_code)s
		""", {
			'sales_order': sales_order,
			'sales_order_item': item.name,
			'item_code': item.item_code
		})

		picked_qty = flt(result[0][0]) if result else 0.0
		frappe.db.set_value("Sales Order Item", item.name, 'picked_qty', picked_qty)

	update_sales_order_total_values(frappe.get_doc("Sales Order", sales_order))
	return "Pick List for this Sales Order has been corrected."


@frappe.whitelist()
def unpick_picked_qty_sales_order(sales_order, sales_order_item, item_code):
	unpick_item(sales_order, sales_order_item=sales_order_item)
	correct_picked_qty(sales_order)


@frappe.whitelist()
def unpick_item_1(sales_order, sales_order_item=None, pick_list=None, pick_list_item=None, unpick_qty=None):
	"""Wrapper with proper error logging"""
	try:
		return unpick_item(sales_order, sales_order_item, pick_list, pick_list_item, unpick_qty)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "unpick_item_1 failed")
		return "Error"


@frappe.whitelist()
def unpick_item(sales_order, sales_order_item=None, pick_list=None, pick_list_item=None, unpick_qty=None, sales_order_differnce_qty=0.0):
	user = frappe.get_doc("User", frappe.session.user)
	role_list = [r.role for r in user.roles]

	if frappe.db.get_value("Sales Order", sales_order, 'lock_picked_qty'):
		dispatch_person_user = frappe.db.get_value(
			"Sales Person",
			frappe.db.get_value("Sales Order", sales_order, 'dispatch_person'),
			'user'
		)
		if dispatch_person_user:
			if user.name != dispatch_person_user and 'Local Admin' not in role_list and 'Sales Head' not in role_list:
				return "Only {} is allowed to unpick".format(dispatch_person_user)

	# ── Case 1: specific pick list item ──────────────────────────────────────
	if pick_list_item and pick_list:
		unpick_qty = flt(unpick_qty)
		doc = frappe.get_doc("Pick List Item", pick_list_item)
		original_picked = doc.qty
		soi_doc = frappe.get_doc("Sales Order Item", sales_order_item)

		if not unpick_qty:
			diff_qty = flt(doc.qty) - flt(doc.delivered_qty) - flt(doc.wastage_qty)
			doc.db_set('qty', flt(doc.qty) - diff_qty)

			if diff_qty == 0:
				frappe.throw(_("Cannot unpick — Delivery Note already exists for this item."))

			picked_qty = frappe.db.get_value("Sales Order Item", doc.sales_order_item, 'picked_qty')
			soi_doc.db_set('picked_qty', flt(picked_qty) - diff_qty)

			if not doc.delivered_qty and not doc.wastage_qty:
				doc.cancel()
				doc.delete()

			if diff_qty > 0:
				unpick_qty_comment(doc.parent, doc.sales_order, f"Unpicked Qty {diff_qty} / {original_picked} from item {doc.item_code}")

		elif unpick_qty > 0:
			if unpick_qty > flt(doc.qty) - flt(doc.wastage_qty) - flt(doc.delivered_qty):
				frappe.throw(f"Cannot unpick qty {unpick_qty} — higher than remaining pick qty {flt(doc.qty) - flt(doc.wastage_qty) - flt(doc.delivered_qty)}")

			doc.db_set('qty', flt(doc.qty) - unpick_qty)
			soi_doc.db_set('picked_qty', flt(soi_doc.picked_qty) - unpick_qty)
			unpick_qty_comment(doc.parent, doc.sales_order, f"Unpicked Qty {unpick_qty} / {original_picked} from item {doc.item_code}")

		elif unpick_qty < 0:
			# Increasing pick qty — check available stock
			actual_qty_data = frappe.db.sql("""
				SELECT IFNULL(SUM(sle.actual_qty), 0)
				FROM `tabStock Ledger Entry` sle
				JOIN `tabBatch` batch ON batch.name = sle.batch_no
				WHERE sle.is_cancelled = 0
				AND sle.item_code = %(item_code)s
				AND sle.batch_no = %(batch_no)s
				GROUP BY sle.batch_no
				HAVING SUM(sle.actual_qty) > 0
			""", {'item_code': soi_doc.item_code, 'batch_no': doc.batch_no})

			if not actual_qty_data:
				frappe.throw(f"No stock available for batch {doc.batch_no}")

			actual_qty = flt(actual_qty_data[0][0])

			pick_list_available_data = frappe.db.sql("""
				SELECT IFNULL(SUM(pli.qty - pli.delivered_qty - pli.wastage_qty), 0)
				FROM `tabPick List Item` AS pli
				JOIN `tabPick List` AS pl ON pl.name = pli.parent
				WHERE pli.item_code = %(item_code)s
				AND pli.batch_no = %(batch_no)s
				AND pl.docstatus = 1
			""", {'item_code': soi_doc.item_code, 'batch_no': doc.batch_no})

			pick_list_available = flt(pick_list_available_data[0][0]) if pick_list_available_data else 0
			available_qty = actual_qty - pick_list_available + flt(doc.qty)

			if available_qty < flt(doc.qty) - unpick_qty:
				frappe.throw(f"Qty cannot be greater than available qty {available_qty} in Lot {doc.lot_no}")

			doc.db_set('qty', flt(doc.qty) - unpick_qty)
			soi_doc.db_set('picked_qty', flt(soi_doc.picked_qty) - unpick_qty)

		update_delivered_percent(frappe.get_doc("Pick List", doc.parent))
		update_sales_order_total_values(frappe.get_doc("Sales Order", doc.sales_order))

	# ── Case 2: sales order item level ───────────────────────────────────────
	elif sales_order and sales_order_item:
		data = frappe.get_all(
			"Pick List Item",
			{'sales_order': sales_order, 'sales_order_item': sales_order_item, 'docstatus': 1},
			['name']
		)

		remaining_diff = flt(sales_order_differnce_qty)

		for pl in data:
			if sales_order_differnce_qty and not remaining_diff:
				break

			doc = frappe.get_doc("Pick List Item", pl.name)
			original_picked = doc.qty
			soi_doc = frappe.get_doc("Sales Order Item", doc.sales_order_item)
			diff_qty = flt(doc.qty) - flt(doc.delivered_qty) - flt(doc.wastage_qty)

			if sales_order_differnce_qty:
				if remaining_diff >= diff_qty:
					remaining_diff -= diff_qty
				else:
					diff_qty = remaining_diff
					remaining_diff = 0

				doc.db_set('qty', flt(doc.qty) - diff_qty)

				if not doc.delivered_qty and not doc.wastage_qty and not flt(doc.qty):
					if doc.docstatus == 1:
						doc.cancel()
					doc.delete()
			else:
				doc.db_set('qty', flt(doc.qty) - diff_qty)
				soi_doc.db_set('picked_qty', flt(soi_doc.picked_qty) - diff_qty)

				if not doc.delivered_qty and not doc.wastage_qty:
					if doc.docstatus == 1:
						doc.cancel()
					doc.delete()

			if diff_qty > 0:
				unpick_qty_comment(doc.parent, doc.sales_order, f"Unpicked Qty {diff_qty} / {original_picked} from item {doc.item_code}")

			update_delivered_percent(frappe.get_doc("Pick List", doc.parent))
			if not sales_order_differnce_qty:
				update_sales_order_total_values(frappe.get_doc("Sales Order", doc.sales_order))

	# ── Case 3: entire sales order ────────────────────────────────────────────
	else:
		data = frappe.get_all(
			"Pick List Item",
			{'sales_order': sales_order, 'docstatus': 1},
			['name']
		)
		for pl in data:
			doc = frappe.get_doc("Pick List Item", pl.name)
			soi_doc = frappe.get_doc("Sales Order Item", doc.sales_order_item)
			original_picked = doc.qty
			diff_qty = flt(doc.qty) - flt(doc.delivered_qty) - flt(doc.wastage_qty)

			doc.db_set('qty', flt(doc.qty) - diff_qty)
			soi_doc.db_set('picked_qty', flt(soi_doc.picked_qty) - diff_qty)

			if not doc.delivered_qty and not doc.wastage_qty:
				if doc.docstatus == 1:
					doc.cancel()
				doc.delete()

			if diff_qty > 0:
				unpick_qty_comment(doc.parent, doc.sales_order, f"Unpicked Qty {diff_qty} / {original_picked} from item {doc.item_code}")

			update_delivered_percent(frappe.get_doc("Pick List", doc.parent))

		update_sales_order_total_values(frappe.get_doc("Sales Order", sales_order))

	return "Pick List for this Sales Order has been updated."

def set_warehouse(self):
    for item in self.locations:
        if not item.warehouse:
            if self.parent_warehouse:
                item.warehouse = self.parent_warehouse
        has_batch_no = frappe.db.get_value("Item", item.item_code, "has_batch_no")
        if has_batch_no:
            item.use_serial_batch_fields = has_batch_no