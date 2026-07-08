import { CommonModule } from "@angular/common";
import { Component, input } from "@angular/core";
import { LucideAngularModule, Paperclip, User, Bot, AlertCircle, Loader2 } from "lucide-angular";
import { ChatMessage } from "../../models/types";
import { SourceBadgeComponent } from "../source-badge/source-badge.component";

@Component({
  selector: "app-message-bubble",
  standalone: true,
  imports: [CommonModule, LucideAngularModule, SourceBadgeComponent],
  template: `
    @if (message().role === 'user') {
      <div class="flex justify-end">
        <div class="flex max-w-[85%] items-start gap-2">
          <div class="rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white shadow-sm">
            @if (message().attachment; as att) {
              <div class="mb-2 flex items-center gap-1.5 rounded-md bg-brand-700/40 px-2 py-1 text-[11px]">
                <lucide-icon [img]="Paperclip" class="h-3 w-3"></lucide-icon>
                <span class="font-medium">{{ att.name }}</span>
              </div>
            }
            <p class="whitespace-pre-wrap break-words">{{ message().content }}</p>
          </div>
          <div class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 ring-1 ring-brand-200">
            <lucide-icon [img]="User" class="h-3.5 w-3.5"></lucide-icon>
          </div>
        </div>
      </div>
    } @else {
      <div class="flex justify-start">
        <div class="flex max-w-[92%] items-start gap-2">
          <div class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600 ring-1 ring-brand-100">
            <lucide-icon [img]="Bot" class="h-3.5 w-3.5"></lucide-icon>
          </div>
          <div class="min-w-0 flex-1">
            <div
              class="rounded-2xl rounded-tl-sm border px-4 py-3 shadow-sm"
              [ngClass]="message().isError
                ? 'border-rose-200 bg-rose-50 text-rose-800'
                : 'border-ink-200 bg-white text-ink-800'"
            >
              @if (message().isLoading) {
                <div class="flex items-center gap-2 text-ink-500">
                  <lucide-icon [img]="Loader2" class="h-4 w-4 animate-spin"></lucide-icon>
                  <span class="text-sm">Thinking…</span>
                </div>
              } @else {
                @if (message().isError) {
                  <div class="mb-1 flex items-center gap-1.5 text-xs font-medium">
                    <lucide-icon [img]="AlertCircle" class="h-3.5 w-3.5"></lucide-icon>
                    Error
                  </div>
                }
                <div class="prose-answer">{{ message().content }}</div>

                @if (message().citations?.length) {
                  <div class="mt-3 border-t border-ink-100 pt-2.5">
                    <div class="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500">Sources</div>
                    <ol class="space-y-1.5">
                      @for (c of message().citations; track c.chunk_id || c.index) {
                        <li class="text-xs text-ink-600">
                          <span class="mr-1 font-mono font-semibold text-brand-600">[{{ c.index }}]</span>
                          <span class="font-medium text-ink-800">{{ c.title }}</span>
                          <span class="text-ink-400"> · {{ c.source }}</span>
                          @if (c.url) {
                            &nbsp;·&nbsp;<a [href]="c.url" target="_blank" rel="noopener" class="text-brand-600 underline underline-offset-2 hover:text-brand-700">link</a>
                          }
                          <span class="ml-1 text-[10px] font-mono text-ink-400">d={{ c.distance.toFixed(3) }}</span>
                        </li>
                      }
                    </ol>
                  </div>
                }
              }
            </div>
            @if (!message().isLoading && !message().isError && message().sourceType) {
              <div class="mt-1.5">
                <app-source-badge
                  [sourceType]="message().sourceType!"
                  [citationCount]="message().citations?.length ?? 0"
                  [filename]="$any(message().sourceInfo?.['filename'])"
                ></app-source-badge>
              </div>
            }
          </div>
        </div>
      </div>
    }
  `,
})
export class MessageBubbleComponent {
  message = input.required<ChatMessage>();

  protected readonly Paperclip = Paperclip;
  protected readonly User = User;
  protected readonly Bot = Bot;
  protected readonly AlertCircle = AlertCircle;
  protected readonly Loader2 = Loader2;
}
