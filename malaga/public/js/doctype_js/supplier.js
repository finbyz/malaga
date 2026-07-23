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
    }
});