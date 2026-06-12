// Copyright (c) 2023, nandu bhadada and contributors
// For license information, please see license.txt

frappe.ui.form.on('Selection Sheet Product', {
	item_code(frm, cdt, cdn) {
		var doc = locals[cdt][cdn];
		frappe.call({
			method: "malaga.api.get_price_list_rate",
			args: { "customer": cur_frm.doc.customer_name, "price_list": cur_frm.doc.customer_price_list, "transaction_date": cur_frm.doc.date, "qty": doc.qty, "item_code": doc.item_code },
			callback: function (r) {
				console.log(r)
				if (r.message) {
					frappe.model.set_value(cdt, cdn, "rate", r.message)
				}
			}
		})
		if(frm.doc.end_client_price_list && frm.doc.client_name){

			frappe.call({
				method: "malaga.api.get_price_list_rate",
				args: { "customer": cur_frm.doc.client_name, "price_list": cur_frm.doc.end_client_price_list, "transaction_date": cur_frm.doc.date, "qty": doc.qty, "item_code": doc.item_code },
				callback: function (r) {
					console.log(r)
					if (r.message) {
						frappe.model.set_value(cdt, cdn, "rate_client", r.message)
					}
				}
			})
		}
	},
	rate(frm, cdt, cdn) {
		calculate_total(cur_frm, cdt, cdn)
	},
	rate_client(frm,cdt,cdn){
		calculate_total(cur_frm, cdt, cdn)
	},
	qty(frm, cdt, cdn) {
		calculate_total(cur_frm, cdt, cdn)
	},
});

function calculate_total(cur_frm, cdt, cdn) {
	cur_frm.call({
		method: "calculate_total",
		doc: cur_frm.doc,
		callback: function (r) {

		}
	})

}