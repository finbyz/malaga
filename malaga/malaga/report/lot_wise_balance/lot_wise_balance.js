frappe.query_reports["Lot-Wise Balance"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": "80",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"width": "80",
			"default": frappe.datetime.get_today(),
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"width": "80",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "MultiSelectList",
			"get_data": function (text) {
				//if (!frappe.query_report.item_group) return;
				return frappe.db.get_link_options('Item Group', text)
			},
			"change": function () {
				frappe.query_report.refresh();
			}
		},
		{
			"fieldname": "tile_quality",
			"label": __("Tile Qulaity"),
			"fieldtype": "MultiSelectList",
			"get_data": function (text) {
				//if (!frappe.query_report.item_group) return;
				return frappe.db.get_link_options('Tile Quality', text)
			},
			"change": function () {
				frappe.query_report.refresh();
			}
		},
		{
			"fieldname": "packing_type",
			"label": __("Packing Type"),
			"fieldtype": "MultiSelectList",
			"get_data": function (text) {
				//if (!frappe.query_report.item_group) return;
				return frappe.db.get_link_options('Packing Type', text)
			},
			"change": function () {
				frappe.query_report.refresh();
			}
		},
		{
			"fieldname": "item_code",
			"label": __("Item Code"),
			"fieldtype": "MultiSelectList",
			"get_data": function (text) {
				//if (!frappe.query_report.item_group) return;
				return frappe.db.get_link_options('Item', text, filters = { 'is_item_series': 0, 'has_batch_no': 1 })
			},
			"change": function () {
				frappe.query_report.refresh();
			},

			// "get_query": function() {
			// 	var item_group = frappe.query_report.get_filter_value('item_group')
			// 	if (item_group){
			// 		return {
			// 			doctype: "Item",
			// 			filters: {
			// 				"item_group": item_group,
			// 				"is_item_series": 0
			// 			}
			// 		}
			// 	} else {
			// 		return {
			// 			doctype: "Item",
			// 			filters: {
			// 				"is_item_series": 0
			// 			}
			// 		}
			// 	}
			// }
		},
		{
			"fieldname": "not_in_item_code",
			"label": __("Not in Item Code"),
			"fieldtype": "MultiSelectList",
			"get_data": function (text) {
				//if (!frappe.query_report.item_group) return;
				return frappe.db.get_link_options('Item', text, filters = { 'is_item_series': 0, 'has_batch_no': 1 })
			},
			"change": function () {
				frappe.query_report.refresh();
			},
		},
		{
			"fieldname": "print_with_picked_qty",
			"label": __("Print With Picked Qty"),
			"fieldtype": "Check",
			"options": "Tile Quality",
		},
		{
			"fieldname": "print_with_unlocked_qty",
			"label": __("Print With Unlocked Qty"),
			"fieldtype": "Check",
		},
		{
			"fieldname": "sales_order",
			"label": __("Sales Order"),
			"fieldtype": "Link",
			"options": "Sales Order",
			"get_query": function () {
				var company = frappe.query_report.get_filter_value('company');
				return {
					"doctype": "Sales Order",
					"filters": {
						"company": ['in', company],
						"docstatus": 1,
						"per_delivered": ['!=', 100],
						"status": ['not in', ('Draft', 'Submitted', 'Closed')]
					}
				}
			}
		},
		{
			"fieldname": "not_in_packing_type",
			"label": __("Not in Packing Type"),
			"fieldtype": "MultiSelectList",
			"get_data": function (text) {
				return frappe.db.get_link_options('Packing Type', text)
			},
			"change": function () {
				frappe.query_report.refresh();
			},
		},
		{
			"fieldname": "warehouse",
			"label": __("Show Warehouse"),
			"fieldtype": "Check",
			"change": function () {
				frappe.query_report.refresh();
			}
		},
		{
			"fieldname": "show_location",
			"label": __("Show Location"),
			"fieldtype": "Check",
			"change": function () {
				frappe.query_report.refresh();
			}
		},
		{
			"fieldname": "group_item_qty",
			"label": __("Group Item Qty"),
			"fieldtype": "Check",
			"change": function () {
				frappe.query_report.refresh();
			}
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (["picked_detail", "new_qty", "change_location"].includes(column.fieldname) && value) {
			return value;
		}
		return default_formatter(value, row, column, data);
	},

	after_datatable_render(datatable) {
		$(datatable.wrapper).off("click.lot_wise").on("click.lot_wise", ".lot-wise-view-btn", function (e) {
			e.preventDefault();
			e.stopPropagation();
			const btn = this;
			window.get_picked_item_details(
				btn.getAttribute("data-item-code"),
				btn.getAttribute("data-batch-no"),
				btn.getAttribute("data-company"),
				btn.getAttribute("data-from-date"),
				btn.getAttribute("data-to-date"),
				btn.getAttribute("data-bal-qty"),
				btn.getAttribute("data-total-picked-qty"),
				btn.getAttribute("data-total-remaining-qty"),
				btn.getAttribute("data-lot-no")
			);
		});

		$(datatable.wrapper).off("click.lot_wise_qty").on("click.lot_wise_qty", ".lot-wise-change-qty-btn", function (e) {
			e.preventDefault();
			e.stopPropagation();
			const btn = this;
			window.new_qty_details(
				btn.getAttribute("data-company"),
				btn.getAttribute("data-item-code"),
				btn.getAttribute("data-item-group"),
				btn.getAttribute("data-balance-qty"),
				btn.getAttribute("data-warehouse"),
				btn.getAttribute("data-buying-unit-price"),
				btn.getAttribute("data-batch-no"),
				btn.getAttribute("data-lot-no"),
				btn.getAttribute("data-packing-type")
			);
		});

		$(datatable.wrapper).off("click.lot_wise_location").on("click.lot_wise_location", ".lot-wise-change-location-btn", function (e) {
			e.preventDefault();
			e.stopPropagation();
			const btn = this;
			window.change_location_details(
				btn.getAttribute("data-batch-no"),
				btn.getAttribute("data-location"),
				btn.getAttribute("data-item-code")
			);
		});
	},
};


