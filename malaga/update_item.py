import frappe
from frappe import _
from frappe.utils import flt, cint
import json
from erpnext.controllers.accounts_controller import set_order_defaults, validate_and_delete_children
from malaga.doc_events.pick_list import unpick_item,unpick_qty_comment
from frappe.utils import get_url_to_form


def set_tax_paid_on_parent(parent, tax_paid=None, tax_paid_from_si=None):
	if not parent.meta.has_field("tax_paid"):
		return
	if not frappe.db.has_column(parent.doctype, "tax_paid"):
		return
	if cint(tax_paid):
		parent.db_set("tax_paid", cint(tax_paid))
	elif cint(tax_paid_from_si):
		parent.db_set("tax_paid", cint(tax_paid_from_si))


def set_payment_terms_on_parent(parent, payment_terms_template):
	if not payment_terms_template or not parent.meta.has_field("payment_terms_template"):
		return
	parent.db_set("payment_terms_template", payment_terms_template)


def update_delivered_percent(self):
    qty = 0
    delivered_qty = 0
    if self.locations:
        for index, item in enumerate(self.locations):
            qty += item.qty
            delivered_qty += item.delivered_qty

            item.db_set('idx', index + 1)

        try:
            self.db_set('per_delivered', (delivered_qty / qty) * 100)
        except:
            self.db_set('per_delivered', 0)

@frappe.whitelist()
def update_child_price(tax_paid, tax_paid_from_si, parent_doctype, trans_items, parent_doctype_name, payment_terms_template_si, child_docname="items"):
    data = json.loads(trans_items)
    parent = frappe.get_doc(parent_doctype, parent_doctype_name)
    price_dict={}
    discount_dict={}
    sqf_dict={}
    item_group_list=[]
    for item in data:
        if item.get("item_group") not in price_dict.keys():
            price_dict[item.get("item_group")]=item.get("rate")
            item_group_list.append(item.get("item_group"))
    for item in data:
        if item.get("item_group") not in sqf_dict.keys():
            sqf_dict[item.get("item_group")]=item.get("sqf_rate")
    for item in data:
        if item.get("item_group") not in discount_dict.keys():
            discount_dict[item.get("item_group")]=item.get("discount_rate")

        
        

    comment = ''
    parent_table= frappe.db.get_all("Sales Order Item",{'parent':parent_doctype_name})
    for child_item in parent_table:
        child_doc=frappe.get_doc("Sales Order Item", child_item)
        if child_doc.item_group in item_group_list:
            if item.get('rate') != child_doc.rate:
                comment += f"Rate Changed in Item Group: {item.get('item_group')} , "
            if item.get('sqf_rate') != child_doc.sqf_rate :
                comment += f"SQF Rate Changed for Item Goups: {item.get('item_group')} , "
            if item.get('discount_rate') != child_doc.discounted_rate :
                comment += f"Discounted Rate Changed for Item Goups: {item.get('item_group')} , "
            # if item.get('item_group') != child_doc.item_code:
            # 	comment += f""" Item Change From {frappe.bold(child_doc.item_code)} to {item.get('item_group')}. """
                # href='{get_url_to_form("Item Group", child_doc.item_group)}'
                # href='{frappe.bold(get_url_to_form("Item Group", item.get("item_group")))}'

            if item.get("item_group") not in item_group_list:
                item_group_list.append(child_doc.item_group)

            if not flt(price_dict[child_doc.item_group]):
                    price_dict[child_doc.item_group] = child_doc.rate
            precision = child_doc.precision("rate") or 2

            if flt(child_doc.billed_amt, precision) > flt(flt(price_dict[child_doc.item_group]) * flt(child_doc.get("qty")), precision):
                frappe.throw(_("Row #{0}: Cannot set Rate if amount is greater than billed amount for Item {1}.")
                            .format(child_doc.idx, child_doc.item_code))
            else:
                child_doc.sqf_rate = flt(sqf_dict[child_doc.item_group])
                if child_doc.sqf_rate:
                    sqf_calculation=frappe.db.get_value("Item Group",child_doc.item_group,'sqf_calculation')
                    child_doc.rate = flt(sqf_dict[child_doc.item_group] * (sqf_calculation or 15.5))
                else:
                    child_doc.rate = flt(price_dict[child_doc.item_group])
                child_doc.discounted_rate = flt(discount_dict[child_doc.item_group])

            if price_dict[child_doc.item_group]:
                child_doc.rate = flt(price_dict[child_doc.item_group])
            if discount_dict[child_doc.item_group]:
                child_doc.discount_amount=flt(discount_dict[child_doc.item_group])
            
            child_doc.discounted_amount = child_doc.real_qty * child_doc.discounted_rate
            child_doc.discounted_net_amount = child_doc.discounted_amount

            if flt(child_doc.price_list_rate):
                if flt(child_doc.rate) > flt(child_doc.price_list_rate):
                    #  if rate is greater than price_list_rate, set margin
                    #  or set discount
                    child_doc.discount_percentage = 0

                    child_doc.margin_type = "Amount"
                    child_doc.margin_rate_or_amount = flt(child_doc.rate - child_doc.price_list_rate,
                        child_doc.precision("margin_rate_or_amount"))
                    child_doc.rate_with_margin = child_doc.rate
                else:
                    child_doc.discount_percentage = flt((1 - flt(child_doc.rate) / flt(child_doc.price_list_rate)) * 100.0,
                        child_doc.precision("discount_percentage"))
                    child_doc.discount_amount = flt(child_doc.price_list_rate) - flt(child_doc.rate)

                    child_doc.margin_type = ""
                    child_doc.margin_rate_or_amount = 0
                    child_doc.rate_with_margin = 0


            child_doc.flags.ignore_validate_update_after_submit = True
            child_doc.save()
        else:
            frappe.throw("Not Permitted to change Item Group")

    # parent.db_set("payment_terms_template", payment_terms_template_si)
    set_tax_paid_on_parent(parent, tax_paid, tax_paid_from_si)
    set_payment_terms_on_parent(parent, payment_terms_template_si)
    
    if comment :
        comment_doc = frappe.new_doc("Comment")
        comment_doc.comment_type = "Info"
        comment_doc.comment_email = frappe.session.user
        comment_doc.reference_doctype = "Sales Order"
        comment_doc.reference_name = parent_doctype_name

        comment_doc.content =  ":" +comment

        comment_doc.save()
    parent.calculate_taxes_and_totals()



    parent_doctype= "Sales Order"
    parent.reload()
    parent.flags.ignore_validate_update_after_submit = True
    parent.flags.ignore_permissions = True
    parent.set_qty_as_per_stock_uom()
    parent.calculate_taxes_and_totals()
    if parent_doctype == "Sales Order":
        parent.set_gross_profit()
    frappe.get_doc('Authorization Control').validate_approving_authority(parent.doctype,
        parent.company, parent.base_grand_total)

    parent.set_payment_schedule()
    if parent_doctype == 'Purchase Order':
        parent.validate_minimum_order_qty()
        parent.validate_budget()
        if parent.is_against_so():
            parent.update_status_updater()
    else:
        parent.check_credit_limit()
    parent.save()

    if parent_doctype == 'Purchase Order':
        update_last_purchase_rate(parent, is_submit = 1)
        parent.update_prevdoc_status()
        parent.update_requested_qty()
        parent.update_ordered_qty()
        parent.update_ordered_and_reserved_qty()
        parent.update_receiving_percentage()
        if parent.is_subcontracted == "Yes":
            parent.update_reserved_qty_for_subcontract()
    else:
        parent.update_reserved_qty()
        parent.update_project()
        parent.update_prevdoc_status('submit')
        parent.update_delivery_status()

    parent.update_blanket_order()
    parent.update_billing_percentage()
    parent.set_status()

