erpnext.utils.update_child_items = function (opts) {
	const frm = opts.frm;
	const cannot_add_row = (typeof opts.cannot_add_row === 'undefined') ? true : opts.cannot_add_row;
	const child_docname = (typeof opts.cannot_add_row === 'undefined') ? "items" : opts.child_docname;
	this.data = [];
	let me = this;
	const dialog = new frappe.ui.Dialog({
		title: __("Update Items"),
		fields: [
			{
				fieldname: "trans_items",
				fieldtype: "Table",
				label: "Items",
				cannot_add_rows: cannot_add_row,
				in_place_edit: true,
				reqd: 1,
				data: this.data,
				get_data: () => { return this.data; },
				fields: [
					{
						fieldtype: 'Data',
						fieldname: "docname",
						read_only: 1,
						hidden: 1,
					},
					{
						fieldtype: 'Link',
						fieldname: "item_code",
						options: 'Item',
						in_list_view: 1,
						read_only: 0,
						reqd: 1,
						disabled: 0,
						columns: 3,
						label: __('Item Code'),
						change: function () {
							let item_code = this.get_value();
							if (item_code) {
								this.grid_row.on_grid_fields_dict.rate.set_value(0);
							}
						},
					},
					{
						fieldtype: 'Float',
						fieldname: "qty",
						default: 0,
						read_only: 0,
						in_list_view: 1,
						columns: 1,
						label: __('Qty')
					},
					{
						fieldtype: 'Float',
						fieldname: "real_qty",
						default: 0,
						read_only: 0,
						in_list_view: 0,
						columns: 1,
						label: __('Real Qty')
					},
					{
						fieldtype: 'Currency',
						fieldname: "sqf_rate",
						default: 0,
						read_only: 0,
						in_list_view: 1,
						permlevel: 1,
						label: __('SQF Rate'),
						change: function () {
							let sqf_rate = this.get_value();
							if (sqf_rate) {
								frappe.db.get_value("Item", this.grid_row.on_grid_fields_dict.item_code.get_value(), 'item_group', (r) => {
									frappe.db.get_value("Item Group", r.item_group, 'sqf_calculation', (r) => {
										if (r.sqf_calculation) {
											this.grid_row.on_grid_fields_dict.rate.set_value(flt(sqf_rate * r.sqf_calculation));
										} else {
											this.grid_row.on_grid_fields_dict.rate.set_value(flt(sqf_rate * 15.5));
										}
									});
								});
							}
						},
					},
					{
						fieldtype: 'Currency',
						fieldname: "rate",
						default: 0,
						read_only: 0,
						in_list_view: 1,
						permlevel: 2,
						label: __('Rate')
					},
					{
						fieldtype: 'Currency',
						fieldname: "discounted_rate",
						default: 0,
						read_only: 0,
						in_list_view: 1,
						permlevel: 1,
						label: __('Discounted Rate')
					}
				]
			},
		],
		primary_action: function () {
			const trans_items = this.get_values()["trans_items"];
			frappe.call({
				method: 'malaga.update_item.update_child_qty_rate',
				freeze: true,
				args: {
					'parent_doctype': frm.doc.doctype,
					'trans_items': trans_items,
					'parent_doctype_name': frm.doc.name,
					'child_docname': child_docname
				},
				callback: function () {
					frm.reload_doc();
				}
			});
			this.hide();
			refresh_field("items");
		},
		primary_action_label: __('Update')
	});

	frm.doc[opts.child_docname].forEach(d => {
		dialog.fields_dict.trans_items.df.data.push({
			"docname": d.name,
			"name": d.name,
			"item_code": d.item_code,
			"qty": d.qty,
			"sqf_rate": d.sqf_rate,
			"rate": d.rate,
			"discounted_rate": d.discounted_rate,
			"real_qty": d.real_qty
		});
		this.data = dialog.fields_dict.trans_items.df.data;
		dialog.fields_dict.trans_items.grid.refresh();
	});
	dialog.show();
};


