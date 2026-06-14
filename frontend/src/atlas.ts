import Graph from "graphology";

import type {
  AtlasEdge,
  AtlasNode,
  GraphPayload,
  Paper,
} from "./types";

type Point = { x: number; y: number };

type DomainLink = {
  source: string;
  target: string;
  strength: number;
};

function hashText(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

function hslToHex(hue: number, saturation: number, lightness: number): string {
  const saturationRatio = saturation / 100;
  const lightnessRatio = lightness / 100;
  const chroma =
    (1 - Math.abs(2 * lightnessRatio - 1)) * saturationRatio;
  const hueSegment = hue / 60;
  const intermediate = chroma * (1 - Math.abs((hueSegment % 2) - 1));
  const [red, green, blue] =
    hueSegment < 1
      ? [chroma, intermediate, 0]
      : hueSegment < 2
        ? [intermediate, chroma, 0]
        : hueSegment < 3
          ? [0, chroma, intermediate]
          : hueSegment < 4
            ? [0, intermediate, chroma]
            : hueSegment < 5
              ? [intermediate, 0, chroma]
              : [chroma, 0, intermediate];
  const offset = lightnessRatio - chroma / 2;
  return `#${[red, green, blue]
    .map((channel) =>
      Math.round((channel + offset) * 255)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

export function normalizedDomain(paper: Paper): string {
  return paper.domain?.trim() || "Uncharted";
}

export function primaryConcept(paper: Paper): string {
  const domain = normalizedDomain(paper).toLowerCase();
  return (
    paper.concepts.find(
      (concept) => concept.trim() && concept.trim().toLowerCase() !== domain,
    )?.trim() || ""
  );
}

export function colorForDomain(domain: string): string {
  return hslToHex(hashText(domain) % 360, 68, 68);
}

function domainPairKey(left: string, right: string): string {
  return [left, right].sort().join("\u0000");
}

function buildDomainLinks(
  payload: GraphPayload,
  paperDomains: Map<string, string>,
): DomainLink[] {
  const links = new Map<string, DomainLink>();

  payload.edges.forEach((edge) => {
    const source = paperDomains.get(edge.source_id);
    const target = paperDomains.get(edge.target_id);
    if (!source || !target || source === target) return;

    const key = domainPairKey(source, target);
    const existing = links.get(key);
    const strength = Math.max(0.1, (edge.score - 0.6) / 0.4);
    if (existing) {
      existing.strength += strength;
    } else {
      const [orderedSource, orderedTarget] = [source, target].sort();
      links.set(key, {
        source: orderedSource,
        target: orderedTarget,
        strength,
      });
    }
  });

  return [...links.values()];
}

function layoutDomainCenters(
  domains: string[],
  protectedRadii: Map<string, number>,
  links: DomainLink[],
): Map<string, Point> {
  const centers = new Map<string, Point>();
  if (domains.length === 1) {
    centers.set(domains[0], { x: 0, y: 0 });
    return centers;
  }

  const initialRadius = Math.max(90, domains.length * 28);
  domains.forEach((domain, index) => {
    const angle =
      (Math.PI * 2 * index) / domains.length +
      ((hashText(domain) % 60) - 30) / 100;
    centers.set(domain, {
      x: Math.cos(angle) * initialRadius,
      y: Math.sin(angle) * initialRadius,
    });
  });

  const velocities = new Map(
    domains.map((domain) => [domain, { x: 0, y: 0 }]),
  );

  for (let iteration = 0; iteration < 180; iteration += 1) {
    const forces = new Map(
      domains.map((domain) => [domain, { x: 0, y: 0 }]),
    );

    for (let leftIndex = 0; leftIndex < domains.length; leftIndex += 1) {
      for (
        let rightIndex = leftIndex + 1;
        rightIndex < domains.length;
        rightIndex += 1
      ) {
        const left = domains[leftIndex];
        const right = domains[rightIndex];
        const leftPoint = centers.get(left)!;
        const rightPoint = centers.get(right)!;
        const dx = rightPoint.x - leftPoint.x;
        const dy = rightPoint.y - leftPoint.y;
        const distance = Math.max(Math.hypot(dx, dy), 0.01);
        const unitX = dx / distance;
        const unitY = dy / distance;
        const minimumDistance =
          protectedRadii.get(left)! + protectedRadii.get(right)! + 18;
        const repulsion = 1800 / Math.max(distance * distance, 100);
        const collision =
          distance < minimumDistance
            ? (minimumDistance - distance) * 0.09
            : 0;
        const force = repulsion + collision;

        forces.get(left)!.x -= unitX * force;
        forces.get(left)!.y -= unitY * force;
        forces.get(right)!.x += unitX * force;
        forces.get(right)!.y += unitY * force;
      }
    }

    links.forEach((link) => {
      const sourcePoint = centers.get(link.source)!;
      const targetPoint = centers.get(link.target)!;
      const dx = targetPoint.x - sourcePoint.x;
      const dy = targetPoint.y - sourcePoint.y;
      const distance = Math.max(Math.hypot(dx, dy), 0.01);
      const unitX = dx / distance;
      const unitY = dy / distance;
      const desiredDistance =
        protectedRadii.get(link.source)! +
        protectedRadii.get(link.target)! +
        28;
      const attraction =
        (distance - desiredDistance) *
        0.004 *
        Math.min(link.strength, 3);

      forces.get(link.source)!.x += unitX * attraction;
      forces.get(link.source)!.y += unitY * attraction;
      forces.get(link.target)!.x -= unitX * attraction;
      forces.get(link.target)!.y -= unitY * attraction;
    });

    domains.forEach((domain) => {
      const point = centers.get(domain)!;
      const force = forces.get(domain)!;
      const velocity = velocities.get(domain)!;
      force.x -= point.x * 0.0008;
      force.y -= point.y * 0.0008;
      velocity.x = (velocity.x + force.x) * 0.78;
      velocity.y = (velocity.y + force.y) * 0.78;
      const speed = Math.max(Math.hypot(velocity.x, velocity.y), 0.01);
      const scale = speed > 4 ? 4 / speed : 1;
      point.x += velocity.x * scale;
      point.y += velocity.y * scale;
    });
  }

  // The force pass gets regions close; this final pass guarantees no overlap.
  for (let pass = 0; pass < 40; pass += 1) {
    for (let leftIndex = 0; leftIndex < domains.length; leftIndex += 1) {
      for (
        let rightIndex = leftIndex + 1;
        rightIndex < domains.length;
        rightIndex += 1
      ) {
        const left = domains[leftIndex];
        const right = domains[rightIndex];
        const leftPoint = centers.get(left)!;
        const rightPoint = centers.get(right)!;
        let dx = rightPoint.x - leftPoint.x;
        let dy = rightPoint.y - leftPoint.y;
        let distance = Math.hypot(dx, dy);
        if (distance < 0.01) {
          const angle = ((hashText(`${left}:${right}`) % 360) * Math.PI) / 180;
          dx = Math.cos(angle);
          dy = Math.sin(angle);
          distance = 1;
        }
        const minimumDistance =
          protectedRadii.get(left)! + protectedRadii.get(right)! + 18;
        if (distance >= minimumDistance) continue;

        const shift = (minimumDistance - distance) / 2;
        const unitX = dx / distance;
        const unitY = dy / distance;
        leftPoint.x -= unitX * shift;
        leftPoint.y -= unitY * shift;
        rightPoint.x += unitX * shift;
        rightPoint.y += unitY * shift;
      }
    }
  }

  const centroid = domains.reduce(
    (total, domain) => {
      const point = centers.get(domain)!;
      return { x: total.x + point.x, y: total.y + point.y };
    },
    { x: 0, y: 0 },
  );
  centroid.x /= domains.length;
  centroid.y /= domains.length;
  domains.forEach((domain) => {
    const point = centers.get(domain)!;
    point.x -= centroid.x;
    point.y -= centroid.y;
  });

  return centers;
}

export function buildAtlasGraph(payload: GraphPayload): Graph<AtlasNode, AtlasEdge> {
  const graph = new Graph<AtlasNode, AtlasEdge>({
    multi: false,
    type: "undirected",
  });
  const domains = [...new Set(payload.papers.map(normalizedDomain))].sort();
  const papersByDomain = new Map<string, Paper[]>();
  const paperDomains = new Map<string, string>();

  payload.papers.forEach((paper) => {
    const domain = normalizedDomain(paper);
    papersByDomain.set(domain, [...(papersByDomain.get(domain) || []), paper]);
    paperDomains.set(paper.id, domain);
  });

  const protectedRadii = new Map(
    domains.map((domain) => {
      const domainPapers = papersByDomain.get(domain) || [];
      const conceptCount = new Set(
        domainPapers.map(primaryConcept).filter(Boolean),
      ).size;
      return [
        domain,
        42 +
          Math.sqrt(domainPapers.length) * 6.5 +
          Math.sqrt(conceptCount) * 5,
      ];
    }),
  );
  const domainCenters = layoutDomainCenters(
    domains,
    protectedRadii,
    buildDomainLinks(payload, paperDomains),
  );

  domains.forEach((domain) => {
    const { x: centerX, y: centerY } = domainCenters.get(domain)!;
    const color = colorForDomain(domain);
    const domainPapers = papersByDomain.get(domain) || [];
    const domainNodeId = `domain::${domain}`;

    graph.addNode(domainNodeId, {
      label: `FIELD / ${domain}`,
      type: "ring",
      x: centerX,
      y: centerY,
      size: 3.2 + Math.min(Math.sqrt(domainPapers.length), 3),
      color,
      nodeType: "domain",
      domain,
    });

    const concepts = [
      ...new Set(domainPapers.map(primaryConcept).filter(Boolean)),
    ].sort();
    const conceptCenters = new Map<string, { x: number; y: number }>();
    concepts.forEach((concept, conceptIndex) => {
      const conceptAngle =
        (Math.PI * 2 * conceptIndex) / Math.max(concepts.length, 1) +
        (hashText(concept) % 80) / 100;
      const conceptDistance = 18 + (conceptIndex % 3) * 9;
      const conceptX = centerX + Math.cos(conceptAngle) * conceptDistance;
      const conceptY = centerY + Math.sin(conceptAngle) * conceptDistance;
      const conceptNodeId = `concept::${domain}::${concept}`;
      conceptCenters.set(concept, { x: conceptX, y: conceptY });

      graph.addNode(conceptNodeId, {
        label: concept,
        type: "diamond",
        x: conceptX,
        y: conceptY,
        size: 2.7,
        color,
        nodeType: "concept",
        domain,
        concept,
      });
    });

    domainPapers.forEach((paper, paperIndex) => {
      const concept = primaryConcept(paper);
      const anchor = conceptCenters.get(concept) || { x: centerX, y: centerY };
      const paperHash = hashText(paper.id);
      const paperAngle = ((paperHash % 360) * Math.PI) / 180;
      const orbit =
        6.5 + (paperIndex % 5) * 2.1 + ((paperHash >> 4) % 30) / 8;

      graph.addNode(paper.id, {
        label: paper.title || "Untitled paper",
        type: "circle",
        x: anchor.x + Math.cos(paperAngle) * orbit,
        y: anchor.y + Math.sin(paperAngle) * orbit,
        size: 3.4 + Math.min(paper.concepts.length, 5) * 0.34,
        color,
        nodeType: "paper",
        domain,
        concept,
        paper,
      });
    });
  });

  payload.edges.forEach((edge, index) => {
    if (!graph.hasNode(edge.source_id) || !graph.hasNode(edge.target_id)) {
      return;
    }
    graph.addEdgeWithKey(`similarity::${index}`, edge.source_id, edge.target_id, {
      size: Math.max(0.4, (edge.score - 0.72) * 5),
      color: "#66748d",
      score: edge.score,
      nominatedBy: edge.nominated_by,
    });
  });

  return graph;
}
