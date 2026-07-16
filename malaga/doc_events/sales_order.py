import frappe
import datetime
from frappe import _
from frappe.utils import flt, cint
from frappe.model.mapper import get_mapped_doc
from frappe.contacts.doctype.address.address import get_company_address
from erpnext.accounts.party import get_party_details
import math


# ─── Doc Event Hooks ──────────────────────────────────────────────────────────

def before_submit(self, method):
	validate_taxes_and_charges(self)


def before_validate(self, method):
	set_dispatch_person_mobile(self)
	ignore_permission(self)
	setting_real_qty(self)
	if not getattr(self, 'primary_customer', None):
		self.primary_customer = self.customer
	update_tax_paid_check_in_taxes(self)


def validate(self, method):
	calculate_order_priority(self)
	calculate_rate(self)
	update_discounted_amount(self)
	update_discounted_net_total(self)


def on_submit(self, method):
	create_main_sales_order(self)
	checking_real_qty(self)
	update_sales_order_total_values(self)
	update_order_rank(self)


def before_cancel(self, method):
	cancel_main_sales_order(self)


def on_cancel(self, method):
	remove_pick_list(self)
	update_sales_order_total_values(self)


def before_validate_after_submit(self, method):
	setting_real_qty(self)
	calculate_order_priority(self)
	update_discounted_amount(self)
	update_idx(self)


def validate_after_submit(self, method):
	update_discounted_net_total(self)


def before_update_after_submit(self, method):
	setting_real_qty(self)
	calculate_order_priority(self)
	self.calculate_taxes_and_totals()
	update_discounted_amount(self)
	update_idx(self)
	update_discounted_net_total(self)
	update_order_rank(self)
	update_linked_order(self)
	update_comment(self)


def on_update_after_submit(self, method):
	calculate_rate(self)
	delete_pick_list(self)
	update_sales_order_total_values(self)
	update_order_rank(self)
	update_item_series(self)
	update_taxes_and_charges(self)


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def ignore_permission(self):
	self.flags.ignore_permissions = True
	if not self.order_priority:
		self.order_priority = frappe.db.get_value("Customer", self.customer, 'customer_priority')
	if self._action == "update_after_submit":
		self.flags.ignore_validate_update_after_submit = True


def setting_real_qty(self):
	for item in self.items:
		if not item.real_qty:
			item.real_qty = item.qty


