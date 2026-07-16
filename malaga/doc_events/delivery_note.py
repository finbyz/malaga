import frappe, re, math
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.contacts.doctype.address.address import get_company_address
from frappe.model.utils import get_fetch_values
from frappe.utils import flt
from malaga.doc_events.sales_order import update_sales_order_total_values, calculate_rate, get_tax_template
# from malaga.doc_events.sales_invoice import validate_tax_template
# from erpnext.stock.doctype.serial_no.serial_no import get_delivery_note_serial_no
# from malaga.api import company_authorization

def before_validate(self, method):
	# get_address(self)
	self.sales_team = []
	self.flags.ignore_permissions = True

	
	for item in self.items:
		if (not item.rate) and (item.so_detail):
			item.rate = frappe.db.get_value("Sales Order Item", item.so_detail, 'rate')

		# if frappe.db.get_value("Item", item.item_code, 'is_stock_item') and (not item.against_sales_order or not item.against_pick_list):
			# frappe.throw(f"Row: {item.idx} No Sales Order or Pick List found for item {item.item_code}")
		
		# if (not item.discounted_rate) and (item.so_detail):
		# 	item.discounted_rate = frappe.db.get_value("Sales Order Item", item.so_detail, 'discounted_rate')
	validate_item_from_so(self)
	sales_order_list = list(set([x.against_sales_order for x in self.items if x.against_sales_order]))

	for x in sales_order_list:
		so_doc = frappe.get_doc("Sales Order",x)
		so_doc.db_set("customer",self.customer)
		so_doc.db_set("title",self.customer)
		so_doc.db_set("customer_name",self.customer_name)
	
	update_tax_paid_check_in_taxes(self)


def validate(self, method):
	calculate_rate(self)
	if self._action == "submit":
		check_rate_qty(self)
	validate_si_ref(self)
	calculate_items_discounted_fields(self)
	update_lock_qty(self)
	validate_item_from_picklist(self)
	# if self._action == "submit":
	# 	validate_tax_template(self)
	update_discounted_net_total(self)
	calculate_totals(self)
	set_pi_details(self)
	

def validate_si_ref(self):
    pass
	# if self.custom_si_ref:
	# 	si_ref, customer, primary_customer, docstatus, company = frappe.db.get_value("Sales Invoice",self.custom_si_ref,["si_ref","customer","primary_customer","docstatus","company"])
	# 	if si_ref:
	# 		frappe.throw("Please select correct invoice, Sales Invoice already generated.")

	# 	if not self.billing_customer:
	# 		frappe.throw("Please Enter Billing Customer")

	# 	if customer != self.billing_customer:
	# 		data_sync = frappe.get_single("Data Sync Setting")  # Use get_single for single doctypes
	# 		sync_enabled = data_sync.sync_enabled
	# 		if not sync_enabled:  # Throw only if sync is NOT enabled
	# 			frappe.throw("Please Select Correct Invoice, Wrong Customer Selected as Per Billing Customer.")

	# 	if primary_customer != self.customer and not frappe.db.get_single_value("Data Sync Setting", "sync_enabled"):
	# 		frappe.throw("Please Select Correct Invoice, Wrong Primary Customer Selected.")

	# 	if docstatus != 1:
	# 		frappe.throw("Please Select Correct Invoice, Selected Document is in Draft State.")

	# 	if company != frappe.db.get_value("Company", self.company, "alternate_company"):
	# 		frappe.throw("Please Select Correct Invoice, Wrong Company.")

def calculate_items_discounted_fields(self):
	if self.custom_si_ref:
		invoice_company, invoice_net_total, total_qty, payment_terms_template = frappe.db.get_value("Sales Invoice",self.custom_si_ref,["company","net_total","total_qty", "payment_terms_template"])

		for item in self.items:
			if self.net_total:
				pass
				# item.discounted_amount = flt(invoice_net_total) * flt(item.net_amount) / flt(self.net_total)
				# item.discounted_net_amount = flt(item.discounted_amount)

		self.total_si_qty = flt(total_qty)
		if payment_terms_template:
			self.payment_terms_template = payment_terms_template
		
def update_lock_qty(self):
	if self.is_new():	
		if self.items[0].against_sales_order:
			so_doc = frappe.get_doc("Sales Order",self.items[0].against_sales_order)
			so_doc.db_set('lock_picked_qty',1)

def validate_item_from_so(self):
	for row in self.items:
		if frappe.db.exists("Sales Order Item",row.so_detail):
			so_item = frappe.db.get_value("Sales Order Item",row.so_detail,"item_code")
			if row.item_code != so_item:
				frappe.throw(_(f"Row: {row.idx}: Not allowed to change item {frappe.bold(row.item_code)}."))