erpnext.selling.SalesOrderController = class SalesOrderController extends erpnext.selling.SellingController {
	refresh(doc, dt, dn) {
		var me = this;

		if (doc.docstatus == 1) {
			if (this.frm.doc.per_delivered == 0) {
				this.frm.add_custom_button(__('Unpick All'), () => this.unpick_all(this.frm.doc));
			}

			if (this.frm.has_perm("submit")) {
				if (doc.status === 'On Hold') {
					this.frm.add_custom_button(__('Resume'), function () {
						me.frm.cscript.update_status('Resume', 'Draft');
					}, __("Status"));

					if (flt(doc.per_delivered, 6) < 100 || flt(doc.per_billed) < 100) {
						this.frm.add_custom_button(__('Close'), () => this.close_sales_order(), __("Status"));
					}
				} else if (doc.status === 'Closed') {
					this.frm.add_custom_button(__('Re-open'), function () {
						me.frm.cscript.update_status('Re-open', 'Draft');
					}, __("Status"));
				}
			}

			if (doc.status !== 'Closed') {
				if (doc.status !== 'On Hold') {
					if (this.frm.has_perm("submit")) {
						if (flt(doc.per_delivered, 6) < 100 || flt(doc.per_billed) < 100) {
							this.frm.add_custom_button(__('Hold'), () => this.hold_sales_order(), __("Status"));
							this.frm.add_custom_button(__('Close'), () => this.close_sales_order(), __("Status"));
						}
					}

					if (this.frm.doc.per_picked !== 100) {
						this.frm.add_custom_button(__('Pick List'), () => this.create_pick_list(), __('Create'));
					}
				}
				this.frm.page.set_inner_btn_group_as_primary(__('Create'));
			}
		}

		this.order_type(doc);
	}

	order_type() {
		this.toggle_delivery_date();
	}

	toggle_delivery_date() {
		this.frm.fields_dict.items.grid.toggle_reqd("delivery_date",
			(this.frm.doc.order_type == "Sales" && !this.frm.doc.skip_delivery_note));
	}

	unpick_all(doc) {
		frappe.call({
			method: "malaga.doc_events.pick_list.unpick_item",
			args: { 'sales_order': doc.name },
			callback: function (r) {
				frappe.msgprint(r.message);
			}
		});
	}

	price_list_rate(doc, cdt, cdn) {
		let d = locals[cdt][cdn];
		frappe.call({
			method: "malaga.doc_events.sales_order.get_rate_discounted_rate",
			args: {
				"item_code": d.item_code,
				"customer": doc.customer,
				"company": doc.company,
				"so_number": doc.name || null
			},
			callback: function (r) {
				if (r.message) {
					frappe.model.set_value(cdt, cdn, 'rate', r.message.rate);
					frappe.model.set_value(cdt, cdn, 'discounted_rate', r.message.discounted_rate);
				}
			}
		});
		this.calculate_taxes_and_totals();
	}

	discounted_rate(frm, cdt, cdn) {
		this.calculate_taxes_and_totals();
	}

	close_sales_order() {
		this.frm.cscript.update_status("Close", "Closed");
		frappe.call({
			method: "malaga.doc_events.pick_list.unpick_item",
			args: { 'sales_order': this.frm.doc.name },
			callback: function (r) {
				frappe.msgprint(r.message);
			}
		});
	}

	update_status(label, status) {
		var doc = this.frm.doc;
		var me = this;
		frappe.ui.form.is_saving = true;
		frappe.call({
			method: "erpnext.selling.doctype.sales_order.sales_order.update_status",
			args: { status: status, name: doc.name },
			callback: function (r) {
				me.frm.reload_doc();
			},
			always: function () {
				frappe.ui.form.is_saving = false;
			}
		});
	}

	create_pick_list() {
		console.log("Creating Pick List");
		frappe.model.open_mapped_doc({
			method: "malaga.doc_events.sales_order.make_pick_list",
			frm: this.frm
		});
	}

	make_delivery_note() {
		frappe.model.open_mapped_doc({
			method: "malaga.doc_events.sales_order.make_delivery_note",
			frm: this.frm
		});
	}
};



