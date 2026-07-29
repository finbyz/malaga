frappe.ui.form.on("Supplier", {
    setup(frm) {
        frm.set_query("custom_driver", () => {
            return {
                query: "malaga.doc_events.supplier.get_driver_query",
                filters: {
                    transporter: frm.doc.name
                }
            };
        });
    },
    refresh(frm) {

		// Driver link field
		let df = frm.get_field("custom_driver").df;

		df.get_route_options_for_new_doc = function () {
			return {
				transporter: frm.doc.name
			};
		};

		frm.refresh_field("custom_driver");
	}

});

