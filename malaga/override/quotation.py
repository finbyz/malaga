import frappe
from frappe.utils import flt, cint
from erpnext.selling.doctype.quotation.quotation import Quotation


class QuotationCustom(Quotation):
    @frappe.whitelist()
    def calculcate(self):
        for row in self.items:
            conversion_factor = frappe.db.get_value(
                "UOM Conversion Detail",
                {"parent": row.item_code, "uom": "Box"},
                "conversion_factor",
            )
            if conversion_factor:
                if cint(row.auto_box_adjust) == 1:
                    adjusted_box = round(flt(row.qty) / flt(conversion_factor))
                    row.qty = flt(adjusted_box) * flt(conversion_factor)
                    row.box = adjusted_box
                else:
                    row.box = flt(row.qty) / flt(conversion_factor)
                    # row.qty = flt(row.box) * flt(conversion_factor)

    @frappe.whitelist()
    def calculcate_box(self):
        for row in self.items:
            conversion_factor = frappe.db.get_value(
                "UOM Conversion Detail",
                {"parent": row.item_code, "uom": "Box"},
                "conversion_factor",
            )
            if conversion_factor:
                row.qty = flt(row.box) * flt(conversion_factor)
