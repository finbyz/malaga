import calendar

import frappe
from frappe.utils import add_days, get_first_day, get_last_day, getdate, nowdate


def _filters_dict(filters=None):
	if isinstance(filters, str) and filters.strip():
		filters = frappe.parse_json(filters)
	if not filters:
		return frappe._dict()
	if isinstance(filters, dict):
		return frappe._dict(filters)

	values = {}
	for row in filters:
		if len(row) >= 4:
			values[row[1]] = row[3]
	return frappe._dict(values)


def _truthy(value):
	if isinstance(value, str):
		return value.strip().lower() not in ("0", "false", "no", "off", "")
	return bool(value)


def _exclude_internal(filters=None):
	return _truthy(_filters_dict(filters).get("exclude_internal", 1))


def _sales_internal_sql(alias, filters=None):
	return f" AND IFNULL({alias}.is_internal_customer, 0) = 0" if _exclude_internal(filters) else ""


def _purchase_internal_sql(alias, filters=None):
	return f" AND IFNULL({alias}.is_internal_supplier, 0) = 0" if _exclude_internal(filters) else ""


def _company(filters=None):
	company = _filters_dict(filters).get("company") or frappe.defaults.get_user_default("Company")
	if not company:
		company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		companies = frappe.get_all("Company", limit=1, pluck="name")
		company = companies[0] if companies else None
	if not company:
		frappe.throw("Company is required")
	frappe.has_permission("Company", doc=company, ptype="read", throw=True)
	return company


def _currency_result(value, company):
	return {
		"value": value or 0,
		"fieldtype": "Currency",
		"options": frappe.get_cached_value("Company", company, "default_currency"),
	}


def _month_dates():
	today = getdate(nowdate())
	return get_first_day(today), get_last_day(today)


def _gross_profit(company, from_date, to_date, exclude_internal=True):
	internal_condition = " AND IFNULL(si.is_internal_customer, 0) = 0" if exclude_internal else ""
	return frappe.db.sql(f"""
		SELECT COALESCE(SUM(sii.base_net_amount - (sii.incoming_rate * sii.stock_qty)), 0)
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 
		AND si.company = %s 
		AND si.posting_date BETWEEN %s AND %s
		{internal_condition}
	""", (company, from_date, to_date))[0][0] or 0


@frappe.whitelist()
def total_sales_this_month(filters=None):
	company = _company(filters)
	from_date, to_date = _month_dates()
	value = frappe.db.sql(
		"""SELECT COALESCE(SUM(base_net_total), 0) FROM `tabSales Invoice`
		WHERE company = %s AND docstatus = 1 AND posting_date BETWEEN %s AND %s""",
		(company, from_date, to_date),
	)[0][0]
	return _currency_result(value, company)


@frappe.whitelist()
def gross_profit_this_month(filters=None):
	company = _company(filters)
	return _currency_result(_gross_profit(company, *_month_dates(), _exclude_internal(filters)), company)


@frappe.whitelist()
def inventory_value(filters=None):
	company = _company(filters)
	value = frappe.db.sql(
		"""
		SELECT SUM(bin.stock_value)
		FROM `tabBin` bin
		INNER JOIN `tabWarehouse` warehouse ON warehouse.name = bin.warehouse
		WHERE warehouse.company = %s
		""",
		company,
	)[0][0]
	return _currency_result(value, company)


@frappe.whitelist()
def open_sales_orders(filters=None):
	company = _company(filters)
	return frappe.db.count(
		"Sales Order",
		{
			"company": company,
			"docstatus": 1,
			"status": ["not in", ["Completed", "Closed", "Cancelled"]],
			"per_delivered": ["<", 100],
		},
	)


@frappe.whitelist()
def open_purchase_orders(filters=None):
	company = _company(filters)
	return frappe.db.count(
		"Purchase Order",
		{
			"company": company,
			"docstatus": 1,
			"status": ["not in", ["Completed", "Closed", "Cancelled"]],
			"per_received": ["<", 100],
		},
	)


