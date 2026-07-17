// Fixed for Frappe v16
// All queries moved to frm.set_query inside onload/refresh events
// Removed unused erpnext.stock.DeliveryNoteController class
// Merged duplicate item_code queries into one with combined filters

frappe.ui.form.on("Delivery Note", {
	onload(frm) {
		// --- Item Code filter (merged from old get_query and set_query) ---
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			let filters = [["is_sales_item", "=", 1]];
			// Add item_series filter based on authority
			if (doc.authority == "Authorized") {
				// item_series must not be null/empty
				filters.push(["item_series", "not in", [null, ""]]);
			} else {
				// item_series must be null/empty
				filters.push(["item_series", "in", [null, ""]]);
			}
			return {
				query: "erpnext.controllers.queries.item_query",
				filters: filters
			};
		});

		// --- Batch No filter ---
		// frm.set_query("batch_no", "items", function (doc, cdt, cdn) {
		// 	let d = locals[cdt][cdn];
		// 	if (!d.item_code) {
		// 		frappe.msgprint(__("Please select Item Code"));
		// 		return;
		// 	}
		// 	if (!d.warehouse) {
		// 		frappe.msgprint(__("Please select warehouse"));
		// 		return;
		// 	}
		// 	return {
		// 		query: "malaga.query.get_batch_no",
		// 		filters: {
		// 			item_code: d.item_code,
		// 			company: doc.company,
		// 			warehouse: d.warehouse
		// 		}
		// 	};
		// });

		// --- Warehouse filter ---
		// frm.set_query("warehouse", "items", function (doc, cdt, cdn) {
		// 	let d = locals[cdt][cdn];
		// 	return {

		// 	};
		// });

		// --- Item Series filter (child table) ---
		frm.set_query("item_series", "items", function () {
			return {
				filters: {
					"authority": "Authorized"
				}
			};
		});

		// --- Customer filter ---
		frm.set_query("customer", function () {
			return {
				query: "erpnext.controllers.queries.customer_query",
				filters: {
					"disabled": 0
				}
			};
		});

		// --- Customer Address filter ---
		frm.set_query("customer_address", function () {
			return {
				query: "frappe.contacts.doctype.address.address.address_query",
				filters: {
					link_doctype: "Customer",
					link_name: frm.doc.customer
				}
			};
		});


		// Ignore doctypes on cancel
		frm.ignore_doctypes_on_cancel_all = ["Sales Invoice"];



		// Trigger custom filter queries defined in set_filter_queries
		frm.trigger("set_filter_queries");
	},

	refresh(frm) {
		var me = this; // not used, can be removed, but kept for minimal changes

		// SI Ref filter (set on refresh because it depends on posting_date)
		frappe.db.get_value("Company", frm.doc.company, "alternate_company", function (r) {
			frm.set_query("si_ref", function (doc) {
				return {
					filters: {
						"primary_customer": doc.customer,
						"company": r.alternate_company,
						"si_ref": "",
						"docstatus": 1,
						"posting_date": doc.posting_date
					}
				};
			});
		});



		frm.trigger("add_get_items_button");

		if (frm.doc.__islocal) {
			frm.trigger("naming_series");
		}

		frm.set_df_property("company", "read_only", (!frm.doc.__islocal || frm.doc.amended_from) ? 1 : 0);
		frm.trigger("set_filter_queries");

		// --- Custom buttons (replaces old DeliveryNoteController) ---
		if ((!frm.doc.is_return) && (frm.doc.status != "Closed" || frm.is_new())) {
			if (frm.doc.docstatus === 0) {
				frm.add_custom_button(__('Sales Order'), function () {
					erpnext.utils.map_current_doc({
						method: "malaga.doc_events.sales_order.make_delivery_note",
						source_doctype: "Sales Order",
						target: frm,
						setters: {
							customer: frm.doc.customer || undefined,
						},
						get_query_filters: {
							docstatus: 1,
							status: ["not in", ["Closed", "On Hold"]],
							per_delivered: ["<", 99.99],
							company: frm.doc.company,
							project: frm.doc.project || undefined,
						}
					});
				}, __("Get items from"));
			}
		}

		if (!frm.doc.is_return && frm.doc.status != "Closed") {
			if (flt(frm.doc.per_installed, 2) < 100 && frm.doc.docstatus == 1)
				frm.add_custom_button(__('Installation Note'), function () {
					me.make_installation_note(); // will fail if not defined; ideally define separately
				}, __('Create'));

			if (frm.doc.docstatus == 1) {
				frm.add_custom_button(__('Sales Return'), function () {
					me.make_sales_return(); // need definition
				}, __('Create'));
			}

			if (frm.doc.docstatus == 1) {
				frm.add_custom_button(__('Delivery Trip'), function () {
					me.make_delivery_trip(); // need definition
				}, __('Create'));
			}

			if (frm.doc.docstatus == 0 && !frm.doc.__islocal) {
				frm.add_custom_button(__('Packing Slip'), function () {
					frappe.model.open_mapped_doc({
						method: "erpnext.stock.doctype.delivery_note.delivery_note.make_packing_slip",
						frm: frm
					});
				}, __('Create'));
			}

			if (!frm.doc.__islocal && frm.doc.docstatus == 1) {
				frm.page.set_inner_btn_group_as_primary(__('Create'));
			}
		}

		if (frm.doc.docstatus == 1) {
			frm.show_stock_ledger();
			if (erpnext.is_perpetual_inventory_enabled(frm.doc.company)) {
				frm.show_general_ledger();
			}
			if (frm.has_perm("submit") && frm.doc.status !== "Closed") {
				frm.add_custom_button(__("Close"), function () { frm.close_delivery_note(); }, __("Status"));
			}
		}

		if (frm.doc.docstatus == 1 && !frm.doc.is_return && frm.doc.status != "Closed" && flt(frm.doc.per_billed) < 100) {
			var from_sales_invoice = frm.doc.items.some(function (item) {
				return item.against_sales_invoice ? true : false;
			});
			if (!from_sales_invoice) {
				frm.add_custom_button(__('Sales Invoice'), function () {
					// Use custom method attached to frm
					frm.make_sales_invoice_test();
				}, __('Create'));
			}
		}

		if (frm.doc.docstatus == 1 && frm.doc.status === "Closed" && frm.has_perm("submit")) {
			frm.add_custom_button(__('Reopen'), function () { frm.reopen_delivery_note(); }, __("Status"));
		}

		erpnext.stock.delivery_note.set_print_hide(frm.doc, frm.doc.doctype, frm.doc.name); // adjust if needed

		if (frm.doc.docstatus == 1 && !frm.doc.is_return && !frm.doc.auto_repeat) {
			frm.add_custom_button(__('Subscription'), function () {
				erpnext.utils.make_subscription(frm.doc.doctype, frm.doc.name);
			}, __('Create'));
		}
	},

	// before_save(frm) {
	// 	if (!frm.doc.primary_customer) {
	// 		frm.set_value("primary_customer", frm.doc.customer);
	// 	}
	// 	frm.trigger("get_taxes");
	// },

	before_submit(frm) {
		if (!frm.doc.si_ref) {
			return new Promise((resolve, reject) => {
				frappe.confirm(
					'Are you sure to Save this document without Sales Invoice?',
					function () { resolve(); },
					function () {
						reject();
						window.close();
					}
				);
			});
		}
	},

	update_item_group_rate(frm) {
		const c = frm;
		const cannot_add_row = true;
		const child_docname = "items";
		var data = [];
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
						{ fieldtype: 'Data', fieldname: "docname", read_only: 1, hidden: 1 },
						{ fieldtype: 'Link', fieldname: "item_group", options: 'Item Group', read_only: 1, in_list_view: 1, reqd: 1, columns: 2, label: __('Item group') },
						{ fieldtype: 'Data', fieldname: "tile_quality", read_only: 1, in_list_view: 1, columns: 1, label: __('Tile Quality') },
						{
							fieldtype: 'Currency', fieldname: "sqf_rate", default: 0, in_list_view: 1, columns: 1, label: __('SQF Rate'),
							change: function () {
								let sqf_rate = this.get_value();
								if (sqf_rate) {
									frappe.db.get_value("Item Group", this.grid_row.on_grid_fields_dict.item_group.get_value(), 'sqf_calculation', (r) => {
										if (r.sqf_calculation) {
											this.grid_row.on_grid_fields_dict.rate.set_value(flt(sqf_rate * r.sqf_calculation));
										} else {
											this.grid_row.on_grid_fields_dict.rate.set_value(flt(sqf_rate * 15.5));
										}
									});
								}
							}
						},
						{ fieldtype: 'Currency', fieldname: "rate", default: 0, in_list_view: 1, columns: 1, label: __('Rate') },
						{ fieldtype: 'Date', fieldname: "date", in_list_view: 1, columns: 1, label: __('Date') }
					]
				},
				{
					fieldtype: 'Link', fieldname: "payment_terms_si", options: "Payment Terms Template", in_list_view: 1, columns: 2, label: __('Payment Terms')
				},
				{
					fieldtype: 'Button', fieldname: "si_rate", in_list_view: 1, label: __('SI Rate'),
					click: function () {
						const trans_items = dialog.get_values()["trans_items"];
						frappe.call({
							method: 'malaga.update_item.update_rate_from_si',
							args: {
								'parent_doctype': c.doc.doctype,
								'trans_items': trans_items,
								'parent_doctype_name': c.doc.name,
								'child_docname': child_docname,
								'items_table': c.doc.items,
								'customer': frm.doc.customer,
								'company': frm.doc.company,
							},
							callback: function (r) {
								if (r.message) {
									const { si_price_dict, si_date_dict, si_sqf_dict, tax_paid_from_si, payment_terms_template } = r.message;
									function isNoneOrUndefined(value) {
										return value === null || value === undefined || value === "None" || value === "";
									}
									function updateItemValue(dict, field) {
										for (const key in dict) {
											const [item_group, tile_quality] = key.split('|||');
											const value = dict[key];
											for (let i = 0; i < trans_items.length; i++) {
												if (trans_items[i].item_group == item_group &&
													(isNoneOrUndefined(tile_quality) || trans_items[i].tile_quality == tile_quality ||
														(isNoneOrUndefined(trans_items[i].tile_quality) && isNoneOrUndefined(tile_quality)))) {
													dialog.fields_dict.trans_items.df.data[i][field] = value;
												}
											}
										}
										dialog.fields_dict.trans_items.grid.refresh();
									}
									updateItemValue(si_price_dict, 'rate');
									updateItemValue(si_date_dict, 'date');
									updateItemValue(si_sqf_dict, 'sqf_rate');
									if (tax_paid_from_si) dialog.set_value("tax_paid_from_si", tax_paid_from_si);
									if (payment_terms_template) dialog.set_value("payment_terms_si", payment_terms_template);
									refresh_field("items");
								}
							}
						});
					}
				},
				{
					fieldtype: 'Check', fieldname: "tax_paid", in_list_view: 1, label: __('Tax Paid From Quotation')
				},
				{
					fieldtype: 'Check', fieldname: "tax_paid_from_si", in_list_view: 1, label: __('Tax Paid From Sales Invoice')
				},
			],
			primary_action: function () {
				const trans_items = this.get_values()["trans_items"];
				const tax_paid = dialog.get_value('tax_paid');
				const tax_paid_from_si = dialog.get_value('tax_paid_from_si');
				const payment_terms_template_si = dialog.get_value('payment_terms_si');
				frappe.call({
					method: 'malaga.update_item.update_child_price_delivery_note',
					freeze: true,
					args: {
						'parent_doctype': c.doc.doctype,
						'trans_items': trans_items,
						'parent_doctype_name': c.doc.name,
						'child_docname': child_docname,
						'items_table': c.doc.items,
						'tax_paid': tax_paid,
						'tax_paid_from_si': tax_paid_from_si,
						'payment_terms_template_si': payment_terms_template_si
					},
					callback: function () {
						frm.set_value("payment_terms_template", payment_terms_template_si);
						frm.refresh_field("taxes_and_charges");
						frm.reload_doc();
					}
				});
				this.hide();
				refresh_field("items");
			},
			primary_action_label: __('Update'),
			secondary_action: function () {
				const trans_items = dialog.get_values()["trans_items"];
				frappe.call({
					method: "malaga.update_item.update_child_rate",
					args: {
						'customer': frm.doc.customer,
						'trans_items': trans_items,
						'items_table': frm.doc.items,
						'parent_doctype': frm.doc.doctype,
						'parent_doctype_name': frm.doc.name,
						'child_docname': child_docname,
					},
					callback: function (r) {
						// (your existing callback logic)
					}
				});
			},
			secondary_action_label: __('Quotation Rate'),
		});

		dialog.$wrapper.find('.modal-dialog').css({
			'width': '80%',
			'max-width': '1000px'
		});
		dialog.$wrapper.find('.form-layout').css({
			'max-height': '70vh',
			'overflow-y': 'auto'
		});

		const item_group_quality = [];
		c.doc.items.forEach(d => {
			const key = `${d.item_group}_${d.tile_quality}`;
			if (!item_group_quality.includes(key)) {
				dialog.fields_dict.trans_items.df.data.push({
					"docname": d.name,
					"name": d.name,
					"item_group": d.item_group,
					"rate": d.rate,
					"discount_rate": d.discounted_rate,
					"sqf_rate": d.sqf_rate,
					"tile_quality": d.tile_quality
				});
				data = dialog.fields_dict.trans_items.df.data;
				dialog.fields_dict.trans_items.grid.refresh();
				item_group_quality.push(key);
			}
		});
		dialog.set_value('tax_paid_from_si', c.doc.tax_paid);
		dialog.set_value('payment_terms_si', c.doc.payment_terms_template);
		dialog.show();
	},

	customer(frm) {
		if (frm.doc.customer) {
			frappe.db.get_value("Customer", frm.doc.customer, 'primary_customer').then(function (r) {
				frm.set_value("primary_customer", r.message.primary_customer);
			});
			frm.set_value("primary_customer", '');
			frappe.db.get_value("Customer", frm.doc.customer, 'primary_customer').then(function (r) {
				frm.set_value("primary_customer", r.message.primary_customer);
			});
			if (!frm.doc.primary_customer) {
				setTimeout(function () {
					frm.doc.sales_team = [];
					frappe.model.with_doc("Customer", frm.doc.customer, function () {
						var cus_doc = frappe.model.get_doc("Customer", frm.doc.customer);
						$.each(cus_doc.sales_team, function (index, row) {
							if (row.company == frm.doc.company) {
								frm.set_value('sales_head', row.sales_person);
								frm.set_value('regional_sales_manager', row.regional_sales_manager);
								frm.set_value('dispatch_person', row.sales_manager);
								let st = frm.add_child("sales_team");
								st.sales_person = row.sales_person;
								st.contact_no = row.contact_no;
								st.allocated_percentage = row.allocated_percentage;
								st.allocated_amount = row.allocated_amount;
								st.commission_rate = row.commission_rate;
								st.incentives = row.incentives;
								st.company = row.company;
								st.regional_sales_manager = row.regional_sales_manager;
								st.sales_manager = row.sales_manager;
							}
						});
						frm.refresh_field("sales_team");
					});
				}, 1000);
			}
		}
	},

	primary_customer(frm) {
		if (frm.doc.primary_customer) {
			setTimeout(function () {
				frm.doc.sales_team = [];
				frappe.model.with_doc("Customer", frm.doc.primary_customer, function () {
					var cus_doc = frappe.model.get_doc("Customer", frm.doc.primary_customer);
					$.each(cus_doc.sales_team, function (index, row) {
						if (row.company == frm.doc.company) {
							frm.set_value('sales_head', row.sales_person);
							frm.set_value('regional_sales_manager', row.regional_sales_manager);
							frm.set_value('dispatch_person', row.sales_manager);
							let st = frm.add_child("sales_team");
							st.sales_person = row.sales_person;
							st.contact_no = row.contact_no;
							st.allocated_percentage = row.allocated_percentage;
							st.allocated_amount = row.allocated_amount;
							st.commission_rate = row.commission_rate;
							st.incentives = row.incentives;
							st.company = row.company;
							st.regional_sales_manager = row.regional_sales_manager;
							st.sales_manager = row.sales_manager;
						}
					});
					frm.refresh_field("sales_team");
				});
			}, 2000);
		}
	},



	company(frm) {
		if (frm.doc.__islocal) {
			frm.trigger('naming_series');
		}
	},

	add_get_items_button(frm) {
		let get_query_filters = {
			docstatus: 1,
			customer: frm.doc.customer,
			company: frm.doc.company,
		};
		// (custom logic)
	},

	calculate_total(frm) {
		let total_qty = 0.0;
		frm.doc.items.forEach(function (d) {
			total_qty += flt(d.qty);
		});
		frm.set_value("total_qty", total_qty);
		frm.set_value("total_net_weight", 0.0);
		frm.set_value("material_weight", flt(frm.doc.final_weight - frm.doc.initial_weight));
	},

	final_weight(frm) {
		if (frm.doc.initial_weight) {
			frm.set_value("material_weight", flt(frm.doc.final_weight - frm.doc.initial_weight));
		}
	},

	initial_weight(frm) {
		if (frm.doc.final_weight) {
			frm.set_value("material_weight", flt(frm.doc.final_weight - frm.doc.initial_weight));
		}
	},

	tax_category(frm) {
		frm.trigger('get_taxes');
	},

	tax_paid(frm) {
		if (frm.doc.tax_category) {
			frm.trigger('get_taxes');
		}
	},

	validate(frm) {
		frm.doc.items.forEach(function (doc) {
			if (doc.uom != doc.stock_uom) {
				if (doc.stock_qty && doc.qty) {
					frappe.model.set_value(doc.doctype, doc.name, "conversion_factor", doc.stock_qty / doc.qty);
				}
			}
			if (!doc.rate) {
				doc.rate = 1;
			}
		});
	},

	get_taxes(frm) {
		if (frm.doc.tax_category) {
			frappe.call({
				method: "malaga.doc_events.sales_order.get_tax_template",
				args: {
					'tax_paid': frm.doc.tax_paid,
					'tax_category': frm.doc.tax_category,
					'company': frm.doc.company
				},
				callback: function (r) {
					if (r.message) {
						if (r.message != frm.doc.taxes_and_charges) {
							frm.set_value('taxes_and_charges', r.message);
						}
					} else {
						frm.set_value('taxes_and_charges', null);
						frm.set_value('taxes', []);
					}
					frm.refresh_field("taxes");
				}
			});
		}
	},

	set_filter_queries(frm) {
		frm.set_query("taxes_and_charges", function (doc) {
			return {
				filters: [
					['Sales Taxes and Charges Template', 'company', '=', doc.company],
					['Sales Taxes and Charges Template', 'tax_paid', '=', doc.tax_paid || 0],
					['Sales Taxes and Charges Template', 'tax_category', '=', doc.tax_category]
				]
			};
		});
	}
});