window.get_picked_item_details = function (item_code, batch_no, company, from_date, to_date, bal_qty, total_picked_qty, total_remaining_qty, lot_no) {
	let template = `
		<div class="lot-wise-detail-modal">
		<table class="table table-borderless" style="border:0 !important;font-size:95%;width:100%;margin-bottom:12px;">
			<tr>
				<td style="border:0 !important;width:50%;"><b>Lot No: </b> {{ data[0]['lot_no'] }}</td>
				<td style="border:0 !important;width:50%;"><b>Picked Qty: </b> {{ data[0]['total_picked_qty'] }}</td>
			</tr>
			<tr>
				<td style="border:0 !important;"><b>Qty: </b> {{ data[0]['bal_qty'] }}</td>
				<td style="border:0 !important;"><b>Available Qty: </b> {{ data[0]['total_remaining_qty'] }}</td>
			</tr>
			<tr>
				<td style="border:0 !important;"></td>
				<td style="border:0 !important;"><b>Unlocked Qty: </b> {{ data[0]['unlocked_qty'] }}</td>
			</tr>
		</table>
		{% if data.length > 1 %}
		<div style="overflow-x:auto;width:100%;">
		<table class="table table-bordered" style="margin:0;font-size:80%;white-space:nowrap;">
			<thead>
				<tr>
					<th>{{ __("Customer") }}</th>
					<th>{{ __("Lock Pick Qty") }}</th>
					<th>{{ __("Sales Order") }}</th>
					<th>{{ __("Order Date") }}</th>
					<th>{{ __("Delivery Date") }}</th>
					<th>{{ __("Dispatch Person") }}</th>
					<th>{{ __("Pick List") }}</th>
					<th>{{ __("% Picked") }}</th>
					<th>{{ __("Picked") }}</th>
					<th>{{ __("Unpick Qty") }}</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{% for (let row of data.slice(1)) { %}
					<tr class="{{ row['pick_list_item'] }}">
						<td>{{ row['customer'] }}</td>
						<td>{{ row['lock_picked_qty'] }}</td>
						<td>{{ row['sales_order_link'] }}</td>
						<td>{{ row['order_date'] }}</td>
						<td>{{ row['delivery_date'] }}</td>
						<td>{{ row['dispatch_person'] }}</td>
						<td>{{ row['pick_list_link'] }}</td>
						<td>{{ row['per_picked_display'] }}</td>
						<td>{{ row['picked_qty'] }}</td>
						<td><input type="number" min="0" style="width:45px" id="{{ row['pick_list_item'] }}"></td>
						<td><button style="border:none;color:#fff;background-color:red;padding:3px 5px;border-radius:5px;" type="button" class="lot-wise-unpick-btn" data-sales-order="{{ row['sales_order'] }}" data-sales-order-item="{{ row['sales_order_item'] }}" data-pick-list="{{ row['pick_list'] }}" data-pick-list-item="{{ row['pick_list_item'] }}">Unpick</button></td>
					</tr>
				{% } %}
			</tbody>
		</table>
		</div>
		{% endif %}
		</div>`;

	// docudocument.getElementById("demo").innerHTML = item_code;

	frappe.call({
		method: "malaga.malaga.report.lot_wise_balance.lot_wise_balance.get_picked_item",
		args: {
			item_code: item_code,
			batch_no: batch_no,
			from_date: from_date,
			to_date: to_date,
			company: company,
			bal_qty: bal_qty,
			total_picked_qty: total_picked_qty,
			total_remaining_qty: total_remaining_qty,
			lot_no: lot_no
		},
		callback: function (r) {
			let message = frappe.template.compile(template)({ 'data': r.message });
			frappe.msgprint({
				message: message,
				title: "Lot-Wise Balance Details : " + item_code,
				wide: true
			});
			setTimeout(function () {
				const $dialog = frappe.msg_dialog.$wrapper.find(".modal-dialog");
				$dialog.css({ "max-width": "min(95vw, 1200px)", width: "auto" });
				$(".lot-wise-unpick-btn").off("click").on("click", function () {
					const btn = this;
					window.remove_picked_item_lot_wise(
						btn.getAttribute("data-sales-order"),
						btn.getAttribute("data-sales-order-item"),
						btn.getAttribute("data-pick-list"),
						btn.getAttribute("data-pick-list-item"),
						document.getElementById(btn.getAttribute("data-pick-list-item")).value
					);
				});
			}, 250);
		}
	});
};

