import { CommonModule } from "@angular/common";
import { Component, EventEmitter, HostListener, Output, computed, input, signal } from "@angular/core";
import { LucideAngularModule, MessageSquare, PanelRightClose, PanelRightOpen } from "lucide-angular";
import { ChatMessage, SearchResult } from "../../models/types";
import { ChatPanelComponent } from "../chat-panel/chat-panel.component";
import { SendPayload } from "../composer/composer.component";
import { ResultsTableComponent } from "../results-table/results-table.component";

@Component({
  selector: "app-split-layout",
  standalone: true,
  imports: [CommonModule, LucideAngularModule, ChatPanelComponent, ResultsTableComponent],
  host: { class: "block h-full min-h-0" },
  template: `
    <div class="grid h-full w-full min-h-0 overflow-hidden" [style.gridTemplateColumns]="gridCols()">
      <!-- Left: results -->
      <div class="min-w-0 min-h-0 h-full overflow-hidden border-r border-ink-200 bg-white">
        <app-results-table
          [results]="results()"
          [query]="query()"
          [summary]="summary()"
          (close)="closePanel.emit()"
        ></app-results-table>
      </div>

      @if (chatVisible()) {
        <!-- Divider (draggable) -->
        <div
          class="group relative w-1.5 cursor-col-resize bg-ink-100 hover:bg-brand-200"
          (mousedown)="startDrag($event)"
          title="Drag to resize"
        >
          <div class="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-ink-200 group-hover:bg-brand-400"></div>
        </div>
        <!-- Right: chat + header bar -->
        <div class="flex min-w-0 min-h-0 h-full flex-col overflow-hidden bg-white">
          <div class="flex shrink-0 items-center justify-between border-b border-ink-200 bg-white/95 px-3 py-1.5">
            <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-500">
              <lucide-icon [img]="MessageSquare" class="h-3.5 w-3.5"></lucide-icon>
              <span>Chat</span>
            </div>
            <button
              type="button"
              (click)="closeChat.emit()"
              title="Close chat panel"
              class="flex h-6 w-6 items-center justify-center rounded text-ink-400 hover:bg-ink-100 hover:text-ink-700"
            >
              <lucide-icon [img]="PanelRightClose" class="h-4 w-4"></lucide-icon>
            </button>
          </div>
          <div class="min-h-0 flex-1">
            <app-chat-panel
              [messages]="messages()"
              [loading]="loading()"
              (send)="send.emit($event)"
            ></app-chat-panel>
          </div>
        </div>
      } @else {
        <!-- Chat closed — slim reopen tab pinned to the right edge -->
        <button
          type="button"
          (click)="openChat.emit()"
          title="Show chat panel"
          class="group relative flex w-8 items-center justify-center border-l border-ink-200 bg-white hover:bg-brand-50"
        >
          <div class="flex flex-col items-center gap-2 py-3 text-ink-500 group-hover:text-brand-700">
            <lucide-icon [img]="PanelRightOpen" class="h-4 w-4"></lucide-icon>
            <span class="[writing-mode:vertical-rl] rotate-180 text-[11px] font-medium tracking-wide">
              Show chat
            </span>
            @if (messages().length > 0) {
              <span class="rounded-full bg-brand-100 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
                {{ messages().length }}
              </span>
            }
          </div>
        </button>
      }
    </div>
  `,
})
export class SplitLayoutComponent {
  results = input.required<SearchResult[]>();
  query = input<string>("");
  summary = input<string | null | undefined>(undefined);
  messages = input.required<ChatMessage[]>();
  loading = input<boolean>(false);
  chatVisible = input<boolean>(true);

  @Output() send = new EventEmitter<SendPayload>();
  @Output() closePanel = new EventEmitter<void>();
  @Output() closeChat = new EventEmitter<void>();
  @Output() openChat = new EventEmitter<void>();

  protected readonly PanelRightClose = PanelRightClose;
  protected readonly PanelRightOpen = PanelRightOpen;
  protected readonly MessageSquare = MessageSquare;

  protected readonly leftWidth = signal<number>(0.55); // 0..1
  private dragging = false;

  protected readonly gridCols = computed(() =>
    this.chatVisible()
      ? `${Math.round(this.leftWidth() * 100)}fr 6px ${100 - Math.round(this.leftWidth() * 100)}fr`
      : `1fr 32px`,
  );

  protected startDrag(_e: MouseEvent) {
    if (!this.chatVisible()) return;
    this.dragging = true;
    document.body.style.cursor = "col-resize";
  }

  @HostListener("window:mousemove", ["$event"])
  onMouseMove(e: MouseEvent) {
    if (!this.dragging) return;
    const total = window.innerWidth;
    const rail = 260; // approx left rail width
    const usable = Math.max(400, total - rail);
    let ratio = (e.clientX - rail) / usable;
    ratio = Math.max(0.28, Math.min(0.78, ratio));
    this.leftWidth.set(ratio);
  }

  @HostListener("window:mouseup")
  onMouseUp() {
    if (this.dragging) {
      this.dragging = false;
      document.body.style.cursor = "";
    }
  }
}
