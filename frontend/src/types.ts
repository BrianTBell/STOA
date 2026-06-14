export type Paper = {
  id: string;
  source_url: string;
  title: string | null;
  authors: string[];
  published: string | null;
  summary: string | null;
  concepts: string[];
  methods: string[];
  domain: string | null;
  created_at: string;
  updated_at: string;
};

export type SimilarityEdge = {
  source_id: string;
  target_id: string;
  score: number;
  nominated_by: string[];
  created_at: string;
  updated_at: string;
};

export type GraphPayload = {
  papers: Paper[];
  edges: SimilarityEdge[];
};

export type AtlasNodeType = "domain" | "concept" | "paper";

export type AtlasNode = {
  label: string;
  type: "circle" | "diamond" | "ring";
  x: number;
  y: number;
  size: number;
  color: string;
  nodeType: AtlasNodeType;
  domain: string;
  concept?: string;
  paper?: Paper;
};

export type AtlasEdge = {
  size: number;
  color: string;
  score: number;
  nominatedBy: string[];
};