function is_none_or_undefined(value) {
	return value === null || value === undefined || value === "None" || value === "";
}

function update_item_group_dialog_values(dialog, trans_items, dict, field) {
	if (!dict) return;
	for (const key in dict) {
		const item_group = key.includes("|||") ? key.split("|||")[0] : key;
		const value = dict[key];
		for (let i = 0; i < trans_items.length; i++) {
			if (trans_items[i].item_group === item_group) {
				dialog.fields_dict.trans_items.df.data[i][field] = value;
			}
		}
	}
	dialog.fields_dict.trans_items.grid.refresh();
}

function apply_sqf_rate_to_row(grid_row) {
	const sqf_rate = grid_row.on_grid_fields_dict.sqf_rate.get_value();
	if (!sqf_rate) return;
	frappe.db.get_value(
		"Item Group",
		grid_row.on_grid_fields_dict.item_group.get_value(),
		"sqf_calculation",
		(r) => {
			const multiplier = r.sqf_calculation || 15.5;
			grid_row.on_grid_fields_dict.rate.set_value(flt(sqf_rate * multiplier));
		}
	);
}

function open_update_item_group_rate_dialog(frm) {
	const c = frm;
	const cannot_add_row = true;
	const child_docname = "items";
	let data = [];
	const dialog = new frappe.ui.Dialog({
		title: __("Update price"),
		fields: [
			{
				fieldname: "trans_items",
				fieldtype: "Table",
				label: "Items",
				cannot_add_rows: cannot_add_row,
				in_place_edit: true,
				reqd: 1,
				data: data,
				get_data: () => data,
				fields: [
					{ fieldtype: "Data", fieldname: "docname", read_only: 1, hidden: 1 },
					{
						fieldtype: "Link",
						fieldname: "item_group",
						options: "Item Group",
						read_only: 1,
						in_list_view: 1,
						reqd: 1,
						columns: 2,
						label: __("Item group"),
					},
					{
						fieldtype: "Currency",
						fieldname: "sqf_price_list_rate",
						default: 0,
						read_only: 1,
						in_list_view: 1,
						columns: 1,
						label: __("SQF Price List Rate"),
					},
					{
						fieldtype: "Currency",
						fieldname: "sqf_rate",
						default: 0,
						in_list_view: 1,
						columns: 1,
						permlevel: 1,
						label: __("SQF Rate"),
						change: function () {
							apply_sqf_rate_to_row(this.grid_row);
						},
					},
					{
						fieldtype: "Currency",
						fieldname: "rate",
						default: 0,
						in_list_view: 1,
						columns: 1,
						permlevel: 2,
						label: __("Rate"),
					},
					{
						fieldtype: "Currency",
						fieldname: "discount_rate",
						default: 0,
						in_list_view: 1,
						columns: 1,
						permlevel: 1,
						label: __("Discounted Rate"),
					},
					{
						fieldtype: "Date",
						fieldname: "date",
						in_list_view: 1,
						columns: 1,
						label: __("Date"),
					},
				],
			},
			{
				fieldtype: "Link",
				fieldname: "payment_terms_si",
				options: "Payment Terms Template",
				label: __("Payment Terms"),
				default: frm.doc.payment_terms_template,
			},
			{
				fieldtype: "Button",
				fieldname: "si_rate",
				label: __("SI Rate"),
				click: function () {
					const trans_items = dialog.get_values()["trans_items"];
					frappe.call({
						method: "malaga.update_item.update_rate_from_si",
						args: {
							parent_doctype: c.doc.doctype,
							trans_items: trans_items,
							parent_doctype_name: c.doc.name,
							child_docname: child_docname,
							items_table: c.doc.items,
							customer: frm.doc.customer,
							company: frm.doc.company,
						},
						callback: function (r) {
							if (!r.message) return;
							const msg = r.message;
							update_item_group_dialog_values(dialog, trans_items, msg.si_price_dict, "rate");
							update_item_group_dialog_values(dialog, trans_items, msg.si_date_dict, "date");
							update_item_group_dialog_values(dialog, trans_items, msg.si_sqf_dict, "sqf_rate");
							update_item_group_dialog_values(dialog, trans_items, msg.si_sqf_pl_dict, "sqf_price_list_rate");
							if (msg.tax_paid_from_si) {
								dialog.set_value("tax_paid_from_si", msg.tax_paid_from_si);
							}
							if (msg.payment_terms_template) {
								dialog.set_value("payment_terms_si", msg.payment_terms_template);
							}
						},
					});
				},
			},
			{
				fieldtype: "Check",
				fieldname: "tax_paid",
				label: __("Tax Paid From Quotation"),
			},
			{
				fieldtype: "Check",
				fieldname: "tax_paid_from_si",
				default: frm.doc.tax_paid,
				label: __("Tax Paid From Sales Invoice"),
			},
		],
		primary_action: function () {
			const trans_items = this.get_values()["trans_items"];
			const tax_paid = dialog.get_value("tax_paid");
			const tax_paid_from_si = dialog.get_value("tax_paid_from_si");
			const payment_terms_template_si = dialog.get_value("payment_terms_si");
			frappe.call({
				method: "malaga.update_item.update_child_price",
				freeze: true,
				args: {
					parent_doctype: c.doc.doctype,
					trans_items: trans_items,
					parent_doctype_name: c.doc.name,
					child_docname: child_docname,
					items_table: c.doc.items,
					tax_paid: tax_paid,
					tax_paid_from_si: tax_paid_from_si,
					payment_terms_template_si: payment_terms_template_si,
				},
				callback: function () {
					if (cint(tax_paid_from_si)) {
						frm.set_value("tax_paid", tax_paid_from_si);
					} else if (cint(tax_paid)) {
						frm.set_value("tax_paid", tax_paid);
					}
					if (payment_terms_template_si) {
						frm.set_value("payment_terms_template", payment_terms_template_si);
					}
					frm.reload_doc();
				},
			});
			this.hide();
		},
		primary_action_label: __("Update"),
		secondary_action: function () {
			const trans_items = dialog.get_values()["trans_items"];
			frappe.call({
				method: "malaga.update_item.update_child_rate",
				args: {
					customer: frm.doc.customer,
					trans_items: trans_items,
					items_table: frm.doc.items,
					parent_doctype: frm.doc.doctype,
					parent_doctype_name: frm.doc.name,
					child_docname: child_docname,
				},
				callback: function (r) {
					if (!r.message) return;
					const msg = r.message;
					update_item_group_dialog_values(dialog, trans_items, msg.quo_price_dict, "rate");
					update_item_group_dialog_values(dialog, trans_items, msg.qo_date_dict, "date");
					update_item_group_dialog_values(dialog, trans_items, msg.qo_sqf_dict, "sqf_rate");
					if (msg.tax_paid_from_qo) {
						dialog.set_value("tax_paid", msg.tax_paid_from_qo);
					}
					if (msg.payment_terms_template_qo) {
						dialog.set_value("payment_terms_si", msg.payment_terms_template_qo);
					}
				},
			});
		},
		secondary_action_label: __("Quotation Rate"),
	});

	dialog.$wrapper.find(".modal-dialog").css({
		width: "80%",
		"max-width": "1000px",
	});
	dialog.$wrapper.find(".form-layout").css({
		"max-height": "70vh",
		"overflow-y": "auto",
	});

	const item_groups = [];
	c.doc.items.forEach((d) => {
		if (!item_groups.includes(d.item_group)) {
			dialog.fields_dict.trans_items.df.data.push({
				docname: d.name,
				name: d.name,
				item_group: d.item_group,
				rate: d.rate,
				discount_rate: d.discounted_rate,
				sqf_rate: d.sqf_rate,
				sqf_price_list_rate: d.sqf_price_list_rate || 0,
				price_list_rate: d.price_list_rate || 0,
			});
			data = dialog.fields_dict.trans_items.df.data;
			dialog.fields_dict.trans_items.grid.refresh();
			item_groups.push(d.item_group);
		}
	});

	dialog.set_value("tax_paid_from_si", c.doc.tax_paid);
	dialog.set_value("payment_terms_si", c.doc.payment_terms_template);
	dialog.show();
}


