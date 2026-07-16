ItemSelector = Class.extend({
	init: function (opts) {
		console.log('[ItemSelector] init called with opts:', opts);
		$.extend(this, opts);
		this.setup();
	},

	setup: function () {
		console.log('[ItemSelector] setup started');
		this.item_locations_data = []
		this.make_dialog();
	},

	make_dialog: function () {
		var me = this;
		console.log('me', me);
		this.data = [];
		frm = cur_frm
		var fields =
			[
				{
					label: __('Item Code'),
					fieldtype: 'Link',
					fieldname: 'item_code',
					options: 'Item',
					read_only: 1,
					reqd: 1,
					default: me.item_code,
				},
				{
					label: __('Customer'),
					fieldtype: 'Link',
					options: 'Customer',
					fieldname: 'customer',
					read_only: 1,
					reqd: 1,
					default: me.customer,
				},
				{
					label: __('Idx'),
					fieldtype: 'Int',
					fieldname: 'idx',
					read_only: 1,
					reqd: 1,
					hidden: 1,
					default: me.idx,
				},



				{ fieldtype: 'Column Break' },

				{
					label: __('Sales Order'),
					fieldtype: 'Link',
					fieldname: 'sales_order',
					options: 'Sales Order',
					reqd: 1,
					read_only: 1,
					default: me.sales_order
				},
				{
					label: __('Sales Order Date'),
					fieldtype: 'Date',
					fieldname: 'so_date',
					read_only: 1,
					reqd: 1,
					default: me.so_date,
				},
				{
					label: __('Sales Order Item'),
					fieldtype: 'Data',
					fieldname: 'sales_order_item',
					reqd: 0,
					read_only: 1,
					hidden: 1,
					default: me.sales_order_item
				},
				{
					label: __('SO Picked %'),
					fieldtype: 'Percent',
					fieldname: 'so_picked_percent',
					reqd: 0,
					read_only: 1,
					default: me.so_picked_percent
				},
				{ fieldtype: 'Section Break', label: __('Quantity') },
				{
					label: __('Sales Order Qty'),
					fieldtype: 'Float',
					fieldname: 'so_qty',
					reqd: 0,
					default: me.so_qty,
					read_only: 0,
					change: function () {
						var previously_picked = this.layout.get_value('previously_picked') || 0;
						var picked_qty = this.layout.get_value('picked_qty') || 0;
						var so_qty = this.layout.get_value('so_qty') || 0;
						cur_dialog.set_value('remaining_to_pick', (so_qty - previously_picked - picked_qty - (me.so_delivered_without_pick || 0)));
						cur_dialog.set_value('so_real_qty', so_qty);
					}
				},
				{
					label: __('Packaging Type'),
					fieldtype: 'Data',
					fieldname: 'packaging_type',
					reqd: 0,
					read_only: 1,
					default: me.packaging_type
				},
				{
					label: __('Previously Picked'),
					fieldtype: 'Float',
					fieldname: 'previously_picked',
					reqd: 0,
					default: me.picked_qty,
					read_only: 1,
					hidden: 1,
				},
				{ fieldtype: 'Column Break' },
				{
					label: __('Sales Order Real Qty'),
					fieldtype: 'Float',
					fieldname: 'so_real_qty',
					reqd: 0,
					default: me.so_real_qty,
					hidden: 1,
					read_only: 0,
				},
				{
					label: __('Previously Picked'),
					fieldtype: 'Float',
					fieldname: 'previously_picked_qty',
					reqd: 0,
					default: me.picked_qty,
					read_only: 1
				},
				{ fieldtype: 'Column Break' },
				{
					label: __('Picked Qty'),
					fieldtype: 'Float',
					fieldname: 'picked_qty',
					default: '0',
					reqd: 0,
					read_only: 1,
					change: function () {
						var previously_picked = this.layout.get_value('previously_picked') || 0;
						var picked_qty = this.layout.get_value('picked_qty') || 0;
						var so_qty = this.layout.get_value('so_qty') || 0;
						cur_dialog.set_value('remaining_to_pick', (so_qty - previously_picked - picked_qty - (me.delivered_without_pick || 0)));
					}
				},
				{
					label: __('Remaining to Pick Qty'),
					fieldtype: 'Float',
					fieldname: 'remaining_to_pick',
					default: me.remaining_to_pick,
					reqd: 0,
					read_only: 1,
					change: function () {
						me.set_item_qty()
					}
				}
			]

		fields = fields.concat(this.get_item_fields());
		console.log('[ItemSelector] make_dialog fields compiled:', fields);

		me.dialog = new frappe.ui.Dialog({
			title: __("Add Items"),
			fields: fields,
		});

		me.dialog.set_primary_action(__("Add"), function () {
			me.values = me.dialog.get_values();
			console.log('[ItemSelector] Primary action clicked. Dialog values:', me.values);

			var picked_qty = me.values.picked_qty + me.picked_qty
			var so_qty = flt(me.values.so_qty)
			console.log('[ItemSelector] Picked qty validation:', {
				values_picked_qty: me.values.picked_qty,
				instance_picked_qty: me.picked_qty,
				total_picked_qty: picked_qty,
				so_qty: so_qty
			});

			if (picked_qty == 0) {
				console.log('[ItemSelector] Picked Qty is 0, hiding dialog');
				me.dialog.hide();
			}
			else if (so_qty >= picked_qty) {
				console.log('[ItemSelector] Picked Qty is valid, setting locations in frm');
				me.set_item_locations_in_frm();
				me.dialog.hide();
			} else {
				console.log('[ItemSelector] Picked Qty validation failed');
				frappe.msgprint("Picked Qty should be less than " + (so_qty - me.picked_qty))
			}
		});

		var $package_wrapper = this.get_item_location_wrapper();

		$($package_wrapper).find('.grid-remove-rows .grid-delete-rows').click(function (event) {
			dialog(this);
			event.preventDefault();
			event.stopPropagation();
			return false;
		});
		// $($package_wrapper).find('.grid-add-row').hide();

		me.dialog.show();

		if (me.customer) {
			me.dialog.set_value('customer', me.customer);
		}
		if (me.date) {
			me.dialog.set_value('so_date', me.so_date);
		}
		if (me.so_qty) {
			me.dialog.set_value('so_qty', me.so_qty);
		}
		if (me.remaining_to_pick || me.remaining_to_pick === 0) {
			me.dialog.set_value('remaining_to_pick', me.remaining_to_pick);
		}

		var filters = { 'item_code': me.item_code };
		console.log('[ItemSelector] Showing dialog. Fetching items with filters:', filters);
		me.get_items(filters);

		this.bind_events();
	},
	get_items: function (filters) {
		var me = this;
		console.log('[ItemSelector] get_items called with filters:', filters);
		var item_locations = me.dialog.fields_dict.item_locations;
		if (!filters['item_code']) {
			console.log('[ItemSelector] No item_code in filters. Clearing locations.');
			item_locations.grid.df.data = [];
			item_locations.grid.refresh();
			return;
		}

		filters['company'] = me.company;
		filters['to_pick_qty'] = me.remaining_to_pick

		console.log('[ItemSelector] Fetching items via API: malaga.doc_events.pick_list.get_items with:', filters);
		frappe.call({
			method: "malaga.doc_events.pick_list.get_items",
			freeze: true,
			args: {
				'filters': filters,
			},
			callback: function (r) {

				console.log('[ItemSelector] get_items API response:', r);
				item_locations.grid.df.data = [];
				console.log('[ItemSelector] Processing items. available_qty in frm:', me.frm.doc.available_qty);
				(r.message || []).forEach(value => {
					var original_available_qty = value.available_qty;
					(me.frm.doc.available_qty || []).forEach(element => {
						if (value.batch_no == element.batch_no) {
							value.available_qty = value.available_qty - (element.picked_in_current || 0)
						}
					});
					setTimeout(function () { }, 2000)
					if (me.batch_no && value.batch_no == me.batch_no) {
						value.available_qty = value.available_qty + me.qty
					}
					value.to_pick_qty = Math.min(me.dialog.fields_dict.remaining_to_pick.value, value.available_qty)
					console.log('[ItemSelector] Item processed:', {
						item_code: value.item_code,
						batch_no: value.batch_no,
						original_qty: original_available_qty,
						adjusted_qty: value.available_qty,
						to_pick_qty: value.to_pick_qty
					});
					item_locations.grid.df.data.push(value)
					item_locations.grid.refresh();
				});

				// item_locations.grid.df.data = r.message;
				console.log('[ItemSelector] Refreshing item locations grid');
				item_locations.grid.refresh();
				// me.set_item_location_data();
			},
		});
	},
	get_item_fields: function () {
		var me = this;

		return [
			{ fieldtype: 'Section Break', label: __('Item Location Details') },
			{
				label: __("Item"),
				fieldname: 'item_locations',
				fieldtype: "Table",
				read_only: 0,
				fields: [
					{
						'label': 'Item Code',
						'fieldtype': 'Link',
						'fieldname': 'item_code',
						'options': 'Item',
						'read_only': 1,
					},
					{
						'label': 'Item Name',
						'fieldtype': 'Data',
						'fieldname': 'item_name',
						'read_only': 1,
					},
					{
						'label': 'Batch No',
						'fieldtype': 'Link',
						'fieldname': 'batch_no',
						'options': 'Batch',
						'read_only': 1,
						'in_list_view': 0,
					},
					{
						'label': 'Lot',
						'fieldtype': 'Data',
						'fieldname': 'lot_no',
						'read_only': 1,
						'in_list_view': 1,
						'columns': 2,
					},
					{
						'label': 'Packing',
						'fieldtype': 'Data',
						'fieldname': 'packing_type',
						'read_only': 1,
						'in_list_view': 1,
						'columns': 2,
					},
					{
						'label': 'To Pick',
						'fieldtype': 'Float',
						'fieldname': 'to_pick_qty',
						'in_list_view': 1,
						'columns': 2,
						change: function () {
							me.cal_picked_qty();
						}
					},
					// {
					// 	'label': 'Avalilable to Pick',
					// 	'fieldtype': 'Float',
					// 	'fieldname': 'to_pick_qty',
					// 	'read_only': 0,
					// 	'in_list_view': 1,
					// 	// change: function(){
					// 	// 	me.cal_picked_qty();
					// 	// }
					// },
					{
						'label': 'Avalilable Qty',
						'fieldtype': 'Float',
						'fieldname': 'available_qty',
						'read_only': 1,
						'in_list_view': 1,
						'columns': 2,
					},
					{
						'label': 'Actual Qty',
						'fieldtype': 'Float',
						'fieldname': 'actual_qty',
						'read_only': 1,
						'in_list_view': 1,
						'columns': 1,
					},
					{
						'label': 'Picked Qty',
						'fieldtype': 'Float',
						'fieldname': 'picked_qty',
						'read_only': 1,
						'in_list_view': 0,
					},

				],
				in_place_edit: false,
				data: this.data,
				get_data: function () {
					return this.data;
				},
			}
		];
	},
	// cal_picked_qty: function(){
	// 	var me = this;

	// 	var selected_item_locations = me.get_selected_item_locations();
	// 	var picked_qty = frappe.utils.sum((selected_item_locations || []).map(row => row.to_pick_qty));
	// 	me.dialog.set_value('picked_qty', picked_qty);

	// },
	cal_picked_qty: function () {
		const me = this;
		const selected = me.get_selected_item_locations();
		const picked_qty = frappe.utils.sum((selected || []).map(d => d.to_pick_qty || 0));
		console.log('[ItemSelector] cal_picked_qty. Selected:', selected, 'Picked Qty:', picked_qty);
		me.dialog.set_value('picked_qty', picked_qty);
	},

	set_item_location_data: function () {
		var me = this;
		me.item_locations_data = me.dialog.get_value('item_locations');
	},
	bind_events: function ($wrapper) {
		var me = this;

		var $item_location_wrapper = me.get_item_location_wrapper();

		$item_location_wrapper.on('click', '.grid-row-check:checkbox', (e) => {
			me.cal_picked_qty();
		})

	},
	get_item_location_wrapper: function () {
		var me = this;
		return me.dialog.get_field('item_locations').$wrapper;
	},
	get_selected_item_locations: function () {
		const me = this;
		const item_locations_all = me.dialog.get_value('item_locations');
		const $item_location_wrapper = me.get_item_location_wrapper();

		// Sync checkboxes in visible DOM to item_locations_all
		$item_location_wrapper.find('.grid-row').each(function () {
			const $row = $(this);
			const docname = $row.attr('data-name');
			const $checkbox = $row.find('.grid-row-check:checkbox');
			const record = item_locations_all.find(d => d.name === docname);
			if (record && $checkbox.length) {
				record.__checked = $checkbox.is(":checked") ? 1 : 0;
			}
		});

		const selected = item_locations_all.filter(d => d.__checked === 1);
		console.log('[ItemSelector] get_selected_item_locations selected:', selected);
		// Return all checked rows from full dataset
		return selected;
	}

	// get_selected_item_locations: function () {
	// const me = this;
	// const selected_item_locations = [];
	// const item_locations_all = me.dialog.get_value('item_locations');
	// const $item_location_wrapper = me.get_item_location_wrapper();

	// $item_location_wrapper.find('.form-grid > .grid-body > .rows > .grid-row').each(function () {
	// 	const $row = $(this);
	// 	const $checkbox = $row.find('.grid-row-check:checkbox');
	// 	const docname = $row.attr("data-name");
	// 	if (!docname || !$checkbox.length) return;

	// 	const data = item_locations_all.find(d => d.name === docname);

	// 	if ($checkbox.is(":checked") && data) {
	// 		data.__checked = 1;
	// 		selected_item_locations.push(data);
	// 	} else if (data) {
	// 		data.__checked = 0;
	// 	}
	// });

	// return selected_item_locations;
	// },
	// get_selected_item_locations: function() {
	// 	var me = this;
	// 	var selected_item_locations = [];
	// 	var $item_location_wrapper = this.get_item_location_wrapper();
	// 	var item_locations = me.dialog.get_value('item_locations');

	// 	$.each($item_location_wrapper.find('.form-grid > .grid-body > .rows > .grid-row'), function (idx, row) {
	// 		var pkg = $(row).find('.grid-row-check:checkbox');

	// 		var item_location = item_locations[idx];

	// 		if($(pkg).is(':checked')){
	// 			selected_item_locations.push(item_location);
	// 			item_location.__checked = 1;
	// 		} else {
	// 			item_location.__checked = 0;
	// 		}
	// 	});

	// 	return selected_item_locations;
	// },
	// set_item_qty: function() {
	// 	var me = this;
	// 	var selected_item_locations = [];
	// 	var $item_location_wrapper = this.get_item_location_wrapper();
	// 	var item_locations = me.dialog.get_value('item_locations');
	// 	var remaining_to_pick = me.dialog.get_value('remaining_to_pick');

	// 	$.each($item_location_wrapper.find('.form-grid > .grid-body > .rows > .grid-row'), function (idx, row) {
	// 		var pkg = $(row).find('.grid-row-check:checkbox');

	// 		var item_location = item_locations[idx];

	// 		if($(pkg).is(':checked')){
	// 			selected_item_locations.push(item_location);
	// 			item_location.__checked = 1;
	// 		} else {
	// 			item_location.__checked = 0;
	// 			item_location.to_pick_qty = Math.min((remaining_to_pick || 0), (item_location.available_qty || 0))
	// 		}
	// 	});
	// 	var item_locations2 = me.dialog.fields_dict.item_locations;
	// 	item_locations2.grid.refresh();

	// 	// return selected_item_locations;
	// },
	,
	set_item_qty: function () {
		const me = this;
		const item_locations = me.dialog.get_value('item_locations');
		const remaining_to_pick = me.dialog.get_value('remaining_to_pick');
		const $item_location_wrapper = me.get_item_location_wrapper();
		console.log('[ItemSelector] set_item_qty remaining_to_pick:', remaining_to_pick);

		// Sync DOM checkbox states to item_locations
		$item_location_wrapper.find('.grid-row').each(function () {
			const $row = $(this);
			const docname = $row.attr('data-name');
			const $checkbox = $row.find('.grid-row-check:checkbox');
			const record = item_locations.find(d => d.name === docname);
			if (!record || !$checkbox.length) return;

			if ($checkbox.is(":checked")) {
				record.__checked = 1;
			} else {
				record.__checked = 0;
				record.to_pick_qty = Math.min((remaining_to_pick || 0), (record.available_qty || 0));
			}
		});

		// Refresh grid after manipulation
		me.dialog.fields_dict.item_locations.grid.refresh();
	},

	set_item_locations_in_frm: function () {
		var me = this;
		var selected_item_locations = this.get_selected_item_locations();
		var item_code = me.values.item_code
		var sales_order = me.values.sales_order
		var sales_order_item = me.values.sales_order_item
		console.log('[ItemSelector] set_item_locations_in_frm', {
			item_code: item_code,
			sales_order: sales_order,
			sales_order_item: sales_order_item,
			selected_item_locations: selected_item_locations
		});

		var loc = [];

		me.frm.doc.locations.forEach(function (value, idx) {
			if (value.sales_order_item != sales_order_item) {
				loc.push(value)
			}
		});
		console.log('[ItemSelector] Existing locations kept:', loc);
		me.frm.doc.locations = loc;

		(selected_item_locations || []).forEach(function (d) {
			d.__checked = 0;
			var locations = me.frm.add_child('locations');
			frappe.model.set_value(locations.doctype, locations.name, 'item_code', d.item_code);
			frappe.model.set_value(locations.doctype, locations.name, 'customer', me.customer);
			frappe.model.set_value(locations.doctype, locations.name, 'so_picked_percent', me.so_picked_percent);
			frappe.model.set_value(locations.doctype, locations.name, 'so_qty', me.values.so_qty);
			frappe.model.set_value(locations.doctype, locations.name, 'so_real_qty', me.values.so_real_qty);
			frappe.model.set_value(locations.doctype, locations.name, 'delivery_date', me.delivery_date);
			frappe.model.set_value(locations.doctype, locations.name, 'date', me.date);
			frappe.model.set_value(locations.doctype, locations.name, 'qty', d.to_pick_qty);
			frappe.model.set_value(locations.doctype, locations.name, 'picked_qty', me.picked_qty || 0);
			frappe.model.set_value(locations.doctype, locations.name, 'available_qty', d.available_qty);
			frappe.model.set_value(locations.doctype, locations.name, 'actual_qty', d.actual_qty);
			frappe.model.set_value(locations.doctype, locations.name, 'sales_order', sales_order);
			frappe.model.set_value(locations.doctype, locations.name, 'sales_order_item', sales_order_item);
			frappe.model.set_value(locations.doctype, locations.name, 'batch_no', d.batch_no);
			frappe.model.set_value(locations.doctype, locations.name, 'packing_type', d.packing_type);
			frappe.model.set_value(locations.doctype, locations.name, 'order_item_priority', d.order_item_priority);
			console.log('[ItemSelector] Appended child location:', locations);
		})

		me.frm.doc.locations.forEach(function (d, idx) {
			frappe.model.set_value(d.doctype, d.name, 'idx', idx + 1);
		});

		console.log('[ItemSelector] Final locations in form:', me.frm.doc.locations);
		refresh_field('locations');
	},
});