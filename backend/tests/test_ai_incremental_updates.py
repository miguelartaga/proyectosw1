import pathlib
import sys
import unittest

from fastapi import HTTPException

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.routers.ai import GraphPayload, apply_incremental_updates


def build_graph(with_edge: bool) -> GraphPayload:
    nodes = [
        {
            "id": "node-pacientes",
            "type": "databaseNode",
            "position": {"x": 100, "y": 120},
            "data": {
                "label": "Pacientes",
                "columns": [
                    {"id": "pac-id", "name": "id", "type": "INT", "pk": True, "nullable": False}
                ],
            },
        },
        {
            "id": "node-tratamientos",
            "type": "databaseNode",
            "position": {"x": 420, "y": 120},
            "data": {
                "label": "Tratamientos",
                "columns": [
                    {"id": "trat-id", "name": "id", "type": "INT", "pk": True, "nullable": False}
                ],
            },
        },
    ]

    edges = []
    if with_edge:
        edges.append(
            {
                "id": "edge-pacientes-tratamientos",
                "source": "node-pacientes",
                "target": "node-tratamientos",
                "data": {
                    "id": "edge-pacientes-tratamientos",
                    "source": "node-pacientes",
                    "target": "node-tratamientos",
                    "kind": "simple",
                    "sourceMult": "1",
                    "targetMult": "*",
                    "label": "",
                },
            }
        )

    return GraphPayload(nodes=nodes, edges=edges)


class IncrementalMultiplicityTests(unittest.TestCase):
    def test_multiplicity_requires_existing_relation(self) -> None:
        graph = build_graph(with_edge=False)
        prompt = (
            "haz la multiplicidad entre la tabla pacientes y tratamientos con * a *"
        )

        with self.assertRaises(HTTPException) as context:
            apply_incremental_updates(prompt, graph)

        exc = context.exception
        self.assertEqual(exc.status_code, 400)
        self.assertIn("No hay relacion", str(exc.detail))

    def test_multiplicity_updates_existing_relation(self) -> None:
        graph = build_graph(with_edge=True)
        prompt = (
            "haz la multiplicidad entre la tabla pacientes y tratamientos con * a *"
        )

        result = apply_incremental_updates(prompt, graph)
        self.assertIsNotNone(result)
        edges = result["edges"]
        self.assertEqual(len(edges), 1)
        edge_data = edges[0].get("data", {})
        self.assertEqual(edge_data.get("sourceMult"), "*")
        self.assertEqual(edge_data.get("targetMult"), "*")

    def test_multiplicity_without_con_still_parses(self) -> None:
        graph = build_graph(with_edge=True)
        prompt = (
            "haz la multiplicidad entre la tabla pacientes y tratamientos 1 a 1"
        )

        result = apply_incremental_updates(prompt, graph)
        self.assertIsNotNone(result)
        edges = result["edges"]
        self.assertEqual(len(edges), 1)
        edge_data = edges[0].get("data", {})
        self.assertEqual(edge_data.get("sourceMult"), "1")
        self.assertEqual(edge_data.get("targetMult"), "1")


if __name__ == "__main__":
    unittest.main()