window.remove_picked_item_lot_wise = function (sales_order, sales_order_item, pick_list, pick_list_item, unpick_qty) {
	frappe.call({
		method: "malaga.doc_events.pick_list.unpick_item",
		args: {
			sales_order: sales_order,
			sales_order_item: sales_order_item,
			pick_list: pick_list,
			pick_list_item: pick_list_item,
			unpick_qty: unpick_qty
		},
		callback: function (r) {
			if (r.message) {
				frappe.msg_dialog && frappe.msg_dialog.hide();
				setTimeout(function () { frappe.msgprint(r.message); }, 500);
			}
			$('.' + pick_list_item).hide();
		}
	});
};

window.change_location_details = function (batch_no, location, item_code) {
	frappe.prompt({
		label: __("Location"),
		fieldname: "location",
		fieldtype: "Data",
		default: location || "",
		reqd: 1
	}, (values) => {
		frappe.call({
			method: "malaga.malaga.report.lot_wise_balance.lot_wise_balance.update_batch_location",
			args: {
				batch_no: batch_no,
				location: values.location
			},
			freeze: true,
			callback: function (r) {
				frappe.show_alert({ message: r.message || __("Location updated"), indicator: "green" });
				frappe.query_report.refresh();
			}
		});
	}, __("Change Location"), __("Update"));
};

