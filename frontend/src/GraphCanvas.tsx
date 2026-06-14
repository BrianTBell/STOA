import { useEffect, useState } from "react";
import {
  SigmaContainer,
  useLoadGraph,
  useRegisterEvents,
  useSigma,
} from "@react-sigma/core";
import type { NodeDisplayData, PartialButFor } from "sigma/types";
import { NodeCircleProgram } from "sigma/rendering";
import type {
  NodeHoverDrawingFunction,
  NodeLabelDrawingFunction,
} from "sigma/rendering";
import "@react-sigma/core/lib/style.css";

import { buildAtlasGraph } from "./atlas";
import { NodeDiamondProgram, NodeRingProgram } from "./nodePrograms";
import type {
  AtlasEdge,
  AtlasNode,
  GraphPayload,
  Paper,
} from "./types";

type GraphCanvasProps = {
  payload: GraphPayload;
  selectedId: string | null;
  focusId: string | null;
  onSelectPaper: (paper: Paper | null) => void;
  onSelectRegion: (label: string, kind: "domain" | "concept") => void;
  onFocusComplete: () => void;
};

type AtlasControlsProps = Omit<GraphCanvasProps, "payload">;

const drawAtlasHover: NodeHoverDrawingFunction<AtlasNode, AtlasEdge> = (
  _context,
  _data,
  _settings,
) => {
  return;
};

function drawPaperLabel(
  context: CanvasRenderingContext2D,
  data: PartialButFor<NodeDisplayData, "x" | "y" | "size" | "label" | "color">,
  settings: {
    labelSize: number;
    labelFont: string;
    labelWeight: string;
  },
) {
  if (!data.label) return;
  const size = settings.labelSize;
  context.font = `${settings.labelWeight} ${size}px ${settings.labelFont}`;
  const lines = wrapLabel(context, data.label, 240);
  const textWidth = Math.max(...lines.map((line) => context.measureText(line).width));
  const lineHeight = size * 1.18;
  const paddingX = 8;
  const paddingY = 4;
  const boxWidth = Math.round(textWidth + paddingX * 2);
  const boxHeight = Math.round(lines.length * lineHeight + paddingY * 2);
  const left = data.x + data.size + 10;
  const top = data.y - boxHeight / 2;

  context.fillStyle = data.highlighted
    ? "rgba(14, 28, 45, 0.98)"
    : "rgba(7, 16, 29, 0.96)";
  context.shadowOffsetX = 0;
  context.shadowOffsetY = 0;
  context.shadowBlur = 8;
  context.shadowColor = "rgba(0, 0, 0, 0.72)";

  context.beginPath();
  context.roundRect(left, top, boxWidth, boxHeight, 6);
  context.fill();

  context.shadowOffsetX = 0;
  context.shadowOffsetY = 0;
  context.shadowBlur = 0;
  context.fillStyle = "#f0e7d2";
  const startY = data.y - ((lines.length - 1) * lineHeight) / 2;

  lines.forEach((line, index) => {
    context.fillText(
      line,
      left + paddingX,
      startY + index * lineHeight + size / 3,
    );
  });
}

function wrapLabel(
  context: CanvasRenderingContext2D,
  label: string,
  maxWidth: number,
): string[] {
  const words = label.split(/\s+/);
  const lines: string[] = [];
  let currentLine = "";

  for (const word of words) {
    const candidate = currentLine ? `${currentLine} ${word}` : word;
    if (currentLine && context.measureText(candidate).width > maxWidth) {
      lines.push(currentLine);
      currentLine = word;
    } else {
      currentLine = candidate;
    }
  }
  if (currentLine) lines.push(currentLine);
  return lines;
}

const drawAtlasLabel: NodeLabelDrawingFunction<AtlasNode, AtlasEdge> = (
  context,
  data,
  settings,
) => {
  if (!data.label) return;
  if (data.type === "circle") {
    drawPaperLabel(context, data, settings);
    return;
  }

  const size = data.type === "ring" ? settings.labelSize + 1 : settings.labelSize;
  context.fillStyle = "#e8e4d9";
  context.font = `${data.type === "ring" ? "700" : settings.labelWeight} ${size}px ${settings.labelFont}`;
  const maxWidth = data.type === "circle" ? 240 : 170;
  const lines = wrapLabel(context, data.label, maxWidth);
  const lineHeight = size * 1.18;
  const startY = data.y - ((lines.length - 1) * lineHeight) / 2;

  lines.forEach((line, index) => {
    context.fillText(
      line,
      data.x + data.size + 5,
      startY + index * lineHeight + size / 3,
    );
  });
};