@frappe.whitelist()
def update_child_price_sales_invoice(tax_paid, tax_paid_from_si, parent_doctype, trans_items, parent_doctype_name, payment_terms_template_si, child_docname="items"):
    data = json.loads(trans_items)
    parent = frappe.get_doc(parent_doctype, parent_doctype_name)
    price_dict={}
    discount_dict={}
    sqf_dict={}
    item_group_list=[]
    for item in data:
        key=(item.get("item_group") ,item.get("tile_quality"))
        if key not in item_group_list:
            item_group_list.append(key)
    for item in data:
        key=(item.get("item_group") ,item.get("tile_quality") )
        if key not in price_dict.keys():
            price_dict[key]=item.get("rate")
    for item in data:
        key=(item.get("item_group") ,item.get("tile_quality"))
        if key not in sqf_dict.keys():
            sqf_dict[key]=item.get("sqf_rate")
    for item in data:
        key=(item.get("item_group") ,item.get("tile_quality"))
        if key not in discount_dict.keys():
            discount_dict[key]=item.get("discount_rate")

    comment = ''
    parent_table= frappe.db.get_all("Sales Invoice Item",{'parent':parent_doctype_name})
    for child_item in parent_table:
        child_doc=frappe.get_doc("Sales Invoice Item", child_item)
        if (child_doc.item_group,child_doc.tile_quality)  in item_group_list:
            if item.get('rate') != child_doc.rate:
                comment += f"Rate Changed in Item Group: {item.get('item_group')} , "
            if item.get('sqf_rate') != child_doc.sqf_rate :
                comment += f"SQF Rate Changed for Item Goups: {item.get('item_group')} , "
            if item.get('discount_rate') != child_doc.discounted_rate :
                comment += f"Discounted Rate Changed for Item Goups: {item.get('item_group')} , "
            # if item.get('item_group') != child_doc.item_code:
            # 	comment += f""" Item Change From {frappe.bold(child_doc.item_code)} to {item.get('item_group')}. """
                # href='{get_url_to_form("Item Group", child_doc.item_group)}'
                # href='{frappe.bold(get_url_to_form("Item Group", item.get("item_group")))}'

            key=(item.get("item_group") ,item.get("tile_quality") )
            if key not in item_group_list:
                item_group_list.append(key)

            if not flt(price_dict.get((child_doc.item_group,child_doc.tile_quality))):
                    price_dict[(child_doc.item_group,child_doc.tile_quality)] = child_doc.rate
            precision = child_doc.precision("rate") or 2


            # if flt(child_doc.billed_amt, precision) > flt(flt(price_dict[child_doc.item_group]) * flt(child_doc.get("qty")), precision):
            # 	frappe.throw(_("Row #{0}: Cannot set Rate if amount is greater than billed amount for Item {1}.")
            # 				.format(child_doc.idx, child_doc.item_code))
            # else:
            child_doc.sqf_rate = flt(sqf_dict[(child_doc.item_group,child_doc.tile_quality)])
            if child_doc.sqf_rate:
                sqf_calculation=frappe.db.get_value("Item Group",child_doc.item_group,'sqf_calculation')
                child_doc.rate = flt(sqf_dict[(child_doc.item_group,child_doc.tile_quality)] * (sqf_calculation or 15.5))
            else:
                child_doc.rate = flt(price_dict[(child_doc.item_group,child_doc.tile_quality)])
            child_doc.discounted_rate = flt(discount_dict[(child_doc.item_group,child_doc.tile_quality)])

            if price_dict[(child_doc.item_group,child_doc.tile_quality)]:
                child_doc.rate = flt(price_dict[(child_doc.item_group,child_doc.tile_quality)])
            if discount_dict[(child_doc.item_group,child_doc.tile_quality)]:
                child_doc.discount_amount=flt(discount_dict[(child_doc.item_group,child_doc.tile_quality)])
            
            child_doc.discounted_amount = child_doc.real_qty * child_doc.discounted_rate
            child_doc.discounted_net_amount = child_doc.discounted_amount

            if flt(child_doc.price_list_rate):
                if flt(child_doc.rate) > flt(child_doc.price_list_rate):
                    #  if rate is greater than price_list_rate, set margin
                    #  or set discount
                    child_doc.discount_percentage = 0

                    child_doc.margin_type = "Amount"
                    child_doc.margin_rate_or_amount = flt(child_doc.rate - child_doc.price_list_rate,
                        child_doc.precision("margin_rate_or_amount"))
                    child_doc.rate_with_margin = child_doc.rate
                else:
                    child_doc.discount_percentage = flt((1 - flt(child_doc.rate) / flt(child_doc.price_list_rate)) * 100.0,
                        child_doc.precision("discount_percentage"))
                    child_doc.discount_amount = flt(child_doc.price_list_rate) - flt(child_doc.rate)

                    child_doc.margin_type = ""
                    child_doc.margin_rate_or_amount = 0
                    child_doc.rate_with_margin = 0


            child_doc.flags.ignore_validate_update_after_submit = True
            child_doc.save()
        else:
            frappe.throw("Not Permitted to change Item Group")
    # parent.db_set("payment_terms_template", payment_terms_template_si)
    set_tax_paid_on_parent(parent, tax_paid, tax_paid_from_si)
    set_payment_terms_on_parent(parent, payment_terms_template_si)
    if comment :
        comment_doc = frappe.new_doc("Comment")
        comment_doc.comment_type = "Info"
        comment_doc.comment_email = frappe.session.user
        comment_doc.reference_doctype = "Sales Invoice"
        comment_doc.reference_name = parent_doctype_name

        comment_doc.content =  ":" +comment

        comment_doc.save()
    parent.calculate_taxes_and_totals()


    parent_doctype= "Sales Invoice"
    parent.reload()
    parent.flags.ignore_validate_update_after_submit = True
    parent.flags.ignore_permissions = True
    parent.set_qty_as_per_stock_uom()
    parent.calculate_taxes_and_totals()
    if parent_doctype == "Sales Invoice":
        parent.set_gross_profit()
    parent.calculate_taxes_and_totals()
    parent.save()
    
    # parent.update_blanket_order()
    # parent.update_billing_percentage()
    # parent.set_status()


