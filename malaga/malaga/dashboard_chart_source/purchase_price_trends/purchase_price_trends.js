frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Purchase Price Trends"] = {
	method: "malaga.malaga.dashboard_chart_source.purchase_price_trends.purchase_price_trends.get",
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
