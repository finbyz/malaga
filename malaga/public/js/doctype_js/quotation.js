frappe.ui.form.on("Quotation Item", {
	item_code: async function (frm, cdt, cdn) {
		await apply_box_qty_conversion(frm, cdt, cdn);
	},

	qty : async function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row._setting_qty) {
			row._setting_qty = false;
			return;
		}
		await apply_box_qty_conversion(frm, cdt, cdn);
	},

	box: async function(frm, cdt, cdn) {
			let row = locals[cdt][cdn];

		if (row._setting_box) {
			row._setting_box = false;
			return;
		}
			await set_qty_from_box(frm, cdt, cdn);
	}
});


async function get_box_details(row) {
	if (row._box_details) {
		return row._box_details;
	}

	let r = await frappe.db.get_value(
		"Item",
		row.item_code,
		[
			"allow_box_conversion",
			"custom_box_qty_sqm",
			"auto_roundoff_qty",
			"only_round_up_qty",
			"only_round_down_qty"
		]
	);

	row._box_details = r.message || {};
	return row._box_details;
}

async function apply_box_qty_conversion(frm, cdt, cdn) {

	let row = locals[cdt][cdn];

	// Ignore if qty is being updated from box
	if (row._setting_qty) {
		row._setting_qty = false;
		return;
	}

	if (!row.item_code || !row.qty) return;

	let item = await get_box_details(row);

	if (!item.allow_box_conversion) return;

	let box_qty = flt(item.custom_box_qty_sqm);

	if (!box_qty) return;

	let qty = flt(row.qty);

	let boxes;

	if (item.only_round_up_qty)
		boxes = Math.ceil(qty / box_qty);

	else if (item.only_round_down_qty)
		boxes = Math.floor(qty / box_qty);

	else
		boxes = Math.round(qty / box_qty);

	boxes = Math.max(1, boxes);

	let new_qty = flt(boxes * box_qty, precision("qty", row));

	// Always update box
	row._setting_box = true;
	await frappe.model.set_value(cdt, cdn, "box", boxes);

	// Qty already correct
	if (Math.abs(new_qty - qty) < 0.000001)
		return;

	row._setting_qty = true;
	await frappe.model.set_value(cdt, cdn, "qty", new_qty);
}


async function set_box_value(frm, cdt, cdn) {

	let row = locals[cdt][cdn];

	if (row._setting_box) {
		row._setting_box = false;
		return;
	}

	if (!row.item_code) return;

	let item = await get_box_details(row);

	let box_qty = flt(item.custom_box_qty_sqm);

	if (!box_qty) return;

	let boxes = flt(row.qty / box_qty, precision("box", row));

	row._setting_box = true;

	await frappe.model.set_value(cdt, cdn, "box", boxes);
}

async function set_qty_from_box(frm, cdt, cdn) {

	let row = locals[cdt][cdn];

	if (row._setting_box) {
		row._setting_box = false;
		return;
	}

	if (!row.item_code) return;

	let item = await get_box_details(row);

	let box_qty = flt(item.custom_box_qty_sqm);

	if (!box_qty) return;

	let qty = flt(row.box * box_qty, precision("qty", row));

	if (Math.abs(qty - row.qty) < 0.000001)
		return;

	row._setting_qty = true;

	await frappe.model.set_value(cdt, cdn, "qty", qty);
}