frappe.ui.form.on('Sales Order', {
	onload: function (frm) {
		// Set filter queries
		frm.set_query("taxes_and_charges", function (doc) {
			return {
				filters: [
					['Sales Taxes and Charges Template', 'company', '=', doc.company],
					['Sales Taxes and Charges Template', 'tax_paid', '=', doc.tax_paid || 0],
					['Sales Taxes and Charges Template', 'tax_category', '=', doc.tax_category]
				]
			};
		});

		frm.fields_dict.customer.get_query = function (doc) {
			return { filters: { "disabled": 0 } };
		};

		frm.set_query("shipping_address_name", function () {
			return {
				query: "frappe.contacts.doctype.address.address.address_query",
				filters: { link_doctype: "Customer", link_name: frm.doc.customer }
			};
		});

		frm.set_query("customer_address", function () {
			return {
				query: "frappe.contacts.doctype.address.address.address_query",
				filters: { link_doctype: "Customer", link_name: frm.doc.customer }
			};
		});

		frm.set_query("item_code", "items", function (doc) {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters: [['is_sales_item', '=', 1]]
			};
		});

		frm.set_query("customer", function (doc) {
			return { query: "erpnext.controllers.queries.customer_query" };
		});

		frm.set_query("primary_customer", function (doc) {
			return { query: "erpnext.controllers.queries.customer_query" };
		});

		frm.fields_dict.items.grid.get_field("item_series").get_query = function (doc) {
			return { filters: { "authority": "Authorized" } };
		};

		frm.set_query('primary_customer', function () {
			return { filters: { 'is_primary_customer': 1 } };
		});

		frm.set_query('company', function () {
			return { filters: { 'authority': "Unauthorized" } };
		});

		frm.trigger('naming_series');

		if (frm.doc.__islocal) {
			frm.trigger('set_bank_account');
		}

		if (frm.doc.per_delivered > 0) {
			frm.set_df_property("tax_category", "allow_on_submit", 0);
			frm.set_df_property("tax_paid", "allow_on_submit", 0);
			frm.set_df_property("taxes_and_charges", "allow_on_submit", 0);
		}

		if (frm.doc.docstatus == 1) {
			frm.add_custom_button(__("Change Customer"), function () {
				let dialog = new frappe.ui.Dialog({
					'title': 'Change Customer',
					'fields': [
						{ fieldtype: "Link", fieldname: "old_customer", label: __('Old Customer'), options: "Customer", default: frm.doc.customer, read_only: 1 },
						{ fieldtype: "Link", fieldname: "new_customer", label: __('New Customer'), options: "Customer" },
					],
				});
				dialog.show();
				dialog.set_primary_action(__('Change'), function () {
					var values = dialog.get_values();
					frappe.call({
						method: "malaga.doc_events.sales_order.change_customer",
						args: { customer: values.new_customer, doc: frm.doc.name },
						callback: (r) => {
							if (r.message) {
								dialog.hide();
								frm.reload_doc();
							}
						}
					});
				});
				dialog.get_close_btn().on('click', () => dialog.hide());
			});
		}
	},

	refresh: function (frm) {
		frm.set_df_property("company", "read_only", (!frm.doc.__islocal || frm.doc.amended_from) ? 1 : 0);

		if (frm.doc.amended_from && frm.doc.__islocal && frm.doc.docstatus == 0) {
			frm.set_value("so_ref", "");
		}

		// Remove default Delivery Note button and add custom one
		setTimeout(() => {
			frm.remove_custom_button('Delivery Note', 'Create');
		}, 10);


		if (frm.doc.status !== 'Closed' && frm.doc.status !== 'On Hold') {
			frm.add_custom_button(__('Delivery Note '), () => make_delivery_note_based_on_delivery_date(frm), __('Create'));
		}

	},

	before_save: function (frm) {
		frm.trigger('calculate_total');
		if (!frm.doc.primary_customer && frm.fields_dict['primary_customer']) {
			frm.set_value('primary_customer', frm.doc.customer);
		}
		frm.doc.sales_team = [];
		if (frm.doc.tax_category) {
			frm.trigger('get_taxes');
		}
	},
	validate: function (frm) {
		frm.doc.items.forEach(function (doc) {
			if (doc.uom != doc.stock_uom) {
				if (doc.stock_qty && doc.qty) {
					frappe.model.set_value(doc.doctype, doc.name, "conversion_factor", doc.stock_qty / doc.qty);
				}
			}
		});
		if (frm.doc.tax_category) {
			frm.trigger('get_taxes');
		}
	},

	unpick_all: function (frm) {
		frappe.call({
			method: "malaga.doc_events.pick_list.unpick_item",
			args: { 'sales_order': frm.doc.name },
			callback: function (r) {
				frappe.msgprint(r.message);
			}
		});
	},

	correct_picked_qty: function (frm) {
		frappe.call({
			method: "malaga.doc_events.pick_list.correct_picked_qty",
			args: { 'sales_order': frm.doc.name },
			callback: function (r) {
				frappe.msgprint(r.message);
			}
		});
	},

	lotwise_balance: function (frm) {
		window.open(`/app/query-report/Lot-Wise Balance/?company=${frm.doc.company}&sales_order=${frm.doc.name}`);
	},

	customer: function (frm) {
		if (frm.doc.customer) {
			frm.set_value("primary_customer", '');
			frappe.db.get_value("Customer", frm.doc.customer, 'primary_customer').then(function (r) {
				frm.set_value("primary_customer", r.message.primary_customer);
			});
			frappe.db.get_value("Customer", frm.doc.customer, 'sales_head').then(function (r) {
				frm.set_value("sales_head", r.message.sales_head);
			});
			frappe.db.get_value("Customer", frm.doc.customer, 'dispatch_person').then(function (r) {
				frm.set_value("dispatch_person", r.message.dispatch_person);
			});
			frappe.db.get_value("Customer", frm.doc.customer, 'sales_representative').then(function (r) {
				frm.set_value("regional_sales_manager", r.message.sales_representative);
			});
		}
	},

	company: function (frm) {
		frm.trigger('naming_series');
		frm.trigger('set_bank_account');
		frm.trigger('order_priority');
	},

	delivery_date: function (frm) {
		$.each(frm.doc.items || [], function (i, d) {
			d.delivery_date = frm.doc.delivery_date;
		});
		refresh_field("items");
	},

	transaction_date: function (frm) {
		frm.trigger('naming_series');
		frm.trigger('order_priority');
	},

	tax_category: function (frm) {
		frm.trigger('get_taxes');
	},

	tax_paid: function (frm) {
		if (frm.doc.tax_category) {
			frm.trigger('get_taxes');
		}
	},

	get_taxes: function (frm) {
		frappe.call({
			method: "malaga.doc_events.sales_order.get_tax_template",
			args: {
				'tax_paid': frm.doc.tax_paid,
				'tax_category': frm.doc.tax_category,
				'company': frm.doc.company,
				'is_opening': frm.doc.is_opening
			},
			callback: function (r) {
				if (r.message) {
					frm.set_value('taxes_and_charges', r.message);
				} else {
					frm.set_value('taxes_and_charges', null);
					frm.set_value('taxes', []);
				}
				frm.refresh_field("taxes");
			}
		});
	},

	set_bank_account: function (frm) {
		frappe.db.get_value("Company", frm.doc.company, ['authority', 'alternate_company'], function (d) {
			if (d.authority == 'Authorized') {
				frappe.db.get_value("Bank Account", { 'company': frm.doc.company, 'is_default': 1 }, 'name', function (r) {
					frm.set_value('bank_account', r.name);
				});
			} else if (d.authority == 'Unauthorized') {
				frappe.db.get_value("Bank Account", { 'company': d.alternate_company, 'is_default': 1 }, 'name', function (s) {
					frm.set_value('bank_account', s.name);
				});
			}
		});
	},

	order_priority: function (frm) {
		if (frm.doc.order_priority && frm.doc.company && frm.doc.transaction_date) {
			frappe.call({
				method: "malaga.doc_events.sales_order.update_order_rank_",
				args: {
					'date': frm.doc.transaction_date,
					'order_priority': frm.doc.order_priority,
					'company': frm.doc.company
				},
				callback: function (r) {
					if (r.message) {
						frm.set_value('order_item_priority', r.message.order_item_priority);
						frm.set_value('order_rank', r.message.order_rank);
					}
				}
			});
		}
	},

	calculate_total: function (frm) {
		let total_qty = 0.0;
		let total_real_qty = 0.0;
		let total_picked_qty = 0.0;
		let total_picked_weight = 0.0;

		frm.doc.items.forEach(function (d) {
			total_qty += flt(d.qty);
			total_real_qty += flt(d.real_qty);
			total_picked_qty += flt(d.picked_qty);
			d.picked_weight = flt(d.weight_per_unit * d.picked_qty);
			total_picked_weight += flt(d.picked_weight);
			d.total_weight = flt(d.weight_per_unit * d.qty);
		});

		frm.set_value("total_qty", total_qty);
		frm.set_value("total_real_qty", total_real_qty);
		frm.set_value("total_picked_qty", total_picked_qty);
		frm.set_value("total_picked_weight", total_picked_weight);
	},

	update_items: function (frm) {
		erpnext.utils.update_child_items({
			frm: frm,
			child_docname: "items",
			child_doctype: "Sales Order Detail",
			cannot_add_row: false,
		});
	},

	update_item_group_rate: function (frm) {
		open_update_item_group_rate_dialog(frm);
	},

	before_workflow_action: function (frm) {
		if (frm.doc.workflow_state == 'Applied') {
			frm.doc.items.forEach(function (d) {
				if (!d.rate) { d.rate = 1; }
			});
		}
	},
});


