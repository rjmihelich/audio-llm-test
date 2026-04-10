"""Graph executor — validates, topologically sorts, and executes node graphs.

Implements the Pipeline protocol from backend.app.pipeline.base so it can
drop into the existing test scheduler without changes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Per-node-type timeout (seconds). Keeps the total response under proxy limits.
_NODE_TIMEOUTS: dict[str, float] = {
    "stt": 30,
    "llm": 45,
    "llm_realtime": 45,
}

from backend.app.audio.types import AudioBuffer
from backend.app.pipeline.base import PipelineInput, PipelineResult

from .node_registry import NODE_REGISTRY, PortType, get_port_type


# ---------------------------------------------------------------------------
# Graph data structures
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    id: str
    type_id: str
    config: dict = field(default_factory=dict)
    position: dict = field(default_factory=dict)  # {x, y} for frontend


@dataclass
class GraphEdge:
    id: str
    source: str
    source_handle: str
    target: str
    target_handle: str
    edge_type: str = "normal"  # "normal" or "feedback"


@dataclass
class ValidatedGraph:
    nodes: dict[str, GraphNode]
    edges: list[GraphEdge]
    forward_edges: list[GraphEdge]
    feedback_edges: list[GraphEdge]
    sorted_node_ids: list[str]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_graph(graph_json: dict) -> ValidationResult:
    """Validate a graph JSON structure. Returns errors and warnings."""
    errors: list[str] = []
    warnings: list[str] = []

    nodes_raw = graph_json.get("nodes", [])
    edges_raw = graph_json.get("edges", [])

    if not nodes_raw:
        errors.append("Graph has no nodes")
        return ValidationResult(valid=False, errors=errors)

    # Parse nodes
    nodes: dict[str, GraphNode] = {}
    for n in nodes_raw:
        nid = n.get("id")
        type_id = n.get("type") or n.get("data", {}).get("type_id", "")
        if not nid:
            errors.append("Node missing 'id'")
            continue
        if type_id not in NODE_REGISTRY:
            errors.append(f"Node {nid}: unknown type '{type_id}'")
            continue
        config = n.get("data", {}).get("config", {})
        nodes[nid] = GraphNode(id=nid, type_id=type_id, config=config,
                               position=n.get("position", {}))

    if not nodes:
        errors.append("No valid nodes found")
        return ValidationResult(valid=False, errors=errors)

    # Parse edges
    edges: list[GraphEdge] = []
    for e in edges_raw:
        edge = GraphEdge(
            id=e.get("id", ""),
            source=e.get("source", ""),
            source_handle=e.get("sourceHandle", ""),
            target=e.get("target", ""),
            target_handle=e.get("targetHandle", ""),
            edge_type=e.get("data", {}).get("edge_type", "normal"),
        )
        if edge.source not in nodes:
            errors.append(f"Edge {edge.id}: source node '{edge.source}' not found")
            continue
        if edge.target not in nodes:
            errors.append(f"Edge {edge.id}: target node '{edge.target}' not found")
            continue
        edges.append(edge)

    # 1. Type compatibility check
    for edge in edges:
        src_node = nodes[edge.source]
        tgt_node = nodes[edge.target]
        try:
            src_type = get_port_type(src_node.type_id, edge.source_handle, "output")
            tgt_type = get_port_type(tgt_node.type_id, edge.target_handle, "input")
            if src_type != tgt_type:
                errors.append(
                    f"Edge {edge.id}: type mismatch — {src_node.type_id}.{edge.source_handle} "
                    f"({src_type.value}) → {tgt_node.type_id}.{edge.target_handle} ({tgt_type.value})"
                )
        except KeyError as exc:
            errors.append(f"Edge {edge.id}: {exc}")

    # 2. Partition edges into forward and feedback
    forward_edges = [e for e in edges if e.edge_type != "feedback"]
    feedback_edges = [e for e in edges if e.edge_type == "feedback"]

    # 3. Feedback edges: only allowed targeting echo_simulator.speaker_in
    for fe in feedback_edges:
        tgt_node = nodes[fe.target]
        if tgt_node.type_id != "echo_simulator" or fe.target_handle != "speaker_in":
            errors.append(
                f"Feedback edge {fe.id}: feedback edges only allowed to "
                f"echo_simulator.speaker_in, not {tgt_node.type_id}.{fe.target_handle}"
            )

    # 4. Cycle detection on forward edges (Kahn's algorithm)
    sorted_ids = _topological_sort(nodes, forward_edges)
    if sorted_ids is None:
        errors.append("Graph contains a cycle (excluding feedback edges)")

    # 5. Check required inputs have connections
    incoming: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        incoming[e.target].add(e.target_handle)

    for node in nodes.values():
        node_def = NODE_REGISTRY.get(node.type_id)
        if not node_def:
            continue
        for port in node_def.inputs:
            if port.required and port.name not in incoming.get(node.id, set()):
                # Special case: LLM nodes need at least one of audio_in/text_in
                if node.type_id in ("llm", "network_sim"):
                    continue  # checked separately below
                errors.append(f"Node {node.id} ({node.type_id}): required input '{port.name}' has no connection")

    # 6. LLM node: at least one input connected
    for node in nodes.values():
        if node.type_id == "llm":
            connected = incoming.get(node.id, set())
            if "audio_in" not in connected and "text_in" not in connected:
                errors.append(f"LLM node {node.id}: at least one of audio_in or text_in must be connected")
        if node.type_id == "network_sim":
            connected = incoming.get(node.id, set())
            if "audio_in" not in connected and "text_in" not in connected:
                errors.append(f"Network sim node {node.id}: at least one of audio_in or text_in must be connected")

    # 7. At least one source and one sink
    has_source = any(not NODE_REGISTRY[n.type_id].inputs for n in nodes.values() if n.type_id in NODE_REGISTRY)
    has_sink = any(not NODE_REGISTRY[n.type_id].outputs for n in nodes.values() if n.type_id in NODE_REGISTRY)
    if not has_source:
        warnings.append("Graph has no source nodes (nodes with no inputs)")
    if not has_sink:
        warnings.append("Graph has no sink nodes (nodes with no outputs)")

    valid = len(errors) == 0
    return ValidationResult(valid=valid, errors=errors, warnings=warnings)


def _topological_sort(nodes: dict[str, GraphNode], edges: list[GraphEdge]) -> list[str] | None:
    """Kahn's algorithm. Returns sorted node IDs or None if cycle detected."""
    in_degree: dict[str, int] = {nid: 0 for nid in nodes}
    adj: dict[str, list[str]] = {nid: [] for nid in nodes}

    for edge in edges:
        if edge.source in nodes and edge.target in nodes:
            adj[edge.source].append(edge.target)
            in_degree[edge.target] += 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    result: list[str] = []

    while queue:
        nid = queue.popleft()
        result.append(nid)
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(nodes):
        return None
    return result


