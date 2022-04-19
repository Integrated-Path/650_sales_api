from odoo import models, fields, api

class ResPartner(models.Model):
	_inherit = "sale.order"

	cashier = fields.Char("Cashier", readonly=True, copy=False)