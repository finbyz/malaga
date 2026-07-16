import frappe


def set_batch_from_voucher_detail(doc, method=None):
	if doc.batch_no:
		return

	batch_no = get_batch_no_for_sle(doc)
	if batch_no:
		doc.batch_no = batch_no


def persist_batch_on_sle(doc, method=None):
	if doc.batch_no:
		return

	batch_no = get_batch_no_for_sle(doc)
	if batch_no:
		frappe.db.set_value("Stock Ledger Entry", doc.name, "batch_no", batch_no, update_modified=False)


def get_batch_no_for_args(args):
	if args.get("batch_no"):
		return args.get("batch_no")

	batch_no = get_batch_from_voucher_detail(args.get("voucher_type"), args.get("voucher_detail_no"))
	if batch_no:
		return batch_no

	if args.get("serial_and_batch_bundle"):
		return get_batch_from_bundle(args.get("serial_and_batch_bundle"))

	return None


def get_batch_no_for_sle(doc):
	batch_no = get_batch_from_voucher_detail(doc.voucher_type, doc.voucher_detail_no)
	if batch_no:
		return batch_no

	if doc.serial_and_batch_bundle:
		return get_batch_from_bundle(doc.serial_and_batch_bundle)

	return None


def get_batch_from_bundle(bundle_name):
	return frappe.db.get_value(
		"Serial and Batch Entry",
		{"parent": bundle_name, "batch_no": ("is", "set")},
		"batch_no",
	)


def get_batch_from_voucher_detail(voucher_type, voucher_detail_no):
	if not voucher_type or not voucher_detail_no:
		return None

	detail_doctype = get_voucher_detail_doctype(voucher_type)
	if not detail_doctype:
		return None

	detail_meta = frappe.get_meta(detail_doctype)
	fields = []
	if detail_meta.has_field("batch_no"):
		fields.append("batch_no")
	if detail_meta.has_field("serial_and_batch_bundle"):
		fields.append("serial_and_batch_bundle")

	if not fields:
		return None

	detail = frappe.db.get_value(detail_doctype, voucher_detail_no, fields, as_dict=True)
	if not detail:
		return None

	if detail.get("batch_no"):
		return detail.batch_no

	if detail.get("serial_and_batch_bundle"):
		return get_batch_from_bundle(detail.serial_and_batch_bundle)

	return None


def get_voucher_detail_doctype(voucher_type):
	if voucher_type == "Stock Entry":
		return "Stock Entry Detail"

	item_doctype = f"{voucher_type} Item"
	if frappe.db.exists("DocType", item_doctype):
		child_meta = frappe.get_meta(item_doctype)
		if child_meta.has_field("batch_no") or child_meta.has_field("serial_and_batch_bundle"):
			return item_doctype

	for field in frappe.get_meta(voucher_type).get_table_fields():
		child_meta = frappe.get_meta(field.options)
		if child_meta.has_field("batch_no") or child_meta.has_field("serial_and_batch_bundle"):
			return field.options

	return None