frappe.ui.form.on("Sales Order Item", {
	items_add: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		row.delivery_date = frm.doc.delivery_date;
		frm.refresh_field("items");
	},

	item_code: function (frm, cdt, cdn) {
		frappe.db.get_value("Company", frm.doc.company, "default_packing_type", function (r) {
			if (r.default_packing_type) {
				frappe.model.set_value(cdt, cdn, 'packing_type', r.default_packing_type);
			}
		});
		setTimeout(() => apply_box_qty_conversion(frm, cdt, cdn), 500);
	},

	sqf_rate: function (frm, cdt, cdn) {
		let d = locals[cdt][cdn];
		if (d.sqf_rate) {
			frappe.db.get_value("Item Group", d.item_group, 'sqf_calculation', function (r) {
				if (r.sqf_calculation) {
					frappe.model.set_value(cdt, cdn, 'rate', flt(d.sqf_rate * r.sqf_calculation));
				} else {
					frappe.model.set_value(cdt, cdn, 'rate', flt(d.sqf_rate * 15.5));
				}
			});
		}
	},

	discounted_rate: function (frm, cdt, cdn) {
		let d = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, 'discounted_amount', d.discounted_rate * d.real_qty);
		frappe.model.set_value(cdt, cdn, 'discounted_net_amount', d.discounted_rate * d.real_qty);
	},

	qty: function (frm, cdt, cdn) {
		let d = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, 'real_qty', d.qty);
		frm.events.calculate_total(frm);
		if (d.uom != d.stock_uom) {
			if (d.stock_qty && d.qty) {
				frappe.model.set_value(cdt, cdn, "conversion_factor", d.stock_qty / d.qty);
			}
		}
		apply_box_qty_conversion(frm, cdt, cdn);
	},

	real_qty: function (frm, cdt, cdn) {
		let d = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, 'discounted_amount', d.discounted_rate * d.real_qty);
		frappe.model.set_value(cdt, cdn, 'discounted_net_amount', d.discounted_rate * d.real_qty);
		frm.events.calculate_total(frm);
	},

	stock_qty: function (frm, cdt, cdn) {
		var doc = locals[cdt][cdn];
		if (doc.uom != doc.stock_uom) {
			if (doc.stock_qty && doc.qty) {
				frappe.model.set_value(cdt, cdn, "conversion_factor", doc.stock_qty / doc.qty);
			}
		}
	},

	uom: function (frm, cdt, cdn) {
		var doc = locals[cdt][cdn];
		if (doc.uom != doc.stock_uom) {
			if (doc.stock_qty && doc.qty) {
				frappe.model.set_value(cdt, cdn, "conversion_factor", doc.stock_qty / doc.qty);
			}
		}
	},

	unpick_item: function (frm, cdt, cdn) {
		let d = locals[cdt][cdn];
		frappe.call({
			method: "malaga.doc_events.pick_list.unpick_picked_qty_sales_order",
			args: {
				'sales_order': frm.doc.name,
				'sales_order_item': d.name,
				'item_code': d.item_code
			},
			callback: function (r) {
				frappe.msgprint(r.message);
			}
		});
	},
});


