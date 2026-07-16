import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, format_time, floor
from erpnext.stock.stock_ledger import get_previous_sle, NegativeStockError
from erpnext.stock.doctype.pick_list.pick_list import get_available_item_locations_for_batched_item
from frappe.model.naming import parse_naming_series
from frappe.permissions import get_doctypes_with_read
from datetime import datetime
from six import iteritems


def raise_exceptions(self):
	msg_list = []
	for warehouse, exceptions in iteritems(self.exceptions):
		deficiency = min(e["diff"] for e in exceptions)

		if ((exceptions[0]["voucher_type"], exceptions[0]["voucher_no"]) in
			frappe.local.flags.currently_saving):

			msg = _("{0} units of {1} needed in {2} to complete this transaction.").format(
				abs(deficiency), frappe.get_desk_link('Item', exceptions[0]["item_code"]),
				frappe.get_desk_link('Warehouse', warehouse))
		else:
			msg = _("{0} units of {1} needed in {2} on {3} {4} for {5} to complete this transaction.").format(
				abs(deficiency), frappe.get_desk_link('Item', exceptions[0]["item_code"]),
				frappe.get_desk_link('Warehouse', warehouse),
				exceptions[0]["posting_date"], exceptions[0]["posting_time"],
				frappe.get_desk_link(exceptions[0]["voucher_type"], exceptions[0]["voucher_no"]))

		if msg:
			msg_list.append(msg)

	allow_negative_stock = frappe.db.get_value("Company", self.company, "allow_negative_stock")

	if not allow_negative_stock:
		if msg_list:
			message = "\n\n".join(msg_list)
			if self.verbose:
				frappe.throw(message, NegativeStockError, title='Insufficient Stock')
			else:
				raise NegativeStockError(message)


def set_actual_qty(self):
	allow_negative_stock = cint(frappe.db.get_value("Stock Settings", None, "allow_negative_stock")) or cint(frappe.db.get_value("Company", self.company, "allow_negative_stock"))

	for d in self.get('items'):
		previous_sle = get_previous_sle({
			"item_code": d.item_code,
			"warehouse": d.s_warehouse or d.t_warehouse,
			"posting_date": self.posting_date,
			"posting_time": self.posting_time
		})

		d.actual_qty = previous_sle.get("qty_after_transaction") or 0

		if d.docstatus==1 and d.s_warehouse and not allow_negative_stock and flt(d.actual_qty, d.precision("actual_qty")) < flt(d.transfer_qty, d.precision("actual_qty")):
			frappe.throw(_("Row {0}: Quantity not available for {4} in warehouse {1} at posting time of the entry ({2} {3})").format(d.idx,
				frappe.bold(d.s_warehouse), formatdate(self.posting_date),
				format_time(self.posting_time), frappe.bold(d.item_code))
				+ '<br><br>' + _("Available quantity is {0}, you need {1}").format(frappe.bold(d.actual_qty),
					frappe.bold(d.transfer_qty)),
				NegativeStockError, title=_('Insufficient Stock'))


def set_item_locations(self):
	pass


def pick_list_before_submit(self):
	for item in self.locations:
		if not frappe.get_cached_value("Item", item.item_code, "has_serial_no"):
			continue
		if not item.serial_no:
			frappe.throw(
				_("Row #{0}: {1} does not have any available serial numbers in {2}").format(
					frappe.bold(item.idx), frappe.bold(item.item_code), frappe.bold(item.warehouse)
				),
				title=_("Serial Nos Required"),
			)
		if len(item.serial_no.split("\n")) == item.picked_qty:
			continue
		frappe.throw(
			_(
				"For item {0} at row {1}, count of serial numbers does not match with the picked quantity"
			).format(frappe.bold(item.item_code), frappe.bold(item.idx)),
			title=_("Quantity Mismatch"),
		)


