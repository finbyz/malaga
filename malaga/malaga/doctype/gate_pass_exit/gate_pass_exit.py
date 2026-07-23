# Copyright (c) 2026, nandu bhadada and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GatePassExit(Document):

	def on_submit(self):
		if not self.delivery__note:
			return
		
		transporter_name = frappe.db.get_value(
			"Supplier",
			self.transporter,
			"supplier_name"
		)

		frappe.db.set_value(
			"Delivery Note",
			self.delivery__note,
			{
				"transporter": self.transporter,
				"transporter_name": transporter_name or self.transporter,
				"driver": self.driver_id,
				"driver_name": self.driver_name,
				"vehicle_no": self.vehicle_number,
				
			},
			update_modified=True
		)

		frappe.db.commit()
