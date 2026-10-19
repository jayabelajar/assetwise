from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AssetWiseMaintenance(models.Model):
    _name = "assetwise.maintenance"
    _description = "Asset Maintenance"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "scheduled_date desc, id desc"
    _check_company_auto = True

    reference = fields.Char(
        required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True
    )
    asset_id = fields.Many2one(
        "assetwise.asset", required=True, index=True, check_company=True, tracking=True
    )
    maintenance_type = fields.Selection(
        [("preventive", "Preventive"), ("corrective", "Corrective")],
        required=True,
        default="preventive",
        index=True,
        tracking=True,
    )
    description = fields.Text(required=True)
    scheduled_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    start_date = fields.Date(readonly=True, tracking=True)
    completion_date = fields.Date(readonly=True, tracking=True)
    assigned_technician_id = fields.Many2one("res.users", tracking=True)
    maintenance_cost = fields.Monetary(required=True, default=0.0, tracking=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    notes = fields.Text()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        readonly=True,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    _active_maintenance_unique = models.UniqueIndex(
        "(asset_id) WHERE state IN ('scheduled', 'in_progress')",
        "An asset can only have one active maintenance job.",
    )
    _maintenance_cost_nonnegative = models.Constraint(
        "CHECK(maintenance_cost >= 0)", "Maintenance cost cannot be negative."
    )
    _completion_after_start = models.Constraint(
        "CHECK(completion_date IS NULL OR start_date IS NULL OR completion_date >= start_date)",
        "Completion date cannot be before start date.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("reference") or vals["reference"] == _("New"):
                vals["reference"] = self.env["ir.sequence"].next_by_code(
                    "assetwise.maintenance"
                ) or _("New")
            asset = self.env["assetwise.asset"].browse(vals.get("asset_id"))
            if asset:
                if asset.status == "disposed":
                    raise UserError(_("Disposed assets cannot receive maintenance."))
                vals.setdefault("company_id", asset.company_id.id)
        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals and not self.env.context.get("assetwise_workflow"):
            raise UserError(_("Maintenance status can only be changed through workflow actions."))
        protected = self.filtered(lambda record: record.state in ("completed", "cancelled"))
        if protected and not self.env.context.get("assetwise_workflow"):
            raise UserError(_("Completed maintenance records are immutable."))
        return super().write(vals)

    def _lock_asset(self):
        self.env.cr.execute(
            "SELECT id FROM assetwise_asset WHERE id = ANY(%s) FOR UPDATE", [self.asset_id.ids]
        )

    @api.constrains("assigned_technician_id", "company_id")
    def _check_technician_company(self):
        for maintenance in self:
            if (
                maintenance.assigned_technician_id
                and maintenance.company_id not in maintenance.assigned_technician_id.company_ids
            ):
                raise ValidationError(_("The technician must have access to the maintenance company."))

    def action_schedule(self):
        for maintenance in self:
            maintenance._lock_asset()
            maintenance.asset_id.invalidate_recordset(["status"])
            if maintenance.state != "draft":
                raise UserError(_("Only draft maintenance can be scheduled."))
            if maintenance.asset_id.status != "available":
                raise UserError(_("Only available assets can enter maintenance."))
            maintenance.asset_id.with_context(assetwise_workflow=True).write(
                {"status": "maintenance"}
            )
            maintenance.with_context(assetwise_workflow=True).write({"state": "scheduled"})
        return True

    def action_start(self):
        for maintenance in self:
            if maintenance.state != "scheduled":
                raise UserError(_("Only scheduled maintenance can be started."))
            maintenance.with_context(assetwise_workflow=True).write(
                {"state": "in_progress", "start_date": fields.Date.context_today(self)}
            )
        return True

    def action_complete(self):
        for maintenance in self:
            if maintenance.state != "in_progress":
                raise UserError(_("Only maintenance in progress can be completed."))
            completion_date = fields.Date.context_today(self)
            if maintenance.start_date and completion_date < maintenance.start_date:
                raise ValidationError(_("Completion date cannot be before start date."))
            maintenance.with_context(assetwise_workflow=True).write(
                {"state": "completed", "completion_date": completion_date}
            )
            active_assignment = self.env["assetwise.assignment"].search_count(
                [("asset_id", "=", maintenance.asset_id.id), ("state", "=", "assigned")],
                limit=1,
            )
            maintenance.asset_id.with_context(assetwise_workflow=True).write(
                {"status": "assigned" if active_assignment else "available"}
            )
        return True

    def action_cancel(self):
        for maintenance in self:
            if maintenance.state not in ("draft", "scheduled"):
                raise UserError(_("Only draft or scheduled maintenance can be cancelled."))
            was_active = maintenance.state == "scheduled"
            maintenance.with_context(assetwise_workflow=True).write({"state": "cancelled"})
            if was_active:
                maintenance.asset_id.with_context(assetwise_workflow=True).write(
                    {"status": "available"}
                )
        return True

    def unlink(self):
        if any(record.state not in ("draft", "cancelled") for record in self):
            raise UserError(_("Active or completed maintenance history cannot be deleted."))
        return super().unlink()