def validate_item_from_picklist(self):
	for row in self.items:
		if row.custom_pi_details:
			if frappe.db.exists("Pick List Item",row.custom_pi_details):
				picked_qty = flt(frappe.db.get_value("Pick List Item",row.custom_pi_details,"qty"))
				if flt(row.qty) > picked_qty:
					frappe.throw(_(f"Row: {row.idx}: Delivered Qty {frappe.bold(row.qty)} can not be higher than picked Qty {frappe.bold(picked_qty)} for item {frappe.bold(row.item_code)}."))
			else:
				frappe.throw(_(f"Row: {row.idx}: The item {frappe.bold(row.item_code)} has been unpicked from picklist {frappe.bold(row.against_pick_list)}"))

def update_discounted_net_total(self):
    return
	# self.discounted_total = sum(x.discounted_amount for x in self.items)
	# self.discounted_net_total = sum(x.discounted_net_amount for x in self.items)
	# testing_only_tax = 0
	
	# for tax in self.taxes:
	# 	if tax.testing_only:
	# 		testing_only_tax += tax.tax_amount
	
	# self.discounted_grand_total = flt(self.discounted_net_total) + flt(self.total_taxes_and_charges) - flt(testing_only_tax)
	# self.discounted_rounded_total = round(self.discounted_grand_total)
	# self.real_difference_amount = flt(self.rounded_total) - flt(self.discounted_rounded_total)

def calculate_totals(self):
	for d in self.items:
		d.total_weight = flt(d.weight_per_unit * d.qty)
	self.total_qty = sum([row.qty for row in self.items])
	self.total_net_weight = sum([row.total_weight for row in self.items])


def check_item_without_pick(self):
	
	item_without_pick_list_dict = {}
	for row in self.items:
		if not row.custom_pi_details and row.so_detail:
			if not item_without_pick_list_dict.get(row.so_detail):
				item_without_pick_list_dict[row.so_detail] = 0
			
			item_without_pick_list_dict[row.so_detail] += row.qty

	for key, row in item_without_pick_list_dict.items():
		item_code, parent, so_qty, so_picked_qty, so_delivered_qty, so_delivered_without_pick = frappe.db.get_value("Sales Order Item", key, ['item_code', 'parent', 'qty', 'picked_qty', 'delivered_qty', 'delivered_without_pick'])
		
		allowed_qty = so_qty - so_picked_qty - so_delivered_without_pick
		
		if allowed_qty < row:
			frappe.throw(f"You can not deliver more than {allowed_qty} without Pick List for Item {item_code} for Sales Order {parent}.")

def update_status_pick_list_and_sales_order(self):
	for item in self.items:
		if item.against_pick_list:
			pick_list_item = frappe.get_doc("Pick List Item", item.custom_pi_details)
			if item.batch_no != pick_list_item.batch_no:
				frappe.throw(f"Row: {item.idx} You can not change batch as pick list is already made.")
			
			delivered_qty = item.qty + pick_list_item.delivered_qty
			
			
			# if delivered_qty + wastage_qty > pick_list_item.qty:
			# 	frappe.throw(f"Row {item.idx}: You can not deliver more than picked qty")
			
			frappe.db.set_value("Pick List Item", pick_list_item.name, 'delivered_qty', flt(delivered_qty))
			# frappe.db.set_value("Pick List Item", pick_list_item.name, 'wastage_qty', flt(wastage_qty))

		if item.against_sales_order:
			sales_order_item = frappe.get_doc("Sales Order Item", item.so_detail)
			# wastage_qty = item.wastage_qty + sales_order_item.wastage_qty
			
			delivered_qty = item.qty + sales_order_item.delivered_qty

			# if delivered_qty + wastage_qty > sales_order_item.qty:
				# frappe.throw(f"Row {item.idx}: You can not deliver more than sales order qty")
			
			
			# if item.against_pick_list:
				# frappe.db.set_value("Sales Order Item", sales_order_item.name, 'picked_qty', flt(sales_order_item.picked_qty - wastage_qty))

			update_sales_order_total_values(frappe.get_doc("Sales Order", item.against_sales_order))
		
		if not item.against_pick_list and item.against_sales_order:
			so_delivered_without_pick = frappe.db.get_value("Sales Order Item", item.so_detail, 'delivered_without_pick')
			frappe.db.set_value("Sales Order Item", item.so_detail, 'delivered_without_pick', so_delivered_without_pick + item.qty)
		
		if item.custom_pi_details:
			pick_list_batch_no = frappe.db.get_value("Pick List Item", item.custom_pi_details, 'batch_no')

			if item.batch_no != pick_list_batch_no:
				frappe.throw(_(f"Row: {item.idx} : Batch No {frappe.bold(item.batch_no)} is Not same as Pick List Batch No {frappe.bold(pick_list_batch_no)}."))

