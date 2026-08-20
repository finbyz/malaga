frappe.ui.form.on('Sales Invoice', {
    refresh: function (frm) {
        force_return_signs(frm);
    },
    is_return: function (frm) {
        force_return_signs(frm);
    },
    validate: function (frm) {
        force_return_signs(frm);
    },
    onload_post_render: function (frm) {
        if (!frm.doc.is_return) return;
        setTimeout(function () {
            force_return_signs(frm);
        }, 500);
    }
});

frappe.ui.form.on('Sales Invoice Item', {
    item_code: async function (frm, cdt, cdn) {
        await apply_box_qty_conversion(frm, cdt, cdn);
        await set_default_qty_from_box(frm, cdt, cdn);
    },

    qty: async function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row._setting_qty) {
            row._setting_qty = false;
            return;
        }
        await apply_box_qty_conversion(frm, cdt, cdn);
    },

    box: async function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row._setting_box) {
            row._setting_box = false;
            return;
        }
        await set_qty_from_box(frm, cdt, cdn);
    },
});

function force_return_signs(frm) {
    if (!frm.doc.is_return) return;

    let changed = false;
    (frm.doc.items || []).forEach(function (row) {
        if (flt(row.box) > 0) {
            row.box = -Math.abs(flt(row.box));
            changed = true;
        }
        if (flt(row.qty) > 0) {
            row.qty = -Math.abs(flt(row.qty));
            changed = true;
        }
    });

    if (changed) frm.refresh_field("items");
}

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

    if (row._setting_qty) {
        row._setting_qty = false;
        return;
    }

    if (!row.item_code || !row.qty) return;

    let item = await get_box_details(row);
    if (!item.allow_box_conversion) return;

    let box_qty = flt(item.custom_box_qty_sqm);
    if (!box_qty) return;

    let qty = Math.abs(flt(row.qty));
    let boxes;

    if (item.only_round_up_qty)
        boxes = Math.ceil(qty / box_qty);
    else if (item.only_round_down_qty)
        boxes = Math.floor(qty / box_qty);
    else
        boxes = Math.round(qty / box_qty);

    boxes = Math.max(1, boxes);

    let new_qty = flt(boxes * box_qty, precision("qty", row));

    if (frm.doc.is_return) {
        new_qty = -Math.abs(new_qty);
    }

    row._setting_box = true;
    await frappe.model.set_value(
        cdt, cdn, "box",
        frm.doc.is_return ? -boxes : boxes
    );

    if (Math.abs(new_qty - qty) < 0.000001) return;

    row._setting_qty = true;
    await frappe.model.set_value(cdt, cdn, "qty", new_qty);
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

    let qty = flt(Math.abs(row.box) * box_qty, precision("qty", row));

    if (frm.doc.is_return) {
        qty = -Math.abs(qty);
    }

    if (Math.abs(qty - row.qty) < 0.000001) return;

    row._setting_qty = true;
    await frappe.model.set_value(cdt, cdn, "qty", qty);
}

async function set_default_qty_from_box(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (!row.item_code) return;

    let item = await get_box_details(row);
    if (!item.allow_box_conversion) return;

    let box_qty = flt(item.custom_box_qty_sqm);
    if (!box_qty) return;

    row._setting_box = true;
    await frappe.model.set_value(
        cdt, cdn, "box",
        frm.doc.is_return ? -1 : 1
    );

    row._setting_qty = true;
    await frappe.model.set_value(
        cdt, cdn, "qty",
        frm.doc.is_return ? -box_qty : box_qty
    );
}