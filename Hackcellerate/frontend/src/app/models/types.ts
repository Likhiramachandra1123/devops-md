export type SourceType =
  | "knowledge_base"
  | "uploaded_document"
  | "general_knowledge"
  | "none";

export interface Citation {
  index: number;
  title: string;
  source: string;
  url?: string | null;
  doc_id?: string | null;
  chunk_id?: string | null;
  distance: number;
  snippet: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  summary: string;
  citations: Citation[];
  used_rag: boolean;
  grounded: boolean;
  source_type: SourceType;
  source_info: Record<string, unknown>;
  model: string;
  usage: Record<string, number>;
}

export interface SearchResult {
  index: number;
  title: string;
  source: string;
  url?: string | null;
  doc_id?: string | null;
  chunk_id?: string | null;
  distance: number;
  score: number;
  snippet: string;
  text?: string;
  metadata: Record<string, unknown>;
}

export interface SearchResponse {
  session_id: string;
  query: string;
  results: SearchResult[];
  total: number;
  summary?: string | null;
}

export type Role = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  createdAt: number;
  citations?: Citation[];
  sourceType?: SourceType;
  sourceInfo?: Record<string, unknown>;
  attachment?: { name: string; size: number };
  isError?: boolean;
  isLoading?: boolean;
}

export interface HealthResponse {
  status: string;
  version: string;
  model: string;
  embedding_model: string;
  vector_store_count: number;
}

export interface SessionInfo {
  session_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  title?: string | null;
}

export interface SessionListResponse {
  sessions: SessionInfo[];
}

export interface StoredMessage {
  role: Role;
  content: string;
  created_at: string;
}

export interface SessionMessagesResponse {
  session_id: string;
  messages: StoredMessage[];
}

export interface ModelInfo {
  id: string;
  display_name: string;
  family: string;
  context_window: number;
  input_price_per_mtok: number | null;
  output_price_per_mtok: number | null;
  created_at?: string | null;
  is_default: boolean;
  pricing_known: boolean;
  description?: string | null;
}

export interface ModelsResponse {
  models: ModelInfo[];
  default_model: string;
  source: "api" | "static";
}