def parse_graph(graph_json: dict) -> ValidatedGraph:
    """Parse and validate a graph, returning a ValidatedGraph ready for execution."""
    validation = validate_graph(graph_json)
    if not validation.valid:
        raise ValueError(f"Invalid graph: {'; '.join(validation.errors)}")

    nodes_raw = graph_json.get("nodes", [])
    edges_raw = graph_json.get("edges", [])

    nodes: dict[str, GraphNode] = {}
    for n in nodes_raw:
        nid = n["id"]
        type_id = n.get("type") or n.get("data", {}).get("type_id", "")
        config = n.get("data", {}).get("config", {})
        nodes[nid] = GraphNode(id=nid, type_id=type_id, config=config,
                               position=n.get("position", {}))

    edges: list[GraphEdge] = []
    for e in edges_raw:
        edges.append(GraphEdge(
            id=e.get("id", ""),
            source=e["source"],
            source_handle=e.get("sourceHandle", ""),
            target=e["target"],
            target_handle=e.get("targetHandle", ""),
            edge_type=e.get("data", {}).get("edge_type", "normal"),
        ))

    forward_edges = [e for e in edges if e.edge_type != "feedback"]
    feedback_edges = [e for e in edges if e.edge_type == "feedback"]
    sorted_ids = _topological_sort(nodes, forward_edges)

    return ValidatedGraph(
        nodes=nodes,
        edges=edges,
        forward_edges=forward_edges,
        feedback_edges=feedback_edges,
        sorted_node_ids=sorted_ids or [],
    )


