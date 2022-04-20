# Copyright 2018 ACSONE SA/NV
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo.addons.component.core import Component
from odoo.exceptions import UserError, MissingError

REQUIRED_CREATION_FIELDS = {"card_number", "partner_name", "smart_id", "date", "order_line", "cashier_name"}
ALLOWED_ACTIONS = {"refund"}

class SaleRestApiService(Component):
    _inherit = "base.rest.service"
    _name = "sale.rest.api.service"
    _usage = "handle"
    _collection = "sale.rest.api.collection"
    _description = """A service for creating endpoints"""

    def create_wizard_object(self, wizard_name: str, model_name: str, record_ids: list, values: dict) -> object:
        """Create & Return Wizard Model Object"""
        args = {
            "active_ids": record_ids,
            "active_model": model_name
        }
        if len(record_ids) == 1:
            args["active_id"] = record_ids[0]
        return_wizard_id = self.env[wizard_name].with_context(**args).create(values)
        return return_wizard_id

    def update(self, _id, **params):
        # ================= INTERNAL FUNCTIONS =========================
        def get_sale_order(rcd_id: int) -> object:
            sale_id = self.env["sale.order"].browse([rcd_id])
            if not sale_id:
                raise UserError(f"No Sale Orde Was Found With The Smart ID {rcd_id}")
            return sale_id
        
        def validate_action(action_name: str) -> None:
            if action_name in ALLOWED_ACTIONS:
                pass
            else:
                raise UserError(f"The Action {action_name} is not allowed")

        def covert_poducts_ids_list_to_general_line_values(product_ids: list) -> list:
            formated_values = {}
            for product_id in product_ids:
                if formated_values.get(product_id):
                    formated_values[product_id]["quantity"] += 1
                else:
                    formated_values[product_id] = {
                        "product_id": product_id,
                        "quantity": 1
                    }
            return list(formated_values.values())

        def validate_product_lines(product_lines: list, sale_id: object) -> None:
            if len(product_lines) == 0:
                raise UserError("No Product ID's were provided")
            for product_line in product_lines:
                product_int = product_line["product_id"]
                product_qty = product_line["quantity"]
                # using search() instead of browse() to handle no record found
                product_id = self.env["product.product"].search([("id", "=", product_int)])
                if len(product_id) == 0:
                    raise UserError(f"No product with ID {product_int} was found")
                line_id = sale_id.order_line.filtered(lambda x: x.product_id == product_id)
                if len(line_id) == 0:
                    raise UserError(f"The Product with ID {product_int} does not exist in registery")
                elif len(line_id) == 1:
                    if line_id.qty_delivered < product_qty:
                        raise UserError(f"You are trying to refund more quantity for product with ID {product_int}, than what it is available")
                    else:
                        pass
                else:
                    raise UserError("Something went wrong, please contact the API support (EC: 400)")


        def handle_refund_action(sale_id: object, product_lines: list) -> bool:
            process_tranfer_return(sale_id, product_lines)
            process_invoice_refund(sale_id, product_lines)
            sale_id.message_post(
                body= "The Sale Order Was Refunded",
                message_type='comment',
                subtype = 'mail.mt_note',
            )

        def process_tranfer_return(sale_id: object, product_lines: list) -> object:
            picking_ids = sale_id.picking_ids.filtered(lambda x: x.picking_type_code == "outgoing" and x.state == "done")
            refund_line_values = convert_general_product_lines_to_return_line_values(product_lines, picking_ids)
            return_wizard_id = self.create_wizard_object(
                wizard_name="stock.return.picking",
                model_name="stock.picking",
                record_ids=picking_ids.ids,
                values={
                    "location_id": picking_ids.location_id.id,
                    "product_return_moves": refund_line_values
                }
            )
            return_tranfer_int = return_wizard_id._create_returns()[0]
            # changing `return_tranfer_id` from int to recor object
            return_tranfer_id = self.env["stock.picking"].browse([return_tranfer_int])
            for stock_move in return_tranfer_id.move_lines:
                stock_move.quantity_done = stock_move.product_uom_qty
            return_tranfer_id.button_validate()
            return return_tranfer_id

        def convert_general_product_lines_to_return_line_values(product_lines: list, picking_id: object) -> list:
            return_line_values = [(0, 0, {
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "to_refund": True,
                "move_id": fetch_related_stock_move_line_for_product(picking_id, item["product_id"] )
            }) for item in product_lines]
            return return_line_values

        def fetch_related_stock_move_line_for_product(picking_id: object, product_id: int) -> object:
            move_id = picking_id.move_lines.filtered(lambda x: x.product_id.id == product_id)
            if len(move_id) == 0:
                raise UserError(f"The product ID {product_id} was not found in the sale order")
            elif len(move_id) == 1:
                return move_id.id
            else:
                raise UserError("Something went wrong, please contact the API support (EC: 200)")

        def process_invoice_refund(sale_id: object, product_lines: list) -> object:
            # ---- Invoice Refund ----
            invoice_id = sale_id.invoice_ids.filtered(lambda x: x.type == "out_invoice" and x.state == "posted" and x.invoice_payment_state == "paid")
            if len(invoice_id) == 0:
                raise UserError("Something went wrong, please contact the API support (EC: 300)")
            elif len(invoice_id) == 1:
                reverse_wizard_id = self.create_wizard_object(
                    wizard_name="account.move.reversal",
                    model_name="account.move",
                    record_ids=invoice_id.ids,
                    values={
                        "refund_method": "refund"
                    }
                )
                # This return a dictionary for odoo actions
                reverse_result = reverse_wizard_id.reverse_moves()
                refund_invoice_id = self.env["account.move"].browse([ reverse_result["res_id"] ])
                to_update_account_move_line_values = convert_product_lines_to_account_move_lines(product_lines, refund_invoice_id)
                refund_invoice_id.write({"invoice_line_ids": to_update_account_move_line_values})
                refund_invoice_id.action_post()
                payment_id = self.create_wizard_object(
                    wizard_name="account.payment",
                    model_name="account.move",
                    record_ids=refund_invoice_id.ids,
                    values={
                        "payment_type": "outbound",
                        "partner_type": "customer",
                        "partner_id": refund_invoice_id.partner_id.id,
                        "journal_id": refund_invoice_id.journal_id.id,
                        "payment_method_id": self.env.ref("account.account_payment_method_manual_in").id
                    }
                )
                payment_id.post()
                return payment_id
            else:
                raise UserError("Something went wrong, please contact the API support (EC: 100)")

        def convert_product_lines_to_account_move_lines(product_lines: list, account_move_id: object) -> list:
            product_lines_list_to_dict = {item["product_id"]: item for item in product_lines}
            move_lines_values = []
            for move_line in account_move_id.invoice_line_ids:
                if product_lines_list_to_dict.get(move_line.product_id.id):
                    format_1_qty = product_lines_list_to_dict[move_line.product_id.id]["quantity"]
                    if format_1_qty != move_line.quantity:
                        move_lines_values.append((1, move_line.id, {"quantity": format_1_qty}))
                    else:
                        pass
                else:
                    move_lines_values.append((3, move_line.id ))
            return move_lines_values

        # =====================================================

        sale_id = get_sale_order(_id)
        action = params.get("action", "")
        product_ids = params.get("product_ids", [])
        validate_action(action)
        product_lines = covert_poducts_ids_list_to_general_line_values(product_ids)
        # we are converting before validating because we need the convered value
        # to do a proper validation
        validate_product_lines(product_lines, sale_id)
        if action == "refund":
            handle_refund_action(sale_id, product_lines)
        return {"is_success": True}

    def create(self, **params):
        # ================= INTERNAL FUNCTIONS =========================
        def validate_request_data(data: dict) -> None:
            if data.keys() == REQUIRED_CREATION_FIELDS:
                pass
            else:
                raise UserError("Missing Required Fields")

        def get_or_create_partner(partner_name: str, card_number: str) -> object:
            partner_id = self.env["res.partner"].search([("card_number", "=", card_number)])
            if not partner_id:
                partner_id = self.env["res.partner"].create({
                    "name": partner_name,
                    "card_number": card_number
                })
            if partner_id.name != partner_name:
                partner_id.name = partner_name
            return partner_id
        
        def get_journal() -> object:
            journal_id = self.env["account.journal"].search([
                ('company_id', '=', self.env.company.id),
                ('type', '=', 'cash'),
            ], limit=1)
            return journal_id

        def create_and_confirm_sale_order(data: dict, partner_id: object) -> object:
            sale_id = self.env["sale.order"].create({
                "partner_id": partner_id.id,
                "origin": data["smart_id"],
                "date_order": data["date"],
                "cashier": data["cashier_name"],
                "order_line": [
                    (0, 0, {
                    "product_id": line["product"],
                    "product_uom_qty": line["quantity"],
                    "price_unit": line["unit_price"],
                    "discount": line.get("discount", 0),
                    }) for line in data["order_line"]
                ]
            })
            sale_id.action_confirm()
            return sale_id

        def create_and_confirm_transfer(sale_id: object) -> object:
            tranfer_id = sale_id.picking_ids
            tranfer_id.ensure_one()
            for stock_move in tranfer_id.move_lines:
                stock_move.quantity_done = stock_move.product_uom_qty
            tranfer_id.button_validate()
            return tranfer_id

        def create_and_confirm_invoice(sale_id: object) -> object:
            move_id = sale_id._create_invoices()
            move_id.action_post()
            return move_id

        def create_and_confirm_payment(move_id: object, partner_id: object, journal_id: object) -> object:
            move_id.ensure_one()
            payment_id = self.create_wizard_object(
                wizard_name="account.payment",
                model_name="account.move",
                record_ids=move_id.ids,
                values={
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": partner_id.id,
                    "journal_id": journal_id.id,
                    "payment_method_id": self.env.ref("account.account_payment_method_manual_in").id
                }
            )
            payment_id.post()
            return payment_id
        # =====================================================

        records = []
        for data in params.get("data", [{}]):
            validate_request_data(data)
            partner_id = get_or_create_partner(data["partner_name"], data["card_number"])
            journal_id = get_journal()
            sale_id = create_and_confirm_sale_order(data, partner_id)
            transfer_id = create_and_confirm_transfer(sale_id)
            move_id = create_and_confirm_invoice(sale_id)
            paymnet_id =  create_and_confirm_payment(move_id, partner_id, journal_id)
            records.append({
                "smart_id": data["smart_id"],
                "odoo_sale_id": sale_id.id
            })
        return {"response": records}

    def _validator_update(self):
        return {
            "action": {"type": "string"},
            "product_ids": {"type": "list"}
        }

    def _validator_return_update(self):
        return {"is_success": {"type": "boolean"}}

    def _validator_create(self):
        return {"data": {"type": "list"}}

    def _validator_return_create(self):
        return {"response": {"type": "list"}}
