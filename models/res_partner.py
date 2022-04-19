from odoo import models, fields, api

class ResPartner(models.Model):
	_inherit = "res.partner"

	_sql_constraints = [
		('unique_card_number',
		'unique(card_number)',
		'Card Number Must Be Unique !')
	]

	card_number = fields.Char("Card Number", copy=False)