def before_submit(self, method):
	check_item_without_pick(self)
	update_status_pick_list_and_sales_order(self)
	validate_taxes_sales_invoice(self)

	# if not self.loading_notes:
	# 	frappe.throw(_('Loading Notes is mandatory'), frappe.MandatoryError)

	if self.vehicle_no:
		if not bool(re.match('^[a-zA-Z0-9]+$', self.vehicle_no)):
			frappe.throw("Invalid Vehicle Number Found, Please Enter Correct Vehicle Number")

	# if not self.initial_weight:
	# 	frappe.throw(_('Initial Weight is mandatory'), frappe.MandatoryError)

	# if not self.final_weight:
	# 	frappe.throw(_('Final Weight is mandatory'), frappe.MandatoryError)

	# validate_quantity(self, method)

def validate_taxes_sales_invoice(self):
	tax_map={}
	source_company_abbr = frappe.db.get_value("Company", self.company, "abbr")
	dn_tax=0
	si_tax_total=0

	if self.custom_si_ref:
		for tax in self.taxes:
			tax_map.setdefault(tax.account_head,tax.tax_amount)
			if ('IGST' in tax.account_head or 'CGST' in tax.account_head or 'SGST' in tax.account_head):
				dn_tax+=tax.tax_amount
		si_ref_doc = frappe.get_doc("Sales Invoice",self.custom_si_ref)
		target_company_abbr = frappe.db.get_value("Company", si_ref_doc.company, "abbr")

		for si_tax in si_ref_doc.taxes:
			if ('IGST' in si_tax.account_head or 'CGST' in si_tax.account_head or 'SGST' in si_tax.account_head):
				si_tax_total += si_tax.tax_amount
			if math.floor(flt(si_tax.tax_amount)) != math.floor(flt(tax_map.get(si_tax.account_head.replace(target_company_abbr,source_company_abbr)))):
				value = flt(si_tax.tax_amount) - flt(tax_map.get(si_tax.account_head.replace(target_company_abbr,source_company_abbr)))
				if -0.02 <= value <= 0.02:
					continue
				frappe.throw("Tax Amount is Different in Row: {}".format(si_tax.idx))

		if (round(si_tax_total) != round(dn_tax)):
			total_val = si_tax_total - dn_tax
			if not (-0.02 <= total_val <= 0.02):
				frappe.throw('Tax Amount is Different')

def update_status_pick_list(self):
	pick_list = list(set([item.against_pick_list for item in self.items if item.against_pick_list]))

	for pick in pick_list:
		pl = frappe.get_doc("Pick List", pick)
		delivered_qty = 0
		picked_qty = 0
		wastage_qty = 0

		for item in pl.locations:
			delivered_qty += item.delivered_qty
			# wastage_qty += item.wastage_qty
			picked_qty += item.qty

		if picked_qty == 0:
			per_delivered = 100.0
		else:
			per_delivered = flt((delivered_qty / picked_qty) * 100)
		frappe.db.set_value("Pick List", pick, 'per_delivered', per_delivered)

	change_delivery_authority(self.name)

def on_submit(self,method):
	# validate_addresses(self)
	link_dn_to_si_ref(self)
	# check_payment_terms(self)
	# company_authorization(self)
	wastage_stock_entry(self)
	for item in self.items:
		if item.against_sales_order:
			update_sales_order_total_values(frappe.get_doc("Sales Order", item.against_sales_order))
	# validate_customer_sales_person(self)
	if self.custom_si_ref:
		frappe.db.set_value("Sales Invoice", self.custom_si_ref, "verify_mobile_no", self.verify_mobile_no)

	
def validate_addresses(self):
	if not self.shipping_address_name:
		frappe.throw(_("Shipping Address is mandatory"))
	if not self.customer_address or self.customer_address==None or self.customer_address=='':
		frappe.throw(_("Billing Address is mandatory"))

def check_rate_qty(self):
	for item in self.items:
		if not item.rate or item.rate <= 0:
			frappe.throw(f"Row: {item.idx} Rate cannot be 0")
		if not item.qty or item.qty == 0:
			frappe.throw(f"Row: {item.idx} Quantity can not be 0 ")

# def check_qty_rate(self):
# 	for item in self.items:
# 		if not item.discounted_rate:
# 			frappe.msgprint(f"Row {item.idx}: Discounted rate is 0, you will not be able to create invoice in {frappe.db.get_value('Company', self.company, 'alternate_company')}")
# 		if not item.real_qty:
# 			frappe.msgprint(f"Row {item.idx}: Real qty is 0, you will not be able to create invoice in {frappe.db.get_value('Company', self.company, 'alternate_company')}")

