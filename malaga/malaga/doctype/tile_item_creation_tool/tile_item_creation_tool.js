// Copyright (c) 2024, Finbyz and contributors
// For license information, please see license.txt

cur_frm.fields_dict.item_defaults.grid.get_field("default_warehouse").get_query = function(doc, cdt, cdn) {
	let d = locals[cdt][cdn];
	return {
		filters: {
			"is_group": 0,
			"company": d.company,
		}
	};
};

cur_frm.fields_dict.item_series.get_query = function(doc) {
	return {
		filters: {
			'is_item_series': 1,
		}
	};
};

cur_frm.fields_dict.item_group.get_query = function(doc) {
	return {
		filters: {
			'is_group': 0,
		}
	};
};

frappe.ui.form.on('Tile Item Creation Tool', {
	refresh: function(frm) {
		if (frm.doc.__islocal) {
			frappe.call({
				method: "malaga.malaga.doctype.tile_item_creation_tool.tile_item_creation_tool.get_tile_quality",
				callback: function(r) {
					if (r.message) {
						frm.doc.tile_quality = [];

						$.each(r.message, function(index, value) {
							var row = frm.add_child('tile_quality');
							frappe.model.set_value(row.doctype, row.name, 'tile_quality', value);
						});

						frm.refresh_field('tile_quality');
					}
				}
			});
		}

		if (frm.doc.docstatus == 1 && frm.doc.item_series) {
			frm.add_custom_button(__("Change Design"), function() {
				var dialog = new frappe.ui.Dialog({
					title: __("Change Item Design Name"),
					fields: [
						{
							"fieldtype": "Data",
							"label": __("Old Item Design"),
							"fieldname": "old_item_design",
							"reqd": 1,
							"default": frm.doc.item_design,
							"read_only": 1
						},
						{
							"fieldtype": "Data",
							"label": __("New Item Design"),
							"fieldname": "new_item_design",
							"reqd": 1
						},
					]
				});

				dialog.show();

				dialog.set_primary_action(__("Done"), function() {
					var values = dialog.get_values();
					frappe.call({
						method: "malaga.malaga.doctype.tile_item_creation_tool.tile_item_creation_tool.change_item_design",
						args: {
							'doc': frm.doc.name,
							'new_value': values.new_item_design
						},
						callback: function(r) {
							if (r.message) {
								frappe.set_route("Form", frm.doc.doctype, r.message[0]);
							}
						}
					});
					dialog.hide();
				});
			});
		}
	},

	item_group: function(frm) {
		if (frm.doc.__islocal) {
			if (frm.doc.is_item_series) {
				frm.doc.item_name = frm.doc.item_design;
			} else {
				frm.doc.item_name = frm.doc.item_design + '-' + frm.doc.item_group_name;
			}
		}
	},

	item_design: function(frm) {
		if (frm.doc.__islocal) {
			if (frm.doc.is_item_series) {
				frm.doc.item_name = frm.doc.item_design;
			} else {
				frm.doc.item_name = frm.doc.item_design + '-' + frm.doc.item_group_name;
			}
		}
	},
});