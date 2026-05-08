"""Codebase knowledge graph integration."""

from __future__ import annotations

from pathlib import Path

from diffguard.core.db import DiffGuardDB
from diffguard.core.models import FileContext
from diffguard.v2.models import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, SemanticChange


class KnowledgeGraphBuilder:
    """Builds and queries a codebase graph from learned DiffGuard context."""

    def __init__(self, db: DiffGuardDB) -> None:
        self.db = db

    def build(self) -> KnowledgeGraph:
        graph = KnowledgeGraph()
        for file_context in self.db.list_files():
            graph.add_node(KnowledgeNode(file_context.path, "file", Path(file_context.path).name, {"summary": file_context.summary}))
            self._add_symbol_nodes(graph, file_context)
        for file_context in self.db.list_files():
            for relation in self.db.list_relations_for(file_context.path):
                graph.add_edge(KnowledgeEdge(relation.source_file, relation.target_file, relation.relation_type, relation.evidence))
        return graph

    def impacts_for_changes(self, changes: list[SemanticChange]) -> list[dict[str, object]]:
        graph = self.build()
        impacts: list[dict[str, object]] = []
        for change in changes:
            for edge in graph.neighbors(change.path):
                other = edge.target if edge.source == change.path else edge.source
                impacts.append({"changed_file": change.path, "related_node": other, "relation": edge.relation, "change_type": change.type, "evidence": edge.evidence})
        return impacts

    def _add_symbol_nodes(self, graph: KnowledgeGraph, context: FileContext) -> None:
        for pattern in context.patterns:
            if pattern.get("name") != "symbols":
                continue
            for kind in ("functions", "classes", "routes"):
                for symbol in pattern.get(kind, []):
                    node_id = f"{context.path}::{symbol}"
                    graph.add_node(KnowledgeNode(node_id, kind.rstrip("s"), str(symbol), {"file": context.path}))
                    graph.add_edge(KnowledgeEdge(context.path, node_id, "declares", {}))