def on_cancel(self, method):
	if self.custom_si_ref:
		doc = frappe.get_doc("Sales Invoice", self.custom_si_ref)
		doc.db_set("delivery_note", None)
		self.db_set('si_ref',None)
	# # below changes because of wastage qty issue
	# new_items=[]
	# for i in self.items:
	# 	new_items.append(frappe._dict(i.__dict__))
	# items = sorted(new_items, key = lambda i: i['wastage_qty'],reverse=True)
	# for item in items:
	# # Changes complete
	for item in self.items:
		if item.against_pick_list:
			pick_list_item = frappe.get_doc("Pick List Item", item.custom_pi_details)
			delivered_qty = pick_list_item.delivered_qty - item.qty
			# wastage_qty = pick_list_item.wastage_qty - item.wastage_qty
			# frappe.db.set_value("Pick List Item", pick_list_item.name, 'delivered_qty', flt(delivered_qty))
			# frappe.db.set_value("Pick List Item", pick_list_item.name, 'wastage_qty', flt(wastage_qty))
	
		if item.against_sales_order:
			sales_order_item = frappe.get_doc("Sales Order Item", item.so_detail)
			if item.against_pick_list:
				# if sales_order_item.picked_qty + wastage_qty > sales_order_item.qty:
				# 	frappe.throw(f"Please Unpick {sales_order_item.picked_qty + wastage_qty - sales_order_item.qty} for Sales Order {sales_order_item.parent} Row: {sales_order_item.idx}")
				
				frappe.db.set_value("Sales Order Item", sales_order_item.name, 'picked_qty', flt(sales_order_item.picked_qty + item.wastage_qty))
			update_sales_order_total_values(frappe.get_doc("Sales Order", item.against_sales_order))
		
		if not item.against_pick_list and item.against_sales_order:
			so_delivered_without_pick = frappe.db.get_value("Sales Order Item", item.so_detail, 'delivered_without_pick')
			frappe.db.set_value("Sales Order Item", item.so_detail, 'delivered_without_pick', item.qty - so_delivered_without_pick)
	update_status_pick_list(self)
	cancel_wastage_entry(self)

def before_save(self, method):
	# customer_group = frappe.db.get_value("Customer", self.customer, 'customer_group')
	# frappe.msgprint(customer_group)
	for row in self.items:
		row.full_qty = flt(row.qty)

def change_delivery_authority(name):
	dn_status = frappe.get_value("Delivery Note", name, "status")
	if dn_status == 'Completed':
		frappe.db.set_value("Delivery Note",name, "authority", "Unauthorized")
	else:
		frappe.db.set_value("Delivery Note",name, "authority", "Authorized")

