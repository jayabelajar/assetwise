from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AssetWiseAssignment(models.Model):
    _name = "assetwise.assignment"
    _description = "Asset Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "assignment_date desc, id desc"
    _check_company_auto = True

    reference = fields.Char(
        required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True
    )
    asset_id = fields.Many2one(
        "assetwise.asset", required=True, index=True, check_company=True, tracking=True
    )
    assigned_to_id = fields.Many2one(
        "res.users", string="Assigned To", required=True, index=True, tracking=True
    )
    assigned_by_id = fields.Many2one(
        "res.users", string="Assigned By", readonly=True, default=lambda self: self.env.user
    )
    assignment_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    expected_return_date = fields.Date(tracking=True)
    actual_return_date = fields.Date(readonly=True, tracking=True)
    received_by_id = fields.Many2one("res.users", readonly=True, tracking=True)
    return_condition = fields.Selection(
        [
            ("excellent", "Excellent"),
            ("good", "Good"),
            ("fair", "Fair"),
            ("damaged", "Damaged"),
        ],
        readonly=True,
        tracking=True,
    )
    return_notes = fields.Text(readonly=True)
    notes = fields.Text()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("assigned", "Assigned"),
            ("returned", "Returned"),
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

    _active_asset_unique = models.UniqueIndex(
        "(asset_id) WHERE state = 'assigned'",
        "An asset can only have one active assignment.",
    )
    _return_after_assignment = models.Constraint(
        "CHECK(actual_return_date IS NULL OR actual_return_date >= assignment_date)",
        "Return date cannot be before assignment date.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("reference") or vals["reference"] == _("New"):
                vals["reference"] = self.env["ir.sequence"].next_by_code(
                    "assetwise.assignment"
                ) or _("New")
            asset = self.env["assetwise.asset"].browse(vals.get("asset_id"))
            if asset:
                vals.setdefault("company_id", asset.company_id.id)
        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals and not self.env.context.get("assetwise_workflow"):
            raise UserError(_("Assignment status can only be changed through workflow actions."))
        protected = self.filtered(lambda record: record.state in ("returned", "cancelled"))
        if protected and not self.env.context.get("assetwise_workflow"):
            raise UserError(_("Completed assignments are immutable."))
        return super().write(vals)

    @api.constrains("expected_return_date", "assignment_date")
    def _check_expected_return_date(self):
        for assignment in self:
            if (
                assignment.expected_return_date
                and assignment.expected_return_date < assignment.assignment_date
            ):
                raise ValidationError(_("Expected return date cannot be before assignment date."))

    @api.constrains("assigned_to_id", "company_id")
    def _check_assignee_company(self):
        for assignment in self:
            if assignment.company_id not in assignment.assigned_to_id.company_ids:
                raise ValidationError(_("The assignee must have access to the assignment company."))

    def _lock_assets(self):
        if self.asset_id:
            self.env.cr.execute(
                "SELECT id FROM assetwise_asset WHERE id = ANY(%s) FOR UPDATE",
                [self.asset_id.ids],
            )

    def action_assign(self):
        for assignment in self:
            assignment._lock_assets()
            assignment.asset_id.invalidate_recordset(["status"])
            if assignment.state != "draft":
                raise UserError(_("Only draft assignments can be confirmed."))
            if assignment.asset_id.status != "available":
                raise UserError(_("Only available assets can be assigned."))
            assignment.asset_id.with_context(assetwise_workflow=True).write(
                {
                    "status": "assigned",
                    "responsible_user_id": assignment.assigned_to_id.id,
                }
            )
            assignment.with_context(assetwise_workflow=True).write(
                {"state": "assigned", "assigned_by_id": self.env.user.id}
            )
        return True

    def action_return(self):
        return_date = self.env.context.get("return_date") or fields.Date.context_today(self)
        condition = self.env.context.get("return_condition") or "good"
        notes = self.env.context.get("return_notes")
        for assignment in self:
            assignment._lock_assets()
            if assignment.state != "assigned":
                raise UserError(_("Only active assignments can be returned."))
            if return_date < assignment.assignment_date:
                raise ValidationError(_("Return date cannot be before assignment date."))
            assignment.with_context(assetwise_workflow=True).write(
                {
                    "state": "returned",
                    "actual_return_date": return_date,
                    "received_by_id": self.env.user.id,
                    "return_condition": condition,
                    "return_notes": notes,
                }
            )
            assignment.asset_id.with_context(assetwise_workflow=True).write(
                {
                    "status": "available",
                    "condition": condition,
                    "responsible_user_id": False,
                }
            )
            if condition == "damaged":
                maintenance = self.env["assetwise.maintenance"].create(
                    {
                        "asset_id": assignment.asset_id.id,
                        "maintenance_type": "corrective",
                        "description": _("Inspection required after damaged return %s")
                        % assignment.reference,
                        "scheduled_date": return_date,
                        "company_id": assignment.company_id.id,
                    }
                )
                maintenance.action_schedule()
        return True

    def action_open_return_wizard(self):
        self.ensure_one()
        if self.state != "assigned":
            raise UserError(_("Only active assignments can be returned."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Return Asset"),
            "res_model": "assetwise.return.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_assignment_id": self.id},
        }

    def action_cancel(self):
        for assignment in self:
            if assignment.state != "draft":
                raise UserError(_("Only draft assignments can be cancelled."))
            assignment.with_context(assetwise_workflow=True).write({"state": "cancelled"})
        return True

    def unlink(self):
        if any(record.state not in ("draft", "cancelled") for record in self):
            raise UserError(_("Active or completed assignment history cannot be deleted."))
        return super().unlink()
