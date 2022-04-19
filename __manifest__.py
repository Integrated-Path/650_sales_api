# Copyright 2018 ACSONE SA/NV
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    "name": "Sale Rest API",
    "version": "13.1",
    "license": "LGPL-3",
    "author": "Integrated Path",
    "website": "https://www.int-path.com",
    "depends": ["base_rest", "component", "contacts", "sale_management", "stock"],
    "data": [
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
    ],
    "external_dependencies": {"python": ["jsondiff"]},
}