// ─── Delivery Note helpers ───────────────────────────────────────────────────

function make_delivery_note_based_on_delivery_date(frm) {
	var delivery_dates = [];
	$.each(frm.doc.items || [], function (i, d) {
		if (!delivery_dates.includes(d.delivery_date)) {
			delivery_dates.push(d.delivery_date);
		}
	});

	var item_grid = frm.fields_dict["items"].grid;
	if (!item_grid.get_selected().length && delivery_dates.length > 1) {
		var dialog = new frappe.ui.Dialog({
			title: __("Select Items based on Delivery Date"),
			fields: [{ fieldtype: "HTML", fieldname: "dates_html" }]
		});

		var html = $(`
			<div style="border: 1px solid #d1d8dd">
				<div class="list-item list-item--head">
					<div class="list-item__content list-item__content--flex-2">
						${__('Delivery Date')}
					</div>
				</div>
				${delivery_dates.map(date => `
					<div class="list-item">
						<div class="list-item__content list-item__content--flex-2">
							<label>
								<input type="checkbox" data-date="${date}" checked="checked"/>
								${frappe.datetime.str_to_user(date)}
							</label>
						</div>
					</div>
				`).join("")}
			</div>
		`);

		var wrapper = dialog.fields_dict.dates_html.$wrapper;
		wrapper.html(html);

		dialog.set_primary_action(__("Select"), function () {
			var dates = wrapper.find('input[type=checkbox]:checked')
				.map((i, el) => $(el).attr('data-date')).toArray();

			if (!dates) return;

			$.each(dates, function (i, d) {
				$.each(item_grid.grid_rows || [], function (j, row) {
					if (row.doc.delivery_date == d) {
						row.doc.__checked = 1;
					}
				});
			});
			make_delivery_note(frm);
			dialog.hide();
		});
		dialog.show();
	} else {
		make_delivery_note(frm);
	}
}

function make_delivery_note(frm) {
	frappe.model.open_mapped_doc({
		method: "malaga.doc_events.sales_order.make_delivery_note",
		frm: frm
	});
}

function apply_box_qty_conversion(frm, cdt, cdn) {
	let row = locals[cdt][cdn];

	if (!row.item_code || !row.qty) {
		return;
	}

	frappe.db.get_value(
		"Item",
		row.item_code,
		["allow_box_conversion", "custom_box_qty_sqm"]
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
		let multiples = Math.floor((original_qty / box_qty) + 0.5);  // round-half-up
		if (multiples < 1) {
			multiples = 1;
		}

		let new_qty = flt(multiples * box_qty, precision("qty", row));

		// guard against float precision loops re-triggering this handler forever
		if (Math.abs(new_qty - original_qty) > 0.0001) {
			frappe.model.set_value(cdt, cdn, "qty", new_qty);
			frappe.show_alert({
				message: __("Row {0}: Qty adjusted from {1} to {2} to match box quantity of {3} for item {4}.",
					[row.idx, original_qty, new_qty, box_qty, row.item_code]),
				indicator: "orange"
			});
		}
	});
}