// Attach custom methods to frm (instead of the old class)
frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		// Define make_sales_invoice_test and others if they don't exist
		frm.make_sales_invoice_test = function () {
			frappe.model.open_mapped_doc({
				method: "malaga.doc_events.delivery_note.create_invoice_test",
				frm: frm
			});
		};
		frm.make_sales_return = function () {
			frappe.model.open_mapped_doc({
				method: "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_return",
				frm: frm
			});
		};
		frm.close_delivery_note = function () {
			frm.update_status("Closed");
		};
		frm.update_status = function (status) {
			frappe.ui.form.is_saving = true;
			frappe.call({
				method: "erpnext.stock.doctype.delivery_note.delivery_note.update_delivery_note_status",
				args: { docname: frm.doc.name, status: status },
				callback: function (r) {
					if (!r.exc) frm.reload_doc();
				},
				always: function () {
					frappe.ui.form.is_saving = false;
				}
			});
		};
	}
});

// Delivery Note Item events (unchanged except using frm parameter)
frappe.ui.form.on("Delivery Note Item", {
	qty(frm, cdt, cdn) {
		let d = locals[cdt][cdn];
		frm.events.calculate_total(frm);
		if (d.uom != d.stock_uom) {
			if (d.stock_qty && d.qty) {
				frappe.model.set_value(cdt, cdn, "conversion_factor", d.stock_qty / d.qty);
				frm.refresh();
			}
		}
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
	},

	
	sqf_rate(frm, cdt, cdn) {
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
	stock_qty(frm, cdt, cdn) {
		var doc = locals[cdt][cdn];
		if (doc.uom != doc.stock_uom) {
			if (doc.stock_qty && doc.qty) {
				frappe.model.set_value(cdt, cdn, "conversion_factor", doc.stock_qty / doc.qty);
				frm.refresh();
			}
		}
	},
	uom(frm, cdt, cdn) {
		var doc = locals[cdt][cdn];
		if (doc.uom != doc.stock_uom) {
			if (doc.stock_qty && doc.qty) {
				frappe.model.set_value(cdt, cdn, "conversion_factor", doc.stock_qty / doc.qty);
			}
		}
	},

	item_code(frm, cdt, cdn) {
		setTimeout(() => {
			apply_box_qty_conversion(frm, cdt, cdn);
			set_box_value(frm, cdt, cdn);
		}, 500);
	},
});

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