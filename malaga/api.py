import frappe
from frappe.query_builder.functions import CombineDatetime, IfNull, Sum
from frappe.utils import flt, cint
from erpnext.stock.get_item_details import get_price_list_rate_for
from frappe.model.mapper import get_mapped_doc
from frappe.desk.reportview import get_match_cond, get_filters_cond
import frappe
from frappe import _
from frappe.utils import flt, cint, nowdate, cstr, getdate
from frappe.model.mapper import get_mapped_doc
import datetime
from frappe.utils import getdate
from frappe.desk.notifications import get_filters_for
from frappe.utils import  get_absolute_url
import json
from frappe.utils import now_datetime, add_days


@frappe.whitelist()
def get_price_list_rate(
    customer=None, price_list=None, transaction_date=None, qty=0, item_code=None
):
    args = {
        "item_code": item_code,
        "customer": customer,
        "price_list": price_list,
        "price_list_currency": "AUD",
        "transaction_date": transaction_date,
        "conversion_rate": 1.0,
        "qty": qty,
    }
    return get_price_list_rate_for(args, item_code)


@frappe.whitelist()
def make_selection_sheet(source_name, target_doc=None, ignore_permissions=False):
    doclist = get_mapped_doc(
        "Quotation",
        source_name,
        {
            "Quotation": {
                "doctype": "Selection Sheet",
                "field_map": {"name": "quotation", "party_name": "customer_name"},
            },
            "Quotation Item": {"doctype": "Selection Sheet Product"},
        },
        target_doc,
        ignore_permissions=ignore_permissions,
    )

    doclist.calculate_total()

    return doclist


@frappe.whitelist()
def make_selection_sheet(source_name, target_doc=None, ignore_permissions=False):
    doclist = get_mapped_doc(
        "Quotation",
        source_name,
        {
            "Quotation": {
                "doctype": "Selection Sheet",
                "field_map": {"name": "quotation", "party_name": "customer_name"},
            },
            "Quotation Item": {"doctype": "Selection Sheet Product"},
        },
        target_doc,
        ignore_permissions=ignore_permissions,
    )

    doclist.calculate_total()

    return doclist


@frappe.whitelist()
def make_quotation(source_name, target_doc=None, ignore_permissions=False):
    def set_missing_values(source, target):
        target.quotation_to = "Customer"
        # target.run_method("set_missing_values")
        # target.run_method("get_schedule_dates")
        # target.run_method("calculate_taxes_and_totals")

    doclist = get_mapped_doc(
        "Selection Sheet",
        source_name,
        {
            "Selection Sheet": {
                "doctype": "Quotation",
                "field_map": {"customer_name": "party_name"},
            },
            "Selection Sheet Product": {"doctype": "Quotation Item"},
        },
        target_doc,
        set_missing_values,
        ignore_permissions=ignore_permissions,
    )

    return doclist


@frappe.whitelist()
def calculate_box(item_code, qty, auto_box_adjust=False):
    conversion_factor = frappe.db.get_value(
        "UOM Conversion Detail",
        {"parent": item_code, "uom": "Box"},
        "conversion_factor",
    )
    if conversion_factor:
        if cint(auto_box_adjust) == 1:
            adjusted_box = round(flt(qty) * flt(conversion_factor))
            return dict(
                qty=flt(adjusted_box) / flt(conversion_factor), box=adjusted_box
            )
        else:
            return dict(qty=qty, box=flt(qty) * flt(conversion_factor))


@frappe.whitelist()
def check_counter_series(name, company_series = None, date = None):
    
    if not date:
        date = datetime.date.today()
    
    
    check = frappe.db.get_value('Series', name, 'current', order_by="name")
    
    if check == 0:
        return 1
    elif check == None:
        frappe.db.sql(f"insert into tabSeries (name, current) values ('{name}', 0)")
        return 1
    else:
        return int(frappe.db.get_value('Series', name, 'current', order_by="name")) + 1


@frappe.whitelist()
def get_batch_no(doctype, txt, searchfield, start, page_len, filters):
	cond = ""

	meta = frappe.get_meta("Batch")
	searchfield = meta.get_search_fields()

	searchfields = " or ".join(["batch." + field + " like %(txt)s" for field in searchfield])

	if filters.get("posting_date"):
		cond = "and (batch.expiry_date is null or batch.expiry_date >= %(posting_date)s)"
		
	if filters.get("customer"):
		cond = "and (batch.customer = %(customer)s or ifnull(batch.customer, '') = '') "

	batch_nos = None
	args = {
		'item_code': filters.get("item_code"),
		'warehouse': filters.get("warehouse"),
		'posting_date': filters.get('posting_date'),
		'txt': "%{0}%".format(txt),
		"start": start,
		"page_len": page_len
	}

	if args.get('warehouse'):
		batch_nos = frappe.db.sql("""select sle.batch_no, batch.lot_no, batch.packing_type, round(sum(sle.actual_qty),2), sle.stock_uom
				from `tabStock Ledger Entry` sle
					INNER JOIN `tabBatch` batch on sle.batch_no = batch.name
				where
					sle.item_code = %(item_code)s
					and sle.warehouse = %(warehouse)s
					and batch.docstatus < 2
					and (sle.batch_no like %(txt)s or {searchfields})
					{0}
					{match_conditions}
				group by batch_no having sum(sle.actual_qty) > 0
				order by batch.expiry_date, sle.batch_no desc
				limit %(start)s, %(page_len)s""".format(cond, match_conditions=get_match_con(doctype), searchfields=searchfields), args)
    
	if batch_nos:
		return batch_nos
	else:
		return frappe.db.sql("""select batch.name, batch.lot_no, batch.packing_type, batch.expiry_date, sle.batch_no, batch.lot_no, round(sum(sle.actual_qty),2), sle.stock_uom from `tabBatch` batch
			JOIN `tabStock Ledger Entry` sle on sle.batch_no = batch.name
			where batch.item = %(item_code)s
			and batch.docstatus < 2
			and (sle.batch_no like %(txt)s or {searchfields})
			{0}
			{match_conditions} AND
			sle.company = '{company}'
			group by sle.batch_no having sum(sle.actual_qty) > 0
			order by batch.expiry_date, batch.name desc
			limit %(start)s, %(page_len)s""".format(cond, match_conditions=get_match_cond(doctype), company=filters.get('company'), searchfields=searchfields), args)