@frappe.whitelist()
def create_invoice(source_name, target_doc=None):
	doc = frappe.get_doc('Delivery Note', source_name)
	from erpnext.stock.doctype.delivery_note.delivery_note import get_returned_qty_map, get_invoiced_qty_map
	to_make_invoice_qty_map = {}
	returned_qty_map = get_returned_qty_map(source_name)
	invoiced_qty_map = get_invoiced_qty_map(source_name)

	def set_missing_values(source, target):
		target.is_pos = 0
		target.ignore_pricing_rule = 1
		alternate_company = source.invoice_company or frappe.db.get_value("Company", source.company, "alternate_company")
		target.expense_account = ""

		target.update_stock = 1
		# target_doc.delivery_note = "T"

		if alternate_company:
			target.company = alternate_company
			target.authority = frappe.db.get_value("Company",alternate_company,'authority')

		if len(target.get("items")) == 0:
			frappe.throw(_(f"You can not create invoice in company {target.company}"))

		target.run_method("calculate_taxes_and_totals")

		# set company address
		if source.company_address:
			target.update({'company_address': source.company_address})
		else:
			# set company address
			target.update(get_company_address(target.company))

		if target.company_address:
			target.update(get_fetch_values("Sales Invoice", 'company_address', target.company_address))

		target_company_abbr = frappe.db.get_value("Company", target.company, "abbr")
		source_company_abbr = frappe.db.get_value("Company", source.company, "abbr")
		
		if source.set_warehouse:
			target.set_warehouse = source.set_warehouse.replace(source_company_abbr, target_company_abbr)
		
		if source.taxes_and_charges:
			target_taxes_and_charges = source.taxes_and_charges.replace(source_company_abbr, target_company_abbr)
			if frappe.db.exists("Sales Taxes and Charges Template", target_taxes_and_charges):
				target.taxes_and_charges = target_taxes_and_charges
			
		# target.taxes = source.taxes
		# if source.taxes:
		# 	for index, value in enumerate(source.taxes):
		# 		if not source.taxes[index].testing_only:
		# 			if source.taxes[index].tax_exclusive:
		# 				source.taxes[index].included_in_print_rate = 0
		# 			if source.taxes[index].cost_center:
		# 				target.taxes[index].cost_center = source.taxes[index].cost_center.replace(source_company_abbr, target_company_abbr)

		target.run_method("set_missing_values")
		target.run_method("set_po_nos")

	def get_pending_qty(item_row):
		pending_qty = item_row.qty - invoiced_qty_map.get(item_row.name, 0)

		returned_qty = 0
		if returned_qty_map.get(item_row.item_code, 0) > 0:
			returned_qty = flt(returned_qty_map.get(item_row.item_code, 0))
			returned_qty_map[item_row.item_code] -= pending_qty

		if returned_qty:
			if returned_qty >= pending_qty:
				pending_qty = 0
				returned_qty -= pending_qty
			else:
				pending_qty -= returned_qty
				returned_qty = 0

		to_make_invoice_qty_map[item_row.name] = pending_qty

		return pending_qty
	
	def update_taxes(source_doc, target_doc, source_parent):
		target_company = source_parent.invoice_company or frappe.db.get_value("Company", source_parent.company, "alternate_company")
		# item_code = frappe.db.get_value("Item", source_doc.item_code, "item_series")
		doc = frappe.get_doc("Company", target_company)
		target_company_abbr = frappe.db.get_value("Company", target_company, "abbr")
		source_company_abbr = frappe.db.get_value("Company", source_parent.company, "abbr")
		
		target_doc.account_head = source_doc.account_head.replace(source_company_abbr, target_company_abbr)

		if source_doc.tax_exclusive:
			target_doc.included_in_print_rate = 0
		
		if source_doc.cost_center:
			target_doc.cost_center = source_doc.cost_center.replace(source_company_abbr, target_company_abbr)

	
	def update_item(source_doc, target_doc, source_parent):
		target_company = source_parent.invoice_company or frappe.db.get_value("Company", source_parent.company, "alternate_company")
		# item_code = frappe.db.get_value("Item", source_doc.item_code, "item_series")
		doc = frappe.get_doc("Company", target_company)
		target_company_abbr = frappe.db.get_value("Company", target_company, "abbr")
		source_company_abbr = frappe.db.get_value("Company", source_parent.company, "abbr")
		# frappe.msgprint(item_code)
		# target_doc.item_code = item_code
		# target_doc.name = item_code
		target_doc.income_account = doc.default_income_account
		target_doc.expense_account = doc.default_expense_account
		target_doc.cost_center = doc.cost_center
		if source_doc.warehouse:
			target_doc.warehouse = source_doc.warehouse.replace(source_company_abbr, target_company_abbr)

	doc = get_mapped_doc("Delivery Note", source_name, {
		"Delivery Note": {
			"doctype": "Sales Invoice",
			"field_map": {
				"is_return": "is_return",
				"posting_date":"posting_date",
				"posting_time":"posting_time",
				"set_posting_time":"set_posting_time",
				"verify_mobile_no":"verify_mobile_no"
			},
			"validation": {
				"docstatus": ["=", 1]
			}
		},
		"Delivery Note Item": {
			"doctype": "Sales Invoice Item",
			"field_map": {
				"item_code": "item_design",
				"item_series": "item_code",
				"parent": "delivery_docname",
				"name":"delivery_childname",
				"so_detail": "so_childname" ,
				"against_sales_order": "so_docname",
				"serial_no": "serial_no",
				"discounted_rate": "rate",
				"qty": "full_qty",
				"rate":"full_rate",
				"batch_no": "real_batch_no",
				"stock_uom": "stock_uom",
				"conversion_factor": "conversion_factor"
			},
			"field_no_map": [
				"income_account",
				"expense_account",
				"cost_center",
				"warehouse",
				"batch_no",
				"lot_no",
				"discounted_rate",
				"authority"
			],
			"postprocess": update_item,
			"condition": lambda doc: abs(doc.real_qty) > 0 and abs(doc.discounted_rate) != 0,
			"filter": lambda d: get_pending_qty(d) <= 0 if not doc.get("is_return") else get_pending_qty(d) > 0
		},
		"Sales Taxes and Charges": {
			"doctype": "Sales Taxes and Charges",
			"add_if_empty": True,
			"condition": lambda doc: abs(doc.testing_only) == 0,
			"postprocess": update_taxes,
		},
		"Sales Team": {
			"doctype": "Sales Team",
			"field_map": {
				"incentives": "incentives"
			},
			"add_if_empty": True
		}
	}, target_doc, set_missing_values, ignore_permissions = True)

	if len(doc.items) == 0:
		alternate_company = frappe.db.get_value("Company", doc.company, 'alternate_company')
		frappe.throw(f"All item has already been invoiced in company {alternate_company}")

	return doc

