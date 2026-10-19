from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AssetWiseCategory(models.Model):
    _name = "assetwise.category"
    _description = "Asset Category"
    _order = "name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    asset_count = fields.Integer(compute="_compute_asset_count")

    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        "The category code must be unique per company.",
    )

    @api.depends("company_id")
    def _compute_asset_count(self):
        grouped = self.env["assetwise.asset"]._read_group(
            [("category_id", "in", self.ids)], ["category_id"], ["__count"]
        )
        counts = {category.id: count for category, count in grouped}
        for category in self:
            category.asset_count = counts.get(category.id, 0)

    def unlink(self):
        if self.env["assetwise.asset"].with_context(active_test=False).search_count(
            [("category_id", "in", self.ids)]
        ):
            raise UserError(_("Categories used by assets cannot be deleted. Archive them instead."))
        return super().unlink()
