from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class AssetWiseAsset(models.Model):
    _name = "assetwise.asset"
    _description = "Company Asset"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code desc"
    _check_company_auto = True

    code = fields.Char(
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        index=True,
        tracking=True,
    )
    name = fields.Char(required=True, index=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    category_id = fields.Many2one(
        "assetwise.category", required=True, index=True, check_company=True, tracking=True
    )
    serial_number = fields.Char(index=True, tracking=True)
    description = fields.Html()
    purchase_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    purchase_value = fields.Monetary(
        string="Acquisition Cost", required=True, default=0.0, tracking=True
    )
    vendor_id = fields.Many2one("res.partner")
    location = fields.Char(required=True, index=True, tracking=True)
    responsible_user_id = fields.Many2one(
        "res.users", string="Asset Custodian", index=True, tracking=True
    )
    condition = fields.Selection(
        [
            ("excellent", "Excellent"),
            ("good", "Good"),
            ("fair", "Fair"),
            ("damaged", "Damaged"),
        ],
        required=True,
        default="good",
        index=True,
        tracking=True,
    )
    status = fields.Selection(
        [
            ("available", "Available"),
            ("assigned", "Assigned"),
            ("maintenance", "Maintenance"),
            ("disposed", "Disposed"),
        ],
        required=True,
        default="available",
        readonly=True,
        index=True,
        tracking=True,
    )
    warranty_expiration = fields.Date(tracking=True)
    notes = fields.Text()
    image_1920 = fields.Image(max_width=1920, max_height=1920)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    assignment_ids = fields.One2many("assetwise.assignment", "asset_id")
    maintenance_ids = fields.One2many("assetwise.maintenance", "asset_id")
    assignment_count = fields.Integer(compute="_compute_history_counts")
    maintenance_count = fields.Integer(compute="_compute_history_counts")

    residual_value = fields.Monetary(required=True, default=0.0)
    useful_life_years = fields.Integer(
        string="Useful Life (Years)", required=True, default=5
    )
    depreciation_start_date = fields.Date()
    annual_depreciation = fields.Monetary(compute="_compute_depreciation")
    accumulated_depreciation = fields.Monetary(compute="_compute_depreciation")
    estimated_book_value = fields.Monetary(compute="_compute_depreciation")

    _code_unique = models.Constraint("UNIQUE(code)", "Asset code must be unique.")
    _purchase_value_nonnegative = models.Constraint(
        "CHECK(purchase_value >= 0)", "Acquisition cost cannot be negative."
    )
    _residual_value_nonnegative = models.Constraint(
        "CHECK(residual_value >= 0)", "Residual value cannot be negative."
    )
    _useful_life_positive = models.Constraint(
        "CHECK(useful_life_years > 0)", "Useful life must be greater than zero."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == _("New"):
                vals["code"] = self.env["ir.sequence"].next_by_code("assetwise.asset") or _("New")
        return super().create(vals_list)

    def write(self, vals):
        if "status" in vals and not self.env.context.get("assetwise_workflow"):
            raise UserError(_("Asset status can only be changed through an AssetWise workflow action."))
        if "active" in vals and not self.env.user.has_group("assetwise.group_assetwise_admin"):
            raise AccessError(_("Only AssetWise administrators can archive or restore assets."))
        return super().write(vals)

    @api.constrains("residual_value", "purchase_value")
    def _check_residual_value(self):
        for asset in self:
            if asset.residual_value > asset.purchase_value:
                raise ValidationError(_("Residual value cannot exceed acquisition cost."))

    @api.constrains("responsible_user_id", "company_id")
    def _check_responsible_user_company(self):
        for asset in self:
            if (
                asset.responsible_user_id
                and asset.company_id not in asset.responsible_user_id.company_ids
            ):
                raise ValidationError(_("The responsible user must have access to the asset company."))

    @api.depends(
        "purchase_value", "residual_value", "useful_life_years", "depreciation_start_date"
    )
    def _compute_depreciation(self):
        today = fields.Date.context_today(self)
        for asset in self:
            depreciable = max(asset.purchase_value - asset.residual_value, 0.0)
            annual = depreciable / asset.useful_life_years if asset.useful_life_years else 0.0
            elapsed_years = 0.0
            if asset.depreciation_start_date and asset.depreciation_start_date < today:
                elapsed_years = min(
                    (today - asset.depreciation_start_date).days / 365.0,
                    float(asset.useful_life_years),
                )
            accumulated = min(annual * elapsed_years, depreciable)
            asset.annual_depreciation = annual
            asset.accumulated_depreciation = accumulated
            asset.estimated_book_value = max(
                asset.purchase_value - accumulated, asset.residual_value
            )

    @api.depends("assignment_ids", "maintenance_ids")
    def _compute_history_counts(self):
        assignment_rows = self.env["assetwise.assignment"]._read_group(
            [("asset_id", "in", self.ids)], ["asset_id"], ["__count"]
        )
        maintenance_rows = self.env["assetwise.maintenance"]._read_group(
            [("asset_id", "in", self.ids)], ["asset_id"], ["__count"]
        )
        assignment_counts = {asset.id: count for asset, count in assignment_rows}
        maintenance_counts = {asset.id: count for asset, count in maintenance_rows}
        for asset in self:
            asset.assignment_count = assignment_counts.get(asset.id, 0)
            asset.maintenance_count = maintenance_counts.get(asset.id, 0)

    def action_dispose(self):
        if not self.env.user.has_group("assetwise.group_assetwise_admin"):
            raise AccessError(_("Only AssetWise administrators can dispose assets."))
        for asset in self:
            if asset.status != "available":
                raise UserError(_("Only available assets can be disposed."))
        self.with_context(assetwise_workflow=True).write({"status": "disposed"})
        self.message_post(body=_("Asset disposed by %s.") % self.env.user.display_name)
        return True

    def unlink(self):
        raise UserError(_("Assets cannot be deleted. Archive them to preserve operational history."))

    def action_open_assignments(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("assetwise.action_assetwise_assignment")
        action["domain"] = [("asset_id", "=", self.id)]
        action["context"] = {"default_asset_id": self.id}
        return action

    def action_open_maintenance(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("assetwise.action_assetwise_maintenance")
        action["domain"] = [("asset_id", "=", self.id)]
        action["context"] = {"default_asset_id": self.id}
        return action
