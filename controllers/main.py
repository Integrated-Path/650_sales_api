# Copyright 2018 ACSONE SA/NV
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo.addons.base_rest.controllers import main


class SalesRestApi(main.RestController):
    _root_path = "/sales_api/"
    _collection_name = "sale.rest.api.collection"
    _default_auth = "user"