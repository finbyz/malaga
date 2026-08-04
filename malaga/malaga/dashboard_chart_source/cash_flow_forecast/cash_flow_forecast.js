frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Cash Flow Forecast"] = {
	method: "malaga.malaga.dashboard_chart_source.cash_flow_forecast.cash_flow_forecast.get",
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
