import { CommonModule } from "@angular/common";
import { AfterViewChecked, Component, ElementRef, EventEmitter, Output, ViewChild, input } from "@angular/core";
import { ChatMessage } from "../../models/types";
import { ComposerComponent, SendPayload } from "../composer/composer.component";
import { MessageBubbleComponent } from "../message-bubble/message-bubble.component";

@Component({
  selector: "app-chat-panel",
  standalone: true,
  imports: [CommonModule, ComposerComponent, MessageBubbleComponent],
  host: { class: "block h-full min-h-0" },
  template: `
    <div class="flex h-full min-h-0 flex-col bg-ink-50/40">
      <div #scroller class="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-6">
        @for (m of messages(); track m.id) {
          <app-message-bubble [message]="m"></app-message-bubble>
        }
      </div>
      <div class="border-t border-ink-200 bg-white px-5 py-3">
        <app-composer
          [loading]="loading()"
          [size]="'md'"
          [placeholder]="'Ask a follow-up…'"
          (send)="send.emit($event)"
        ></app-composer>
      </div>
    </div>
  `,
})
export class ChatPanelComponent implements AfterViewChecked {
  messages = input.required<ChatMessage[]>();
  loading = input<boolean>(false);
  @Output() send = new EventEmitter<SendPayload>();

  @ViewChild("scroller") scroller?: ElementRef<HTMLDivElement>;
  private lastCount = 0;

  ngAfterViewChecked(): void {
    const list = this.messages();
    if (list.length !== this.lastCount && this.scroller) {
      this.lastCount = list.length;
      const el = this.scroller.nativeElement;
      el.scrollTop = el.scrollHeight;
    }
  }
}
