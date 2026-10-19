from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    assetwise_total_assets = fields.Integer(compute="_compute_assetwise_metrics")
    assetwise_available_assets = fields.Integer(compute="_compute_assetwise_metrics")
    assetwise_assigned_assets = fields.Integer(compute="_compute_assetwise_metrics")
    assetwise_maintenance_assets = fields.Integer(compute="_compute_assetwise_metrics")
    assetwise_disposed_assets = fields.Integer(compute="_compute_assetwise_metrics")
    assetwise_total_value = fields.Monetary(compute="_compute_assetwise_metrics")
    assetwise_maintenance_cost = fields.Monetary(compute="_compute_assetwise_metrics")
    assetwise_upcoming_maintenance = fields.Integer(compute="_compute_assetwise_metrics")

    def _compute_assetwise_metrics(self):
        Asset = self.env["assetwise.asset"].with_context(active_test=False)
        Maintenance = self.env["assetwise.maintenance"]
        status_rows = Asset._read_group(
            [("company_id", "in", self.ids)],
            ["company_id", "status"],
            ["__count", "purchase_value:sum"],
        )
        cost_rows = Maintenance._read_group(
            [("company_id", "in", self.ids), ("state", "=", "completed")],
            ["company_id"],
            ["maintenance_cost:sum"],
        )
        upcoming_rows = Maintenance._read_group(
            [
                ("company_id", "in", self.ids),
                ("state", "=", "scheduled"),
                ("scheduled_date", ">=", fields.Date.context_today(self)),
            ],
            ["company_id"],
            ["__count"],
        )
        costs = {company.id: cost for company, cost in cost_rows}
        upcoming = {company.id: count for company, count in upcoming_rows}
        values = {company.id: {"total": 0, "value": 0.0} for company in self}
        for company, status, count, purchase_sum in status_rows:
            row = values[company.id]
            row[status] = count
            row["total"] += count
            row["value"] += purchase_sum or 0.0
        for company in self:
            row = values[company.id]
            company.assetwise_total_assets = row["total"]
            company.assetwise_available_assets = row.get("available", 0)
            company.assetwise_assigned_assets = row.get("assigned", 0)
            company.assetwise_maintenance_assets = row.get("maintenance", 0)
            company.assetwise_disposed_assets = row.get("disposed", 0)
            company.assetwise_total_value = row["value"]
            company.assetwise_maintenance_cost = costs.get(company.id, 0.0)
            company.assetwise_upcoming_maintenance = upcoming.get(company.id, 0)