@frappe.whitelist()
def update_child_price_delivery_note(tax_paid, tax_paid_from_si, parent_doctype, trans_items, parent_doctype_name, payment_terms_template_si, child_docname="items"):
    data = json.loads(trans_items)
    parent = frappe.get_doc(parent_doctype, parent_doctype_name)
    price_dict={}
    discount_dict={}
    sqf_dict={}
    item_group_list=[]
    for item in data:
        key=(item.get("item_group") ,item.get("tile_quality"))
        if key not in item_group_list:
            item_group_list.append(key)
    for item in data:
        key=(item.get("item_group") ,item.get("tile_quality") )
        if key not in price_dict.keys():
            price_dict[key]=item.get("rate")
    for item in data:
        key=(item.get("item_group") ,item.get("tile_quality"))
        if key not in sqf_dict.keys():
            sqf_dict[key]=item.get("sqf_rate")
    for item in data:
        key=(item.get("item_group") ,item.get("tile_quality"))
        if key not in discount_dict.keys():
            discount_dict[key]=item.get("discount_rate")
            
    comment = ''
    parent_table= frappe.db.get_all("Delivery Note Item",{'parent':parent_doctype_name})
    for child_item in parent_table:
        child_doc=frappe.get_doc("Delivery Note Item", child_item)
        if (child_doc.item_group,child_doc.tile_quality) in item_group_list:
            if item.get('rate') != child_doc.rate:
                comment += f"Rate Changed in Item Group: {item.get('item_group')} , "
            if item.get('sqf_rate') != child_doc.sqf_rate :
                comment += f"SQF Rate Changed for Item Goups: {item.get('item_group')} , "
            if item.get('discount_rate') != child_doc.discounted_rate :
                comment += f"Discounted Rate Changed for Item Goups: {item.get('item_group')} , "
            # if item.get('item_group') != child_doc.item_code:
            # 	comment += f""" Item Change From {frappe.bold(child_doc.item_code)} to {item.get('item_group')}. """
                # href='{get_url_to_form("Item Group", child_doc.item_group)}'
                # href='{frappe.bold(get_url_to_form("Item Group", item.get("item_group")))}'
            key=(item.get("item_group") ,item.get("tile_quality") )
            if key not in item_group_list:
                item_group_list.append(key)

            if not flt(price_dict.get((child_doc.item_group,child_doc.tile_quality))):
                    price_dict[(child_doc.item_group,child_doc.tile_quality)] = child_doc.rate
            precision = child_doc.precision("rate") or 2

            # if flt(child_doc.billed_amt, precision) > flt(flt(price_dict[child_doc.item_group]) * flt(child_doc.get("qty")), precision):
            # 	frappe.throw(_("Row #{0}: Cannot set Rate if amount is greater than billed amount for Item {1}.")
            # 				.format(child_doc.idx, child_doc.item_code))
            # else:
            child_doc.sqf_rate = flt(sqf_dict[(child_doc.item_group,child_doc.tile_quality)])
            if child_doc.sqf_rate:
                sqf_calculation=frappe.db.get_value("Item Group",child_doc.item_group,'sqf_calculation')
                child_doc.rate = flt(sqf_dict[(child_doc.item_group,child_doc.tile_quality)] * (sqf_calculation or 15.5))
            else:
                child_doc.rate = flt(price_dict[(child_doc.item_group,child_doc.tile_quality)])
            child_doc.discounted_rate = flt(discount_dict[(child_doc.item_group,child_doc.tile_quality)])

            if price_dict[(child_doc.item_group,child_doc.tile_quality)]:
                child_doc.rate = flt(price_dict[(child_doc.item_group,child_doc.tile_quality)])
            if discount_dict[(child_doc.item_group,child_doc.tile_quality)]:
                child_doc.discount_amount=flt(discount_dict[(child_doc.item_group,child_doc.tile_quality)])
            
            child_doc.discounted_amount = child_doc.real_qty * child_doc.discounted_rate
            child_doc.discounted_net_amount = child_doc.discounted_amount

            if flt(child_doc.price_list_rate):
                if flt(child_doc.rate) > flt(child_doc.price_list_rate):
                    #  if rate is greater than price_list_rate, set margin
                    #  or set discount
                    child_doc.discount_percentage = 0

                    child_doc.margin_type = "Amount"
                    child_doc.margin_rate_or_amount = flt(child_doc.rate - child_doc.price_list_rate,
                        child_doc.precision("margin_rate_or_amount"))
                    child_doc.rate_with_margin = child_doc.rate
                else:
                    child_doc.discount_percentage = flt((1 - flt(child_doc.rate) / flt(child_doc.price_list_rate)) * 100.0,
                        child_doc.precision("discount_percentage"))
                    child_doc.discount_amount = flt(child_doc.price_list_rate) - flt(child_doc.rate)

                    child_doc.margin_type = ""
                    child_doc.margin_rate_or_amount = 0
                    child_doc.rate_with_margin = 0


            child_doc.flags.ignore_validate_update_after_submit = True
            child_doc.save()
        else:
            frappe.throw("Not Permitted to change Item Group")
    for row in parent.items:
        row.image = None
    # parent.db_set("payment_terms_template", payment_terms_template_si)
    set_tax_paid_on_parent(parent, tax_paid, tax_paid_from_si)
    set_payment_terms_on_parent(parent, payment_terms_template_si)
    if comment :
        comment_doc = frappe.new_doc("Comment")
        comment_doc.comment_type = "Info"
        comment_doc.comment_email = frappe.session.user
        comment_doc.reference_doctype = "Delivery Note"
        comment_doc.reference_name = parent_doctype_name

        comment_doc.content =  ":" +comment

        comment_doc.save()

    parent.calculate_taxes_and_totals()


    parent_doctype= "Delivery Note"
    parent.reload()
    parent.flags.ignore_validate_update_after_submit = True
    parent.flags.ignore_permissions = True
    parent.set_qty_as_per_stock_uom()
    parent.calculate_taxes_and_totals()
    if parent_doctype == "Delivery Note":
        parent.set_gross_profit()
    parent.calculate_taxes_and_totals()
    parent.save()
    # parent.update_blanket_order()
    # parent.update_billing_percentage()
    # parent.set_status()


