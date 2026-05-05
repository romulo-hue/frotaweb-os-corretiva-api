import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import HTTPException

from api.main import app
from api.panel_store import PanelStore


class PanelFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = PanelStore(Path(self.temp_dir.name) / "panel.db")
        self.client = TestClient(app)
        self.patcher = patch("api.main.panel_store", self.store)
        self.patcher.start()

    def tearDown(self):
        self.client.close()
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_panel_accepts_order_and_lists_it(self):
        response = self.client.post(
            "/panel/os",
            json={
                "vehicle_code": "1830",
                "plate": "THP2B33",
                "defect_description": "Falha de teste",
                "opening_datetime": "12/03/2026 15:45:00",
                "odometer": "5",
                "exit_datetime": "12/03/2026 15:55:00",
                "branch_code": "4",
                "department_code": "420115",
                "credentials": {"empresa": "1", "filial": "1", "usuario": "232", "senha": "x"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["accepted"])

        listing = self.client.get("/panel/os")
        self.assertEqual(listing.status_code, 200)
        items = listing.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "PENDING_REVIEW")
        self.assertEqual(items[0]["payload"]["vehicle_code"], "1830")

    def test_launch_returns_frotaweb_error_message(self):
        created = self.client.post(
            "/panel/os",
            json={
                "vehicle_code": "1830",
                "plate": "THP2B33",
                "defect_description": "Falha de teste",
                "opening_datetime": "12/03/2026 15:45:00",
                "odometer": "5",
                "exit_datetime": "12/03/2026 15:55:00",
                "branch_code": "4",
                "department_code": "420115",
                "credentials": {"empresa": "1", "filial": "1", "usuario": "232", "senha": "x"},
            },
        ).json()
        panel_id = int(created["panel_id"])

        with patch("api.main.create_corrective_order", side_effect=HTTPException(status_code=502, detail="Erro FrotaWeb de teste")):
            launched = self.client.post(
                f"/panel/os/{panel_id}/launch",
                json={"credenciais": {"empresa": "1", "filial": "1", "usuario": "232", "senha": "x"}},
            )

        self.assertEqual(launched.status_code, 200)
        body = launched.json()
        self.assertFalse(body["created"])
        self.assertEqual(body["message"], "Erro FrotaWeb de teste")
        self.assertEqual(self.store.get_order(panel_id)["status"], "FAILED")
        self.assertEqual(self.store.get_order(panel_id)["error_message"], "Erro FrotaWeb de teste")

    def test_batch_launch_counts_success_and_failure(self):
        first = self.client.post(
            "/panel/os",
            json={
                "vehicle_code": "1830",
                "plate": "THP2B33",
                "defect_description": "Falha 1",
                "opening_datetime": "12/03/2026 15:45:00",
                "odometer": "5",
                "exit_datetime": "12/03/2026 15:55:00",
                "branch_code": "4",
                "department_code": "420115",
                "credentials": {"empresa": "1", "filial": "1", "usuario": "232", "senha": "x"},
            },
        ).json()
        second = self.client.post(
            "/panel/os",
            json={
                "vehicle_code": "1682",
                "plate": "RKH1F96",
                "defect_description": "Falha 2",
                "opening_datetime": "12/03/2026 16:00:00",
                "odometer": "9",
                "exit_datetime": "12/03/2026 16:10:00",
                "branch_code": "3",
                "department_code": "420112",
                "credentials": {"empresa": "1", "filial": "1", "usuario": "232", "senha": "x"},
            },
        ).json()

        def fake_launch(payload, dry_run=False):
            if payload.vehicle_code == "1830":
                return {"created": True, "message": "OK", "order_number": "65001"}
            raise HTTPException(status_code=502, detail="Erro FrotaWeb 2")

        with patch("api.main.create_corrective_order", side_effect=fake_launch):
            launched = self.client.post(
                "/panel/os/launch-batch",
                json={
                    "order_ids": [int(first["panel_id"]), int(second["panel_id"])],
                    "credenciais": {"empresa": "1", "filial": "1", "usuario": "232", "senha": "x"},
                },
            )

        self.assertEqual(launched.status_code, 200)
        body = launched.json()
        self.assertEqual(body["success_count"], 1)
        self.assertEqual(body["failure_count"], 1)
        self.assertEqual(body["results"][1]["message"], "Erro FrotaWeb 2")


if __name__ == "__main__":
    unittest.main()