def get_current_tax_amount(self, item, tax, item_tax_map):
	tax_rate = self._get_tax_rate(tax, item_tax_map)
	current_tax_amount = 0.0

	if tax.charge_type == "Actual":
		actual = flt(tax.tax_amount, tax.precision("tax_amount"))
		current_tax_amount = item.net_amount*actual / self.doc.net_total if self.doc.net_total else 0.0

	elif tax.charge_type == "On Net Total":
		if self.doc.get('authority') == "Unauthorized":
			current_tax_amount = (tax_rate / 100.0) * item.discounted_net_amount
		else:
			current_tax_amount = (tax_rate / 100.0) * item.net_amount
	elif tax.charge_type == "On Previous Row Amount":
		current_tax_amount = (tax_rate / 100.0) * \
			self.doc.get("taxes")[cint(tax.row_id) - 1].tax_amount_for_current_item
	elif tax.charge_type == "On Previous Row Total":
		current_tax_amount = (tax_rate / 100.0) * \
			self.doc.get("taxes")[cint(tax.row_id) - 1].grand_total_for_current_item
	elif tax.charge_type == "On Item Quantity":
		current_tax_amount = tax_rate * item.stock_qty

	if self.doc.get('authority') == "Unauthorized":
		current_net_amount = item.discounted_net_amount
	else:
		current_net_amount = item.net_amount

	self.set_item_wise_tax(
		item,
		tax,
		tax_rate,
		current_tax_amount,
		current_net_amount
	)

	return current_tax_amount


def determine_exclusive_rate(self):
	if not any((cint(tax.included_in_print_rate) for tax in self.doc.get("taxes"))):
		return

	for item in self.doc.get("items"):
		item_tax_map = self._load_item_tax_rate(item.item_tax_rate)
		cumulated_tax_fraction = 0
		for i, tax in enumerate(self.doc.get("taxes")):
			tax.tax_fraction_for_current_item, inclusive_tax_amount_per_qty = self.get_current_tax_fraction(tax, item_tax_map)
			if i == 0:
				tax.grand_total_fraction_for_current_item = 1 + tax.tax_fraction_for_current_item
			else:
				tax.grand_total_fraction_for_current_item = \
					self.doc.get("taxes")[i-1].grand_total_fraction_for_current_item \
					+ tax.tax_fraction_for_current_item

			cumulated_tax_fraction += tax.tax_fraction_for_current_item

		if cumulated_tax_fraction and not self.discount_amount_applied and item.qty:
			if self.doc.get('authority') == "Unauthorized":
				amount_diff = item.amount - item.discounted_amount
				if tax.tax_exclusive == 1:
					item.discounted_net_amount = flt(item.amount - amount_diff)
					item.net_amount = item.amount - ((flt(item.amount - amount_diff)) * cumulated_tax_fraction)
				else:
					item.discounted_net_amount = flt((item.amount - amount_diff) / (1 + cumulated_tax_fraction))
					item.net_amount = item.amount - (item.discounted_amount - item.discounted_net_amount)

				try:
					item.discounted_net_rate = flt(item.discounted_net_amount / item.real_qty)
				except:
					item.discounted_net_rate = 0

				item.net_rate = flt(item.net_amount / item.qty, item.precision("net_rate"))
			else:
				item.net_amount = flt(item.amount / (1 + cumulated_tax_fraction))
				item.net_rate = flt(item.net_amount / item.qty, item.precision("net_rate"))

			item.discount_percentage = flt(item.discount_percentage, item.precision("discount_percentage"))
			self._set_in_company_currency(item, ["net_rate", "net_amount"])