function AtlasControls({
  selectedId,
  focusId,
  onSelectPaper,
  onSelectRegion,
  onFocusComplete,
}: AtlasControlsProps) {
  const sigma = useSigma<AtlasNode, AtlasEdge>();
  const registerEvents = useRegisterEvents<AtlasNode, AtlasEdge>();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [zoomRatio, setZoomRatio] = useState(1);

  function focusNode(node: string, ratio: number) {
    const displayData = sigma.getNodeDisplayData(node);
    if (!displayData) return;
    sigma.getCamera().animate(
      { x: displayData.x, y: displayData.y, ratio },
      { duration: 650 },
    );
  }

  useEffect(() => {
    registerEvents({
      clickNode: ({ node }) => {
        const attributes = sigma.getGraph().getNodeAttributes(node);
        focusNode(node, attributes.nodeType === "paper" ? 0.28 : 0.55);
        if (attributes.nodeType === "paper" && attributes.paper) {
          onSelectPaper(attributes.paper);
        } else if (
          attributes.nodeType === "domain" ||
          attributes.nodeType === "concept"
        ) {
          onSelectPaper(null);
          onSelectRegion(
            attributes.nodeType === "domain"
              ? attributes.domain
              : attributes.concept || attributes.domain,
            attributes.nodeType,
          );
        }
      },
      clickStage: () => onSelectPaper(null),
      enterNode: ({ node }) => setHoveredId(node),
      leaveNode: () => setHoveredId(null),
    });
  }, [onSelectPaper, onSelectRegion, registerEvents, sigma]);

  useEffect(() => {
    const camera = sigma.getCamera();
    const updateRatio = () => setZoomRatio(camera.getState().ratio);
    updateRatio();
    camera.on("updated", updateRatio);
    return () => {
      camera.off("updated", updateRatio);
    };
  }, [sigma]);

  useEffect(() => {
    if (!focusId || !sigma.getGraph().hasNode(focusId)) {
      return;
    }
    focusNode(focusId, 0.26);
    onFocusComplete();
  }, [focusId, onFocusComplete, sigma]);

  useEffect(() => {
    const graph = sigma.getGraph();
    const activeId = hoveredId || selectedId;
    const neighborhood = new Set<string>();
    if (activeId && graph.hasNode(activeId)) {
      neighborhood.add(activeId);
      graph.neighbors(activeId).forEach((node) => neighborhood.add(node));
    }

    sigma.setSetting("nodeReducer", (node, data) => {
      const result: PartialButFor<NodeDisplayData, "x" | "y" | "label"> = {
        ...data,
      };
      const attributes = graph.getNodeAttributes(node);
      result.highlighted = node === hoveredId;
      result.selected = node === selectedId;

      if (attributes.nodeType === "domain") {
        result.label = attributes.label.toUpperCase();
        result.size = data.size * (zoomRatio > 1.2 ? 0.9 : 1);
        result.forceLabel = true;
        result.zIndex = 3;
      } else if (attributes.nodeType === "concept") {
        result.label = zoomRatio < 0.78 ? attributes.label : "";
        result.size = zoomRatio < 1.4 ? data.size : 2.2;
        result.forceLabel = zoomRatio < 0.78;
        result.zIndex = 2;
      } else {
        const paperLabelsVisible = zoomRatio < 0.72;
        result.label =
          paperLabelsVisible && (zoomRatio < 0.48 || node === activeId)
            ? attributes.label
            : "";
        result.zIndex = node === activeId ? 5 : 1;
      }

      if (activeId && !neighborhood.has(node)) {
        if (attributes.nodeType === "paper") result.label = "";
      } else if (node === activeId || node === selectedId) {
        result.size = data.size * 1.65;
      }
      return result;
    });

    sigma.setSetting("edgeReducer", (edge, data) => {
      if (!activeId) {
        return { ...data, color: "#334055", size: data.size * 0.75 };
      }
      const [source, target] = graph.extremities(edge);
      const connected = source === activeId || target === activeId;
      const chosenByActivePaper =
        connected && data.nominatedBy.includes(activeId);
      return {
        ...data,
        color: chosenByActivePaper
          ? "#d9b978"
          : connected
            ? "#66748d"
            : "#172131",
        size: connected ? Math.max(1.4, data.size * 1.8) : 0.25,
        hidden: !connected,
      };
    });
    sigma.refresh();
  }, [hoveredId, selectedId, sigma, zoomRatio]);

  return null;
}

function GraphLoader({
  payload,
  ...controls
}: GraphCanvasProps) {
  const loadGraph = useLoadGraph<AtlasNode, AtlasEdge>();

  useEffect(() => {
    loadGraph(buildAtlasGraph(payload));
  }, [loadGraph, payload]);

  return <AtlasControls {...controls} />;
}

export default function GraphCanvas(props: GraphCanvasProps) {
  return (
    <SigmaContainer<AtlasNode, AtlasEdge>
      className="atlas-canvas"
      settings={{
        allowInvalidContainer: true,
        defaultDrawNodeHover: drawAtlasHover,
        defaultDrawNodeLabel: drawAtlasLabel,
        defaultNodeColor: "#f2b96f",
        defaultEdgeColor: "#334055",
        labelColor: { color: "#e8e4d9" },
        labelFont: "Aptos, Trebuchet MS, sans-serif",
        labelSize: 12,
        labelWeight: "500",
        nodeProgramClasses: {
          circle: NodeCircleProgram,
          diamond: NodeDiamondProgram,
          ring: NodeRingProgram,
        },
        renderEdgeLabels: false,
        stagePadding: 48,
        zIndex: true,
      }}
    >
      <GraphLoader {...props} />
    </SigmaContainer>
  );
}