def _commission_earned(company, from_date, to_date, exclude_internal=True):
	internal_condition = " AND IFNULL(invoice.is_internal_customer, 0) = 0" if exclude_internal else ""
	return frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(team.incentives), 0)
		FROM `tabSales Team` team
		INNER JOIN `tabSales Invoice` invoice
			ON invoice.name = team.parent AND team.parenttype = 'Sales Invoice'
		WHERE invoice.docstatus = 1
			AND invoice.company = %s
			AND invoice.posting_date BETWEEN %s AND %s
			{internal_condition}
		""",
		(company, from_date, to_date),
	)[0][0]


@frappe.whitelist()
def commission_earned_this_month(filters=None):
	company = _company(filters)
	return _currency_result(_commission_earned(company, *_month_dates(), _exclude_internal(filters)), company)


@frappe.whitelist()
def profit_after_commission_this_month(filters=None):
	company = _company(filters)
	from_date, to_date = _month_dates()
	exclude_internal = _exclude_internal(filters)
	value = _gross_profit(company, from_date, to_date, exclude_internal) - _commission_earned(company, from_date, to_date, exclude_internal)
	return _currency_result(value, company)


def monthly_sales_revenue_data(filters=None):
	company = _company(filters)
	internal_condition = _sales_internal_sql("si", filters)
	current_year = getdate(nowdate()).year
	rows = frappe.db.sql(
		f"""
		SELECT YEAR(posting_date) AS year, MONTH(posting_date) AS month, SUM(base_net_total) AS revenue
		FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND company = %s AND YEAR(posting_date) IN (%s, %s)
		{internal_condition}
		GROUP BY YEAR(posting_date), MONTH(posting_date)
		""",
		(company, current_year, current_year - 1),
		as_dict=True,
	)
	values = {(row.year, row.month): row.revenue for row in rows}
	current_month = getdate(nowdate()).month
	return {
		"labels": [calendar.month_abbr[month] for month in range(1, 13)],
		"datasets": [
			{
				"name": str(current_year),
				"values": [values.get((current_year, month), 0) if month <= current_month else None for month in range(1, 13)],
			},
			{
				"name": str(current_year - 1),
				"values": [values.get((current_year - 1, month), 0) for month in range(1, 13)],
			},
		],
		"type": "line",
	}


def sku_sales_classification_data(filters=None):
	company = _company(filters)
	counts = {"Best Seller": 0, "Great Seller": 0, "Good Seller": 0, "No Sales": 0}

	items = frappe.db.sql(
		"""
		SELECT item.custom_sales_tier, COUNT(DISTINCT item.name) as count
		FROM `tabItem` item
		INNER JOIN `tabItem Default` def ON def.parent = item.name
		WHERE def.company = %s AND item.disabled = 0
		GROUP BY item.custom_sales_tier
		""",
		(company,),
		as_dict=True,
	)
	
	for row in items:
		tier = row.custom_sales_tier
		if tier in counts:
			counts[tier] += row.count
		elif not tier:
			counts["No Sales"] += row.count

	return {
		"labels": list(counts.keys()),
		"datasets": [{"name": "Items", "values": list(counts.values())}],
		"type": "donut",
	}


def slow_moving_inventory_data(filters=None):
	company = _company(filters)
	internal_condition = _sales_internal_sql("invoice", filters)
	rows = frappe.db.sql(
		f"""
		SELECT bin.item_code, SUM(bin.stock_value) AS stock_value, MAX(sales.last_sale_date) AS last_sale_date
		FROM `tabBin` bin
		INNER JOIN `tabWarehouse` warehouse ON warehouse.name = bin.warehouse
		LEFT JOIN (
			SELECT item.item_code, MAX(invoice.posting_date) AS last_sale_date
			FROM `tabSales Invoice Item` item
			INNER JOIN `tabSales Invoice` invoice ON invoice.name = item.parent
			WHERE invoice.docstatus = 1 AND invoice.company = %s
			{internal_condition}
			GROUP BY item.item_code
		) sales ON sales.item_code = bin.item_code
		WHERE warehouse.company = %s
		GROUP BY bin.item_code
		HAVING SUM(bin.actual_qty) > 0 AND SUM(bin.stock_value) > 0
		""",
		(company, company),
		as_dict=True,
	)
	buckets = {"30-59 Days": 0, "60-89 Days": 0, "90-179 Days": 0, "180+ Days": 0, "Never Sold": 0}
	today = getdate(nowdate())
	for row in rows:
		if not row.last_sale_date:
			buckets["Never Sold"] += row.stock_value
			continue
		age = (today - getdate(row.last_sale_date)).days
		if 30 <= age < 60:
			buckets["30-59 Days"] += row.stock_value
		elif 60 <= age < 90:
			buckets["60-89 Days"] += row.stock_value
		elif 90 <= age < 180:
			buckets["90-179 Days"] += row.stock_value
		elif age >= 180:
			buckets["180+ Days"] += row.stock_value

	return {
		"labels": list(buckets),
		"datasets": [{"name": "Stock Value", "values": list(buckets.values())}],
		"type": "bar",
	}


def sales_and_commission_by_salesperson_data(filters=None):
	filters = _filters_dict(filters)
	company = _company(filters)
	from_date = filters.get("from_date") or f"{getdate(nowdate()).year}-01-01"
	to_date = filters.get("to_date") or nowdate()
	internal_condition = _sales_internal_sql("invoice", filters)
	rows = frappe.db.sql(
		f"""
		SELECT team.sales_person, SUM(team.allocated_amount) AS sales, SUM(team.incentives) AS commission
		FROM `tabSales Team` team
		INNER JOIN `tabSales Invoice` invoice
			ON invoice.name = team.parent AND team.parenttype = 'Sales Invoice'
		WHERE invoice.docstatus = 1 AND invoice.company = %s
			AND invoice.posting_date BETWEEN %s AND %s
			{internal_condition}
		GROUP BY team.sales_person
		ORDER BY sales DESC
		LIMIT 10
		""",
		(company, from_date, to_date),
		as_dict=True,
	)
	return {
		"labels": [row.sales_person for row in rows],
		"datasets": [
			{"name": "Sales", "values": [float(row.sales or 0) for row in rows]},
			{"name": "Commission Earned", "values": [float(row.commission or 0) for row in rows]},
		],
		"type": "bar",
	}


def _get_gross_profit_report_data(company, from_date, to_date, group_by):
	from erpnext.accounts.report.gross_profit.gross_profit import execute

	columns, data = execute(
		frappe._dict(
			company=company,
			from_date=from_date,
			to_date=to_date,
			group_by=group_by,
			include_returned_invoices=1,
		)
	)
	if not data:
		return []

	fieldnames = []
	for column in columns:
		if isinstance(column, dict):
			fieldnames.append(column.get("fieldname"))
		else:
			fieldnames.append(str(column).split(":", 1)[0])

	rows = []
	for row in data:
		if isinstance(row, dict):
			row_dict = row
		else:
			row_dict = frappe._dict({fieldname: value for fieldname, value in zip(fieldnames, row)})
		first_value = row_dict.get(fieldnames[0]) if fieldnames else None
		if first_value == "Total":
			continue
		rows.append(row_dict)
	return rows


@frappe.whitelist()
def gross_profit_by_warehouse_data(filters=None):
	company = _company(filters)
	from_date = f"{getdate(nowdate()).year}-01-01"
	to_date = nowdate()
	rows = _get_gross_profit_report_data(company, from_date, to_date, group_by="Warehouse")
	labels = []
	values = []
	for row in rows:
		indent = row.get("indent", 0.0)
		warehouse = row.get("warehouse") or "No Warehouse"
		gross_profit = row.get("gross_profit", 0)
		if indent in [0.0, None]:
			labels.append(warehouse)
			values.append(float(gross_profit))

	sorted_data = sorted(zip(labels, values), key=lambda x: x[1], reverse=True)[:10]
	return {
		"labels": [d[0] for d in sorted_data],
		"datasets": [{"name": "Gross Profit", "values": [d[1] for d in sorted_data]}],
		"type": "bar",
	}

@frappe.whitelist()
def total_purchases_this_month(filters=None):
	company = _company(filters)
	from_date = f"{getdate(nowdate()).year}-{getdate(nowdate()).month:02d}-01"
	to_date = nowdate()
	
	result = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(base_grand_total), 0)
		FROM `tabPurchase Invoice`
		WHERE docstatus = 1
			AND company = %s
			AND posting_date BETWEEN %s AND %s
		""",
		(company, from_date, to_date),
	)
	
	value = result[0][0] if result else 0
	return {
		"value": value,
		"fieldtype": "Currency",
		"currency": frappe.get_cached_value("Company", company, "default_currency")
	}