# ---------------------------------------------------------------------------
# Graph Pipeline (implements Pipeline protocol)
# ---------------------------------------------------------------------------

class GraphPipeline:
    """Executes a node graph as a Pipeline.

    Implements the Pipeline protocol from backend.app.pipeline.base so it can
    be used as a drop-in replacement in the test scheduler.
    """

    def __init__(
        self,
        graph_json: dict,
        node_executors: dict[str, Any] | None = None,
        *,
        # Sweep parameter overrides
        snr_db: float | None = None,
        noise_type: str | None = None,
        echo_config: Any | None = None,
    ):
        self._graph = parse_graph(graph_json)
        self._node_executors = node_executors or {}
        self._snr_override = snr_db
        self._noise_type_override = noise_type
        self._echo_config_override = echo_config

    @property
    def pipeline_type(self) -> str:
        return "graph"

    async def execute(self, input: PipelineInput) -> PipelineResult:
        """Execute the graph pipeline."""
        start_time = time.monotonic()

        # Build execution context
        ctx = ExecutionContext(
            pipeline_input=input,
            snr_override=self._snr_override,
            noise_type_override=self._noise_type_override,
            echo_config_override=self._echo_config_override,
        )

        try:
            # Pass 1: forward execution (feedback ports get silence)
            outputs = await self._run_pass(ctx, feedback_values={})

            # Pass 2: if feedback edges exist, inject feedback and re-execute
            if self._graph.feedback_edges:
                feedback_values = self._collect_feedback(outputs)
                outputs = await self._run_pass(ctx, feedback_values)

            return self._collect_result(outputs, start_time)

        except Exception as e:
            return PipelineResult(
                pipeline_type="graph",
                error=f"{type(e).__name__}: {e}",
                total_latency_ms=(time.monotonic() - start_time) * 1000,
            )

    async def _run_pass(
        self,
        ctx: ExecutionContext,
        feedback_values: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Execute all nodes in topological order.

        Slow nodes (LLM, STT) have per-node timeouts so the audio path
        can return quickly without waiting for the text/LLM branch.
        """
        outputs: dict[str, dict[str, Any]] = {}

        for node_id in self._graph.sorted_node_ids:
            node = self._graph.nodes[node_id]

            # Gather inputs from upstream nodes
            node_inputs = self._gather_inputs(node_id, outputs, feedback_values)

            # Skip node if a required upstream timed out (no useful inputs)
            if any(
                isinstance(v, dict) and v.get("_timed_out")
                for v in node_inputs.values()
            ):
                logger.info("Skipping %s (%s) — upstream timed out", node_id, node.type_id)
                outputs[node_id] = {"_timed_out": True}
                continue

            # Apply sweep overrides to matching nodes
            config = dict(node.config)
            if self._snr_override is not None and node.type_id == "mixer":
                config["snr_db"] = self._snr_override
            if self._noise_type_override and node.type_id == "noise_generator":
                config["noise_type"] = self._noise_type_override
            if self._echo_config_override and node.type_id == "echo_simulator":
                if hasattr(self._echo_config_override, "delay_ms"):
                    config["delay_ms"] = self._echo_config_override.delay_ms
                    config["gain_db"] = self._echo_config_override.gain_db

            # Execute the node with optional timeout
            executor = self._get_executor(node.type_id)
            timeout = _NODE_TIMEOUTS.get(node.type_id)

            try:
                if timeout:
                    node_outputs = await asyncio.wait_for(
                        executor(node, node_inputs, config, ctx),
                        timeout=timeout,
                    )
                else:
                    node_outputs = await executor(node, node_inputs, config, ctx)
            except asyncio.TimeoutError:
                logger.warning("Node %s (%s) timed out after %.0fs", node_id, node.type_id, timeout)
                node_outputs = {"_timed_out": True}
            except Exception as e:
                logger.warning("Node %s (%s) failed: %s", node_id, node.type_id, e)
                node_outputs = {"_error": str(e)}

            outputs[node_id] = node_outputs

        return outputs

    def _gather_inputs(
        self,
        node_id: str,
        outputs: dict[str, dict[str, Any]],
        feedback_values: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Gather inputs for a node from upstream outputs and feedback."""
        inputs: dict[str, Any] = {}

        # Forward edges
        for edge in self._graph.forward_edges:
            if edge.target == node_id:
                src_outputs = outputs.get(edge.source, {})
                if edge.source_handle in src_outputs:
                    inputs[edge.target_handle] = src_outputs[edge.source_handle]

        # Feedback edges
        for edge in self._graph.feedback_edges:
            if edge.target == node_id:
                fb = feedback_values.get(edge.source, {})
                if edge.source_handle in fb:
                    inputs[edge.target_handle] = fb[edge.source_handle]

        # Handle dynamic mixer inputs: collect all audio_in_N into a list
        node = self._graph.nodes[node_id]
        if node.type_id == "mixer":
            audio_inputs = []
            for key in sorted(inputs.keys()):
                if key.startswith("audio_in_"):
                    audio_inputs.append(inputs[key])
            if audio_inputs:
                inputs["_audio_inputs"] = audio_inputs

        return inputs

    def _collect_feedback(self, outputs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Collect output values that feed into feedback edges."""
        feedback: dict[str, dict[str, Any]] = {}
        for edge in self._graph.feedback_edges:
            if edge.source in outputs:
                feedback[edge.source] = outputs[edge.source]
        return feedback

    def _collect_result(
        self,
        outputs: dict[str, dict[str, Any]],
        start_time: float,
    ) -> PipelineResult:
        """Build a PipelineResult from the graph execution outputs."""
        result = PipelineResult(
            pipeline_type="graph",
            total_latency_ms=(time.monotonic() - start_time) * 1000,
        )

        # Walk outputs looking for known result types
        for node_id, node_outputs in outputs.items():
            if node_outputs.get("_timed_out") or node_outputs.get("_error"):
                continue
            node = self._graph.nodes[node_id]

            # Capture degraded audio from mixer/echo/postprocess
            if node.type_id in ("mixer", "echo_simulator", "audio_postprocess") and "audio_out" in node_outputs:
                if isinstance(node_outputs["audio_out"], AudioBuffer):
                    result.degraded_audio = node_outputs["audio_out"]

            # Capture LLM response
            if node.type_id in ("llm", "llm_realtime") and "text_out" in node_outputs:
                from backend.app.llm.base import LLMResponse
                text = node_outputs.get("text_out", "")
                latency = node_outputs.get("_latency_ms", 0)
                result.llm_response = LLMResponse(
                    text=text,
                    audio=node_outputs.get("audio_out"),
                    latency_ms=latency,
                )

            # Capture ASR transcript
            if node.type_id == "stt" and "text_out" in node_outputs:
                from backend.app.llm.base import Transcription
                result.transcription = Transcription(
                    text=node_outputs["text_out"],
                    language=node_outputs.get("_language", "en"),
                    confidence=node_outputs.get("_confidence", 0.0),
                )

            # Capture audio_output sink nodes
            if node.type_id == "audio_output" and "_audio" in node_outputs:
                audio = node_outputs["_audio"]
                if isinstance(audio, AudioBuffer):
                    result.degraded_audio = audio

            # Capture text_output sink nodes
            if node.type_id == "text_output" and "_text" in node_outputs:
                # Store in dedicated attribute for the API to return
                if not hasattr(result, "_text_output_text"):
                    result._text_output_text = node_outputs["_text"]
                if not result.transcription:
                    from backend.app.llm.base import Transcription
                    result.transcription = Transcription(
                        text=node_outputs["_text"],
                        language="en",
                        confidence=0.0,
                    )

        return result

    def _get_executor(self, type_id: str):
        """Get the executor function for a node type."""
        if type_id in self._node_executors:
            return self._node_executors[type_id]
        # Import default executors lazily
        from ..nodes import get_default_executor
        return get_default_executor(type_id)


@dataclass
class ExecutionContext:
    """Context passed to all node executors during graph execution."""
    pipeline_input: PipelineInput
    snr_override: float | None = None
    noise_type_override: str | None = None
    echo_config_override: Any | None = None
    # Accumulated metadata
    metadata: dict[str, Any] = field(default_factory=dict)
