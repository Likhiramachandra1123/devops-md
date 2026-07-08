import { CommonModule } from "@angular/common";
import { Component, EventEmitter, Output, input, signal } from "@angular/core";
import {
  Activity,
  LucideAngularModule,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCcw,
  Trash2,
} from "lucide-angular";
import { SessionInfo } from "../../models/types";
import { ModelPickerComponent } from "../model-picker/model-picker.component";

@Component({
  selector: "app-shell",
  standalone: true,
  imports: [CommonModule, LucideAngularModule, ModelPickerComponent],
  host: { class: "flex h-full min-h-0 flex-col" },
  template: `
    <div class="flex h-full min-h-0 flex-col">
      <!-- Header -->
      <header class="flex h-14 shrink-0 items-center justify-between border-b border-ink-200 bg-white px-4">
        <div class="flex items-center gap-3">
          <div class="flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm">
              <lucide-icon [img]="Activity" class="h-4 w-4"></lucide-icon>
            </div>
            <div>
              <div class="text-sm font-semibold leading-none text-ink-900">RegView</div>
              <div class="text-[10px] uppercase tracking-widest text-ink-400">Regulatory · RWD</div>
            </div>
          </div>

          <div class="ml-4 h-6 w-px bg-ink-200"></div>

          <span
            class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1"
            [ngClass]="statusPill()"
          >
            <span class="h-1.5 w-1.5 rounded-full" [ngClass]="statusDot()"></span>
            Backend: {{ backendStatus() }}
          </span>
        </div>

        <div class="flex items-center gap-2">
          <app-model-picker (modelChange)="modelChange.emit($event)"></app-model-picker>
        </div>
      </header>

      <!-- Body -->
      <div class="flex min-h-0 flex-1">
        <!-- Left Rail -->
        <aside
          class="flex shrink-0 flex-col border-r border-ink-200 bg-white transition-all"
          [style.width.px]="collapsed() ? 60 : 260"
        >
          <div class="p-3">
            <button
              type="button"
              (click)="newChat.emit()"
              class="flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
              [title]="collapsed() ? 'New chat' : ''"
            >
              <lucide-icon [img]="Plus" class="h-4 w-4"></lucide-icon>
              @if (!collapsed()) { <span>New chat</span> }
            </button>
          </div>

          <nav class="flex min-h-0 flex-1 flex-col px-2">
            @if (!collapsed()) {
              <div class="flex items-center justify-between px-2 pb-1 pt-2">
                <span class="text-[10px] font-semibold uppercase tracking-wider text-ink-400">
                  Recent conversations
                </span>
                <button
                  type="button"
                  (click)="refreshSessions.emit()"
                  class="flex h-6 w-6 items-center justify-center rounded text-ink-400 hover:bg-ink-100 hover:text-ink-700"
                  title="Refresh"
                >
                  <lucide-icon [img]="RefreshCcw" class="h-3.5 w-3.5"></lucide-icon>
                </button>
              </div>
            }

            <div class="min-h-0 flex-1 overflow-y-auto pb-2">
              @if (sessions().length === 0) {
                @if (!collapsed()) {
                  <div class="px-2 py-6 text-center text-xs text-ink-400">
                    No conversations yet.<br />
                    Start one from the composer.
                  </div>
                } @else {
                  <div class="flex justify-center py-3 text-ink-300">
                    <lucide-icon [img]="MessageSquare" class="h-4 w-4"></lucide-icon>
                  </div>
                }
              } @else {
                @for (s of sessions(); track s.session_id) {
                  <div
                    class="group flex items-center gap-1 rounded-md px-1"
                    [ngClass]="s.session_id === activeSessionId()
                      ? 'bg-brand-50 ring-1 ring-brand-100'
                      : 'hover:bg-ink-50'"
                  >
                    <button
                      type="button"
                      (click)="openSession.emit(s.session_id)"
                      class="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left text-sm"
                      [title]="s.title || 'Untitled conversation'"
                    >
                      <lucide-icon
                        [img]="MessageSquare"
                        class="h-4 w-4 shrink-0"
                        [ngClass]="s.session_id === activeSessionId() ? 'text-brand-600' : 'text-ink-400'"
                      ></lucide-icon>
                      @if (!collapsed()) {
                        <div class="min-w-0 flex-1">
                          <div class="truncate text-[13px] leading-tight text-ink-800">
                            {{ s.title || 'Untitled conversation' }}
                          </div>
                          <div class="mt-0.5 text-[10px] leading-tight text-ink-400">
                            {{ s.message_count }} msg · {{ formatWhen(s.updated_at) }}
                          </div>
                        </div>
                      }
                    </button>
                    @if (!collapsed()) {
                      <button
                        type="button"
                        (click)="deleteSession.emit(s.session_id); $event.stopPropagation()"
                        class="hidden h-7 w-7 items-center justify-center rounded text-ink-300 hover:bg-rose-50 hover:text-rose-600 group-hover:flex"
                        title="Delete conversation"
                      >
                        <lucide-icon [img]="Trash2" class="h-3.5 w-3.5"></lucide-icon>
                      </button>
                    }
                  </div>
                }
              }
            </div>
          </nav>

          <div class="border-t border-ink-100 p-2">
            <button
              type="button"
              (click)="toggle()"
              class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm text-ink-500 hover:bg-ink-100 hover:text-ink-700"
              [title]="collapsed() ? 'Expand' : 'Collapse'"
            >
              @if (collapsed()) {
                <lucide-icon [img]="PanelLeftOpen" class="h-4 w-4"></lucide-icon>
              } @else {
                <lucide-icon [img]="PanelLeftClose" class="h-4 w-4"></lucide-icon>
                <span>Collapse</span>
              }
            </button>
          </div>
        </aside>

        <!-- Content slot -->
        <main class="min-w-0 min-h-0 flex-1 overflow-hidden">
          <ng-content></ng-content>
        </main>
      </div>
    </div>
  `,
})
export class AppShellComponent {
  backendStatus = input<"online" | "offline" | "checking">("checking");
  sessions = input<SessionInfo[]>([]);
  activeSessionId = input<string | null>(null);