window.new_qty_details = function (company, item_code, item_group, balance_qty, warehouse, buying_unit_price, batch_no, lot_no, packing_type) {
	let template = `
		<table class="table table-borderless" style="border: 0 !important; font-size:95%;">
			<tr style="border: 0 !important;">
			<td style="border: 0 !important;"><b>Company : </b>{{data['company']}}</td>
			<td style="border: 0 !important;"><b>Item Group: </b> {{ data['item_group'] }}</td>

			</tr>
			<tr style="border: 0 !important;">
			<td style="border: 0 !important;"><b>Available Qty : </b>{{data['balance_qty']}}</td>
			<td style="border: 0 !important;"><b>Warehouse : </b>{{data['warehouse']}}</td>
			</tr>
			<tr style="border: 0 !important;">
			<td style="border: 0 !important;"><b>Batch : </b>{{data['batch_no']}}</td>
			<td style="border: 0 !important;"><b>Lot : </b>{{data['lot_no']}}</td>
			</tr>
			<tr style="border: 0 !important;">
			<td style="border: 0 !important;"><input type="date" id="date"></td>
			<td style="border: 0 !important;"><input type="time" id="time"></td>
			</tr>
			<tr style="border: 0 !important;">
			<td style="border: 0 !important;"><input type="number" style="width:50px" id="new_qty"></input>
			<td style="border: 0 !important;">
			<button style="margin-left:5px;border:0 !important;color:#fff;background-color:blue;padding:3px 5px;border-radius:5px;" type="button" class="lot-wise-create-se-btn" data-company="{{ data['company'] }}" data-warehouse="{{ data['warehouse'] }}" data-balance-qty="{{ data['balance_qty'] }}" data-item-code="{{ data['item_code'] }}" data-buying-unit-price="{{ data['buying_unit_price'] }}" data-batch-no="{{ data['batch_no'] }}" data-lot-no="{{ data['lot_no'] }}" data-packing-type="{{ data['packing_type'] }}">Create Stock Entry</button>
			</tr>
		</table>`;
	let message = frappe.template.compile(template)({ 'data': { "company": company, "item_code": item_code, "item_group": item_group, "balance_qty": balance_qty, "warehouse": warehouse, "buying_unit_price": buying_unit_price, "batch_no": batch_no, "lot_no": lot_no, "packing_type": packing_type } });
	frappe.msgprint({
		message: message,
		title: "Item Code : " + item_code,
		wide: true,
	});
	setTimeout(function () {
		$(".lot-wise-create-se-btn").off("click").on("click", function () {
			const btn = this;
			window.create_stock_entry(
				btn.getAttribute("data-company"),
				btn.getAttribute("data-warehouse"),
				btn.getAttribute("data-item-code"),
				btn.getAttribute("data-balance-qty"),
				btn.getAttribute("data-buying-unit-price"),
				document.getElementById("new_qty").value,
				document.getElementById("date").value,
				document.getElementById("time").value,
				btn.getAttribute("data-batch-no"),
				btn.getAttribute("data-lot-no"),
				btn.getAttribute("data-packing-type")
			);
		});
	}, 250);
};

window.create_stock_entry = function (company, warehouse, item_code, balance_qty, buying_unit_price, new_qty, date, time, batch_no, lot_no, packing_type) {
	if ((new_qty) < 0) {
		frappe.throw("Please Don't Enter Negative Qty")
	}

	frappe.msg_dialog && frappe.msg_dialog.hide();
	frappe.call({
		method: "malaga.malaga.report.lot_wise_balance.lot_wise_balance.create_stock_entry",
		args:
		{
			company: company,
			warehouse: warehouse,
			item_code: item_code,
			balance_qty: balance_qty,
			buying_unit_price: buying_unit_price,
			new_qty: new_qty,
			date: date,
			time: time,
			batch_no: batch_no,
			lot_no: lot_no,
			packing_type: packing_type
		},
		freeze: true,
		freeze_message: "<b>creating stock entry...<b>",
		callback: function (r) {
			frappe.msgprint(r.message);
		}
	});
};