def calculate_order_priority(self):
	for item in self.items:
		try:
			try:
				days = ((datetime.date.today() - datetime.datetime.strptime(self.transaction_date, '%Y-%m-%d').date()) // datetime.timedelta(days=1)) + 1
			except Exception:
				try:
					days = ((datetime.date.today() - datetime.datetime.strptime(str(self.transaction_date), '%Y-%m-%d %H:%M:%S').date()) // datetime.timedelta(days=1)) + 1
				except Exception:
					days = ((datetime.date.today() - datetime.datetime.strptime(str(self.transaction_date), '%Y-%m-%d').date()) // datetime.timedelta(days=1)) + 1
		except Exception:
			days = ((datetime.date.today() - self.transaction_date) // datetime.timedelta(days=1)) + 1

		days = 1 if days <= 0 else days
		base_factor = 4
		item.order_item_priority = cint((days * (base_factor ** (cint(self.order_priority) - 1))) + cint(self.order_priority))

	if self.items:
		self.order_item_priority = self.items[0].order_item_priority


def update_order_rank(self):
	result = frappe.db.sql("""
		SELECT order_rank, ABS(order_item_priority - %(priority)s) AS difference
		FROM `tabSales Order`
		WHERE status NOT IN ('Completed', 'Draft', 'Cancelled')
		AND order_rank > 0
		HAVING difference > 0
		ORDER BY difference
		LIMIT 1
	""", {'priority': self.order_item_priority})

	order_rank = result[0][0] if result else 0
	self.db_set('order_rank', order_rank)


def update_discounted_amount(self):
	for item in self.items:
		item.discounted_rate = item.discounted_rate or 0
		item.real_qty = item.real_qty or 0
		item.discounted_amount = item.discounted_rate * flt(item.real_qty)
		item.discounted_net_amount = item.discounted_amount


def update_discounted_net_total(self):
	self.discounted_total = sum(x.discounted_amount for x in self.items)
	self.discounted_net_total = sum(x.discounted_net_amount for x in self.items)
	testing_only_tax = 0

	for tax in self.taxes:
		if getattr(tax, 'testing_only', 0):
			testing_only_tax += tax.tax_amount

	self.discounted_grand_total = self.discounted_net_total + self.total_taxes_and_charges - testing_only_tax
	self.discounted_rounded_total = round(self.discounted_grand_total)
	self.real_difference_amount = self.rounded_total - self.discounted_rounded_total


def checking_real_qty(self):
	alternate_company = frappe.db.get_value("Company", self.company, 'alternate_company')
	for item in self.items:
		if not item.real_qty:
			frappe.msgprint(_(f"Row {item.idx}: You will not be able to make invoice in company {alternate_company}."))


def update_taxes_and_charges(self):
	get_tax_template_name = get_tax_template(self.tax_category, self.company, self.tax_paid)
	if get_tax_template_name:
		self.taxes_and_charges = get_tax_template_name


def update_comment(self):
	field_list = ['lock_picked_qty', 'delivery_date']
	for field in field_list:
		current_val = frappe.db.get_value("Sales Order", self.name, field)
		if str(self.get(field)) != str(current_val):
			comment = frappe.new_doc("Comment")
			comment.comment_type = "Info"
			comment.comment_email = frappe.session.user
			comment.reference_doctype = "Sales Order"
			comment.reference_name = self.name
			comment.content = f"Changed {field} from {current_val} to {self.get(field)}"
			comment.save()


def update_item_series(self):
	for item in self.items:
		item_series = frappe.db.get_value("Item", item.item_code, "item_series")
		if item_series != item.item_series:
			frappe.db.set_value("Sales Order Item", item.name, "item_series", item_series)


def update_linked_order(self):
	self.flags.ignore_validate_update_after_submit = True
	if self.so_ref:
		so = frappe.get_doc("Sales Order", self.so_ref)
		so.db_set('sales_partner', self.sales_partner)
		so.db_set('primary_customer', self.primary_customer)
		if self.sales_team:
			for row in self.sales_team:
				so.append('sales_team', {
					'sales_person': row.sales_person,
					'contact_no': row.contact_no,
					'allocated_percentage': row.allocated_percentage,
					'allocated_amount': row.allocated_amount,
					'commission_rate': row.commission_rate,
					'incentives': row.incentives,
					'company': row.company,
					'regional_sales_manager': row.regional_sales_manager,
					'sales_manager': row.sales_manager
				})


def delete_pick_list(self):
	pick_list_list = frappe.get_all("Pick List Item", {'sales_order': self.name, 'docstatus': 1})
	for item in pick_list_list:
		pl = frappe.get_doc("Pick List Item", item.name)
		if not frappe.db.exists("Sales Order Item", pl.sales_order_item):
			user = frappe.get_doc("User", frappe.session.user)
			role_list = [r.role for r in user.roles]
			if frappe.db.get_value("Sales Order", self.name, 'lock_picked_qty'):
				dispatch_person_user = frappe.db.get_value(
					"Sales Person",
					frappe.db.get_value("Sales Order", self.name, 'dispatch_person'),
					'user'
				)
				if dispatch_person_user:
					if user.name != dispatch_person_user and 'Local Admin' not in role_list and 'Sales Head' not in role_list:
						frappe.throw("Only {} is allowed to unpick".format(dispatch_person_user))
			if pl.docstatus == 1:
				pl.cancel()
				_unpick_comment(pl.parent, self.name, f"Unpicked full Qty from item {pl.item_code}")
			pl.delete()


def _unpick_comment(reference_name, sales_order, data):
	for doctype, name in [("Pick List", reference_name), ("Sales Order", sales_order)]:
		comment = frappe.new_doc("Comment")
		comment.comment_type = "Info"
		comment.comment_email = frappe.session.user
		comment.reference_doctype = doctype
		comment.reference_name = name
		comment.content = data
		comment.save()


def cancel_main_sales_order(self):
	company_auth = frappe.db.get_value("Company", self.company, 'authority')
	if company_auth == "Authorized":
		if self.so_ref:
			so_ref = frappe.get_doc("Sales Order", self.so_ref)
			so_ref.db_set('so_ref', '')
		self.db_set('so_ref', '')


def remove_pick_list(self):
	from malaga.doc_events.pick_list import update_delivered_percent
	parent_docs = []

	for item in self.items:
		if item.picked_qty:
			for picked_item in frappe.get_all(
				"Pick List Item",
				{'sales_order': self.name, 'sales_order_item': item.name}
			):
				doc = frappe.get_doc("Pick List Item", picked_item.name)

				if doc.delivered_qty:
					frappe.throw(_("Cannot cancel this Sales Order — Delivery Note already exists."))

				doc.cancel()
				doc.delete()

				for dn in frappe.get_all("Delivery Note Item", {'against_pick_list': doc.name}):
					frappe.db.set_value("Delivery Note Item", dn.name, 'against_pick_list', None)
					frappe.db.set_value("Delivery Note Item", dn.name, 'pl_detail', None)

				parent_docs.append(doc.parent)
				item.db_set('picked_qty', 0)

	for pl in frappe.get_all("Pick List", {'sales_order': self.name}):
		frappe.db.set_value("Pick List", pl.name, 'sales_order', None)

	for pl_name in set(parent_docs):
		update_delivered_percent(frappe.get_doc("Pick List", pl_name))


def update_idx(self):
	for idx, item in enumerate(self.items):
		item.idx = idx + 1


def update_sales_order_total_values(self):
	# Fixed: was checking "Close" — correct ERPNext status is "Closed"
	if self.status == "Closed":
		frappe.throw("Cannot update totals on a closed sales order.")

	qty = 0
	total_picked_qty = 0.0
	total_picked_weight = 0.0
	total_delivered_qty = 0.0
	total_wastage_qty = 0.0
	total_deliverd_weight = 0.0
	total_qty = 0.0
	total_real_qty = 0.0
	total_net_weight = 0.0

	for row in self.items:
		qty += row.qty
		row.db_set('picked_weight', flt(row.weight_per_unit * row.picked_qty))
		total_picked_qty += row.picked_qty
		total_picked_weight += row.picked_weight
		total_delivered_qty += row.delivered_qty
		total_wastage_qty += row.wastage_qty
		total_deliverd_weight += flt(row.weight_per_unit * row.delivered_qty)
		total_qty += row.qty
		total_real_qty += row.real_qty
		row.db_set('total_weight', flt(row.weight_per_unit * row.qty))
		total_net_weight += row.total_weight

	per_picked = (total_picked_qty / qty) * 100 if qty else 0

	self.db_set('total_qty', total_qty)
	self.db_set('total_real_qty', total_real_qty)
	self.db_set('total_net_weight', total_net_weight)
	self.db_set('per_picked', per_picked)
	self.db_set('total_picked_qty', flt(total_picked_qty))
	self.db_set('total_picked_weight', total_picked_weight)
	self.db_set('total_delivered_qty', total_delivered_qty)
	self.db_set('picked_to_be_delivered_qty',
		self.total_picked_qty - flt(total_delivered_qty - flt(total_wastage_qty)))
	self.db_set('picked_to_be_delivered_weight',
		flt(total_picked_weight) - total_deliverd_weight)


def create_main_sales_order(self):
	authority = frappe.db.get_value("Company", self.company, "authority")

	def get_sales_order_entry(source_name, target_doc=None, ignore_permissions=True):
		def set_target_values(source, target):
			target_company = frappe.db.get_value("Company", source.company, "alternate_company")
			target_company_abbr = frappe.db.get_value("Company", target_company, "abbr")
			source_company_abbr = frappe.db.get_value("Company", source.company, "abbr")

			target.so_ref = self.name
			target.authority = "Authorized"

			if source.taxes_and_charges:
				taxes_and_charges = source.taxes_and_charges.replace(source_company_abbr, target_company_abbr)
				if frappe.db.exists("Sales Taxes and Charges Template", taxes_and_charges):
					target.taxes_and_charges = taxes_and_charges
				else:
					target.taxes_and_charges = ''

			if source.taxes:
				for index, i in enumerate(source.taxes):
					target.taxes[index].charge_type = source.taxes[index].charge_type
					target.taxes[index].included_in_print_rate = source.taxes[index].included_in_print_rate
					if source.taxes[index].cost_center:
						target.taxes[index].cost_center = source.taxes[index].cost_center.replace(source_company_abbr, target_company_abbr)
					if source.taxes[index].account_head:
						target.taxes[index].account_head = source.taxes[index].account_head.replace(source_company_abbr, target_company_abbr)

			if self.amended_from:
				name = frappe.db.get_value("Sales Order", {"so_ref": source.amended_from}, "name")
				target.amended_from = name

			target.set_missing_values()

		def account_details(source_doc, target_doc, source_parent):
			target_company = frappe.db.get_value("Company", source_parent.company, "alternate_company")
			target_company_abbr = frappe.db.get_value("Company", target_company, "abbr")
			source_company_abbr = frappe.db.get_value("Company", source_parent.company, "abbr")

			target_doc.real_qty = source_doc.qty

			if source_doc.warehouse:
				target_doc.warehouse = source_doc.warehouse.replace(source_company_abbr, target_company_abbr)

		fields = {
			"Sales Order": {
				"doctype": "Sales Order",
				"field_map": {"so_ref": "name"},
				"field_no_map": {"authority", "update_stock", "transaction_status"}
			},
			"Sales Order Item": {
				"doctype": "Sales Order Item",
				"field_map": {
					"item_name": "item_name",
					"item_code": "item_code",
					"rate": "discounted_rate",
					"qty": "real_qty",
					"warehouse": "warehouse",
				},
				"postprocess": account_details,
			}
		}

		return get_mapped_doc(
			"Sales Order", source_name, fields, target_doc,
			set_target_values, ignore_permissions=ignore_permissions
		)

	if authority == "Unauthorized" and not self.dont_replicate:
		so = get_sales_order_entry(self.name)
		so.naming_series = self.naming_series
		so.flags.ignore_permissions = True
		so.so_ref = self.name
		so.delivery_date = self.delivery_date
		so.transaction_date = self.transaction_date
		if self.amended_from:
			so.amended_from = frappe.db.get_value("Sales Order", {"so_ref": self.amended_from}, "name")
		so.ignore_item_validate = True
		so.save(ignore_permissions=True)
		for tax in so.taxes:
			if tax.tax_exclusive and tax.charge_type != "Actual":
				tax.included_in_print_rate = 1
		so.save(ignore_permissions=True)
		so.pay_amount_left = so.rounded_total - self.rounded_total
		if so.pay_amount_left < 0:
			so.pay_amount_left = 0.0
		so.save(ignore_permissions=True)
		self.db_set('so_ref', so.name)
		so.submit()


def calculate_rate(self):
	for row in self.items:
		pass
		# if row.sqf_rate:
		# 	sqf_calculation = frappe.db.get_value("Item Group", row.item_group, 'sqf_calculation')
		# 	row.rate = round(flt(row.sqf_rate * (sqf_calculation or 15.5)), 2)


def update_tax_paid_check_in_taxes(self):
	tax_dict = {}
	tax_paid = getattr(self, 'tax_paid', 0)
	tax_category = getattr(self, 'tax_category', None)

	get_tax_template_name = get_tax_template(tax_category, self.company, tax_paid)
	if get_tax_template_name:
		self.taxes_and_charges = get_tax_template_name
		data = frappe.get_all(
			"Sales Taxes and Charges",
			{"parent": get_tax_template_name},
			["charge_type", "account_head", "included_in_print_rate", "tax_exclusive"]
		)
		for row in data:
			tax_dict[(row.charge_type, row.account_head)] = row

	if tax_dict:
		for tax in self.taxes:
			tax_template_data = tax_dict.get((tax.charge_type, tax.account_head))
			if tax_template_data:
				tax.included_in_print_rate = tax_template_data.included_in_print_rate
				if hasattr(tax, 'tax_exclusive'):
					tax.tax_exclusive = tax_template_data.tax_exclusive
			else:
				if hasattr(tax, 'tax_exclusive'):
					tax.tax_exclusive = tax_paid


def validate_taxes_and_charges(self):
	tax_paid = getattr(self, 'tax_paid', 0)
	for row in self.taxes:
		if "gst" in row.account_head.lower() and row.included_in_print_rate != tax_paid:
			frappe.throw("Please correct the Sales Taxes and Charges Template first.")


def set_dispatch_person_mobile(self):
	dispatch_person = frappe.db.get_value("Sales Person", self.dispatch_person, "user")
	self.dispatch_person_mobile_no = frappe.db.get_value("User", dispatch_person, "mobile_no")
	self.alternate_company = frappe.db.get_value("Company", self.company, "alternate_company")


def cancel_on_sales_status():
	so_list = frappe.get_list("Sales Order", {'authority': 'Authorized'})
	for idx, sale_order in enumerate(so_list):
		if frappe.db.exists("Sales Order", sale_order.name):
			so_ref = frappe.db.get_value("Sales Order", sale_order.name, 'so_ref')
			if so_ref:
				st = frappe.db.get_value("Sales Order", so_ref, "status")
				if not st or st in ["Cancelled", "Completed", "Closed"]:
					so_doc = frappe.get_doc("Sales Order", sale_order.name)
					try:
						# Fixed: save so_ref before clearing it
						so_ref_name = so_doc.so_ref
						if so_doc.docstatus == 1:
							if so_doc.status == "Closed":
								so_doc.db_set('status', "Overdue")
							so_doc.db_set('so_ref', '')
							if so_ref_name:
								frappe.db.set_value("Sales Order", so_ref_name, 'so_ref', '')
							so_doc.cancel()
							so_doc.delete()
						elif so_doc.docstatus != 1:
							so_doc.delete()
					except Exception:
						frappe.log_error(frappe.get_traceback(), f'Error While Deleting Sales Order: {sale_order.name}')

					if idx % 10 == 0:
						frappe.db.commit()


def schedule_daily():
	pass
	# from frappe.utils.background_jobs import enqueue
	# enqueue(execute_schedule_daily, queue="long", timeout=10800)


def execute_schedule_daily():
	frappe.log_error("Cron event running for SO deletion")
	calculate_order_item_priority()
	calculate_order_rank()
	set_transaction_status()
	cancel_on_sales_status()


def set_transaction_status():
	cutoff = str(datetime.datetime.today() - datetime.timedelta(7))
	frappe.db.sql(f"""
		UPDATE `tabSales Order`
		SET transaction_status = 'Old'
		WHERE status IN ('Cancelled', 'Closed', 'Completed')
		AND transaction_status != 'Old'
		AND modified < '{cutoff}'
	""")
	frappe.db.sql("""
		UPDATE `tabSales Order`
		SET transaction_status = 'New'
		WHERE status NOT IN ('Cancelled', 'Closed', 'Completed')
		AND transaction_status != 'New'
	""")
	frappe.db.sql(f"""
		UPDATE `tabDelivery Note`
		SET transaction_status = 'Old'
		WHERE transaction_status != 'Old'
		AND modified < '{cutoff}'
	""")
	frappe.db.sql(f"""
		UPDATE `tabDelivery Note`
		SET transaction_status = 'New'
		WHERE transaction_status != 'New'
		AND modified >= '{cutoff}'
	""")


def calculate_order_item_priority():
	data = frappe.db.sql("""
		SELECT soi.name, so.transaction_date, so.order_priority
		FROM `tabSales Order Item` AS soi
		JOIN `tabSales Order` AS so ON so.name = soi.parent
		WHERE soi.qty > soi.delivered_qty
		AND so.docstatus = 1
		AND so.status NOT IN ('Completed', 'Stopped', 'Hold', 'Closed')
	""", as_dict=1)

	for soi in data:
		days = ((datetime.date.today() - soi.transaction_date) // datetime.timedelta(1)) + 1
		base_factor = 4
		order_item_priority = cint((days * (base_factor ** (cint(soi.order_priority) - 1))) + cint(soi.order_priority))
		frappe.db.set_value("Sales Order Item", soi.name, 'order_item_priority', order_item_priority, update_modified=True)


def calculate_order_rank():
	companies_list = frappe.get_list("Company", {'authority': 'Unauthorized'})

	data = frappe.db.sql("""
		SELECT so.name AS so_name
		FROM `tabSales Order` AS so
		WHERE so.per_delivered < 100
		AND so.docstatus = 1
		AND so.status NOT IN ('Completed', 'Stopped', 'Hold', 'Closed')
	""", as_dict=1)

	for soi in data:
		doc = frappe.get_doc("Sales Order", soi.so_name)
		if doc.items:
			doc.db_set('order_item_priority', doc.items[0].order_item_priority, update_modified=False)

	for i in companies_list:
		priority = frappe.db.sql("""
			SELECT name, ROW_NUMBER() OVER (ORDER BY order_item_priority DESC, transaction_date DESC) AS rank
			FROM `tabSales Order`
			WHERE docstatus = 1
			AND status NOT IN ('Closed', 'Stopped', 'Completed', 'Hold')
			AND per_delivered < 100
			AND company = %(company)s
			ORDER BY order_item_priority DESC
		""", {'company': i.name}, as_dict=True)

		for item in priority:
			frappe.db.set_value("Sales Order", item.name, 'order_rank', item.rank, update_modified=False)


# ─── Whitelisted APIs ─────────────────────────────────────────────────────────

@frappe.whitelist()
def update_order_rank_(date, order_priority, company):
	try:
		days = ((datetime.date.today() - datetime.datetime.strptime(date, '%Y-%m-%d').date()) // datetime.timedelta(days=1)) + 1
	except Exception:
		days = ((datetime.date.today() - date) // datetime.timedelta(days=1)) + 1

	days = 1 if days <= 0 else days
	base_factor = 4
	order_item_priority = cint((days * (base_factor ** (cint(order_priority) - 1))) + cint(order_priority))

	result = frappe.db.sql("""
		SELECT order_rank, ABS(order_item_priority - %(priority)s) AS difference
		FROM `tabSales Order`
		WHERE status NOT IN ('Completed', 'Draft', 'Cancelled', 'Hold')
		AND order_rank > 0
		AND company = %(company)s
		HAVING difference > 0
		ORDER BY difference
		LIMIT 1
	""", {'priority': order_item_priority, 'company': company})

	order_rank = result[0][0] if result else 0
	return {'order_item_priority': order_item_priority, 'order_rank': order_rank}


@frappe.whitelist()
def change_customer(customer, doc):
	so = frappe.get_doc("Sales Order", doc)
	customer_data = get_party_details(customer, "Customer")

	so.db_set('customer', customer)
	so.db_set('primary_customer', frappe.db.get_value("Customer", customer, 'primary_customer') or customer)
	so.db_set('title', customer)
	so.db_set('customer_name', frappe.db.get_value("Customer", customer, 'customer_name'))
	so.db_set('order_priority', frappe.db.get_value("Customer", customer, 'customer_priority'))
	so.db_set('customer_address', customer_data.get('customer_address'))
	so.db_set('address_display', customer_data.get('address_display'))
	so.db_set('shipping_address_name', customer_data.get('shipping_address_name'))
	so.db_set('shipping_address', customer_data.get('shipping_address'))
	so.db_set('contact_person', customer_data.get('contact_person'))
	so.db_set('contact_display', customer_data.get('contact_display'))
	so.db_set('contact_email', customer_data.get('contact_email'))
	so.db_set('contact_mobile', customer_data.get('contact_mobile'))
	so.db_set('contact_phone', customer_data.get('contact_phone'))
	so.db_set('customer_group', customer_data.get('customer_group'))
	return "Customer Changed Successfully."


@frappe.whitelist()
def get_tax_template(tax_category, company, tax_paid=0, is_opening="No"):
	# Only throw if this is a server-side validation call, not a UI lookup
	if not tax_category:
		return None  # Remove the frappe.throw — let the UI handle it
	
	name = frappe.db.get_value(
		"Sales Taxes and Charges Template",
		{'tax_paid': tax_paid, 'tax_category': tax_category, 'company': company},
		'name'
	)
	return name


@frappe.whitelist()
def get_rate_discounted_rate(item_code, customer, company, so_number=None):
	pass


@frappe.whitelist()
def make_pick_list(source_name, target_doc=None):
	frappe.throw("Pick List creation is not allowed for this Sales Order.")
	frappe.log_error(
		title="source_name",
		message=str(source_name)
	)
	
	def update_item_quantity(source, target, source_parent):
		
		target.qty = flt(source.qty) - flt(source.picked_qty) - flt(source.delivered_without_pick)
		target.so_qty = flt(source.qty)
		target.so_real_qty = flt(source.real_qty)
		target.stock_qty = (flt(source.qty) - flt(source.picked_qty)) * flt(source.conversion_factor)
		target.picked_qty = source.picked_qty
		target.remaining_qty = target.so_qty - target.qty - target.picked_qty
		target.customer = source_parent.customer
		target.date = source_parent.transaction_date
		target.delivery_date = source.delivery_date
		target.so_picked_percent = source_parent.per_picked
		target.warehouse = source_parent.warehouse
		target.order_item_priority = source.order_item_priority
		target.so_delivered_without_pick = source.delivered_without_pick

	doc = get_mapped_doc('Sales Order', source_name, {
		'Sales Order': {
			'doctype': 'Pick List',
			'validation': {'docstatus': ['=', 1]}
		},
		'Sales Order Item': {
			'doctype': 'Pick List Item',
			'field_map': {
				'parent': 'sales_order',
				'name': 'sales_order_item'
			},
			'field_no_map': ['warehouse'],
			'postprocess': update_item_quantity,
			'condition': lambda doc: abs(doc.picked_qty) < abs(doc.qty) and doc.delivered_by_supplier != 1
		},
	}, target_doc)

	doc.purpose = 'Delivery'
	doc.set_item_locations()
	return doc


@frappe.whitelist()
def make_delivery_note(source_name, target_doc=None, skip_item_mapping=False):
	def set_missing_values(source, target):
		target.ignore_pricing_rule = 1
		target.run_method("set_missing_values")
		target.run_method("set_po_nos")
		target.run_method("calculate_taxes_and_totals")

		if source.company_address:
			target.update({'company_address': source.company_address})
		else:
			target.update(get_company_address(target.company))

		if target.company_address:
			pass
			# from frappe.model.utils import get_fetch_values
			# target.update(get_fetch_values("Delivery Note", 'company_address', target.company_address))

	def update_item(source, target, source_parent):
		for i in source.items:
			if frappe.db.get_value("Item", i.item_code, 'is_stock_item'):
				real_delivered_qty = flt(i.real_qty) - flt(i.delivered_real_qty)
				for j in frappe.get_all(
					"Pick List Item",
					filters={"sales_order": source.name, "sales_order_item": i.name, "docstatus": 1}
				):
					pick_doc = frappe.get_doc("Pick List Item", j.name)

					warehouse_query = frappe.db.sql("""
						SELECT sle.warehouse
						FROM `tabStock Ledger Entry` sle
						JOIN `tabBatch` batch ON sle.batch_no = batch.name
						WHERE sle.is_cancelled = 0
						AND sle.item_code = %(item_code)s
						AND batch.docstatus < 2
						AND sle.batch_no = %(batch_no)s
						GROUP BY sle.warehouse
						HAVING SUM(sle.actual_qty) > 0
						ORDER BY SUM(sle.actual_qty) DESC
						LIMIT 1
					""", {'item_code': pick_doc.item_code, 'batch_no': pick_doc.batch_no})

					warehouse = warehouse_query[0][0] if warehouse_query else None

					real_delivered_qty = max(real_delivered_qty, 0)

					if flt(pick_doc.qty) - flt(pick_doc.delivered_qty):
						target.append('items', {
							'item_code': pick_doc.item_code,
							'qty': flt(pick_doc.qty) - flt(pick_doc.delivered_qty),
							'real_qty': real_delivered_qty if i.qty != i.real_qty else flt(pick_doc.qty) - flt(pick_doc.delivered_qty),
							'rate': i.rate,
							'discounted_rate': i.discounted_rate,
							'against_sales_order': source.name,
							'so_detail': i.name,
							'against_pick_list': pick_doc.parent,
							'pl_detail': pick_doc.name,
							'warehouse': warehouse,
							'batch_no': pick_doc.batch_no,
							'lot_no': pick_doc.lot_no,
							'item_series': i.item_series,
							'picked_qty': flt(pick_doc.qty) - flt(pick_doc.delivered_qty)
						})
						real_delivered_qty = 0
			else:
				target.append('items', {
					'item_code': i.item_code,
					'qty': flt(i.qty) - flt(i.delivered_qty),
					'real_qty': flt(i.qty) - flt(i.delivered_real_qty) if i.qty != i.real_qty else flt(i.qty) - flt(i.delivered_qty),
					'rate': i.rate,
					'discounted_rate': i.discounted_rate,
					'against_sales_order': source.name,
					'so_detail': i.name,
					'warehouse': i.warehouse,
					'item_series': i.item_series,
					'batch_no': ''
				})

	mapper = {
		"Sales Order": {
			"doctype": "Delivery Note",
			"validation": {"docstatus": ["=", 1]},
			"postprocess": update_item
		},
		"Sales Taxes and Charges": {
			"doctype": "Sales Taxes and Charges",
			"add_if_empty": True
		},
		"Sales Team": {
			"doctype": "Sales Team",
			"add_if_empty": True
		}
	}

	return get_mapped_doc("Sales Order", source_name, mapper, target_doc, set_missing_values)

