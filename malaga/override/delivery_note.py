import frappe
from frappe import _
from frappe.utils import flt
from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote
from erpnext.stock.doctype.batch.batch import get_batch_qty


def set_batch_nos(doc, warehouse_field, throw=False):
	"""Automatically validate batch qty for outgoing items."""
	for d in doc.items:
		qty = d.get("stock_qty") or d.get("transfer_qty") or d.get("qty") or 0
		has_batch_no = frappe.db.get_value("Item", d.item_code, "has_batch_no")
		warehouse = d.get(warehouse_field, None)
		if has_batch_no and warehouse and qty > 0:
			if d.remove_batch:
				d.batch_no = None
				frappe.throw(
					_("Row {0}: Please add Batch No for Item {1}.").format(
						d.idx, frappe.bold(d.item_code)
					)
				)
			if d.batch_no:
				batch_qty = get_batch_qty(batch_no=d.batch_no, warehouse=warehouse)
				if flt(batch_qty, d.precision("qty")) < flt(qty, d.precision("qty")):
					frappe.throw(
						_(
							"Row #{0}: The batch {1} has only {2} qty. Please select another batch "
							"which has {3} qty available or split the row into multiple rows, "
							"to deliver/issue from multiple batches"
						).format(d.idx, d.batch_no, batch_qty, qty)
					)


_original_delivery_note_validate = DeliveryNote.validate


def validate(self):
	for item in self.items:
		item.remove_batch = False
		if not item.batch_no:
			item.remove_batch = True

	_original_delivery_note_validate(self)

	if (
		self._action not in ("save", "submit")
		and not self.is_return
		and not self.get("ignore_batch_validate")
	):
		set_batch_nos(self, "warehouse", True)