@frappe.whitelist()
def create_invoice_test(source_name, target_doc=None):
	doc = frappe.get_doc('Delivery Note', source_name)

	to_make_invoice_qty_map = {}
	returned_qty_map = get_returned_qty_map(source_name)
	invoiced_qty_map = get_invoiced_qty_map(source_name)

	def set_missing_values(source, target):
		target.ignore_pricing_rule = 1
		target.run_method("set_missing_values")
		target.run_method("set_po_nos")

		if len(target.get("items")) == 0:
			frappe.throw(_("All these items have already been Invoiced/Returned"))

		target.run_method("calculate_taxes_and_totals")

		# set company address
		if source.company_address:
			target.update({'company_address': source.company_address})
		else:
			# set company address
			target.update(get_company_address(target.company))

		if target.company_address:
			target.update(get_fetch_values("Sales Invoice", 'company_address', target.company_address))

	def update_item(source_doc, target_doc, source_parent):
		target_doc.qty = to_make_invoice_qty_map[source_doc.name]

		# if source_doc.serial_no and source_parent.per_billed > 0:
		# 	target_doc.serial_no = get_delivery_note_serial_no(source_doc.item_code,
		# 		target_doc.qty, source_parent.name)

	def get_pending_qty(item_row):
		pending_qty = item_row.qty - invoiced_qty_map.get(item_row.name, 0)

		returned_qty = 0
		if returned_qty_map.get(item_row.name, 0) > 0:
			returned_qty = flt(returned_qty_map.get(item_row.name, 0))
			returned_qty_map[item_row.name] -= pending_qty

		if returned_qty:
			if returned_qty >= pending_qty:
				pending_qty = 0
				returned_qty -= pending_qty
			else:
				pending_qty -= returned_qty
				returned_qty = 0

		to_make_invoice_qty_map[item_row.name] = pending_qty

		return pending_qty

	doc = get_mapped_doc("Delivery Note", source_name, {
		"Delivery Note": {
			"doctype": "Sales Invoice",
			"field_map": {
				"is_return": "is_return",
				"posting_date":"posting_date",
				"posting_time":"posting_time",
				"set_posting_time":"set_posting_time",
				"si_ref":"si_ref",
				"payment_terms_template": "payment_terms_template",
				"verify_mobile_no": "verify_mobile_no"
			},
			"validation": {
				"docstatus": ["=", 1]
			}
		},
		"Delivery Note Item": {
			"doctype": "Sales Invoice Item",
			"field_map": {
				"name": "dn_detail",
				"parent": "delivery_note",
				"so_detail": "so_detail",
				"against_sales_order": "sales_order",
				"serial_no": "serial_no",
				"cost_center": "cost_center",
				"stock_uom": "stock_uom",
				"conversion_factor": "conversion_factor"
			},
			"postprocess": update_item,
			"filter": lambda d: get_pending_qty(d) <= 0 if not doc.get("is_return") else get_pending_qty(d) > 0
		},
		"Sales Taxes and Charges": {
			"doctype": "Sales Taxes and Charges",
			"add_if_empty": True
		},
		"Sales Team": {
			"doctype": "Sales Team",
			"field_map": {
				"incentives": "incentives"
			},
			"add_if_empty": True
		}
	}, target_doc, set_missing_values)

	if doc.si_ref:
		si_company_series, si_naming_series, si_series_value = frappe.db.get_value("Sales Invoice",doc.si_ref,["company_series","naming_series","series_value"])
		doc.naming_series =  'A' + si_naming_series
		doc.series_value = si_series_value
		doc.save(ignore_permissions=True)
	return doc

def on_update_after_submit(self, method):
	change_authority(self)

def change_authority(self):
	if self.status == 'Completed':
		self.db_set("authority", "Unauthorized")
	else:
		self.db_set("authority", "Authorized")

def get_returned_qty_map(delivery_note):
	"""returns a map: {so_detail: returned_qty}"""
	returned_qty_map = frappe._dict(frappe.db.sql("""select dn_item.item_code, sum(abs(dn_item.qty)) as qty
		from `tabDelivery Note Item` dn_item, `tabDelivery Note` dn
		where dn.name = dn_item.parent
			and dn.docstatus = 1
			and dn.is_return = 1
			and dn.return_against = %s
		group by dn_item.item_code
	""", delivery_note))

	return returned_qty_map

def get_invoiced_qty_map(delivery_note):
	"""returns a map: {dn_detail: invoiced_qty}"""
	invoiced_qty_map = {}

	for dn_detail, qty in frappe.db.sql("""select dn_detail, qty from `tabSales Invoice Item`
		where delivery_note=%s and docstatus=1""", delivery_note):
			if not invoiced_qty_map.get(dn_detail):
				invoiced_qty_map[dn_detail] = 0
			invoiced_qty_map[dn_detail] += qty

	return invoiced_qty_map

