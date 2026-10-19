from odoo import fields, models


class AssetWiseReturnWizard(models.TransientModel):
    _name = "assetwise.return.wizard"
    _description = "Return Asset"

    assignment_id = fields.Many2one("assetwise.assignment", required=True, readonly=True)
    return_date = fields.Date(required=True, default=fields.Date.context_today)
    return_condition = fields.Selection(
        [
            ("excellent", "Excellent"),
            ("good", "Good"),
            ("fair", "Fair"),
            ("damaged", "Damaged"),
        ],
        required=True,
        default="good",
    )
    return_notes = fields.Text()

    def action_confirm(self):
        self.ensure_one()
        self.assignment_id.with_context(
            return_date=self.return_date,
            return_condition=self.return_condition,
            return_notes=self.return_notes,
        ).action_return()
        return {"type": "ir.actions.act_window_close"}
