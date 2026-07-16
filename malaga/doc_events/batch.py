from frappe.utils import random_string

def before_insert(doc, method):
    doc.lot_no = random_string(10)  # e.g. "A7kP9xQ2mN"