@frappe.whitelist()
def gross_profit_by_category_data(filters=None):
	data = _gross_profit_sql_group(filters, "item.item_group")
	return {
		"labels": [d.label for d in data],
		"datasets": [{"name": "Gross Profit", "values": [float(d.gross_profit or 0) for d in data]}],
		"type": "bar",
	}


@frappe.whitelist()
def gross_profit_by_customer_data(filters=None):
	data = _gross_profit_sql_group(filters, "invoice.customer")
	return {
		"labels": [d.label for d in data],
		"datasets": [{"name": "Gross Profit", "values": [float(d.gross_profit or 0) for d in data]}],
		"type": "bar",
	}


@frappe.whitelist()
def gross_profit_by_item_data(filters=None):
	data = _gross_profit_sql_group(filters, "item.item_code")
	return {
		"labels": [d.label for d in data],
		"datasets": [{"name": "Gross Profit", "values": [float(d.gross_profit or 0) for d in data]}],
		"type": "bar",
	}


def _gross_profit_sql_group(filters=None, group_expr="item.item_code"):
	filters = _filters_dict(filters)
	company = _company(filters)
	from_date = filters.get("from_date") or add_days(nowdate(), -60)
	to_date = filters.get("to_date") or nowdate()
	internal_condition = _sales_internal_sql("invoice", filters)
	return frappe.db.sql(
		f"""
		SELECT COALESCE({group_expr}, 'Not Set') AS label,
			COALESCE(SUM(item.base_net_amount - (item.incoming_rate * item.stock_qty)), 0) AS gross_profit
		FROM `tabSales Invoice Item` item
		INNER JOIN `tabSales Invoice` invoice ON invoice.name = item.parent
		WHERE invoice.docstatus = 1
			AND invoice.company = %s
			AND invoice.posting_date BETWEEN %s AND %s
			{internal_condition}
		GROUP BY {group_expr}
		HAVING gross_profit != 0
		ORDER BY gross_profit DESC
		LIMIT 10
		""",
		(company, from_date, to_date),
		as_dict=True,
	)


