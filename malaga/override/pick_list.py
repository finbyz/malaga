from erpnext.stock.doctype.pick_list.pick_list import PickList

_original_validate_warehouses = PickList.validate_warehouses


def validate_warehouses(self):
	# Allow draft saves while batch/warehouse picking is still in progress.
	if self.docstatus.is_draft() and getattr(self, "_action", None) != "submit":
		return
	_original_validate_warehouses(self)