@frappe.whitelist()
def update_child_qty_rate(parent_doctype, trans_items, parent_doctype_name, child_docname="items"):
    data = json.loads(trans_items)

    sales_doctypes = ['Sales Order', 'Sales Invoice', 'Delivery Note', 'Quotation']
    parent = frappe.get_doc(parent_doctype, parent_doctype_name)

    validate_and_delete_children(parent, data)

    for d in data:
        new_child_flag = False
        if not d.get('item_code'):
            frappe.throw("Please Enter Item Code Properly.")
            
        if not d.get("docname"):
            new_child_flag = True
            child_doctype = "Sales Order Item" if parent_doctype == "Sales Order" else "Purchase Order Item" 
            child_item = set_order_defaults(parent_doctype, parent_doctype_name, child_doctype, child_docname, d)
            # if parent_doctype == "Sales Order":
            # 	child_item  = set_sales_order_defaults(parent_doctype, parent_doctype_name, child_docname, d)
            # if parent_doctype == "Purchase Order":
            # 	child_item = set_purchase_order_defaults(parent_doctype, parent_doctype_name, child_docname, d)
        else:
            child_item = frappe.get_doc(parent_doctype + ' Item', d.get("docname"))
            
            if child_item.item_code != d.get("item_code"):
                frappe.throw("Please delete old item row and add new row for item change")

            if child_item.item_code == d.get("item_code") and (not d.get("rate") or flt(child_item.get("rate")) == flt(d.get("rate"))) and flt(child_item.get("qty")) == flt(d.get("qty")) and flt(child_item.get("discounted_rate")) == flt(d.get("discounted_rate")) and flt(child_item.get("real_qty")) == flt(d.get("real_qty")) and flt(child_item.get("sqf_rate")) == flt(d.get("sqf_rate")):
                continue

        comment = ''
        
        if d.get('item_code') != child_item.item_code:
            comment += f""" Item Change From <a href='{get_url_to_form("Item", child_item.item_code)}'>{frappe.bold(child_item.item_code)}</a> to <a href='{frappe.bold(get_url_to_form("Item", d.get("item_code")))}'>{d.get('item_code')}.</a>"""
        if d.get('qty') != child_item.qty:
            comment += f" Qty Change From {child_item.qty} to {d.get('qty')}."
        if d.get('rate') != child_item.rate or d.get('discounted_rate') != child_item.discounted_rate:
            comment += f" Rate Changed in Item: {d.get('item_code')}"
        if d.get('sqf_rate') != child_item.sqf_rate or d.get('discounted_rate') != child_item.discounted_rate:
            comment += f"SQF Rate Changed in Item: {d.get('item_code')}"

        if parent_doctype == "Sales Order" and flt(d.get("qty")) < flt(child_item.delivered_qty):
            frappe.throw(_("Cannot set quantity less than delivered quantity"))

        if parent_doctype == "Purchase Order" and flt(d.get("qty")) < flt(child_item.received_qty):
            frappe.throw(_("Cannot set quantity less than received quantity"))
        
        # if parent_doctype == "Sales Order" and flt(d.get("real_qty")) < flt(child_item.delivered_real_qty):
        # 	frappe.throw(_("Cannot set real quantity less than delivered real quantity"))

        # if parent_doctype == "Sales Order" and (flt(d.get("real_qty")) - flt(child_item.delivered_real_qty)) > (flt(d.get("qty")) - flt(child_item.delivered_qty)):
        # 	frappe.throw(_("Real Qty difference cannot be grater than Qty difference"))

        if parent_doctype == "Sales Order" and d.get("item_code") != child_item.item_code and child_item.delivered_qty:
            frappe.throw(_("Cannot change item as delivery note is already made"))

        if parent_doctype == "Sales Order" and (d.get("rate") or d.get("discounted_rate")):
            if (
                (d.get("rate") and flt(d.get("rate")) != child_item.rate and child_item.delivered_qty)
                or 
                (d.get("discounted_rate") and (flt(d.get("discounted_rate")) != child_item.discounted_rate) and child_item.delivered_qty)
            ):
                frappe.throw(_("Cannot change rate as delivery note is already made"))
        
        # if parent_doctype == "Sales Order" and flt(d.get("qty")) != flt(child_item.qty) and child_item.delivered_qty:
        # 	frappe.throw(_("Cannot change qty as delivery note is already made"))
        item_name, item_group, description,tile_quality = frappe.db.get_value("Item", d.get("item_code"), ["item_name","item_group","description","tile_quality"])
        child_item.qty = flt(d.get("qty"))
        child_item.item_name = item_name
        child_item.item_group = item_group
        child_item.description = description or item_name
        child_item.tile_quality = tile_quality
        child_item.parent_item_group = frappe.db.get_value("Item Group",item_group,"parent_item_group")
        if parent_doctype == "Sales Order":
            packing_type = frappe.db.get_value("Company",parent.company,"custom_default_packing_type")
            if packing_type and not child_item.packing_type:
                child_item.packing_type=packing_type
        child_item.real_qty = flt(d.get("qty"))
        child_item.sqf_rate = flt(d.get("sqf_rate"))
        precision = child_item.precision("rate") or 2

        
        if parent_doctype == "Sales Order" and d.get("item_code") != child_item.item_code:
            for picked_item in frappe.get_all("Pick List Item", {'sales_order':child_item.parent, 'sales_order_item':child_item.name}):
                pl = frappe.get_doc("Pick List Item", picked_item.name)

                user = frappe.get_doc("User",frappe.session.user)
                role_list = [r.role for r in user.roles]
                if frappe.db.get_value("Sales Order",child_item.parent,'lock_picked_qty'):
                    dispatch_person_user = frappe.db.get_value("Sales Person",frappe.db.get_value("Sales Order",child_item.parent,'dispatch_person'),'user')
                    if dispatch_person_user:
                        if user.name != dispatch_person_user and 'Local Admin' not in role_list and 'Sales Head' not in role_list:
                            frappe.throw("Only {} is allowed to unpick".format(dispatch_person_user))
                pl.cancel()
                pl.delete()
            
                unpick_qty_comment(pl.parent, child_item.parent, f"Unpicked full Qty from item {child_item.item_code}")
                        
            child_item.picked_qty = 0
            frappe.msgprint(_(f"All Pick List For Item {child_item.item_code} has been deleted."))

        if parent_doctype == "Sales Order" and (flt(d.get("qty")) < flt(child_item.picked_qty) and d.get("item_code") == child_item.item_code):
            diff_qty = flt(child_item.picked_qty) - flt(d.get("qty"))
            unpick_item(child_item.parent, child_item.name, sales_order_differnce_qty = diff_qty)
            
            child_item.picked_qty = child_item.picked_qty - diff_qty
        
        if not flt(d.get('rate')):
            d['rate'] = child_item.rate

        
        if flt(child_item.billed_amt, precision) > flt(flt(d.get("rate")) * flt(d.get("qty")), precision):
            frappe.throw(_("Row #{0}: Cannot set Rate if amount is greater than billed amount for Item {1}.")
                         .format(child_item.idx, child_item.item_code))
        else:
            child_item.sqf_rate = flt(d.get("sqf_rate"))
            if child_item.sqf_rate:
                sqf_calculation=frappe.db.get_value("Item Group",child_item.item_group,'sqf_calculation')
                child_item.rate = flt(d.get("sqf_rate") * (sqf_calculation or 15.5))
            else:
                child_item.rate = flt(d.get("rate"))
            child_item.discounted_rate = flt(d.get("discounted_rate"))
        child_item.item_code = d.get('item_code')
        
        
        child_item.discounted_amount = child_item.real_qty * child_item.discounted_rate
        child_item.discounted_net_amount = child_item.discounted_amount
        if flt(child_item.price_list_rate):
            if flt(child_item.rate) > flt(child_item.price_list_rate):
                #  if rate is greater than price_list_rate, set margin
                #  or set discount
                child_item.discount_percentage = 0

                if parent_doctype in sales_doctypes:
                    child_item.margin_type = "Amount"
                    child_item.margin_rate_or_amount = flt(child_item.rate - child_item.price_list_rate,
                        child_item.precision("margin_rate_or_amount"))
                    child_item.rate_with_margin = child_item.rate
            else:
                child_item.discount_percentage = flt((1 - flt(child_item.rate) / flt(child_item.price_list_rate)) * 100.0,
                    child_item.precision("discount_percentage"))
                child_item.discount_amount = flt(
                    child_item.price_list_rate) - flt(child_item.rate)

                if parent_doctype in sales_doctypes:
                    child_item.margin_type = ""
                    child_item.margin_rate_or_amount = 0
                    child_item.rate_with_margin = 0

        child_item.flags.ignore_validate_update_after_submit = True
        if new_child_flag:
            child_item.idx = len(parent.items) + 1
            child_item.insert()
        else:
            child_item.save()

        if comment and not new_child_flag:
            comment_doc = frappe.new_doc("Comment")
            comment_doc.comment_type = "Info"
            comment_doc.comment_email = frappe.session.user
            comment_doc.reference_doctype = "Sales Order"
            comment_doc.reference_name = child_item.parent

            comment_doc.content = f" changed Row: {child_item.idx}" + comment

            comment_doc.save()



    parent.reload()
    parent.flags.ignore_validate_update_after_submit = True
    parent.flags.ignore_permissions = True
    parent.set_qty_as_per_stock_uom()
    parent.calculate_taxes_and_totals()
    if parent_doctype == "Sales Order":
        parent.set_gross_profit()
    frappe.get_doc('Authorization Control').validate_approving_authority(parent.doctype,
        parent.company, parent.base_grand_total)

    parent.set_payment_schedule()
    if parent_doctype == 'Purchase Order':
        parent.validate_minimum_order_qty()
        parent.validate_budget()
        if parent.is_against_so():
            parent.update_status_updater()
    else:
        parent.check_credit_limit()
    parent.save()

    if parent_doctype == 'Purchase Order':
        update_last_purchase_rate(parent, is_submit = 1)
        parent.update_prevdoc_status()
        parent.update_requested_qty()
        parent.update_ordered_qty()
        parent.update_ordered_and_reserved_qty()
        parent.update_receiving_percentage()
        if parent.is_subcontracted == "Yes":
            parent.update_reserved_qty_for_subcontract()
    else:
        parent.update_reserved_qty()
        parent.update_project()
        parent.update_prevdoc_status('submit')
        parent.update_delivery_status()

    parent.update_blanket_order()
    parent.update_billing_percentage()
    parent.set_status()