@frappe.whitelist()
def create_delivery_note_from_pick_list(source_name, target_doc = None):
	def update_item_quantity(source, target, source_parent):
		target.qty = flt(source.qty) - flt(source.delivered_qty)
		target.stock_qty = (flt(source.qty) - flt(source.delivered_qty)) * flt(source.conversion_factor)
	
	doc = get_mapped_doc('Pick List', source_name, {
		'Pick List': {
			'doctype': 'Delivery Note',
			'validation': {
				'docstatus': ['=', 1]
			}
		},
		'Sales Order Item': {
			'doctype': 'Delivery Note Item',
			'field_map': {
				'parent': 'sales_order',
				'name': 'sales_order_item'
			},
			'postprocess': update_item_quantity,
			'condition': lambda doc: abs(doc.delivered_qty) < abs(doc.qty) and doc.delivered_by_supplier!=1
		},
	}, target_doc)

	return doc

def wastage_stock_entry(self):
	flag = 0
	# for row in self.items:
	# 	if row.wastage_qty < 0:
	# 		frappe.throw("Row {}: Please Don't Enter Negative Value in Wastage Qty".format(row.idx))
	# 	elif row.wastage_qty > 0:
	# 		flag = 1
	# 		break
	if flag == 1:
		abbr = frappe.db.get_value('Company',self.company,'abbr')
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Issue"
		se.purpose = "Material Issue"
		se.posting_date = self.posting_date
		se.posting_time = self.posting_time
		se.set_posting_time = 1
		se.company = self.company
		se.reference_doctype = self.doctype
		se.reference_docname = self.name
		se.wastage = 1
	
		

		se.save(ignore_permissions=True)
		se.submit()

def cancel_wastage_entry(self):
	if frappe.db.exists("Stock Entry",{'reference_doctype': self.doctype,'reference_docname':self.name}):
		se = frappe.get_doc("Stock Entry",{'reference_doctype': self.doctype,'reference_docname':self.name})
		se.flags.ignore_permissions = True
		if se.docstatus == 1:
			se.cancel()
		se.db_set('reference_doctype','')
		se.db_set('reference_docname','')
		se.delete()

@frappe.whitelist()
def get_rate_discounted_rate(item_code, customer, company, so_number = None):
	""" This function is use to get discounted rate and rate """
	item_group, tile_quality = frappe.get_value("Item", item_code, ['item_group', 'tile_quality'])
	# parent_item_group = frappe.get_value("Item Group", item_group, 'parent_item_group')

	count = frappe.db.sql(f"""
		SELECT 
			COUNT(*) 
		FROM 
			`tabDelivery Note Item` as soi 
		JOIN 
			`tabDelivery Note` as so ON so.`name` = soi.`parent`
		WHERE 
			soi.`item_group` = '{item_group}' AND
			soi.`docstatus` = 1 AND
			so.customer = '{customer}' AND
			soi.`tile_quality` = '{tile_quality}' AND
			so.`company` = '{company}'
		LIMIT 1
	""")
	where_clause = ''
	if count[0][0]:
		where_clause = f"soi.item_group = '{item_group}' AND"
	
	data = None

	if so_number:
		data = frappe.db.sql(f"""
			SELECT 
				soi.`rate` as `rate`, soi.`discounted_rate` as `discounted_rate`
			FROM 
				`tabDelivery Note Item` as soi 
			JOIN
				`tabDelivery Note` as so ON soi.parent = so.name
			WHERE
				{where_clause}
				soi.`tile_quality` = '{tile_quality}' AND
				so.`customer` = '{customer}' AND
				so.`company` = '{company}' AND
				so.`docstatus` != 2 AND
				so.`name` = '{so_number}'
			ORDER BY
				soi.`creation` DESC
			LIMIT 
				1
		""", as_dict = True)

	if not data:
		data = frappe.db.sql(f"""
			SELECT 
				soi.`rate` as `rate`, soi.`discounted_rate` as `discounted_rate`
			FROM 
				`tabDelivery Note Item` as soi JOIN
				`tabDelivery Note` as so ON soi.parent = so.name
			WHERE
				{where_clause}
				soi.`tile_quality` = '{tile_quality}' AND
				so.`customer` = '{customer}' AND
				so.`company` = '{company}' AND
				so.`docstatus` != 2
			ORDER BY
				soi.`creation` DESC
			LIMIT 
				1
		""", as_dict = True)

	return data[0] if data else {'rate': 0, 'discounted_rate': 0}

