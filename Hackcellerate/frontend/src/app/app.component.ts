import { CommonModule } from "@angular/common";
import { Component, OnInit, computed, inject, signal } from "@angular/core";
import { AppShellComponent } from "./components/app-shell/app-shell.component";
import { ChatPanelComponent } from "./components/chat-panel/chat-panel.component";
import { SendPayload } from "./components/composer/composer.component";
import { SplitLayoutComponent } from "./components/split-layout/split-layout.component";
import { WelcomeViewComponent } from "./components/welcome-view/welcome-view.component";
import { ChatMessage, Citation, SearchResult, SessionInfo, StoredMessage } from "./models/types";
import { ApiService } from "./services/api.service";

let idSeed = 0;
const nid = () => `${Date.now()}-${++idSeed}`;

@Component({
  selector: "app-root",
  standalone: true,
  imports: [
    CommonModule,
    AppShellComponent,
    WelcomeViewComponent,
    SplitLayoutComponent,
    ChatPanelComponent,
  ],
  host: { class: "block h-screen min-h-0 overflow-hidden" },
  template: `
    <app-shell
      [backendStatus]="backendStatus()"
      [sessions]="sessions()"
      [activeSessionId]="sessionId()"
      (newChat)="onNewChat()"
      (openSession)="onOpenSession($event)"
      (deleteSession)="onDeleteSession($event)"
      (refreshSessions)="refreshSessions()"
      (modelChange)="onModelChange($event)"
    >
      @if (splitOpen()) {
        <app-split-layout
          [results]="results()"
          [query]="lastQuery()"
          [summary]="summary()"
          [messages]="messages()"
          [loading]="loading()"
          [chatVisible]="!chatHidden()"
          (send)="onSend($event)"
          (closePanel)="closePanel()"
          (closeChat)="closeChat()"
          (openChat)="reopenChat()"
        ></app-split-layout>
      } @else if (messages().length > 0) {
        <div class="mx-auto flex h-full min-h-0 max-w-4xl flex-col">
          @if (hasHiddenResults()) {
            <div class="flex shrink-0 items-center justify-between border-b border-brand-100 bg-brand-50/60 px-4 py-2">
              <div class="text-xs text-brand-800">
                <span class="font-semibold">{{ results().length }}</span> search result{{ results().length === 1 ? '' : 's' }} available
                @if (lastQuery()) { for <span class="font-medium">"{{ lastQuery() }}"</span> }
              </div>
              <button
                type="button"
                (click)="reopenPanel()"
                class="rounded-md bg-brand-600 px-3 py-1 text-xs font-medium text-white shadow-sm hover:bg-brand-700"
              >
                Show results
              </button>
            </div>
          }
          <div class="min-h-0 flex-1">
            <app-chat-panel
              [messages]="messages()"
              [loading]="loading()"
              (send)="onSend($event)"
            ></app-chat-panel>
          </div>
        </div>
      } @else {
        <app-welcome-view (send)="onSend($event)"></app-welcome-view>
      }
    </app-shell>
  `,
})
export class AppComponent implements OnInit {
  private api = inject(ApiService);

  readonly backendStatus = signal<"online" | "offline" | "checking">("checking");
  readonly sessionId = signal<string | null>(null);
  readonly messages = signal<ChatMessage[]>([]);
  readonly results = signal<SearchResult[]>([]);
  readonly summary = signal<string | null | undefined>(undefined);
  readonly lastQuery = signal<string>("");
  readonly loading = signal<boolean>(false);
  readonly sessions = signal<SessionInfo[]>([]);
  readonly panelHidden = signal<boolean>(false);
  readonly chatHidden = signal<boolean>(false);
  readonly selectedModel = signal<string | null>(null);

  readonly splitOpen = computed(() => this.results().length > 0 && !this.panelHidden());
  readonly hasHiddenResults = computed(
    () => this.results().length > 0 && this.panelHidden(),
  );

  ngOnInit(): void {
    this.pingBackend();
    this.refreshSessions();
  }

  private pingBackend() {
    this.api.health().subscribe({
      next: () => this.backendStatus.set("online"),
      error: () => this.backendStatus.set("offline"),
    });
  }

  refreshSessions() {
    this.api.listSessions(100).subscribe({
      next: (res) => this.sessions.set(res.sessions),
      error: () => this.sessions.set([]),
    });
  }

  onOpenSession(id: string) {
    this.api.getSessionMessages(id, 200).subscribe({
      next: (res) => {
        this.sessionId.set(id);
        this.results.set([]);
        this.summary.set(undefined);
        this.lastQuery.set("");
        this.panelHidden.set(false);
        this.chatHidden.set(false);
        this.messages.set(res.messages.map((m) => this.hydrate(m)));
      },
      error: (err) => {
        this.messages.set([]);
        this.messages.update((prev) => [
          ...prev,
          {
            id: nid(),
            role: "assistant",
            content: this.errText(err),
            createdAt: Date.now(),
            isError: true,
            sourceType: "none",
          },
        ]);
      },
    });
  }

  onDeleteSession(id: string) {
    this.api.deleteSession(id).subscribe({
      next: () => {
        if (this.sessionId() === id) this.onNewChat();
        this.refreshSessions();
      },
    });
  }

