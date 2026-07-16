frappe.listview_settings['Pick List'] = {
	get_indicator: function(doc) {

		if (doc.docstatus === 0) {
			return [__("Draft"), "red", "docstatus,=,0"];
		}

		if (doc.docstatus === 2) {
			return [__("Cancelled"), "darkgrey", "docstatus,=,2"];
		}

		if (doc.docstatus === 1) {

			if (flt(doc.per_delivered || 0) >= 99.99) {
				return [__("Delivered"), "green", "per_delivered,>=,99.99"];
			}

			return [__("To Deliver"), "orange", "per_delivered,<,99.99"];
		}
	}
};