  @Output() newChat = new EventEmitter<void>();
  @Output() openSession = new EventEmitter<string>();
  @Output() deleteSession = new EventEmitter<string>();
  @Output() refreshSessions = new EventEmitter<void>();
  @Output() modelChange = new EventEmitter<string>();

  protected readonly collapsed = signal<boolean>(false);

  protected readonly Activity = Activity;
  protected readonly MessageSquare = MessageSquare;
  protected readonly PanelLeftClose = PanelLeftClose;
  protected readonly PanelLeftOpen = PanelLeftOpen;
  protected readonly Plus = Plus;
  protected readonly RefreshCcw = RefreshCcw;
  protected readonly Trash2 = Trash2;

  protected toggle() {
    this.collapsed.set(!this.collapsed());
  }

  protected formatWhen(iso: string): string {
    try {
      const d = new Date(iso);
      const now = Date.now();
      const diff = Math.max(0, now - d.getTime());
      const min = Math.floor(diff / 60000);
      if (min < 1) return "just now";
      if (min < 60) return `${min}m ago`;
      const hr = Math.floor(min / 60);
      if (hr < 24) return `${hr}h ago`;
      const day = Math.floor(hr / 24);
      if (day < 7) return `${day}d ago`;
      return d.toLocaleDateString();
    } catch {
      return "";
    }
  }

  protected statusPill(): string {
    switch (this.backendStatus()) {
      case "online":
        return "bg-emerald-50 text-emerald-700 ring-emerald-200";
      case "offline":
        return "bg-rose-50 text-rose-700 ring-rose-200";
      default:
        return "bg-ink-100 text-ink-600 ring-ink-200";
    }
  }

  protected statusDot(): string {
    switch (this.backendStatus()) {
      case "online":
        return "bg-emerald-500";
      case "offline":
        return "bg-rose-500";
      default:
        return "bg-ink-400 animate-pulse";
    }
  }
}