@frappe.whitelist()
def update_child_rate(customer, trans_items, parent_doctype, parent_doctype_name, child_docname = "items"):
    data = json.loads(trans_items)
    parent = frappe.get_doc(parent_doctype, parent_doctype_name)

    price_dict={}
    quo_price_dict={}
    qo_date_dict = {}
    item_group_list=[]
    quo_item_group_list = []
    qo_list = []
    qo_pt_dict = {}
    qo_sqf_dict = {}
    doctype = "Quotation"

    for item in data:	
        if item.get("item_group") not in price_dict.keys():
            price_dict[item.get("item_group")]=item.get("custom_rate")
            item_group_list.append(item.get("item_group"))

        qo_data = frappe.db.sql(f""" 
            SELECT 
                qo.name, qo.transaction_date, qoi.item_group, qoi.rate, qoi.sqf_rate
            FROM
                `tabQuotation` as qo
            LEFT JOIN
                `tabQuotation Item` as qoi ON qoi.parent = qo.name
            WHERE
                qo.docstatus = 1 AND
                qo.party_name = '{customer}' AND
                qoi.item_group = '{item.get("item_group")}'
            ORDER BY
                qo.transaction_date DESC
        """, as_dict = 1)

        if qo_data:
            qo_list.append(qo_data[0])
    
    if qo_list:
        for qo in qo_list:
            latest_qo_doc = frappe.get_doc("Quotation", qo.name)	

            tax_paid_from_qo = latest_qo_doc.tax_paid
            payment_terms_template_qo = latest_qo_doc.payment_terms_template
            # date_list.append(latest_si_doc.posting_date)

            for row in latest_qo_doc.items:
                if row.get("item_group") not in quo_price_dict.keys():
                    quo_price_dict[row.get("item_group")]=row.get("rate")
                    qo_date_dict[row.get('item_group')] = latest_qo_doc.transaction_date
                    qo_pt_dict[row.get('item_group')] = latest_qo_doc.payment_terms_template
                    qo_sqf_dict[row.get('item_group')] = row.get("sqf_rate")
                    quo_item_group_list.append(item.get("item_group"))
        return {'quo_price_dict': quo_price_dict, 'tax_paid_from_qo': tax_paid_from_qo, 'qo_date_dict': qo_date_dict, "payment_terms_template_qo": payment_terms_template_qo, "qo_sqf_dict": qo_sqf_dict}

    else:
        frappe.throw("Quotation not found.")
    # latest_quotation = frappe.get_all(
    #     doctype,
    #     fields=["name", "creation"],
    #     filters={"party_name": customer },  # Filter to get only submitted quotations
    #     order_by="creation DESC",  # Sort by creation date in descending order (latest first)
    #     limit_page_length=1,  # Get only the top 1 record (latest)
    # )
    # if latest_quotation:
    # 	latest_quotation_doc = frappe.get_doc("Quotation", latest_quotation[0].name)
    # 	tax_paid = latest_quotation_doc.tax_paid
    # 	date = latest_quotation_doc.transaction_date
    # 	payment_terms_template_qo = latest_quotation_doc.payment_terms_template

    # 	for row in latest_quotation_doc.items:
    # 		if row.get("item_group") not in quo_price_dict.keys():
    # 			quo_price_dict[row.get("item_group")]=row.get("custom_rate")
    # 			qo_date_dict[row.get("item_group")] = latest_si_doc.
    # 			quo_item_group_list.append(item.get("item_group"))

    # 	return {'quo_price_dict': quo_price_dict, 'tax_paid': tax_paid, 'date': date, 'payment_terms_template_qo': payment_terms_template_qo}
    # else: 
    # 	frappe.throw("Quotation is not found.")