@frappe.whitelist()
def fulfillment_time_data(filters=None):
	company = _company(filters)
	internal_condition = _sales_internal_sql("dn", filters)
	rows = frappe.db.sql(
		f"""
		SELECT MONTH(dn.posting_date) AS month, YEAR(dn.posting_date) AS year,
		AVG(DATEDIFF(dn.posting_date, so.transaction_date)) AS avg_days
		FROM `tabDelivery Note` dn
		INNER JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
		INNER JOIN `tabSales Order` so ON so.name = dni.against_sales_order
		WHERE dn.docstatus = 1 AND dn.company = %s
		AND dn.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
		{internal_condition}
		GROUP BY YEAR(dn.posting_date), MONTH(dn.posting_date)
		ORDER BY YEAR(dn.posting_date), MONTH(dn.posting_date)
		""",
		company,
		as_dict=True,
	)
	labels = []
	values = []
	import calendar
	for row in rows:
		labels.append(f"{calendar.month_abbr[row.month]} {str(row.year)[-2:]}")
		values.append(round(row.avg_days or 0, 1))

	return {
		"labels": labels,
		"datasets": [{"name": "Average Days to Fulfill", "values": values}],
		"type": "line",
	}


@frappe.whitelist()
def purchase_price_trends_data(filters=None):
	filters = _filters_dict(filters)
	company = _company(filters)
	from_date = filters.get("from_date") or add_days(nowdate(), -180)
	to_date = filters.get("to_date") or nowdate()
	internal_condition = _purchase_internal_sql("pr", filters)
	
	# Get the top 5 items by purchase amount
	top_items = frappe.db.sql(
		f"""
		SELECT item_code, SUM(base_net_amount) AS total_amount
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1 AND pr.company = %s
		AND pr.posting_date BETWEEN %s AND %s
		{internal_condition}
		GROUP BY item_code
		ORDER BY total_amount DESC
		LIMIT 5
		""",
		(company, from_date, to_date),
		as_dict=True
	)
	
	if not top_items:
		return {"labels": [], "datasets": [], "type": "bar"}
	
	labels = [d.item_code for d in top_items]
	values = [d.total_amount for d in top_items]
	
	return {
		"labels": labels,
		"datasets": [{"name": "Purchase Amount", "values": values}],
		"type": "bar"
	}