def calculate_taxes(self):
    self.doc.rounding_adjustment = 0
    actual_tax_dict = dict([[tax.idx, flt(tax.tax_amount, tax.precision("tax_amount"))]
        for tax in self.doc.get("taxes") if tax.charge_type == "Actual"])

    for n, item in enumerate(self.doc.get("items")):
        item_tax_map = self._load_item_tax_rate(item.item_tax_rate)
        for i, tax in enumerate(self.doc.get("taxes")):
            current_tax_amount = self.get_current_tax_amount(item, tax, item_tax_map)

            if tax.charge_type == "Actual":
                actual_tax_dict[tax.idx] -= current_tax_amount
                if n == len(self.doc.get("items")) - 1:
                    current_tax_amount += actual_tax_dict[tax.idx]

            if tax.charge_type != "Actual" and \
                not (self.discount_amount_applied and self.doc.apply_discount_on == "Grand Total"):
                    tax.tax_amount += current_tax_amount

            tax.tax_amount_for_current_item = current_tax_amount
            tax.tax_amount_after_discount_amount += current_tax_amount

            current_tax_amount = self.get_tax_amount_if_for_valuation_or_deduction(current_tax_amount, tax)

            if i == 0:
                if self.doc.get('authority') == "Unauthorized":
                    tax.grand_total_for_current_item = flt(item.discounted_net_amount + current_tax_amount)
                else:
                    tax.grand_total_for_current_item = flt(item.net_amount + current_tax_amount)
            else:
                tax.grand_total_for_current_item = \
                    flt(self.doc.get("taxes")[i-1].grand_total_for_current_item + current_tax_amount)

            if n == len(self.doc.get("items")) - 1:
                self.round_off_totals(tax)
                self.set_cumulative_total(i, tax)

                self._set_in_company_currency(tax,
                    ["total", "tax_amount", "tax_amount_after_discount_amount"])

                if i == (len(self.doc.get("taxes")) - 1) and self.discount_amount_applied \
                    and self.doc.discount_amount and self.doc.apply_discount_on == "Grand Total":
                        self.doc.rounding_adjustment = flt(self.doc.grand_total
                            - flt(self.doc.discount_amount) - tax.total,
                            self.doc.precision("rounding_adjustment"))

    # ── ADD THIS BLOCK ──────────────────────────────────────────────────────
    if self.doc.get("taxes"):
        last_tax = self.doc.get("taxes")[-1]
        self.grand_total_diff = flt(last_tax.total) - flt(self.doc.grand_total)
    else:
        self.grand_total_diff = 0.0


def actual_amt_check(self):
	if self.batch_no and not self.get("allow_negative_stock"):
		batch_bal_after_transaction = flt(frappe.db.sql("""select sum(actual_qty)
			from `tabStock Ledger Entry`
			where warehouse=%s and item_code=%s and batch_no=%s""",
			(self.warehouse, self.item_code, self.batch_no))[0][0])

		if batch_bal_after_transaction < 0:
			frappe.throw(_("Stock balance in Batch {0} will become negative {1} for Item {2} at Warehouse {3}")
				.format(self.batch_no, batch_bal_after_transaction, self.item_code, self.warehouse))

		batch_bal_after_transaction_without_warehouse = flt(frappe.db.sql("""select sum(actual_qty)
			from `tabStock Ledger Entry`
			where item_code=%s and batch_no=%s""",
			(self.item_code, self.batch_no))[0][0])

		picked_qty = flt(frappe.db.sql("""select sum(qty - (delivered_qty + wastage_qty))
			from `tabPick List Item` as pli
			JOIN `tabPick List` as pl on pl.name = pli.parent
			where pli.item_code=%s and pli.batch_no=%s and pl.docstatus = 1""",
			(self.item_code, self.batch_no))[0][0])

		if batch_bal_after_transaction_without_warehouse - picked_qty < 0:
			frappe.throw(_("Stock balance after Picked Qty in Batch {0} will become negative {1} for Item {2}")
				.format(self.batch_no, (batch_bal_after_transaction - picked_qty), self.item_code))


# from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
# class CustomStockEntry(StockEntry):
# 	def update_stock_ledger(self):
# 		sl_entries = []
# 		finished_item_row = self.get_finished_item_row()

# 		self.get_sle_for_source_warehouse(sl_entries, finished_item_row)
# 		self.get_sle_for_target_warehouse(sl_entries, finished_item_row)

# 		if self.docstatus == 2:
# 			sl_entries.reverse()

# 		allow_negative_stock = False
# 		# allow_negative_stock = frappe.db.get_value("Company", self.company, "allow_negative_stock")
# 		# self.make_sl_entries(sl_entries, 1, allow_negative_stock=1)