# @frappe.whitelist()
# def update_child_rate(customer, trans_items, parent_doctype, parent_doctype_name, child_docname = "items"):
#     data = json.loads(trans_items)
#     parent = frappe.get_doc(parent_doctype, parent_doctype_name)

#     price_dict={}
#     quo_price_dict={}
#     qo_date_dict = {}
#     item_group_list=[]
#     quo_item_group_list = []
#     qo_list = []
#     qo_pt_dict = {}
#     qo_sqf_dict = {}
#     doctype = "Quotation"

#     for item in data:	
#         if item.get("item_group") not in price_dict.keys():
#             price_dict[item.get("item_group")]=item.get("custom_rate")
#             item_group_list.append(item.get("item_group"))

#         qo_data = frappe.db.sql(f""" 
#             SELECT 
#                 qo.name, qo.transaction_date, qoi.item_group, qoi.rate, qoi.sqf_rate
#             FROM
#                 `tabQuotation` as qo
#             LEFT JOIN
#                 `tabQuotation Item` as qoi ON qoi.parent = qo.name
#             WHERE
#                 qo.docstatus = 1 AND
#                 qo.party_name = '{customer}' AND
#                 qoi.item_group = '{item.get("item_group")}'
#             ORDER BY
#                 qo.transaction_date DESC
#         """, as_dict = 1)