@frappe.whitelist()
def cash_flow_forecast_data(filters=None):
	company = _company(filters)
	if isinstance(filters, str):
		import json
		try: filters = json.loads(filters)
		except: filters = {}
	if not isinstance(filters, dict): filters = {}
	forecast_mode = filters.get("forecast_mode", "future")
	sales_internal_condition = _sales_internal_sql("si", filters)
	purchase_internal_condition = _purchase_internal_sql("pi", filters)
	
	import datetime
	today = getdate(nowdate())

	overdue_ar = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(outstanding_amount), 0)
		FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND company = %s AND outstanding_amount > 0
		AND due_date < CURDATE()
		{sales_internal_condition}
		""", company
	)[0][0]

	overdue_ap = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(outstanding_amount), 0)
		FROM `tabPurchase Invoice` pi
		WHERE docstatus = 1 AND company = %s AND outstanding_amount > 0
		AND due_date < CURDATE()
		{purchase_internal_condition}
		""", company
	)[0][0]
	
	date_filter = "AND due_date >= CURDATE() AND due_date <= DATE_ADD(CURDATE(), INTERVAL 90 DAY)"
	if forecast_mode == "overdue":
		date_filter = "AND due_date <= DATE_ADD(CURDATE(), INTERVAL 90 DAY)"

	ar_rows = frappe.db.sql(
		f"""
		SELECT SUM(outstanding_amount) as amount, due_date
		FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND company = %s AND outstanding_amount > 0
		{date_filter}
		{sales_internal_condition}
		GROUP BY due_date
		""",
		company,
		as_dict=True
	)
	
	ap_rows = frappe.db.sql(
		f"""
		SELECT SUM(outstanding_amount) as amount, due_date
		FROM `tabPurchase Invoice` pi
		WHERE docstatus = 1 AND company = %s AND outstanding_amount > 0
		{date_filter}
		{purchase_internal_condition}
		GROUP BY due_date
		""",
		company,
		as_dict=True
	)
	
	if forecast_mode == "overdue":
		weeks = ["Overdue", "Week 1", "Week 2", "Week 3", "Week 4", "Week 5+"]
		inflows = [0, 0, 0, 0, 0, 0]
		outflows = [0, 0, 0, 0, 0, 0]
	else:
		weeks = ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5+"]
		inflows = [0, 0, 0, 0, 0]
		outflows = [0, 0, 0, 0, 0]
	
	def bucket_row(row, arr):
		days = (getdate(row.due_date) - today).days
		if forecast_mode == "overdue":
			if days < 0: arr[0] += row.amount
			elif days < 7: arr[1] += row.amount
			elif days < 14: arr[2] += row.amount
			elif days < 21: arr[3] += row.amount
			elif days < 28: arr[4] += row.amount
			else: arr[5] += row.amount
		else:
			if days < 7: arr[0] += row.amount
			elif days < 14: arr[1] += row.amount
			elif days < 21: arr[2] += row.amount
			elif days < 28: arr[3] += row.amount
			else: arr[4] += row.amount

	for row in ar_rows: bucket_row(row, inflows)
	for row in ap_rows: bucket_row(row, outflows)

	future_ar = sum(inflows[1:]) if forecast_mode == "overdue" else sum(inflows)
	future_ap = sum(outflows[1:]) if forecast_mode == "overdue" else sum(outflows)
		
	return {
		"labels": weeks,
		"datasets": [
			{"name": "Expected Inflows (AR)", "values": inflows},
			{"name": "Expected Outflows (AP)", "values": outflows}
		],
		"metrics": {
			"future_ar": future_ar,
			"future_ap": future_ap,
			"net_forecast": future_ar - future_ap,
			"overdue_ar": overdue_ar,
			"overdue_ap": overdue_ap
		},
		"type": "bar",
	}