def update_tax_paid_check_in_taxes(self):
	tax_dict = {}
	get_tax_template_details = get_tax_template(self.tax_category, self.company,)
	if get_tax_template_details:
		if self.taxes_and_charges != get_tax_template_details:
			self.taxes_and_charges = get_tax_template_details
		data = frappe.get_all("Sales Taxes and Charges",{"parent":get_tax_template_details},["charge_type","account_head","included_in_print_rate","tax_exclusive"])
		if data:
			for row in data:
				tax_dict[(row.charge_type, row.account_head)] = row
	if tax_dict:
		for tax in self.taxes:
			tax_template_data = tax_dict.get((tax.charge_type, tax.account_head))
			if tax_template_data:
				tax.included_in_print_rate = tax_template_data.included_in_print_rate
				tax.tax_exclusive = tax_template_data.tax_exclusive
			# else:
			# 	tax.tax_exclusive = self.tax_paid

# def validate_taxes_and_charges(self):
	# for row in self.taxes:
	# 	if "gst" in row.account_head.lower():
	# 		frappe.throw("Please Correct Sales Taxes and Charges Templete first.")

def validate_customer_sales_person(self):
	doc = frappe.get_doc("Customer", self.customer)
	if not doc.sales_team or not doc.sales_team[0].sales_person:
		frappe.throw(_('Mention a Sales Person in Customer {}').format(self.customer))
	if not any(row.company == self.company for row in doc.sales_team):
		frappe.throw(_('Mention a Sales Person in Customer {} for company {}').format(self.customer, self.company))

def change_rate_in_dn_and_so(self):
	for row in self.items:
		row.db_set("rate", 1)
		row.db_set("sqf_rate", 0)
		sales_order = row.against_sales_order
		doc = frappe.get_doc("Sales Order", sales_order)
		for so_row in doc.items:
			so_row.db_set("rate", 1)
			so_row.db_set("sqf_rate", 0)


def si_ref_validation(self):
	si_date = frappe.db.get_value("Sales Invoice", self.custom_si_ref, "posting_date")
	posting_date = self.posting_date
	if self.custom_si_ref:
		if posting_date == si_date:
			pass		
		else:
			frappe.throw('Sales Invoice Date and Delivery Note Date must be a same.')
	

def link_dn_to_si_ref(self):
	if self.custom_si_ref:
		si_doc = frappe.get_doc("Sales Invoice",self.custom_si_ref)
		if self.customer == si_doc.primary_customer:	
			frappe.db.set_value("Sales Invoice", self.custom_si_ref, "delivery_note", self.name)
			frappe.db.set_value("Sales Invoice", self.custom_si_ref, "verify_mobile_no", self.verify_mobile_no)
		
# def validate_mobile_numbers(self, method):
# 	if self.contact_mobile and not self.verify_mobile_no:
# 		frappe.throw("Whatsapp Mobile No is Mandatory to match with Mobile No")
	
# 	if not self.contact_mobile and not self.verify_mobile_no:
# 		frappe.throw("Mobile No and Whatsapp Mobile No is Mandatory.")
# 	# Check if both fields have values
# 	if self.contact_mobile and self.verify_mobile_no:
# 		# Normalize mobile numbers by removing non-numeric characters
# 		normalized_mobile_no = ''.join(filter(str.isdigit, self.contact_mobile))
# 		normalized_verify_mobile_no = ''.join(filter(str.isdigit, self.verify_mobile_no))

# 		# Check if the normalized values match
# 		if normalized_mobile_no != normalized_verify_mobile_no:
# 			if not self.submit_dn_without_matching_mobile_no:
# 				frappe.throw(_("Mobile numbers do not match. Please ensure they are the same."), title="Validation Error")
# 			else:
# 				frappe.msgprint(_("Mobile numbers do not match. You have Submitted this Document without Matching Mobile Nos."))
		
def validate_quantity(self, method):
	if self.total_qty and self.total_si_qty:
		if not self.total_qty == self.total_si_qty:
			if not self.submit_dn_without_matching_qty:
				frappe.throw(_("Total Qty and Total SI Qty not matched."))
			else:
				frappe.msgprint(_("Total Qty and Total SI Qty not matched. You have Submitted this Document without Matching Total Qty."))

def normalize_mobile_number(mobile):
	# Remove non-numeric characters and leading zeros
	return ''.join(filter(str.isdigit, mobile.lstrip('0')))


def set_pi_details(self):
	for row in self.items:
		if row.against_pick_list:

			pick_list_item = frappe.db.get_value(
				"Pick List Item",
				{
					"parent": row.against_pick_list,
					"item_code": row.item_code
				},
				"name"
			)

			if pick_list_item:
				row.custom_pi_details = pick_list_item

			