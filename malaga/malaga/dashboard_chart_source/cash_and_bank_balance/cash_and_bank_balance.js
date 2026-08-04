frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Cash and Bank Balance"] = {
	method: "malaga.malaga.dashboard_chart_source.cash_and_bank_balance.cash_and_bank_balance.get",
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
	],
};
