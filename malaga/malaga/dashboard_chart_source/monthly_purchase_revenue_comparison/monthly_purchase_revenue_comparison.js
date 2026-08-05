frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Monthly Purchase Revenue Comparison"] = {
    method: "malaga.malaga.dashboard_chart_source.monthly_purchase_revenue_comparison.monthly_purchase_revenue_comparison.get",
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