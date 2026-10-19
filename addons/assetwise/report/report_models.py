from odoo import api, fields, models


class _AssetWiseReportMixin:
    def _asset_domain(self, data):
        domain = [("company_id", "=", data["company_id"])]
        if data.get("category_id"):
            domain.append(("category_id", "=", data["category_id"]))
        if data.get("location"):
            domain.append(("location", "ilike", data["location"]))
        if data.get("asset_status"):
            domain.append(("status", "=", data["asset_status"]))
        return domain

    def _related_domain(self, data, date_field):
        domain = [("company_id", "=", data["company_id"])]
        if data.get("date_from"):
            domain.append((date_field, ">=", data["date_from"]))
        if data.get("date_to"):
            domain.append((date_field, "<=", data["date_to"]))
        if data.get("category_id"):
            domain.append(("asset_id.category_id", "=", data["category_id"]))
        if data.get("location"):
            domain.append(("asset_id.location", "ilike", data["location"]))
        if data.get("asset_status"):
            domain.append(("asset_id.status", "=", data["asset_status"]))
        return domain

    def _values(self, model, domain, data, order):
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        return {
            "doc_ids": [],
            "doc_model": model,
            "docs": self.env[model].search(domain, order=order),
            "data": data,
            "company": self.env["res.company"].browse(data["company_id"]),
            "generated_on": now,
            "report_reference": "AW-%s-%s"
            % (
                data["assetwise_report_type"].upper()[:4],
                now.strftime("%Y%m%d-%H%M%S"),
            ),
        }


class ReportAssetWiseInventory(models.AbstractModel, _AssetWiseReportMixin):
    _name = "report.assetwise.report_inventory"
    _description = "AssetWise Inventory Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        domain = self._asset_domain(data)
        if data.get("date_from"):
            domain.append(("purchase_date", ">=", data["date_from"]))
        if data.get("date_to"):
            domain.append(("purchase_date", "<=", data["date_to"]))
        return self._values("assetwise.asset", domain, data, "category_id, code")


class ReportAssetWiseAssignment(models.AbstractModel, _AssetWiseReportMixin):
    _name = "report.assetwise.report_assignment"
    _description = "AssetWise Assignment Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        return self._values(
            "assetwise.assignment",
            self._related_domain(data, "assignment_date"),
            data,
            "assignment_date desc, reference",
        )


class ReportAssetWiseMaintenance(models.AbstractModel, _AssetWiseReportMixin):
    _name = "report.assetwise.report_maintenance"
    _description = "AssetWise Maintenance Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        return self._values(
            "assetwise.maintenance",
            self._related_domain(data, "scheduled_date"),
            data,
            "scheduled_date desc, reference",
        )


class ReportAssetWiseDepreciation(models.AbstractModel, _AssetWiseReportMixin):
    _name = "report.assetwise.report_depreciation"
    _description = "AssetWise Depreciation Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        domain = self._asset_domain(data)
        if data.get("date_from"):
            domain.append(("depreciation_start_date", ">=", data["date_from"]))
        if data.get("date_to"):
            domain.append(("depreciation_start_date", "<=", data["date_to"]))
        return self._values("assetwise.asset", domain, data, "category_id, code")
