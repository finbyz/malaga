import frappe
from frappe.query_builder.functions import CombineDatetime, IfNull, Sum
from frappe.utils import flt, cint
from erpnext.stock.get_item_details import get_price_list_rate_for
from frappe.model.mapper import get_mapped_doc


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