#         if qo_data:
#             qo_list.append(qo_data[0])
    
#     if qo_list:
#         for qo in qo_list:
#             latest_qo_doc = frappe.get_doc("Quotation", qo.name)	

#             tax_paid_from_qo = latest_qo_doc.tax_paid
#             payment_terms_template_qo = latest_qo_doc.payment_terms_template
#             # date_list.append(latest_si_doc.posting_date)

#             for row in latest_qo_doc.items:
#                 if row.get("item_group") not in quo_price_dict.keys():
#                     quo_price_dict[row.get("item_group")]=row.get("rate")
#                     qo_date_dict[row.get('item_group')] = latest_qo_doc.transaction_date
#                     qo_pt_dict[row.get('item_group')] = latest_qo_doc.payment_terms_template
#                     qo_sqf_dict[row.get('item_group')] = row.get("sqf_rate")
#                     quo_item_group_list.append(item.get("item_group"))
#         return {'quo_price_dict': quo_price_dict, 'tax_paid_from_qo': tax_paid_from_qo, 'qo_date_dict': qo_date_dict, "payment_terms_template_qo": payment_terms_template_qo, "qo_sqf_dict": qo_sqf_dict}

#     else:
#         frappe.throw("Quotation not found.")
    # latest_quotation = frappe.get_all(
    #     doctype,
    #     fields=["name", "creation"],
    #     filters={"party_name": customer },  # Filter to get only submitted quotations
    #     order_by="creation DESC",  # Sort by creation date in descending order (latest first)
    #     limit_page_length=1,  # Get only the top 1 record (latest)
    # )
    # if latest_quotation:
    # 	latest_quotation_doc = frappe.get_doc("Quotation", latest_quotation[0].name)
    # 	tax_paid = latest_quotation_doc.tax_paid
    # 	date = latest_quotation_doc.transaction_date
    # 	payment_terms_template_qo = latest_quotation_doc.payment_terms_template

    # 	for row in latest_quotation_doc.items:
    # 		if row.get("item_group") not in quo_price_dict.keys():
    # 			quo_price_dict[row.get("item_group")]=row.get("custom_rate")
    # 			qo_date_dict[row.get("item_group")] = latest_si_doc.
    # 			quo_item_group_list.append(item.get("item_group"))

    # 	return {'quo_price_dict': quo_price_dict, 'tax_paid': tax_paid, 'date': date, 'payment_terms_template_qo': payment_terms_template_qo}
    # else: 
    # 	frappe.throw("Quotation is not found.")


def get_latest_sales_invoice_name(customer, company=None, item_group=None, item_code=None, tile_quality=None):
	conditions = ["si.docstatus = 1"]
	params = {}

	if customer:
		conditions.append("si.customer = %(customer)s")
		params["customer"] = customer
	if company:
		conditions.append("si.company = %(company)s")
		params["company"] = company
	if item_group:
		conditions.append("sii.item_group = %(item_group)s")
		params["item_group"] = item_group
	if item_code:
		conditions.append("sii.item_code = %(item_code)s")
		params["item_code"] = item_code
	if tile_quality and frappe.get_meta("Sales Invoice Item").has_field("tile_quality"):
		conditions.append("sii.tile_quality = %(tile_quality)s")
		params["tile_quality"] = tile_quality

	result = frappe.db.sql(
		f"""
			SELECT si.name
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			WHERE {" AND ".join(conditions)}
			ORDER BY si.posting_date DESC, si.creation DESC
			LIMIT 1
		""",
		params,
		as_dict=True,
	)
	return result[0].name if result else None


def get_si_item_dict_key(item_group, tile_quality=None):
	if tile_quality:
		return f"{item_group}|||{tile_quality}"
	return item_group


@frappe.whitelist()
def update_rate_from_si_item(customer, trans_items, parent_doctype, parent_doctype_name, child_docname="items", company=None):
    """
    Fetch latest Sales Invoice item details filtered by customer + company.
    """
    data = json.loads(trans_items or "[]")
    # price_list_rate sqf_price_list_rate
    si_price_dict = {}
    si_date_dict = {}
    si_sqf_dict = {}
    si_disc_dict = {}
    si_basic_disc_dict = {}
    si_cmd_disc_dict = {}
    si_add_disc_dict = {}
    si_price_list_rate = {}
    si_sqf_price_list_rate = {}
    si_list = []

    for item in data:
        item_code = item.get("item_code")
        if not item_code:
            continue

        si_name = get_latest_sales_invoice_name(
            customer=customer,
            company=company,
            item_code=item_code,
        )
        if si_name:
            si_list.append({"name": si_name})

    if not si_list:
        frappe.throw("SI Rate not found.")

    tax_paid_from_si = None
    payment_terms_template = None
    selling_price_list = None

    for si in si_list:
        latest_si_doc = frappe.get_doc("Sales Invoice", si.get("name"))
        tax_paid_from_si = latest_si_doc.get("tax_paid")
        payment_terms_template = latest_si_doc.get("payment_terms_template")
        selling_price_list = latest_si_doc.get("selling_price_list")

        for row in latest_si_doc.get("items", []):
            code = row.get("item_code")
            if code and code not in si_price_dict:
                si_price_dict[code] = row.get("rate")
                si_sqf_dict[code] = row.get("sqf_rate")
                si_date_dict[code] = str(latest_si_doc.get("posting_date")) if latest_si_doc.get("posting_date") else None
                si_disc_dict[code] = row.get("discount_percentage")
                si_basic_disc_dict[code] = row.get("basic_disc")
                si_cmd_disc_dict[code] = row.get("cmd_discount")
                si_add_disc_dict[code] = row.get("additional_disc")
                si_price_list_rate[code] = row.get("price_list_rate")
                si_sqf_price_list_rate[code] = row.get("sqf_price_list_rate")


    return {
        "si_price_dict": si_price_dict,
        "si_sqf_dict": si_sqf_dict,
        "si_date_dict": si_date_dict,
        "si_disc_dict": si_disc_dict,
        "si_basic_disc_dict": si_basic_disc_dict,
        "si_cmd_disc_dict": si_cmd_disc_dict,
        "si_add_disc_dict": si_add_disc_dict,
        "tax_paid_from_si": tax_paid_from_si,
        "payment_terms_template": payment_terms_template,
        "selling_price_list":selling_price_list,
        "si_price_list_rate":si_price_list_rate,
        "si_sqf_price_list_rate":si_sqf_price_list_rate
    }


