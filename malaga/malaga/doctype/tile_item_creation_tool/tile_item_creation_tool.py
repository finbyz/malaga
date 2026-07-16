# -*- coding: utf-8 -*-
# Copyright (c) 2024, Finbyz and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.model.rename_doc import rename_doc
from erpnext.stock.doctype.item.item import Item

class TileItemCreationTool(Document):

	def on_submit(self):
		self.create_items()

	def on_cancel(self):
		self.delete_item()

	def validate(self):
		pass

	def on_update_after_submit(self):
		for tile in self.tile_quality:
			tile_item = frappe.get_doc("Item", {'item_code': tile.item_code})
			tile_item.db_set('cover_image', self.cover_image)
			tile_item.db_set('image', self.image)
			tile_item.db_set('disabled', self.disabled)
			tile_item.db_set('punch_no', self.punch_no)

			if self.item_defaults:
				item = frappe.get_doc("Item", {'item_name': tile.item_name})
				item.item_code = item.name
				tile.db_set('item_code', item.item_code)
				item.item_defaults = []

				for i in self.item_defaults:
					item.append('item_defaults', {
						'company': i.company,
						'default_warehouse': i.default_warehouse,
						'default_price_list': i.default_price_list,
						'buying_cost_center': i.buying_cost_center,
						'default_supplier': i.default_supplier,
						'expense_account': i.expense_account,
						'selling_cost_center': i.selling_cost_center,
						'income_account': i.income_account,
					})

				if frappe.db.exists("Item Price", {'item_code': item.item_code}):
					price_list_doc = frappe.get_doc("Item Price", {'item_code': item.item_code})
					price_list_doc.price_list = self.price_list
					price_list_doc.price_list_rate = tile.production_price
					price_list_doc.save()
				else:
					price_list_doc = frappe.new_doc("Item Price")
					price_list_doc.item_code = tile.item_code
					price_list_doc.price_list = self.price_list
					price_list_doc.price_list_rate = tile.production_price
					price_list_doc.save()

				item.save()

	def create_items(self):
		tile_size_code = '-' + frappe.db.get_value('Tile Size', self.tile_size, 'size_code')
		tile_type_code = '-' + frappe.db.get_value('Tile Type', self.tile_type, 'type_code')
		tile_surface_code = '-' + frappe.db.get_value('Tile Surface', self.tile_surface, 'surface_code')
		item_group_code = frappe.db.get_value("Item Group", self.item_group, 'item_group_code')
		if item_group_code:
			item_group_code = '-' + item_group_code
		else:
			item_group_code = ''
		item_group_name = frappe.db.get_value("Item Group", self.item_group, 'item_name')
		if item_group_name:
			item_group_name = '-' + item_group_name
		else:
			item_group_name = ''

		if self.item_series and not self.is_item_series:
			for tile in self.tile_quality:
				category = '-' + tile.tile_quality
				tile_grade = '-' + frappe.db.get_value("Tile Quality", tile.tile_quality, 'tile_grade')
				if not frappe.db.exists("Item", {'item_code': self.item_design + tile_grade + item_group_code}):
					item = frappe.new_doc("Item")
				else:
					item = frappe.get_doc("Item", {'item_code': self.item_design + tile_grade + item_group_code})

				item.item_code = self.item_design + tile_grade + item_group_code
				item.item_name = self.item_design + item_group_name + category
				item.item_design = self.item_design
				item.item_series = self.item_series
				item.item_creation_tool = self.name
				item.item_group = self.item_group
				item.is_stock_item = self.maintain_stock
				item.stock_uom = self.uom

				item.is_tile = 1
				item.tile_body_composition = self.tile_body_composition
				item.tile_use = self.tile_use
				item.tile_size = self.tile_size
				item.tile_type = self.tile_type
				item.tile_surface = self.tile_surface
				item.tile_texture = self.tile_texture
				item.tile_technical = self.tile_technical
				item.tile_color = self.tile_color
				item.tile_shape = self.tile_shape
				item.tile_price = self.tile_price
				item.tile_thickness = self.tile_thickness
				item.punch_no = self.punch_no
				item.tile_anti_slip_properties = self.tile_anti_slip_properties
				item.tile_quality = tile.tile_quality
				item.cover_image = self.cover_image
				item.image = self.image
				item.authority = "Unauthorized"

				if self.show_in_website:
					if frappe.db.get_value("Tile Quality", tile.tile_quality, 'show_in_website'):
						item.show_in_website = self.show_in_website
						item.weightage = self.weightage
						item.website_image = self.website_image
						item.website_warehouse = self.website_warehouse

				if not self.is_item_series and self.maintain_stock == True:
					if not item.has_batch_no:
						item.has_batch_no = True
						item.create_new_batch = True
					item.batch_number_series = "BTH-.YY.MM.DD.-.###"

				tile.db_set('item_code', item.item_code)
				tile.db_set('item_name', item.item_name)

				if self.item_defaults:
					for i in self.item_defaults:
						item.append('item_defaults', {
							'company': i.company,
							'default_warehouse': i.default_warehouse,
							'default_price_list': i.default_price_list,
							'buying_cost_center': i.buying_cost_center,
							'default_supplier': i.default_supplier,
							'expense_account': i.expense_account,
							'selling_cost_center': i.selling_cost_center,
							'income_account': i.income_account,
						})

				item.save(ignore_permissions=True)
		else:
			for tile in self.tile_quality:
				category = '-' + tile.tile_quality
				tile_grade = '-' + frappe.db.get_value("Tile Quality", tile.tile_quality, 'tile_grade')
				item = frappe.new_doc("Item")
				item.is_item_series = 1
				item.item_code = self.item_design + tile_grade + item_group_code
				item.item_name = self.item_design + item_group_name + category
				item.item_creation_tool = self.name
				item.item_group = self.item_group
				item.stock_uom = self.uom

				item.is_tile = 1
				item.tile_body_composition = self.tile_body_composition
				item.tile_use = self.tile_use
				item.tile_size = self.tile_size
				item.tile_type = self.tile_type
				item.tile_surface = self.tile_surface
				item.tile_texture = self.tile_texture
				item.tile_technical = self.tile_technical
				item.tile_color = self.tile_color
				item.tile_shape = self.tile_shape
				item.tile_price = self.tile_price
				item.punch_no = self.punch_no
				item.tile_thickness = self.tile_thickness
				item.authority = "Authorized"
				item.tile_anti_slip_properties = self.tile_anti_slip_properties

				tile.db_set('item_code', item.item_code)
				tile.db_set('item_name', item.item_name)

				if not self.is_item_series and self.maintain_stock == True:
					if not item.has_batch_no:
						item.has_batch_no = True
						item.create_new_batch = True
					item.batch_number_series = "BTH-.YY.MM.DD.-.###"

				if self.item_defaults:
					for i in self.item_defaults:
						item.append('item_defaults', {
							'company': i.company,
							'default_warehouse': i.default_warehouse,
							'default_price_list': i.default_price_list,
							'buying_cost_center': i.buying_cost_center,
							'default_supplier': i.default_supplier,
							'expense_account': i.expense_account,
							'selling_cost_center': i.selling_cost_center,
							'income_account': i.income_account,
						})

				item.save(ignore_permissions=True)

	def delete_item(self):
		if self.tile_quality:
			item_list = [row.item_code for row in self.tile_quality]
			for row in self.tile_quality:
				if row.item_code:
					row.db_set('item_code', None)
					row.db_set('item_name', None)

			for item in item_list:
				frappe.db.set_value("Item", item, 'item_creation_tool', None)
				doc = frappe.get_doc("Item", item)
				doc.delete()


@frappe.whitelist()
def get_tile_quality():
	return [item.name for item in frappe.get_all('Tile Quality') if item.name not in ['Economy', 'Classic']]


@frappe.whitelist()
def change_item_design(doc, new_value):
	item_doc = frappe.get_doc('Tile Item Creation Tool', doc)
	if item_doc.tile_quality:
		for row in item_doc.tile_quality:
			if row.item_code:
				item = frappe.get_doc("Item", row.item_code)
				new_name = row.item_code.replace(item_doc.item_design, new_value)
				frappe.rename_doc("Item", row.item_code, new_name, ignore_permissions=True)
				item = frappe.get_doc("Item", new_name)
				item.item_name = item.item_name.replace(item_doc.item_design, new_value)
				item.item_design = new_value
				item.save()

		new_current_name = item_doc.name.replace(item_doc.item_design, new_value)
		frappe.rename_doc("Tile Item Creation Tool", item_doc.name, new_current_name, ignore_permissions=True)
		current_doc = frappe.get_doc("Tile Item Creation Tool", new_current_name)
		current_doc.db_set('item_design', new_value)
		current_doc.db_set('item_name', item_doc.item_name.replace(item_doc.item_design, new_value))
		return current_doc.name, "Item Design Changed"