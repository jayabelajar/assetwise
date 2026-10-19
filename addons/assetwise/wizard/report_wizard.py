from odoo import fields, models, _
from odoo.exceptions import ValidationError


class AssetWiseReportWizard(models.TransientModel):
    _name = "assetwise.report.wizard"
    _description = "AssetWise Report Filters"
    _check_company_auto = True

    report_type = fields.Selection(
        [
            ("inventory", "Asset Inventory"),
            ("assignment", "Assignment History"),
            ("maintenance", "Maintenance History"),
            ("depreciation", "Depreciation Summary"),
        ],
        required=True,
        default=lambda self: self.env.context.get("default_report_type", "inventory"),
    )
    date_from = fields.Date()
    date_to = fields.Date()
    category_id = fields.Many2one("assetwise.category", check_company=True)
    location = fields.Char()
    asset_status = fields.Selection(
        [
            ("available", "Available"),
            ("assigned", "Assigned"),
            ("maintenance", "Maintenance"),
            ("disposed", "Disposed"),
        ]
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )

    def action_print(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError(_("Start date cannot be after end date."))
        report_ids = {
            "inventory": "assetwise.action_report_inventory",
            "assignment": "assetwise.action_report_assignment",
            "maintenance": "assetwise.action_report_maintenance",
            "depreciation": "assetwise.action_report_depreciation",
        }
        data = {
            "assetwise_report_type": self.report_type,
            "date_from": fields.Date.to_string(self.date_from) if self.date_from else False,
            "date_to": fields.Date.to_string(self.date_to) if self.date_to else False,
            "category_id": self.category_id.id or False,
            "location": self.location or False,
            "asset_status": self.asset_status or False,
            "company_id": self.company_id.id,
        }
        return self.env.ref(report_ids[self.report_type]).report_action(self, data=data)