@frappe.whitelist()
def update_rate_from_si(company, customer, trans_items, parent_doctype, parent_doctype_name, child_docname="items"):
    data = json.loads(trans_items)
    si_price_dict = {}
    si_date_dict = {}
    si_sqf_dict = {}
    si_disc_dict = {}
    si_basic_disc_dict = {}
    si_cmd_disc_dict = {}
    si_add_disc_dict = {}
    si_price_list_rate = {}
    si_sqf_price_list_rate = {}
    si_price_list_dict = {}
    si_sqf_pl_dict = {}
    si_names = set()

    for item in data:
        if not item.get("item_group"):
            continue

        si_name = get_latest_sales_invoice_name(
            customer=customer,
            company=company,
            item_group=item.get("item_group"),
            tile_quality=item.get("tile_quality"),
        )
        if si_name:
            si_names.add(si_name)

    if not si_names:
        frappe.throw("SI Rate not found.")

    tax_paid_from_si = None
    payment_terms_template = None
    selling_price_list = None

    for si_name in si_names:
        latest_si_doc = frappe.get_doc("Sales Invoice", si_name)
        tax_paid_from_si = latest_si_doc.get("tax_paid")
        payment_terms_template = latest_si_doc.get("payment_terms_template")
        selling_price_list = latest_si_doc.get("selling_price_list")

        for row in latest_si_doc.items:
            item_group = row.get("item_group")
            tile_quality = row.get("tile_quality") if frappe.get_meta("Sales Invoice Item").has_field("tile_quality") else None
            key = get_si_item_dict_key(item_group, tile_quality)

            si_sqf_dict[key] = row.get("sqf_rate")
            si_price_dict[key] = row.get("rate")
            si_date_dict[key] = str(latest_si_doc.posting_date) if latest_si_doc.posting_date else None
            si_price_list_dict[key] = row.get("price_list_rate")
            si_sqf_pl_dict[key] = row.get("sqf_price_list_rate")
            si_disc_dict[row.item_code] = row.get("discount_percentage")
            si_basic_disc_dict[row.item_code] = row.get("basic_disc")
            si_cmd_disc_dict[row.item_code] = row.get("cmd_discount")
            si_add_disc_dict[row.item_code] = row.get("additional_disc")
            si_price_list_rate[row.item_code] = row.get("price_list_rate")
            si_sqf_price_list_rate[row.item_code] = row.get("sqf_price_list_rate")

    return {
        'si_price_dict': si_price_dict,
        'tax_paid_from_si': tax_paid_from_si,
        'si_date_dict': si_date_dict,
        "payment_terms_template": payment_terms_template,
        "selling_price_list": selling_price_list,
        "si_sqf_dict": si_sqf_dict,
        "si_disc_dict": si_disc_dict,
        "si_basic_disc_dict": si_basic_disc_dict,
        "si_cmd_disc_dict": si_cmd_disc_dict,
        "si_add_disc_dict": si_add_disc_dict,
        "si_price_list_rate": si_price_list_rate,
        "si_sqf_price_list_rate": si_sqf_price_list_rate,
        "si_price_list_dict": si_price_list_dict,
        "si_sqf_pl_dict": si_sqf_pl_dict,
    }



@frappe.whitelist()
def update_child_price_sales_invoice_item(parent_doctype, trans_items, parent_doctype_name,child_docname="items", items_table=None,tax_paid=None, tax_paid_from_si=None,payment_terms_template_si=None,selling_price_list_si=None):
    """
    Update Sales Invoice Item child table with selected values from dialog
    """
    if isinstance(trans_items, str):
        trans_items = json.loads(trans_items)

    parent = frappe.get_doc(parent_doctype, parent_doctype_name)

    # Map for faster lookup
    item_map = {d.get("docname"): d for d in trans_items}

    for d in parent.get(child_docname):
        if d.name in item_map:
            row = item_map[d.name]

            # ✅ update rates
            d.rate = flt(row.get("rate") or d.rate)
            d.sqf_rate = flt(row.get("sqf_rate") or d.sqf_rate)

            # ✅ update discounts
            d.basic_disc = flt(row.get("basic_disc") or d.basic_disc)
            d.cmd_discount = flt(row.get("cmd_discount") or d.cmd_discount)
            d.additional_disc = flt(row.get("additional_disc") or d.additional_disc)
            d.discount_percentage = flt(row.get("discount_percentage") or d.discount_percentage)
            d.price_list_rate = flt(row.get("price_list_rate") or d.price_list_rate)
            d.sqf_price_list_rate = flt(row.get("sqf_price_list_rate") or d.sqf_price_list_rate)

            # ✅ also update date if present
            if row.get("date"):
                d.date = row.get("date")

    # Update parent flags if needed
    if tax_paid is not None:
        parent.tax_paid = tax_paid
    if tax_paid_from_si is not None:
        parent.tax_paid_from_si = tax_paid_from_si
    if payment_terms_template_si:
        parent.payment_terms_template = payment_terms_template_si
    if selling_price_list_si:
        parent.selling_price_list = selling_price_list_si

    parent.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success"}
