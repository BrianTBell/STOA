import { NodeCircleProgram } from "sigma/rendering";

import type { AtlasEdge, AtlasNode } from "./types";

const DIAMOND_FRAGMENT_SHADER = `
precision highp float;

varying vec4 v_color;
varying vec2 v_diffVector;
varying float v_radius;

uniform float u_correctionRatio;

const vec4 transparent = vec4(0.0, 0.0, 0.0, 0.0);

void main(void) {
  float border = u_correctionRatio * 2.0;
  float dist = abs(v_diffVector.x) + abs(v_diffVector.y) - v_radius;

  #ifdef PICKING_MODE
  gl_FragColor = dist > 0.0 ? transparent : v_color;
  #else
  float alpha = 1.0 - smoothstep(-border, border, dist);
  gl_FragColor = mix(transparent, v_color, alpha);
  #endif
}
`;

const RING_FRAGMENT_SHADER = `
precision highp float;

varying vec4 v_color;
varying vec2 v_diffVector;
varying float v_radius;

uniform float u_correctionRatio;

const vec4 transparent = vec4(0.0, 0.0, 0.0, 0.0);

void main(void) {
  float outerBorder = u_correctionRatio * 2.0;
  float ringWidth = max(u_correctionRatio * 3.0, v_radius * 0.28);
  float distanceFromCenter = length(v_diffVector);

  #ifdef PICKING_MODE
  gl_FragColor = distanceFromCenter > v_radius ? transparent : v_color;
  #else
  float outerAlpha = 1.0 - smoothstep(
    v_radius - outerBorder,
    v_radius + outerBorder,
    distanceFromCenter
  );
  float innerAlpha = smoothstep(
    v_radius - ringWidth - outerBorder,
    v_radius - ringWidth + outerBorder,
    distanceFromCenter
  );
  gl_FragColor = mix(transparent, v_color, outerAlpha * innerAlpha);
  #endif
}
`;

export class NodeDiamondProgram extends NodeCircleProgram<AtlasNode, AtlasEdge> {
  getDefinition() {
    return {
      ...super.getDefinition(),
      FRAGMENT_SHADER_SOURCE: DIAMOND_FRAGMENT_SHADER,
    };
  }
}

export class NodeRingProgram extends NodeCircleProgram<AtlasNode, AtlasEdge> {
  getDefinition() {
    return {
      ...super.getDefinition(),
      FRAGMENT_SHADER_SOURCE: RING_FRAGMENT_SHADER,
    };
  }
}