@frappe.whitelist()
def set_user_company(company):
    frappe.defaults.set_user_default("Company", company)
    return {"status": "success"}

@frappe.whitelist()
def cash_and_bank_balance_data(filters=None):
	company = _company(filters)
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "account_type": ["in", ["Cash", "Bank"]]},
		fields=["name", "root_type"],
		order_by="name",
	)
	if not accounts:
		return {"labels": [], "datasets": [{"name": "Balance", "values": []}], "type": "bar"}

	rows = frappe.db.sql(
		"""
		SELECT account, SUM(debit - credit) AS balance
		FROM `tabGL Entry`
		WHERE company = %s
			AND is_cancelled = 0
			AND account IN %s
			AND voucher_type != 'Period Closing Voucher'
		GROUP BY account
		""",
		(company, tuple(account.name for account in accounts)),
		as_dict=True,
	)
	balances = {row.account: row.balance or 0 for row in rows}

	return {
		"labels": [account.name for account in accounts],
		"datasets": [{"name": "Balance", "values": [balances.get(account.name, 0) for account in accounts]}],
		"type": "bar",
	}

@frappe.whitelist()
def revenue_per_commission_dollar_data(filters=None):
	filters = _filters_dict(filters)
	company = _company(filters)
	from_date = filters.get("from_date") or f"{getdate(nowdate()).year}-01-01"
	to_date = filters.get("to_date") or nowdate()
	internal_condition = _sales_internal_sql("invoice", filters)
	rows = frappe.db.sql(
		f"""
		SELECT team.sales_person,
			SUM(team.allocated_amount) AS sales,
			SUM(team.incentives) AS commission
		FROM `tabSales Team` team
		INNER JOIN `tabSales Invoice` invoice
			ON invoice.name = team.parent AND team.parenttype = 'Sales Invoice'
		WHERE invoice.docstatus = 1
			AND invoice.company = %s
			AND invoice.posting_date BETWEEN %s AND %s
			{internal_condition}
		GROUP BY team.sales_person
		HAVING commission > 0
		ORDER BY SUM(team.allocated_amount) / SUM(team.incentives) DESC
		LIMIT 10
		""",
		(company, from_date, to_date),
		as_dict=True,
	)
	return {
		"labels": [row.sales_person for row in rows],
		"datasets": [
			{
				"name": "Revenue per Commission Dollar",
				"values": [round((row.sales or 0) / (row.commission or 1), 2) for row in rows],
			}
		],
		"type": "bar",
	}


