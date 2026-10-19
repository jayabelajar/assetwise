import datetime

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("assetwise", "post_install", "-at_install")
class TestAssetWise(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env["assetwise.category"].create(
            {"name": "Test Equipment", "code": "TEST", "company_id": cls.company.id}
        )
        cls.officer = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Asset Officer",
                "login": "assetwise-officer-test",
                "email": "officer@example.test",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.viewer = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Asset Viewer",
                "login": "assetwise-viewer-test",
                "email": "viewer@example.test",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.env.ref("assetwise.group_assetwise_officer").write(
            {"user_ids": [(4, cls.officer.id)]}
        )
        cls.env.ref("assetwise.group_assetwise_viewer").write(
            {"user_ids": [(4, cls.viewer.id)]}
        )

    def _create_asset(self, **values):
        values.setdefault("name", "Test Laptop")
        values.setdefault("category_id", self.category.id)
        values.setdefault("location", "Test Lab")
        values.setdefault("purchase_value", 10000.0)
        values.setdefault("residual_value", 1000.0)
        values.setdefault("useful_life_years", 5)
        return self.env["assetwise.asset"].create(values)

    def test_01_create_valid_asset_and_sequence(self):
        asset = self._create_asset()
        self.assertTrue(asset.code.startswith("AST/"))
        self.assertEqual(asset.status, "available")

    def test_02_duplicate_asset_code_rejected(self):
        first = self._create_asset()
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self._create_asset(name="Duplicate", code=first.code)

    def test_03_invalid_asset_values_rejected(self):
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self._create_asset(purchase_value=-1)
        with self.assertRaises(ValidationError):
            self._create_asset(purchase_value=100, residual_value=101)
        with self.assertRaises(UserError):
            self._create_asset().write({"status": "disposed"})

    def test_04_assign_and_return_asset(self):
        asset = self._create_asset()
        assignment = self.env["assetwise.assignment"].create(
            {"asset_id": asset.id, "assigned_to_id": self.officer.id}
        )
        assignment.action_assign()
        self.assertEqual(asset.status, "assigned")
        self.assertEqual(asset.responsible_user_id, self.officer)
        assignment.with_context(
            return_date=fields.Date.today(), return_condition="good", return_notes="Complete"
        ).action_return()
        self.assertEqual(assignment.state, "returned")
        self.assertEqual(asset.status, "available")
        self.assertFalse(asset.responsible_user_id)

    def test_05_double_assignment_rejected(self):
        asset = self._create_asset()
        first = self.env["assetwise.assignment"].create(
            {"asset_id": asset.id, "assigned_to_id": self.officer.id}
        )
        second = self.env["assetwise.assignment"].create(
            {"asset_id": asset.id, "assigned_to_id": self.viewer.id}
        )
        first.action_assign()
        with self.assertRaises(UserError):
            second.action_assign()
        self.assertEqual(
            self.env["assetwise.assignment"].search_count(
                [("asset_id", "=", asset.id), ("state", "=", "assigned")]
            ),
            1,
        )

    def test_06_invalid_return_rejected(self):
        assignment = self.env["assetwise.assignment"].create(
            {"asset_id": self._create_asset().id, "assigned_to_id": self.officer.id}
        )
        with self.assertRaises(UserError):
            assignment.action_return()
        assignment.action_assign()
        with self.assertRaises(ValidationError):
            assignment.with_context(
                return_date=assignment.assignment_date - datetime.timedelta(days=1)
            ).action_return()

    def test_07_damaged_return_opens_corrective_maintenance(self):
        asset = self._create_asset()
        assignment = self.env["assetwise.assignment"].create(
            {"asset_id": asset.id, "assigned_to_id": self.officer.id}
        )
        assignment.action_assign()
        assignment.with_context(return_condition="damaged").action_return()
        maintenance = self.env["assetwise.maintenance"].search(
            [("asset_id", "=", asset.id)], limit=1
        )
        self.assertEqual(maintenance.maintenance_type, "corrective")
        self.assertEqual(maintenance.state, "scheduled")
        self.assertEqual(asset.status, "maintenance")

    def test_08_maintenance_workflow(self):
        asset = self._create_asset()
        maintenance = self.env["assetwise.maintenance"].create(
            {
                "asset_id": asset.id,
                "maintenance_type": "preventive",
                "description": "Routine inspection",
                "scheduled_date": fields.Date.today(),
                "maintenance_cost": 250,
            }
        )
        maintenance.action_schedule()
        self.assertEqual(asset.status, "maintenance")
        maintenance.action_start()
        maintenance.action_complete()
        self.assertEqual(maintenance.state, "completed")
        self.assertEqual(asset.status, "available")
        self.assertTrue(maintenance.completion_date)

    def test_09_maintenance_validation(self):
        asset = self._create_asset()
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.env["assetwise.maintenance"].create(
                    {
                        "asset_id": asset.id,
                        "description": "Invalid cost",
                        "maintenance_cost": -1,
                    }
                )
        asset.with_context(assetwise_workflow=True).write({"status": "disposed"})
        with self.assertRaises(UserError):
            self.env["assetwise.maintenance"].create(
                {"asset_id": asset.id, "description": "Impossible maintenance"}
            )

    def test_10_depreciation_calculation_and_floor(self):
        start = fields.Date.today() - datetime.timedelta(days=365)
        asset = self._create_asset(
            purchase_value=11000,
            residual_value=1000,
            useful_life_years=5,
            depreciation_start_date=start,
        )
        self.assertAlmostEqual(asset.annual_depreciation, 2000, places=2)
        self.assertAlmostEqual(asset.accumulated_depreciation, 2000, places=2)
        old_asset = self._create_asset(
            name="Old Asset",
            purchase_value=11000,
            residual_value=1000,
            useful_life_years=5,
            depreciation_start_date=fields.Date.today() - datetime.timedelta(days=365 * 20),
        )
        self.assertEqual(old_asset.estimated_book_value, 1000)

    def test_11_viewer_cannot_write(self):
        asset = self._create_asset()
        with self.assertRaises(AccessError):
            asset.with_user(self.viewer).write({"name": "Unauthorized"})

    def test_12_officer_cannot_dispose_or_archive(self):
        asset = self._create_asset()
        with self.assertRaises(AccessError):
            asset.with_user(self.officer).action_dispose()
        with self.assertRaises(AccessError):
            asset.with_user(self.officer).write({"active": False})

    def test_13_cross_company_access_denied(self):
        other_company = self.env["res.company"].create({"name": "Other Test Company"})
        cross_company_context = {"allowed_company_ids": [self.company.id, other_company.id]}
        other_category = self.env["assetwise.category"].sudo().with_context(
            **cross_company_context
        ).create(
            {"name": "Other Category", "code": "OTHER", "company_id": other_company.id}
        )
        other_asset = self.env["assetwise.asset"].sudo().with_context(
            **cross_company_context
        ).create(
            {
                "name": "Other Company Asset",
                "category_id": other_category.id,
                "company_id": other_company.id,
                "location": "Other Site",
            }
        )
        officer_model = self.env["assetwise.asset"].with_user(self.officer).with_context(
            allowed_company_ids=[self.company.id]
        )
        self.assertFalse(officer_model.search([("id", "=", other_asset.id)]))
        with self.assertRaises(AccessError):
            officer_model.browse(other_asset.id).write({"name": "Forbidden"})

    def test_14_active_maintenance_is_unique(self):
        asset = self._create_asset()
        first = self.env["assetwise.maintenance"].create(
            {"asset_id": asset.id, "description": "First"}
        )
        second = self.env["assetwise.maintenance"].create(
            {"asset_id": asset.id, "description": "Second"}
        )
        first.action_schedule()
        with self.assertRaises(UserError):
            second.action_schedule()

    def test_15_completed_history_is_immutable(self):
        asset = self._create_asset()
        assignment = self.env["assetwise.assignment"].create(
            {"asset_id": asset.id, "assigned_to_id": self.officer.id}
        )
        assignment.action_assign()
        assignment.action_return()
        with self.assertRaises(UserError):
            assignment.write({"notes": "Tamper"})
        with self.assertRaises(UserError):
            assignment.unlink()

    def test_16_all_reports_render_as_html(self):
        self._create_asset()
        report_ids = {
            "inventory": "assetwise.action_report_inventory",
            "assignment": "assetwise.action_report_assignment",
            "maintenance": "assetwise.action_report_maintenance",
            "depreciation": "assetwise.action_report_depreciation",
        }
        for report_type, xml_id in report_ids.items():
            with self.subTest(report_type=report_type):
                wizard = self.env["assetwise.report.wizard"].create(
                    {"report_type": report_type, "company_id": self.company.id}
                )
                action = wizard.with_context(discard_logo_check=True).action_print()
                self.assertEqual(action["type"], "ir.actions.report")
                self.assertEqual(action["report_name"], self.env.ref(xml_id).report_name)
                html, output_type = self.env["ir.actions.report"]._render_qweb_html(
                    action["report_name"], wizard.ids, data=action["data"]
                )
                self.assertTrue(html)
                self.assertEqual(output_type, "html")
