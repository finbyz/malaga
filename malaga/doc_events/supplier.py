import frappe
from frappe.desk.search import validate_and_sanitize_search_inputs

@frappe.whitelist()
@validate_and_sanitize_search_inputs
def get_driver_query(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""
        SELECT name
        FROM `tabDriver`
        WHERE transporter = %(transporter)s
          AND name LIKE %(txt)s
        ORDER BY name
        LIMIT %(start)s, %(page_len)s
    """, {
        "transporter": filters.get("transporter"),
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len,
    })