@frappe.whitelist()
def inventory_turnover_data(filters=None):
	filters = _filters_dict(filters)
	company = _company(filters)
	from_date = filters.get("from_date") or f"{getdate(nowdate()).year}-01-01"
	to_date = filters.get("to_date") or nowdate()
	internal_condition = _sales_internal_sql("invoice", filters)
	inventory_value = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(bin.stock_value), 0)
		FROM `tabBin` bin
		INNER JOIN `tabWarehouse` warehouse ON warehouse.name = bin.warehouse
		WHERE warehouse.company = %s
		""",
		company,
	)[0][0] or 0
	rows = frappe.db.sql(
		f"""
		SELECT YEAR(invoice.posting_date) AS year,
			MONTH(invoice.posting_date) AS month,
			COALESCE(SUM(item.stock_qty * item.incoming_rate), 0) AS cogs
		FROM `tabSales Invoice Item` item
		INNER JOIN `tabSales Invoice` invoice ON invoice.name = item.parent
		WHERE invoice.docstatus = 1
			AND invoice.company = %s
			AND invoice.posting_date BETWEEN %s AND %s
			{internal_condition}
		GROUP BY YEAR(invoice.posting_date), MONTH(invoice.posting_date)
		ORDER BY YEAR(invoice.posting_date), MONTH(invoice.posting_date)
		""",
		(company, from_date, to_date),
		as_dict=True,
	)
	labels = [f"{calendar.month_abbr[row.month]} {str(row.year)[-2:]}" for row in rows]
	values = [round((row.cogs or 0) / inventory_value, 2) if inventory_value else 0 for row in rows]
	return {
		"labels": labels,
		"datasets": [{"name": "Inventory Turnover", "values": values}],
		"type": "line",
	}


@frappe.whitelist()
def inventory_accuracy_data(filters=None):
	filters = _filters_dict(filters)
	company = _company(filters)
	from_date = filters.get("from_date") or f"{getdate(nowdate()).year}-01-01"
	to_date = filters.get("to_date") or nowdate()
	rows = frappe.db.sql(
		"""
		SELECT YEAR(reconciliation.posting_date) AS year,
			MONTH(reconciliation.posting_date) AS month,
			SUM(ABS(COALESCE(item.qty, 0) - COALESCE(item.current_qty, 0))) AS variance_qty,
			SUM(GREATEST(ABS(COALESCE(item.qty, 0)), ABS(COALESCE(item.current_qty, 0)))) AS counted_qty
		FROM `tabStock Reconciliation Item` item
		INNER JOIN `tabStock Reconciliation` reconciliation ON reconciliation.name = item.parent
		WHERE reconciliation.docstatus = 1
			AND reconciliation.company = %s
			AND reconciliation.posting_date BETWEEN %s AND %s
		GROUP BY YEAR(reconciliation.posting_date), MONTH(reconciliation.posting_date)
		ORDER BY YEAR(reconciliation.posting_date), MONTH(reconciliation.posting_date)
		""",
		(company, from_date, to_date),
		as_dict=True,
	)
	labels = []
	values = []
	for row in rows:
		labels.append(f"{calendar.month_abbr[row.month]} {str(row.year)[-2:]}")
		if row.counted_qty:
			accuracy = max(0, 100 * (1 - ((row.variance_qty or 0) / row.counted_qty)))
		else:
			accuracy = 100 if not row.variance_qty else 0
		values.append(round(accuracy, 2))
	return {
		"labels": labels,
		"datasets": [{"name": "Inventory Accuracy %", "values": values}],
		"type": "line",
	}

@frappe.whitelist()
def revenue_by_company_data(filters=None):
	fd = _filters_dict(filters)
	from_date = fd.get("from_date") or f"{getdate(nowdate()).year}-01-01"
	to_date = fd.get("to_date") or nowdate()
	internal_condition = _sales_internal_sql("si", fd)

	rows = frappe.db.sql(
		f"""
		SELECT company, COALESCE(SUM(base_net_total), 0) as revenue
		FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s
		{internal_condition}
		GROUP BY company
		ORDER BY revenue DESC
		""",
		(from_date, to_date),
		as_dict=True
	)

	return {
		"labels": [row.company for row in rows],
		"datasets": [
			{"name": "Revenue", "values": [float(row.revenue or 0) for row in rows]}
		],
		"type": "bar",
	}
