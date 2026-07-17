
frappe.ui.form.on('Sales Invoice Item', {
	item_code(frm, cdt, cdn) {
		setTimeout(() => {
			apply_box_qty_conversion(frm, cdt, cdn);
			set_box_value(frm, cdt, cdn);
		}, 500);
	},

	qty(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row._updating_from_box) {
			row._updating_from_box = false;
			return;
		}

		apply_box_qty_conversion(frm, cdt, cdn);
		set_box_value(frm, cdt, cdn);
	},

	box(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row._updating_from_qty) {
			row._updating_from_qty = false;
			return;
		}

		set_qty_from_box(frm, cdt, cdn);
	}

})



function apply_box_qty_conversion(frm, cdt, cdn) {
	let row = locals[cdt][cdn];

	if (!row.item_code || !row.qty) {
		return;
	}

	frappe.db.get_value(
		"Item",
		row.item_code,
		[
			"allow_box_conversion",
			"custom_box_qty_sqm",
			"auto_roundoff_qty",
			"only_round_up_qty",
			"only_round_down_qty"
		]
	).then(r => {
		let item = r.message;

		if (!item || !item.allow_box_conversion || !item.custom_box_qty_sqm) {
			return;
		}

		let box_qty = flt(item.custom_box_qty_sqm);
		if (box_qty <= 0) {
			return;
		}

		let original_qty = flt(row.qty);
		let ratio = original_qty / box_qty;
		let multiples = 1;

		// Apply rounding logic
		if (item.auto_roundoff_qty) {
			// Round to nearest box quantity
			multiples = Math.round(original_qty / box_qty);
		}
		else if (item.only_round_up_qty) {
			// Always round up
			multiples = Math.ceil(original_qty / box_qty);
		}
		else if (item.only_round_down_qty) {
			// Always round down
			multiples = Math.floor(original_qty / box_qty);
		}
		else {
			// Default to nearest if no option is selected
			multiples = Math.round(original_qty / box_qty);
		}

		// Ensure at least one box
		if (multiples < 1) {
			multiples = 1;
		}

		let new_qty = flt(
			multiples * box_qty,
			precision("qty", row)
		);

		// Prevent infinite loop due to floating-point precision
		if (Math.abs(new_qty - original_qty) > 0.0001) {
			frappe.model.set_value(cdt, cdn, "qty", new_qty);

			frappe.show_alert({
				message: __(
					"Row {0}: Qty adjusted from {1} to {2} using box quantity {3}.",
					[row.idx, original_qty, new_qty, box_qty]
				),
				indicator: "orange"
			});
		}
	});
}


function set_box_value(frm, cdt, cdn) {
	let row = locals[cdt][cdn];

	if (!row.item_code || !row.qty) {
		frappe.model.set_value(cdt, cdn, "box", 0);
		return;
	}

	frappe.db.get_value(
		"Item",
		row.item_code,
		"custom_box_qty_sqm"
	).then(r => {
		let box_qty = flt(r.message.custom_box_qty_sqm);

		if (!box_qty || box_qty <= 0) {
			frappe.model.set_value(cdt, cdn, "box", 0);
			return;
		}

		let boxes = flt(
			flt(row.qty) / box_qty,
			precision("box", row)
		);

		frappe.model.set_value(cdt, cdn, "box", boxes);
	});
}

function set_qty_from_box(frm, cdt, cdn) {
	let row = locals[cdt][cdn];

	if (!row.item_code || !row.box) {
		return;
	}

	frappe.db.get_value(
		"Item",
		row.item_code,
		"custom_box_qty_sqm"
	).then(r => {

		let box_qty = flt(r.message.custom_box_qty_sqm);

		if (!box_qty) return;

		let qty = flt(
			flt(row.box) * box_qty,
			precision("qty", row)
		);

		row._updating_from_box = true;
		frappe.model.set_value(cdt, cdn, "qty", qty);
	});
}