  private hydrate(m: StoredMessage): ChatMessage {
    return {
      id: nid(),
      role: m.role,
      content: m.content,
      createdAt: new Date(m.created_at).getTime() || Date.now(),
    };
  }

  onNewChat() {
    this.messages.set([]);
    this.results.set([]);
    this.summary.set(undefined);
    this.lastQuery.set("");
    this.sessionId.set(null);
    this.panelHidden.set(false);
    this.chatHidden.set(false);
  }

  closePanel() {
    // Hide (keep results cached so the user can reopen)
    this.panelHidden.set(true);
  }

  reopenPanel() {
    this.panelHidden.set(false);
  }

  closeChat() {
    this.chatHidden.set(true);
  }

  reopenChat() {
    this.chatHidden.set(false);
  }

  onModelChange(modelId: string) {
    this.selectedModel.set(modelId);
  }

  onSend(payload: SendPayload) {
    if (payload.mode === "search") {
      this.runSearch(payload.message);
    } else if (payload.file) {
      this.runUpload(payload.message, payload.file);
    } else {
      this.runChat(payload.message);
    }
  }

  private pushUser(content: string, attachment?: { name: string; size: number }) {
    const m: ChatMessage = {
      id: nid(),
      role: "user",
      content,
      createdAt: Date.now(),
      attachment,
    };
    this.messages.update((prev) => [...prev, m]);
  }

  private pushLoading(): string {
    const id = nid();
    this.messages.update((prev) => [
      ...prev,
      { id, role: "assistant", content: "", createdAt: Date.now(), isLoading: true },
    ]);
    return id;
  }

  private replaceMessage(id: string, patch: Partial<ChatMessage>) {
    this.messages.update((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...patch, isLoading: false } : m))
    );
  }

  private citationsToResults(citations: Citation[]): SearchResult[] {
    return citations.map((c) => ({
      index: c.index,
      title: c.title,
      source: c.source,
      url: c.url ?? null,
      doc_id: c.doc_id ?? null,
      chunk_id: c.chunk_id ?? null,
      distance: c.distance,
      score: Math.max(0, Math.min(1, 1 - c.distance)),
      snippet: c.snippet,
      metadata: {},
    }));
  }

  private showCitationsAsResults(query: string, citations: Citation[]) {
    if (!citations || citations.length === 0) return;
    this.lastQuery.set(query);
    this.results.set(this.citationsToResults(citations));
    this.summary.set(undefined);
    this.panelHidden.set(false);
  }

  private runChat(message: string) {
    this.pushUser(message);
    const loadingId = this.pushLoading();
    this.loading.set(true);
    this.api.chat({ message, sessionId: this.sessionId(), model: this.selectedModel() }).subscribe({
      next: (res) => {
        this.sessionId.set(res.session_id);
        this.replaceMessage(loadingId, {
          content: res.answer,
          citations: res.citations,
          sourceType: res.source_type,
          sourceInfo: res.source_info,
        });
        this.showCitationsAsResults(message, res.citations);
        this.loading.set(false);
        this.refreshSessions();
      },
      error: (err) => {
        this.replaceMessage(loadingId, {
          content: this.errText(err),
          isError: true,
          sourceType: "none",
        });
        this.loading.set(false);
      },
    });
  }

  private runUpload(message: string, file: File) {
    this.pushUser(message, { name: file.name, size: file.size });
    const loadingId = this.pushLoading();
    this.loading.set(true);
    this.api.chatWithUpload({ message, file, sessionId: this.sessionId(), model: this.selectedModel() }).subscribe({
      next: (res) => {
        this.sessionId.set(res.session_id);
        this.replaceMessage(loadingId, {
          content: res.answer,
          citations: res.citations,
          sourceType: res.source_type,
          sourceInfo: res.source_info,
        });
        this.showCitationsAsResults(message, res.citations);
        this.loading.set(false);
        this.refreshSessions();
      },
      error: (err) => {
        this.replaceMessage(loadingId, {
          content: this.errText(err),
          isError: true,
          sourceType: "none",
        });
        this.loading.set(false);
      },
    });
  }

  private runSearch(message: string) {
    this.pushUser(message);
    this.lastQuery.set(message);
    this.loading.set(true);
    this.api.search({ message, sessionId: this.sessionId(), topK: 1000, model: this.selectedModel() }).subscribe({
      next: (res) => {
        this.sessionId.set(res.session_id);
        this.results.set(res.results);
        this.summary.set(res.summary);
        this.panelHidden.set(false);
        this.chatHidden.set(false);
        this.loading.set(false);
        this.messages.update((prev) => [
          ...prev,
          {
            id: nid(),
            role: "assistant",
            content: `Found ${res.results.length} result${res.results.length === 1 ? "" : "s"}. See the table on the left — click a row to view its snippet.`,
            createdAt: Date.now(),
            sourceType: "knowledge_base",
          },
        ]);
        this.refreshSessions();
      },
      error: (err) => {
        this.loading.set(false);
        this.messages.update((prev) => [
          ...prev,
          {
            id: nid(),
            role: "assistant",
            content: this.errText(err),
            createdAt: Date.now(),
            isError: true,
            sourceType: "none",
          },
        ]);
      },
    });
  }

  private errText(err: any): string {
    const status = err?.status ?? "?";
    const msg = err?.error?.detail || err?.error?.message || err?.message || "Request failed";
    return `Request failed (HTTP ${status}): ${msg}`;
  }
}
