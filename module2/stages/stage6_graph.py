"""
module2/stages/stage6_graph.py
────────────────────────────────
Stage 6: Supply Chain Graph Risk Propagation.

Models the company's supplier network as a directed NetworkX graph:
    Nodes: company → Tier-1 → Tier-2 → Tier-3 suppliers → source countries
    Edges: labeled with commodity + dependency_weight (0.0–1.0)

Algorithms:
  1. BFS traversal from disrupted node — finds all downstream affected nodes
  2. Risk attenuation per hop:
       Propagated = Original × dependency_weight × (0.65 ^ hop_number)
     Example: 90 at T1 → 90×0.7×0.65=40.95 at T2 → 40.95×0.5×0.65=13.3 at T3

  3. NetworkX PageRank — identifies most critical (most connected) supplier nodes.
     High PageRank nodes = single points of failure.

Graph is built once from the supplier DB and cached.
On each M2 run, affected nodes are updated with new risk scores.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

HOP_ATTENUATION = 0.65   # risk multiplier per hop
MAX_HOPS = 3             # maximum propagation depth


# ─────────────────────────────────────────────────────────────────────────────
#  Graph builder
# ─────────────────────────────────────────────────────────────────────────────

def build_supplier_graph(suppliers: list, company_name: str = "Company"):
    """
    Build a directed NetworkX graph from the supplier list.

    Node attributes:
        type: 'company' | 'tier1' | 'tier2' | 'tier3'
        country_code: str
        criticality: str
        dependency_weight: float

    Edge attributes:
        commodity: str
        weight: dependency_weight (used by PageRank)
    """
    try:
        import networkx as nx
    except ImportError:
        logger.error("networkx not installed. Run: pip install networkx")
        return None

    G = nx.DiGraph()

    # Root node: the company itself
    G.add_node(company_name, type="company", country_code="IN")

    # Add supplier nodes and edges
    for supplier in suppliers:
        node_id = supplier.name
        G.add_node(
            node_id,
            type=f"tier{supplier.tier}",
            country_code=supplier.country_code or "XX",
            criticality=supplier.criticality or "medium",
            dependency_weight=supplier.dependency_weight or 0.0,
            commodity=supplier.commodity or "",
            tier=supplier.tier,
        )

        # Tier 1 → company edge
        if supplier.tier == 1:
            G.add_edge(
                node_id, company_name,
                commodity=supplier.commodity or "",
                weight=supplier.dependency_weight or 0.0,
            )
        # Tier 2 → Tier 1 edges (connect via commodity overlap)
        elif supplier.tier == 2:
            # Find Tier 1 suppliers with overlapping commodity keywords
            commodity_words = set(
                (supplier.commodity or "").lower().split()
            ) - {"and", "the", "of", "for"}

            connected = False
            for other in suppliers:
                if other.tier != 1:
                    continue
                other_words = set((other.commodity or "").lower().split())
                if commodity_words & other_words:
                    G.add_edge(
                        node_id, other.name,
                        commodity=supplier.commodity or "",
                        weight=supplier.dependency_weight or 0.0,
                    )
                    connected = True

            if not connected:
                # Fall back: connect to company directly
                G.add_edge(
                    node_id, company_name,
                    commodity=supplier.commodity or "",
                    weight=supplier.dependency_weight or 0.0,
                )

        # Tier 3 → Tier 2 or Tier 1 edges (raw materials)
        elif supplier.tier == 3:
            commodity_words = set(
                (supplier.commodity or "").lower().split()
            ) - {"and", "the", "of", "for"}

            connected = False
            for other in suppliers:
                if other.tier not in (1, 2):
                    continue
                other_words = set((other.commodity or "").lower().split())
                if commodity_words & other_words:
                    G.add_edge(
                        node_id, other.name,
                        commodity=supplier.commodity or "",
                        weight=supplier.dependency_weight or 0.0,
                    )
                    connected = True

            if not connected:
                G.add_edge(
                    node_id, company_name,
                    commodity=supplier.commodity or "",
                    weight=supplier.dependency_weight or 0.0,
                )

    logger.debug(
        f"Graph built: {G.number_of_nodes()} nodes, "
        f"{G.number_of_edges()} edges"
    )
    return G


def get_pagerank(G) -> dict:
    """
    Run PageRank on the supplier graph.
    Returns dict of {node_name: pagerank_score}.
    High PageRank = high connectivity = single point of failure candidate.
    """
    try:
        import networkx as nx
        pr = nx.pagerank(G, weight="weight")
        return pr
    except Exception as e:
        logger.error(f"PageRank failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
#  Risk propagation
# ─────────────────────────────────────────────────────────────────────────────

def propagate_risk(
    G,
    disrupted_supplier_name: str,
    risk_score: float,
    dependency_weight: float,
) -> list:
    """
    BFS propagation from a disrupted supplier node.

    Args:
        G: NetworkX directed graph
        disrupted_supplier_name: name of the disrupted node
        risk_score: the direct risk score for the disrupted supplier
        dependency_weight: dependency_weight of the disrupted supplier

    Returns:
        list of dicts: [{ node, hop, propagated_risk, path }]
    """
    if G is None or disrupted_supplier_name not in G:
        return []

    try:
        import networkx as nx
    except ImportError:
        return []

    propagated = []
    visited = {disrupted_supplier_name}

    # BFS queue: (node, hop, current_risk)
    queue = [(disrupted_supplier_name, 0, risk_score)]

    while queue:
        node, hop, current_risk = queue.pop(0)

        if hop >= MAX_HOPS:
            continue

        # Traverse successor nodes (downstream in the supply chain)
        for successor in G.successors(node):
            if successor in visited:
                continue
            visited.add(successor)

            edge_data = G.edges[node, successor]
            edge_weight = edge_data.get("weight", 0.5)

            # Attenuation formula:
            # Propagated = Current × edge_weight × HOP_ATTENUATION^(hop+1)
            prop_risk = current_risk * edge_weight * (HOP_ATTENUATION ** (hop + 1))
            prop_risk = max(0.0, min(100.0, prop_risk))

            if prop_risk < 2.0:  # too attenuated to be meaningful
                continue

            propagated.append({
                "node":           successor,
                "hop":            hop + 1,
                "propagated_risk": round(prop_risk, 2),
                "via":            node,
                "commodity":      edge_data.get("commodity", ""),
            })

            queue.append((successor, hop + 1, prop_risk))

    return propagated


# ─────────────────────────────────────────────────────────────────────────────
#  Main Stage 6 runner
# ─────────────────────────────────────────────────────────────────────────────

def run_stage6(
    matched_supplier,
    risk_score: float,
    suppliers: list,
    company_name: str = "Company",
) -> dict:
    """
    Run graph propagation for one matched supplier risk event.

    Returns:
        dict with propagated_risks list and pagerank for the disrupted node
    """
    G = build_supplier_graph(suppliers, company_name)
    if G is None:
        return {"propagated_risks": [], "pagerank": 0.0, "is_critical_node": False}

    pagerank = get_pagerank(G)
    supplier_pagerank = pagerank.get(matched_supplier.supplier_name, 0.0)

    # Normalise pagerank to 0–100 range for display
    max_pr = max(pagerank.values()) if pagerank else 1.0
    pagerank_score = (supplier_pagerank / max_pr) * 100 if max_pr > 0 else 0.0

    # Propagate risk downstream
    propagated = propagate_risk(
        G,
        matched_supplier.supplier_name,
        risk_score,
        matched_supplier.dependency_weight,
    )

    # Flag as critical node if PageRank is in top 20% of all nodes
    pr_values = sorted(pagerank.values(), reverse=True)
    top_20_threshold = pr_values[max(0, len(pr_values) // 5)] if pr_values else 0
    is_critical_node = supplier_pagerank >= top_20_threshold

    result = {
        "propagated_risks": propagated,
        "pagerank":         round(pagerank_score, 2),
        "is_critical_node": is_critical_node,
        "affected_nodes":   [p["node"] for p in propagated],
    }

    if propagated:
        logger.debug(
            f"  Stage 6: {len(propagated)} downstream nodes affected "
            f"from {matched_supplier.supplier_name} "
            f"(PageRank={pagerank_score:.1f}, critical={is_critical_node})"
        )

    return result
