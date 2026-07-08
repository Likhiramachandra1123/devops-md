import { HttpClient } from "@angular/common/http";
import { Injectable, inject } from "@angular/core";
import { Observable } from "rxjs";
import {
  ChatResponse,
  HealthResponse,
  ModelsResponse,
  SearchResponse,
  SessionListResponse,
  SessionMessagesResponse,
} from "../models/types";

const BASE = "/api";

@Injectable({ providedIn: "root" })
export class ApiService {
  private http = inject(HttpClient);

  chat(params: {
    message: string;
    sessionId?: string | null;
    useRag?: boolean;
    model?: string | null;
  }): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${BASE}/chat`, {
      message: params.message,
      session_id: params.sessionId ?? undefined,
      use_rag: params.useRag ?? true,
      model: params.model ?? undefined,
    });
  }

  search(params: {
    message: string;
    sessionId?: string | null;
    topK?: number;
    model?: string | null;
  }): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(`${BASE}/chat/search`, {
      message: params.message,
      session_id: params.sessionId ?? undefined,
      top_k: params.topK,
      model: params.model ?? undefined,
    });
  }

  chatWithUpload(params: {
    message: string;
    file: File;
    sessionId?: string | null;
    model?: string | null;
  }): Observable<ChatResponse> {
    const form = new FormData();
    form.append("message", params.message);
    form.append("file", params.file);
    if (params.sessionId) form.append("session_id", params.sessionId);
    if (params.model) form.append("model", params.model);
    return this.http.post<ChatResponse>(`${BASE}/chat/upload`, form);
  }

  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${BASE}/health`);
  }

  listModels(): Observable<ModelsResponse> {
    return this.http.get<ModelsResponse>(`${BASE}/models`);
  }

  listSessions(limit = 100): Observable<SessionListResponse> {
    return this.http.get<SessionListResponse>(`${BASE}/sessions`, {
      params: { limit: String(limit) },
    });
  }

  getSessionMessages(sessionId: string, limit = 200): Observable<SessionMessagesResponse> {
    return this.http.get<SessionMessagesResponse>(`${BASE}/sessions/${sessionId}/messages`, {
      params: { limit: String(limit) },
    });
  }

  deleteSession(sessionId: string): Observable<{ deleted: string }> {
    return this.http.delete<{ deleted: string }>(`${BASE}/sessions/${sessionId}`);
  }
}
