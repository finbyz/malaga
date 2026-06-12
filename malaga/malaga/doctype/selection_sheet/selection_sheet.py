# Copyright (c) 2023, nandu bhadada and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SelectionSheet(Document):
    def validate(self):
        self.calculate_total()

    @frappe.whitelist()
    def calculate_total(self):
        self.total = 0
        self.grand_total_client = 0
        for row in self.product:
            if row.rate:
                row.amount = row.qty * row.rate
            if row.rate_client:
                row.amount_client = row.qty * row.rate_client
            if row.amount:
                self.total += row.amount
            if row.amount_client:
                self.grand_total_client += row.amount_client
